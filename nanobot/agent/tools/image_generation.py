"""Image generation tool."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger
from pydantic import Field

from nanobot.agent.tools.base import Tool, tool_parameters
from nanobot.agent.tools.schema import (
    ArraySchema,
    IntegerSchema,
    StringSchema,
    tool_parameters_schema,
)
from nanobot.config.paths import get_media_dir
from nanobot.config.schema import Base
from nanobot.providers.image_generation import (
    ImageGenerationError,
    ImageGenerationProvider,
    get_image_gen_provider,
)
from nanobot.utils.artifacts import (
    ArtifactError,
    generated_image_tool_result,
    store_generated_image_artifact,
    store_remote_image_artifact,
)
from nanobot.utils.context_vars import telegram_customer_profile
from nanobot.utils.customer_context import (
    build_prompt_brand_suffix,
    get_default_aspect_ratio_for_channel,
)
from nanobot.utils.helpers import detect_image_mime
from nanobot.utils.vidtory_knowledge import (
    build_professional_prompt_suffix,
    detect_content_type,
)

if TYPE_CHECKING:
    from nanobot.config.schema import ProviderConfig


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
            StringSchema("Local path of an existing image artifact or user-provided image to use as a reference/edit base (maps to refImageUrl for first, startImages for rest)."),
            description="Optional local image paths for reference or starting frames. The first becomes refImageUrl, remaining become startImages.",
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
class ImageGenerationTool(Tool):
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
        return cls(
            workspace=ctx.workspace,
            config=ctx.config.image_generation,
            provider_configs=ctx.image_generation_provider_configs,
        )

    def __init__(
        self,
        *,
        workspace: str | Path,
        config: ImageGenerationToolConfig,
        provider_config: ProviderConfig | None = None,
        provider_configs: dict[str, ProviderConfig] | None = None,
    ) -> None:
        self.workspace = Path(workspace).expanduser()
        self.config = config
        self.provider_configs = dict(provider_configs or {})
        # BUG FIX: was hardcoding "openrouter" — now uses the actual provider name
        if provider_config is not None and self.config.provider not in self.provider_configs:
            self.provider_configs[self.config.provider] = provider_config

    @property
    def name(self) -> str:
        return "generate_image"

    @property
    def description(self) -> str:
        return (
            "Generate or edit images and store them as persistent artifacts. "
            "Returns artifact ids and local paths. For edits, pass prior generated image paths "
            "or user image paths as reference_images."
        )

    def _provider_config(self) -> ProviderConfig | None:
        return self.provider_configs.get(self.config.provider)

    def _provider_client(self) -> ImageGenerationProvider | None:
        from nanobot.utils.context_vars import telegram_user_api_key
        user_key = telegram_user_api_key.get()
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
        return [self._resolve_reference_image(value) for value in values if value]

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
        optimized_prompt, customer_ar = self._apply_customer_context(prompt)
        resolved_ar = aspect_ratio or customer_ar or self.config.default_aspect_ratio

        try:
            refs = self._resolve_reference_images(reference_images)
            artifacts: list[dict[str, Any]] = []
            while len(artifacts) < requested:
                response = await client.generate(
                    prompt=optimized_prompt,
                    model=self.config.model,
                    reference_images=refs,
                    style_image_url=style_image_url,
                    aspect_ratio=resolved_ar,
                    image_size=image_size or self.config.default_image_size,
                )
                for image_data_url in response.images:
                    artifact = store_generated_image_artifact(
                        image_data_url,
                        prompt=optimized_prompt,
                        model=self.config.model,
                        source_images=refs,
                        save_dir=self.config.save_dir,
                        provider=self.config.provider,
                    )
                    artifacts.append(artifact)
                    if len(artifacts) >= requested:
                        break
                # Handle remote URLs (e.g. Vidtory CDN) — no download needed
                for remote_url in (response.image_urls or []):
                    artifact = store_remote_image_artifact(
                        remote_url,
                        prompt=optimized_prompt,
                        model=self.config.model,
                        source_images=refs,
                        save_dir=self.config.save_dir,
                        provider=self.config.provider,
                    )
                    artifacts.append(artifact)
                    if len(artifacts) >= requested:
                        break
            return generated_image_tool_result(artifacts)
        except (ArtifactError, ImageGenerationError, OSError) as exc:
            return f"Error: {exc}"

    def _apply_customer_context(self, prompt: str) -> tuple[str, str | None]:
        """Apply customer brand guidelines and Vidtory professional standards to the prompt.

        This is the central prompt enrichment pipeline:
        1. Auto-detect content type from prompt
        2. Apply Vidtory professional photography style for that content type
        3. Apply customer brand guidelines (style, mood keywords, colors)
        4. Derive customer's preferred aspect ratio from their primary channel

        Returns:
            Tuple of (enriched_prompt, aspect_ratio_or_None).
            The enriched prompt is non-destructive — original intent is always preserved.
        """
        enriched = prompt
        aspect_ratio: str | None = None

        # ── Step 1: Vidtory professional prompt enhancement ──────────────────
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
        except Exception:
            logger.warning("Customer context enhancement failed — using defaults")

        return enriched, aspect_ratio

    # Keep backward-compatible shims for any external callers.
    def _enhance_prompt_with_brand(self, prompt: str) -> str:
        enriched, _ = self._apply_customer_context(prompt)
        return enriched

    def _customer_aspect_ratio(self) -> str | None:
        _, aspect_ratio = self._apply_customer_context("")
        return aspect_ratio


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
