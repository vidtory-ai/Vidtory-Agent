"""Image generation tool."""

from __future__ import annotations

import json
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from loguru import logger
from pydantic import Field

from nanobot.agent.tools.base import Tool, tool_parameters
from nanobot.agent.tools.context import ContextAware, RequestContext
from nanobot.agent.tools.schema import (
    ArraySchema,
    IntegerSchema,
    StringSchema,
    tool_parameters_schema,
)
from nanobot.bus.events import OutboundMessage
from nanobot.config.paths import get_media_dir
from nanobot.config.schema import Base
from nanobot.providers.image_generation import (
    ImageGenerationError,
    ImageGenerationProvider,
    get_image_gen_provider,
)
from nanobot.utils.context_vars import telegram_customer_profile
from nanobot.utils.customer_context import (
    build_prompt_brand_suffix,
    get_default_aspect_ratio_for_channel,
    get_customer_logo_url,
)
from nanobot.utils.helpers import detect_image_mime
from nanobot.utils.vidtory_knowledge import (
    build_professional_prompt_suffix,
    detect_content_type,
)

if TYPE_CHECKING:
    from nanobot.config.schema import ProviderConfig

# Module-level ContextVar so there is exactly one per process (not one per tool instance)
_image_gen_request_ctx: ContextVar[RequestContext | None] = ContextVar(
    "image_gen_request_context", default=None
)


class ImageGenerationToolConfig(Base):
    """Image generation tool configuration."""
    enabled: bool = True
    provider: str = "vidtory"
    model: str = "gemini-3.1-flash-image-preview"
    default_aspect_ratio: str = "1:1"
    default_image_size: str = "1K"
    max_images_per_turn: int = Field(default=4, ge=1, le=8)
    save_dir: str = "generated"


@tool_parameters(
    tool_parameters_schema(
        prompt=StringSchema(
            "Detailed image generation or edit prompt. Include style, subject, composition, colors, and constraints.",
            min_length=1,
        ),
        reference_images=ArraySchema(
            StringSchema("Local path of a user-provided image or existing generated artifact to use as reference. IMPORTANT: When the user sends multiple images (e.g. 2 photos), include ALL image paths here — do NOT omit any."),
            description=(
                "CRITICAL: When the user uploads or provides multiple images, you MUST include ALL image paths in this list. "
                "Example: if user sends 2 images at paths ['/path/img1.jpg', '/path/img2.jpg'], pass both paths here. "
                "The first image becomes the primary reference (refImageUrl), all remaining images are sent as additional context (startImages). "
                "Never omit any user-provided image — the model needs all images to fulfill requests like combining, merging, or referencing multiple subjects."
            ),
        ),
        style_image_url=StringSchema(
            "Optional URL or local path of a style reference image to apply stylistic transfer (styleImageUrl).",
        ),
        aspect_ratio=StringSchema(
            "Optional output aspect ratio, e.g. 1:1, 16:9, 9:16, 4:3, 3:4.",
        ),
        image_size=StringSchema(
            "Optional output resolution: 1K, 2K, or 4K.",
        ),
        count=IntegerSchema(
            description="Number of images to generate in this turn.",
            minimum=1,
            maximum=8,
        ),
        required=["prompt"],
    )
)
class ImageGenerationTool(Tool, ContextAware):
    """Generate persistent image artifacts through the configured image provider."""

    config_key = "image_generation"

    @classmethod
    def config_cls(cls):
        return ImageGenerationToolConfig

    @classmethod
    def enabled(cls, ctx: Any) -> bool:
        return ctx.config.image_generation.enabled

    @classmethod
    def create(cls, ctx: Any) -> Tool:
        send_callback = ctx.bus.publish_outbound if ctx.bus else None
        return cls(
            workspace=ctx.workspace,
            config=ctx.config.image_generation,
            provider_configs=ctx.image_generation_provider_configs,
            send_callback=send_callback,
        )

    def __init__(
        self,
        *,
        workspace: str | Path,
        config: ImageGenerationToolConfig,
        provider_config: ProviderConfig | None = None,
        provider_configs: dict[str, ProviderConfig] | None = None,
        send_callback: Callable[[OutboundMessage], Awaitable[None]] | None = None,
    ) -> None:
        self.workspace = Path(workspace).expanduser()
        self.config = config
        self.provider_configs = dict(provider_configs or {})
        # BUG FIX: was hardcoding "openrouter" — now uses the actual provider name
        if provider_config is not None and self.config.provider not in self.provider_configs:
            self.provider_configs[self.config.provider] = provider_config
        self._send_callback = send_callback

    @property
    def name(self) -> str:
        return "generate_image"

    def set_context(self, ctx: RequestContext) -> None:
        """Receive the current request context (channel, chat_id, metadata)."""
        _image_gen_request_ctx.set(ctx)

    @property
    def description(self) -> str:
        return (
            "Generate or edit images and store them as persistent artifacts. "
            "Returns artifact ids and local paths. "
            "IMPORTANT: When the user provides multiple images (uploads 2+ photos), you MUST pass ALL image paths "
            "into reference_images — the provider needs every image to correctly combine or reference them. "
            "Never call this tool with only 1 image when the user sent 2 or more."
        )

    def _provider_config(self) -> ProviderConfig | None:
        return self.provider_configs.get(self.config.provider)

    def _provider_client(self) -> ImageGenerationProvider | None:
        from nanobot.utils.context_vars import telegram_vidtory_api_key
        user_key = telegram_vidtory_api_key.get()
        provider = self._provider_config()
        cls = get_image_gen_provider(self.config.provider)
        if cls is None:
            return None
        kwargs = {
            "api_key": user_key or (provider.api_key if provider else None),
            "api_base": provider.api_base if provider else None,
            "extra_headers": provider.extra_headers if provider else None,
            "extra_body": provider.extra_body if provider else None,
        }
        return cls(**kwargs)

    def _resolve_reference_image(self, value: str) -> str:
        """Resolve a reference image path or URL.

        HTTP(S) URLs (e.g. Vidtory CDN) are returned as-is.
        Local paths are validated and resolved to absolute paths.
        """
        # Remote URL — pass through directly
        if value.startswith(("http://", "https://")):
            return value

        raw_path = Path(value).expanduser()
        path = raw_path if raw_path.is_absolute() else self.workspace / raw_path
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise ImageGenerationError(f"reference image not found: {value}") from exc

        allowed_roots = [self.workspace.resolve(), get_media_dir().resolve()]
        if not any(_is_relative_to(resolved, root) for root in allowed_roots):
            raise ImageGenerationError(
                "reference_images must be inside the workspace or nanobot media directory"
            )
        if not resolved.is_file():
            raise ImageGenerationError(f"reference image is not a file: {value}")
        raw = resolved.read_bytes()
        if detect_image_mime(raw) is None:
            raise ImageGenerationError(f"unsupported reference image: {value}")
        return str(resolved)

    def _resolve_reference_images(self, values: list[str] | None) -> list[str]:
        if not values:
            return []
        resolved = [self._resolve_reference_image(value) for value in values if value]
        # Dedup while preserving order — LLM may pass the same image path twice
        return list(dict.fromkeys(resolved))

    async def execute(
        self,
        prompt: str,
        reference_images: list[str] | None = None,
        style_image_url: str | None = None,
        aspect_ratio: str | None = None,
        image_size: str | None = None,
        count: int | None = None,
        **kwargs: Any,
    ) -> str:
        client = self._provider_client()
        if client is None:
            return f"Error: unsupported image generation provider '{self.config.provider}'"

        requested = count or 1
        if requested > self.config.max_images_per_turn:
            return (
                "Error: count exceeds tools.imageGeneration.maxImagesPerTurn "
                f"({self.config.max_images_per_turn})"
            )

        # Apply Vidtory professional standards + customer brand guidelines
        optimized_prompt, customer_ar, logo_url = self._apply_customer_context(prompt)
        resolved_ar = aspect_ratio or customer_ar or self.config.default_aspect_ratio

        try:
            refs = self._resolve_reference_images(reference_images)
            image_urls: list[str] = []
            while len(image_urls) < requested:
                # Build generate() kwargs — pass logo_url only when the
                # provider supports it (VidtoryImageGenerationClient).
                gen_kwargs: dict[str, Any] = dict(
                    prompt=optimized_prompt,
                    model=self.config.model,
                    reference_images=refs,
                    style_image_url=style_image_url,
                    aspect_ratio=resolved_ar,
                    image_size=image_size or self.config.default_image_size,
                )
                if logo_url and hasattr(client, "_resolve_logo_url"):
                    gen_kwargs["logo_url"] = logo_url

                response = await client.generate(**gen_kwargs)
                # Collect remote CDN URLs directly — no local storage
                for url in (response.image_urls or []):
                    image_urls.append(url)
                    if len(image_urls) >= requested:
                        break
                # base64 images (non-Vidtory providers): still need to decode to send
                for image_data_url in response.images:
                    image_urls.append(image_data_url)
                    if len(image_urls) >= requested:
                        break

            # ── Record task + build design note ──────────────────────────
            task_id = ""
            design_note = ""
            try:
                profile = telegram_customer_profile.get()
                user_id = str(
                    (profile or {}).get("telegramUserId")
                    or (profile or {}).get("telegram_user_id")
                    or ""
                ).strip()
                if user_id:
                    from nanobot.db.customer_db import get_db
                    from nanobot.utils.design_notes import build_design_note
                    from nanobot.utils.quality_metrics import get_lifecycle_stage

                    task_id = f"gen-{uuid.uuid4().hex[:12]}"
                    stage = get_lifecycle_stage(user_id)
                    content_type_detected = None
                    if not self._is_detailed_prompt(prompt):
                        content_type_detected = detect_content_type(prompt)

                    design_note = build_design_note(
                        user_id=user_id,
                        original_prompt=prompt,
                        enhanced_prompt=optimized_prompt,
                        content_type=content_type_detected,
                        model_used=self.config.model,
                        aspect_ratio=resolved_ar,
                    )

                    db = get_db()
                    db.create_task(
                        user_id,
                        task_id=task_id,
                        brief=prompt[:500],
                        content_type="image",
                        lifecycle_stage=stage,
                        model_used=self.config.model,
                        prompt_used=prompt[:500],
                        enhanced_prompt=optimized_prompt[:500],
                        design_note=design_note[:1000],
                        result_url=image_urls[0] if image_urls else "",
                    )
                    # Also record in generation_history for backward compat
                    db.record_generation(
                        user_id,
                        content_type="image",
                        prompt=prompt,
                        enhanced_prompt=optimized_prompt,
                        model=self.config.model,
                        result_url=image_urls[0] if image_urls else "",
                    )
            except Exception as exc:
                logger.debug("Task recording/design note failed (non-fatal): {}", exc)

            # Auto-send images directly via bus so LLM doesn't need to call message tool
            ctx = _image_gen_request_ctx.get()
            if ctx and self._send_callback and image_urls:
                try:
                    outbound = OutboundMessage(
                        channel=ctx.channel,
                        chat_id=ctx.chat_id,
                        content="",
                        media=image_urls,
                        metadata=dict(ctx.metadata or {}),
                    )
                    await self._send_callback(outbound)
                    logger.info(
                        "ImageGenerationTool: auto-sent {} image(s) to {}:{}",
                        len(image_urls), ctx.channel, ctx.chat_id,
                    )
                    result = {
                        "status": "sent",
                        "count": len(image_urls),
                    }
                    if task_id:
                        result["task_id"] = task_id
                    if design_note:
                        result["design_note"] = design_note
                    return json.dumps(result, ensure_ascii=False)
                except Exception as send_exc:
                    logger.warning("ImageGenerationTool: auto-send failed: {}", send_exc)
                    # Fall through to returning URLs for LLM to deliver manually

            result = {
                "image_urls": image_urls,
                "next_step": (
                    "Call the message tool with these URLs in the media parameter "
                    "to deliver the images to the user."
                ),
            }
            if task_id:
                result["task_id"] = task_id
            if design_note:
                result["design_note"] = design_note
            return json.dumps(result, ensure_ascii=False)
        except (ImageGenerationError, OSError) as exc:
            return f"Error: {exc}"

    # Technical keywords that indicate the user's prompt is already professionally written.
    # When found, skip auto-enhancement to avoid injecting irrelevant content-type styles.
    _DETAILED_PROMPT_KEYWORDS = {
        "cinematic", "composition", "poster", "illustration", "render", "studio",
        "lighting", "bokeh", "depth of field", "editorial", "photorealistic",
        "high detail", "commercial quality", "professional", "high resolution",
        "sharp focus", "4k", "8k", "hdr", "color grade", "blender", "octane",
        "ghép", "kết hợp", "hòa quyện", "bố cục", "ánh sáng", "chuyên nghiệp",
        "poster", "minh họa", "concept", "banner", "logo",
    }

    def _is_detailed_prompt(self, prompt: str) -> bool:
        """Return True if the prompt is already detailed enough to skip auto-enhancement.

        A prompt is considered detailed if:
        - It contains >= 30 words (user put effort into it), OR
        - It contains technical/professional photography/art keywords.
        This prevents injecting unrelated content-type styles (e.g. 'beverage photography')
        into prompts about nature scenes or illustration work.
        """
        word_count = len(prompt.split())
        if word_count >= 30:
            return True
        prompt_lower = prompt.lower()
        return any(kw in prompt_lower for kw in self._DETAILED_PROMPT_KEYWORDS)

    def _apply_customer_context(self, prompt: str) -> tuple[str, str | None, str | None]:
        """Apply customer brand guidelines and Vidtory professional standards to the prompt.

        This is the central prompt enrichment pipeline:
        1. Auto-detect content type from prompt
        2. Apply Vidtory professional photography style for that content type
           (SKIPPED when prompt is already detailed to avoid injecting irrelevant styles)
        3. Apply customer brand guidelines (style, mood keywords, colors)
        4. Derive customer's preferred aspect ratio from their primary channel
        5. Extract brand logo URL (for logo-aware generation)
        6. Inject logo preservation instruction when watermark-related keywords
           are detected in the prompt (prevents AI from erasing the logo)

        Returns:
            Tuple of (enriched_prompt, aspect_ratio_or_None, logo_url_or_None).
            The enriched prompt is non-destructive — original intent is always preserved.
        """
        enriched = prompt
        aspect_ratio: str | None = None
        logo_url: str | None = None

        # ── Step 1: Vidtory professional prompt enhancement ──────────────────
        # Skip when the user has already written a detailed/professional prompt
        # to avoid injecting irrelevant content-type keywords (e.g. 'beverage
        # photography' into a nature/illustration prompt).
        if not self._is_detailed_prompt(prompt):
            try:
                content_type = detect_content_type(prompt)
                pro_suffix = build_professional_prompt_suffix(prompt, content_type=content_type)
                if pro_suffix:
                    enriched = f"{enriched}, {pro_suffix}"
                    logger.debug(
                        "Vidtory professional enhancement applied (content_type={}): +{} chars",
                        content_type or "auto",
                        len(pro_suffix),
                    )
            except Exception:
                logger.warning("Vidtory knowledge enhancement failed — using original prompt")
        else:
            logger.debug(
                "Prompt auto-enhancement skipped: prompt is already detailed ({} words)",
                len(prompt.split()),
            )

        # ── Step 2: Customer brand guidelines ────────────────────────────────
        try:
            profile = telegram_customer_profile.get()
            if profile:
                brand_suffix = build_prompt_brand_suffix(profile)
                if brand_suffix:
                    # Guard: don't double-append if brand keywords already present
                    brand = profile.get("brand") or {}
                    keywords = brand.get("moodKeywords") or []
                    already_present = any(
                        kw.lower() in enriched.lower() for kw in keywords if kw
                    )
                    if not already_present:
                        enriched = f"{enriched}, {brand_suffix}"
                        logger.debug("Customer brand guidelines applied")

                # ── Step 3: Customer channel aspect ratio ─────────────────────
                aspect_ratio = get_default_aspect_ratio_for_channel(profile)

                # ── Step 4: Brand logo URL ────────────────────────────────────
                logo_url = get_customer_logo_url(profile)

                # ── Step 5: Logo preservation guard ──────────────────────────
                # When the user's prompt contains watermark-related keywords AND
                # the customer has a brand logo, inject an explicit instruction
                # telling the AI to KEEP the logo intact.  This prevents Gemini
                # from erasing the logo while removing other watermark elements.
                if logo_url and self._prompt_has_watermark_keywords(prompt):
                    logo_guard = (
                        "IMPORTANT: preserve the existing brand logo exactly as-is — "
                        "do NOT erase, blur, or modify the brand logo"
                    )
                    enriched = f"{enriched}. {logo_guard}"
                    logger.info(
                        "Logo preservation guard injected into prompt "
                        "(watermark keyword detected, customer has logo)"
                    )
        except Exception:
            logger.warning("Customer context enhancement failed — using defaults")

        return enriched, aspect_ratio, logo_url

    # Watermark / overlay keywords that may cause the AI to erase brand logos.
    # When detected alongside a customer logo, a preservation instruction is
    # injected to protect the logo from being mistakenly removed.
    _WATERMARK_KEYWORDS = {
        "watermark", "remove watermark", "xóa watermark", "xóa chữ",
        "remove text", "clean up", "remove overlay", "remove logo",
        "erase watermark", "xóa logo", "xóa nhãn", "bỏ watermark",
    }

    def _prompt_has_watermark_keywords(self, prompt: str) -> bool:
        """Return True if the prompt contains watermark-related keywords."""
        prompt_lower = prompt.lower()
        return any(kw in prompt_lower for kw in self._WATERMARK_KEYWORDS)

    # Keep backward-compatible shims for any external callers.
    def _enhance_prompt_with_brand(self, prompt: str) -> str:
        enriched, _, _logo = self._apply_customer_context(prompt)
        return enriched

    def _customer_aspect_ratio(self) -> str | None:
        _, aspect_ratio, _logo = self._apply_customer_context("")
        return aspect_ratio



def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
