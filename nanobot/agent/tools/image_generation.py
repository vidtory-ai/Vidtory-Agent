"""Image generation tool."""

from __future__ import annotations

import json
import re
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
from nanobot.security.request_policy import evaluate_request, is_resident_designer_profile
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

# Module-level ContextVar so there is exactly one per process (not one per tool instance)
_image_gen_request_ctx: ContextVar[RequestContext | None] = ContextVar(
    "image_gen_request_context", default=None
)


def detect_language(text: str) -> str:
    """Detect prompt language using character ranges and common stop words."""
    text_lower = text.lower()

    # 1. Japanese check
    if re.search(r"[\u3040-\u309F\u30A0-\u30FF]", text):
        return "ja"

    # 2. Korean check
    if re.search(r"[\uAC00-\uD7AF\u1100-\u11FF]", text):
        return "ko"

    # 3. Chinese check (Hanzi only, checking Japanese/Korean first avoids collisions)
    if re.search(r"[\u4E00-\u9FFF]", text):
        return "zh"

    # 4. Cyrillic (Russian, Ukrainian, etc.)
    if re.search(r"[\u0400-\u04FF]", text):
        return "ru"

    # 5. Vietnamese check
    vietnamese_diacritics = r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]"
    if re.search(vietnamese_diacritics, text_lower):
        return "vi"

    # Common unaccented Vietnamese words
    vi_words = {
        "mot", "con", "vit", "vang", "co", "xanh", "ho", "yen", "tinh", "cua",
        "dep", "lam", "tao", "anh", "bo", "cuc", "mau", "sac", "san", "pham",
        "nang", "dong", "tieng", "viet", "khong", "co", "quan", "ca", "phe"
    }
    words = re.findall(r"\b\w+\b", text_lower)
    vi_match_count = sum(1 for w in words if w in vi_words)
    if vi_match_count >= 2:
        return "vi"

    # 6. Western European language checks (diacritics specific to DE, ES, FR)
    if re.search(r"[äöüß]", text_lower):
        return "de"
    if "ñ" in text_lower or "¿" in text_lower or "¡" in text_lower:
        return "es"
    if re.search(r"[çœæëïÿâêîôûàèù]", text_lower):
        return "fr"

    fr_words = {"le", "la", "les", "des", "une", "dans", "pour", "avec", "sans", "est", "sont"}
    es_words = {"el", "la", "los", "las", "un", "una", "en", "para", "con", "sin", "es", "son"}
    de_words = {"der", "die", "das", "ein", "eine", "in", "für", "mit", "ohne", "ist", "sind"}

    fr_matches = sum(1 for w in words if w in fr_words)
    es_matches = sum(1 for w in words if w in es_words)
    de_matches = sum(1 for w in words if w in de_words)

    max_matches = max(fr_matches, es_matches, de_matches)
    if max_matches >= 2:
        if max_matches == fr_matches:
            return "fr"
        elif max_matches == es_matches:
            return "es"
        else:
            return "de"

    return "en"


def get_target_text_language(prompt: str, customer_lang: str | None = None) -> str:
    """Determine the target language for text appearing in the image.

    Checks for explicit language requests first, then falls back to customer preference or detected prompt language.
    """
    prompt_lower = prompt.lower()

    # Check for explicit English request
    english_hints = ["in english", "bằng tiếng anh", "chữ tiếng anh", "text in english", "english text", "english lettering", "write in english"]
    if any(hint in prompt_lower for hint in english_hints):
        return "en"

    # Check for explicit Vietnamese request
    vietnamese_hints = ["in vietnamese", "bằng tiếng việt", "chữ tiếng việt", "text in vietnamese", "vietnamese text", "vietnamese lettering", "write in vietnamese"]
    if any(hint in prompt_lower for hint in vietnamese_hints):
        return "vi"

    # Check for other explicit languages
    if "in japanese" in prompt_lower or "bằng tiếng nhật" in prompt_lower or "chữ tiếng nhật" in prompt_lower:
        return "ja"
    if "in korean" in prompt_lower or "bằng tiếng hàn" in prompt_lower or "chữ tiếng hàn" in prompt_lower:
        return "ko"
    if "in chinese" in prompt_lower or "bằng tiếng trung" in prompt_lower or "chữ tiếng trung" in prompt_lower:
        return "zh"
    if "in french" in prompt_lower or "bằng tiếng pháp" in prompt_lower or "chữ tiếng pháp" in prompt_lower:
        return "fr"
    if "in spanish" in prompt_lower or "bằng tiếng tây ban nha" in prompt_lower or "chữ tiếng tây ban nha" in prompt_lower:
        return "es"
    if "in german" in prompt_lower or "bằng tiếng đức" in prompt_lower or "chữ tiếng đức" in prompt_lower:
        return "de"

    # The current request language wins when it contains a meaningful language
    # signal. Profile preference is only a fallback for one-word/neutral briefs.
    detected = detect_language(prompt)
    if len(re.findall(r"\b\w+\b", prompt, flags=re.UNICODE)) >= 2 or detected in {
        "ja", "ko", "zh", "ru",
    }:
        return detected
    return customer_lang or detected


def build_language_instruction(target_lang: str) -> str:
    """Build the text language instruction for the prompt."""
    instructions = {
        "vi": (
            "Không tự thêm nội dung chữ ngoài yêu cầu. "
            "Mọi chữ xuất hiện trong ảnh phải bằng tiếng Việt, đúng chính tả và dễ đọc; không dùng tiếng Anh."
        ),
        "ja": (
            "IMPORTANT: All text, typography, or words appearing in the image MUST be written in Japanese "
            "(重要：画像内のすべての文字やテキストは日本語で記述してください。)."
        ),
        "ko": (
            "IMPORTANT: All text, typography, or words appearing in the image MUST be written in Korean "
            "(중요: 이미지 내의 모든 글자와 텍스트는 한국어로 작성되어야 합니다.)."
        ),
        "zh": (
            "IMPORTANT: All text, typography, or words appearing in the image MUST be written in Chinese "
            "(重要：图像中的所有文字或文本必须用中文书写。)."
        ),
        "fr": (
            "IMPORTANT: All text, typography, or words appearing in the image MUST be written in French "
            "(IMPORTANT : Tous les textes ou mots dans l'image doivent être écrits en français.)."
        ),
        "es": (
            "IMPORTANT: All text, typography, or words appearing in the image MUST be written in Spanish "
            "(IMPORTANTE: Todos los textos o palabras en la imagen deben estar escritos en español.)."
        ),
        "de": (
            "IMPORTANT: All text, typography, or words appearing in the image MUST be written in German "
            "(WICHTIG: Alle Texte oder Wörter im Bild müssen auf Deutsch geschrieben sein.)."
        ),
        "ru": (
            "IMPORTANT: All text, typography, or words appearing in the image MUST be written in Russian "
            "(ВАЖНО: Все надписи и text на изображении должны быть на русском языке.)."
        ),
        "en": (
            "IMPORTANT: All text, typography, or words appearing in the image MUST be written in English."
        )
    }
    return instructions.get(target_lang, "")


def build_exact_text_instruction(quoted_texts: list[str], target_lang: str) -> str:
    """Require quoted strings to be rendered verbatim in the target language."""
    if not quoted_texts:
        return ""
    if target_lang == "vi":
        exact = ", ".join(f"“{text}”" for text in quoted_texts)
        return f"Hiển thị chính xác nguyên văn: {exact}; không dịch, không đổi dấu hoặc chính tả."
    exact = ", ".join(f"'{text}'" for text in quoted_texts)
    return f"IMPORTANT: Render the exact text {exact} without translating it."


def build_logo_instruction(target_lang: str) -> str:
    """Describe the protected logo asset without duplicating bilingual guidance."""
    if target_lang == "vi":
        return (
            "Logo thương hiệu là ảnh tham chiếu cuối cùng. Chèn đúng logo này vào vị trí sạch, "
            "tự nhiên và chuyên nghiệp; giữ nguyên hình dáng, cấu trúc, tỷ lệ và chi tiết logo, "
            "không vẽ lại, không biến dạng, không thay thế bằng chữ mô phỏng."
        )
    return (
        "The brand logo is the final reference image. Place this exact logo in a clean, natural, "
        "professional position. Preserve its shape, structure, proportions, and details; do not "
        "redraw, deform, or replace it with simulated lettering."
    )


def build_layout_instruction(target_lang: str) -> str:
    """Return one compact layout rule in the prompt's language."""
    if target_lang == "vi":
        return (
            "Bố cục sạch, thoáng, chuyên nghiệp; phân cấp thị giác rõ ràng, khoảng cách cân đối, "
            "độ tương phản tốt; tránh chi tiết thừa và cảm giác chật chội."
        )
    return (
        "Use a clean, spacious, professional composition with clear visual hierarchy, balanced "
        "spacing, and strong contrast. Avoid clutter and unnecessary elements."
    )


def build_multi_image_instruction(target_lang: str) -> str:
    """Tell the model to use every content reference without bilingual duplication."""
    if target_lang == "vi":
        return (
            "Sử dụng đầy đủ tất cả ảnh tham chiếu nội dung theo đúng vai trò trong yêu cầu; "
            "không bỏ sót ảnh nào và kết hợp các yếu tố một cách tự nhiên."
        )
    return (
        "Use every content reference image according to its role in the request. "
        "Do not omit any image, and combine the relevant elements naturally."
    )


def customer_language_preference() -> str | None:
    """Return the active customer's preferred communication language."""
    try:
        profile = telegram_customer_profile.get()
        if profile:
            return (profile.get("preferences") or {}).get("communicationLanguage")
    except Exception:
        pass
    return None


def extract_quoted_texts(prompt: str) -> list[str]:
    """Find all double, single, and smart quoted substrings in the prompt."""
    patterns = [
        r'"([^"\\]*(?:\\.[^"\\]*)*)"',
        r"'([^'\\]*(?:\\.[^'\\]*)*)'",
        r'“([^”]*”?)”',
        r'‘([^’]*’?)’',
    ]
    quotes = []
    for pattern in patterns:
        matches = re.findall(pattern, prompt)
        for m in matches:
            if m.strip():
                quotes.append(m.strip())
    return quotes


def _is_revision_prompt(prompt: str) -> bool:
    """Check if the user's prompt is a revision or edit request."""
    prompt_lower = prompt.lower()
    revision_keywords = [
        "sửa", "sửa lại", "chỉnh lại", "thay đổi", "thêm", "ghép", "lồng",
        "từ ảnh", "ảnh trên", "ảnh trước", "ảnh vừa tạo", "tinh chỉnh", "tối ưu",
        "edit", "modify", "change", "add", "revision", "fix", "update", "replace",
        "chèn logo", "thêm logo", "bỏ logo", "xóa logo", "đặt logo"
    ]
    return any(kw in prompt_lower for kw in revision_keywords)


def _prompt_requests_no_logo(prompt: str) -> bool:
    """Check if the user explicitly requested to omit the logo."""
    prompt_lower = prompt.lower()
    return any(kw in prompt_lower for kw in [
        "không logo", "không cần logo", "bỏ logo", "no logo", "without logo",
        "không có logo", "tạo không cần logo", "không chèn logo"
    ])


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
            capability_profile=getattr(ctx.config, "capability_profile", "standard"),
            sessions=getattr(ctx, "sessions", None),
        )

    def __init__(
        self,
        *,
        workspace: str | Path,
        config: ImageGenerationToolConfig,
        provider_config: ProviderConfig | None = None,
        provider_configs: dict[str, ProviderConfig] | None = None,
        send_callback: Callable[[OutboundMessage], Awaitable[None]] | None = None,
        capability_profile: str = "standard",
        sessions: Any | None = None,
    ) -> None:
        self.workspace = Path(workspace).expanduser()
        self.config = config
        self.provider_configs = dict(provider_configs or {})
        self.capability_profile = capability_profile
        # BUG FIX: was hardcoding "openrouter" — now uses the actual provider name
        if provider_config is not None and self.config.provider not in self.provider_configs:
            self.provider_configs[self.config.provider] = provider_config
        self._send_callback = send_callback
        self.sessions = sessions

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
            "Never call this tool with only 1 image when the user sent 2 or more.\n\n"
            "⛔ DO NOT CALL THIS TOOL if any of the following is true:\n"
            "1. The user's request only states a PURPOSE ('ảnh tuyển sinh', 'quảng cáo về học viện', 'ảnh sản phẩm') "
            "without a concrete SUBJECT (specific visual: what people/objects/scene should appear in the image). "
            "In this case, STOP and ask: 'Bạn muốn ảnh thể hiện hình ảnh gì cụ thể?' with 3 specific suggestions.\n"
            "2. The request mentions a specific brand/organization name that is NOT present in the Customer Profile. "
            "In this case, STOP and ask for logo + brand colors. "
            "NEVER fabricate, hallucinate, or render a logo from a name — this produces incorrect brand representation.\n"
            "3. The request asks for text/headline ON the image but the user has not specified the actual text content. "
            "In this case, STOP and ask: 'Bạn muốn ghi dòng chữ gì trên ảnh?'\n\n"
            "⚠️ LOGO RULE: If Customer Profile contains 'Brand Logo: [URL]', the logo is automatically injected by "
            "the provider — do NOT write logo instructions in the prompt text. "
            "If no logo is in the profile but the user wants one, ask them to upload it first via /setlogo."
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
        if is_resident_designer_profile(self.capability_profile):
            policy = evaluate_request(self.capability_profile, prompt)
            if policy.blocked:
                return (
                    "Error: image generation prompt blocked by resident_designer "
                    f"security policy ({policy.reason})"
                )
            if policy.redacted_text and policy.redacted_text.strip():
                prompt = policy.redacted_text
        client = self._provider_client()
        if client is None:
            return f"Error: unsupported image generation provider '{self.config.provider}'"

        requested = count or 1
        if requested > self.config.max_images_per_turn:
            return (
                "Error: count exceeds tools.imageGeneration.maxImagesPerTurn "
                f"({self.config.max_images_per_turn})"
            )

        # Send a loading/progress message to the user to improve responsiveness
        ctx = _image_gen_request_ctx.get()
        if ctx and self._send_callback:
            try:
                progress_msg = OutboundMessage(
                    channel=ctx.channel,
                    chat_id=ctx.chat_id,
                    content="🎨 *Đã nhận yêu cầu vẽ ảnh!* Designer đang bắt đầu phác thảo và làm việc chăm chỉ... Vui lòng đợi trong giây lát nhé! ⏳",
                    metadata={**(ctx.metadata or {}), "_progress": True},
                )
                await self._send_callback(progress_msg)
            except Exception as e:
                logger.debug("Failed to send image generation progress message: {}", e)

        async def send_progress(text: str) -> None:
            c = _image_gen_request_ctx.get()
            if c and self._send_callback:
                try:
                    progress_msg = OutboundMessage(
                        channel=c.channel,
                        chat_id=c.chat_id,
                        content=text,
                        metadata={**(c.metadata or {}), "_progress": True},
                    )
                    await self._send_callback(progress_msg)
                except Exception as pe:
                    logger.debug("Failed to send progress update: {}", pe)

        # Images attached to the current message or replied-to message are
        # authoritative for edits, even if the LLM omitted or reordered them.
        reference_images = self._merge_revision_references(prompt, reference_images)

        # Apply Vidtory professional standards + customer brand guidelines
        is_vidtory = (self.config.provider == "vidtory")
        optimized_prompt, customer_ar, logo_url = self._apply_customer_context(prompt, is_vidtory_provider=is_vidtory)
        resolved_ar = aspect_ratio or customer_ar or self.config.default_aspect_ratio

        # Append multi-image instruction if multiple reference images are provided
        if reference_images and len(reference_images) > 1:
            target_lang = get_target_text_language(
                prompt,
                customer_language_preference(),
            )
            multi_image_instruction = build_multi_image_instruction(target_lang)
            optimized_prompt = f"{optimized_prompt}. {multi_image_instruction}"

        # Log logo status for traceability
        if logo_url:
            logger.info("Brand logo will be attached to request: {}", logo_url)
        else:
            logger.debug("No brand logo in customer profile — generation without logo overlay")

        try:
            refs = self._resolve_reference_images(reference_images)
            artifacts: list[dict[str, Any]] = []
            delivery_paths: list[str] = []
            while len(artifacts) < requested:
                artifact_count_before_request = len(artifacts)
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
                    logger.info("Vidtory provider: injecting logo_url into API call")
                if self.config.provider == "vidtory":
                    gen_kwargs["progress_callback"] = send_progress

                response = await client.generate(**gen_kwargs)
                for url in (response.image_urls or []):
                    if len(artifacts) >= requested:
                        break
                    artifact = store_remote_image_artifact(
                        url,
                        prompt=optimized_prompt,
                        model=self.config.model,
                        source_images=refs,
                        save_dir=self.config.save_dir,
                        provider=self.config.provider,
                    )
                    artifacts.append(artifact)
                    delivery_paths.append(artifact["path"])
                for image_data_url in response.images:
                    if len(artifacts) >= requested:
                        break
                    artifact = store_generated_image_artifact(
                        image_data_url,
                        prompt=optimized_prompt,
                        model=self.config.model,
                        source_images=refs,
                        save_dir=self.config.save_dir,
                        provider=self.config.provider,
                    )
                    artifacts.append(artifact)
                    delivery_paths.append(artifact["path"])
                if len(artifacts) == artifact_count_before_request:
                    raise ImageGenerationError(
                        "image generation provider returned no images"
                    )

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
                        result_url="",
                    )
                    # Also record in generation_history for backward compat
                    db.record_generation(
                        user_id,
                        content_type="image",
                        prompt=prompt,
                        enhanced_prompt=optimized_prompt,
                        model=self.config.model,
                        result_url="",
                    )
            except Exception as exc:
                logger.debug("Task recording/design note failed (non-fatal): {}", exc)

            # Auto-send images directly via bus so LLM doesn't need to call message tool
            ctx = _image_gen_request_ctx.get()
            if ctx and self._send_callback and delivery_paths:
                try:
                    outbound = OutboundMessage(
                        channel=ctx.channel,
                        chat_id=ctx.chat_id,
                        content="",
                        media=delivery_paths,
                        metadata=dict(ctx.metadata or {}),
                        buttons=[["Đúng ý", "Cần chỉnh"], ["Tạo biến thể"]],
                    )
                    await self._send_callback(outbound)
                    logger.info(
                        "ImageGenerationTool: auto-sent {} image(s) to {}:{}",
                        len(delivery_paths), ctx.channel, ctx.chat_id,
                    )
                    result = {
                        "status": "sent",
                        "count": len(delivery_paths),
                        "artifacts": artifacts,
                    }
                    if task_id:
                        result["task_id"] = task_id
                    if design_note:
                        result["design_note"] = design_note
                    return json.dumps(result, ensure_ascii=False)
                except Exception as send_exc:
                    logger.warning("ImageGenerationTool: auto-send failed: {}", send_exc)
                    # Fall through to returning artifacts for manual delivery.

            result = json.loads(generated_image_tool_result(artifacts))
            if task_id:
                result["task_id"] = task_id
            if design_note:
                result["design_note"] = design_note
            return json.dumps(result, ensure_ascii=False)
        except (ArtifactError, ImageGenerationError, OSError) as exc:
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

    def _find_last_generated_image(self) -> str | None:
        ctx = _image_gen_request_ctx.get()
        if not ctx:
            logger.debug("Cannot find last generated image: request context not available")
            return None
        
        # Check 1: Did the user upload/reply with a media file in the current request?
        media = ctx.metadata.get("media")
        if isinstance(media, list) and media:
            # Filter for files that exist
            valid_media = [m for m in media if m and (m.startswith(("http://", "https://")) or Path(m).is_file())]
            if valid_media:
                logger.info("Found reference image from current request media: {}", valid_media[0])
                return valid_media[0]

        if not ctx.session_key or not self.sessions:
            logger.debug("Cannot find last generated image from history: session_key or sessions not available")
            return None

        try:
            session = self.sessions.get_or_create(ctx.session_key)
            if not session or not session.messages:
                return None
            
            # Scan messages from the newest to oldest
            for msg in reversed(session.messages):
                role = msg.get("role")
                content = msg.get("content")
                
                # Check 2a: Tool response from generate_image
                if role == "tool" and msg.get("name") == "generate_image" and content:
                    try:
                        data = json.loads(content)
                        artifacts = data.get("artifacts") or []
                        if artifacts and isinstance(artifacts, list):
                            last_art = artifacts[-1]
                            path = last_art.get("path") or last_art.get("remote_url")
                            if path:
                                logger.info("Found last generated image from tool response: {}", path)
                                return path
                    except Exception:
                        pass
                
                # Check 2b: Assistant message with media paths
                if role == "assistant" and msg.get("media"):
                    h_media = msg.get("media")
                    if isinstance(h_media, list) and h_media:
                        logger.info("Found last generated image from assistant media: {}", h_media[-1])
                        return h_media[-1]

                # Check 2c: A previously uploaded user image. This supports a
                # follow-up such as "từ ảnh trên hãy sửa..." without a reply.
                if role == "user" and msg.get("media"):
                    h_media = msg.get("media")
                    if isinstance(h_media, list) and h_media:
                        logger.info("Found previous user image from session media: {}", h_media[-1])
                        return h_media[-1]
        except Exception as exc:
            logger.warning("Error finding last generated image: {}", exc)
            
        return None

    @staticmethod
    def _valid_context_media(values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        return [
            value
            for value in values
            if isinstance(value, str)
            and value
            and (
                value.startswith(("http://", "https://"))
                or Path(value).is_file()
            )
        ]

    def _merge_revision_references(
        self,
        prompt: str,
        reference_images: list[str] | None,
    ) -> list[str] | None:
        """Make current and replied-to images authoritative for edit requests."""
        if not _is_revision_prompt(prompt):
            return reference_images

        ctx = _image_gen_request_ctx.get()
        request_media: list[str] = []
        if ctx:
            reply_media = self._valid_context_media(ctx.metadata.get("reply_media"))
            current_media = self._valid_context_media(ctx.metadata.get("current_media"))
            request_media = (
                reply_media + current_media
                if reply_media or current_media
                else self._valid_context_media(ctx.metadata.get("media"))
            )

        merged = list(dict.fromkeys(request_media + list(reference_images or [])))
        if merged:
            return merged

        last_img = self._find_last_generated_image()
        return [last_img] if last_img else reference_images

    def _apply_customer_context(self, prompt: str, is_vidtory_provider: bool = False) -> tuple[str, str | None, str | None]:
        """Apply customer brand guidelines and Vidtory professional standards to the prompt.

        This is the central prompt enrichment pipeline:
        1. Auto-detect target text language from explicit request or detected prompt language
        2. Auto-detect content type from prompt
        3. Apply Vidtory professional photography style for that content type
           (SKIPPED when prompt is already detailed to avoid injecting irrelevant styles)
           Uses language-specific styles matching the target language.
        4. Apply customer brand guidelines (style, mood keywords, colors)
           Uses Vietnamese labels when target language is 'vi'.
        5. Derive customer's preferred aspect ratio from their primary channel
        6. Extract brand logo URL (for logo-aware generation)
        7. Inject logo preservation instruction when watermark-related keywords
           are detected in the prompt (prevents AI from erasing the logo)
        8. Inject text language instruction & preserve quoted text (applied universally)

        Returns:
            Tuple of (enriched_prompt, aspect_ratio_or_None, logo_url_or_None).
            The enriched prompt is non-destructive — original intent is always preserved.
        """
        enriched = prompt
        aspect_ratio: str | None = None
        logo_url: str | None = None

        # ── Detect customer language preference ──────────────────────────────
        customer_lang = customer_language_preference()

        # ── Detect target language (explicit or auto-detected) ──────────
        target_lang = get_target_text_language(prompt, customer_lang)

        # ── Step 1: Vidtory professional prompt enhancement ──────────────────
        # Skip when the user has already written a detailed/professional prompt
        # to avoid injecting irrelevant content-type keywords (e.g. 'beverage
        # photography' into a nature/illustration prompt).
        if not self._is_detailed_prompt(prompt):
            try:
                content_type = detect_content_type(prompt)
                pro_suffix = build_professional_prompt_suffix(
                    prompt, content_type=content_type, lang=target_lang,
                )
                if pro_suffix:
                    enriched = f"{enriched}, {pro_suffix}"
                    logger.debug(
                        "Vidtory professional enhancement applied (content_type={}, lang={}): +{} chars",
                        content_type or "auto",
                        target_lang or "default",
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
                # Read the indexed DB column as the authoritative logo source.
                # Profile JSON is kept in sync, but the indexed value avoids
                # stale in-memory profile data during a logo-change turn.
                try:
                    uid = str(
                        profile.get("telegramUserId")
                        or profile.get("telegram_user_id")
                        or ""
                    ).strip().split("|")[0]
                    if uid:
                        from nanobot.db.customer_db import get_db
                        logo_url = get_db().get_logo_url(uid) or None
                        if logo_url:
                            logger.info("Brand logo loaded from DB (/setlogo): {}", logo_url)
                        else:
                            logger.debug("No logo set for user {} — generating without logo overlay", uid)
                except Exception as _logo_exc:
                    logger.debug("Failed to read logo from DB (non-critical): {}", _logo_exc)

                # If user explicitly requested no logo in prompt, do not use it
                if logo_url and _prompt_requests_no_logo(prompt):
                    logger.info("User prompt explicitly requested no logo; skipping logo injection")
                    logo_url = None

                # ── Step 5: Logo preservation guard & instructions ────────────
                if logo_url:
                    enriched = f"{enriched}. {build_logo_instruction(target_lang)}"

                    if self._prompt_has_watermark_keywords(prompt):
                        logo_guard = (
                            "QUAN TRỌNG: giữ nguyên logo thương hiệu như cũ — "
                            "KHÔNG xóa, làm mờ hoặc chỉnh sửa logo thương hiệu"
                            if target_lang == "vi"
                            else (
                                "IMPORTANT: preserve the existing brand logo exactly as-is — "
                                "do NOT erase, blur, or modify the brand logo"
                            )
                        )
                        enriched = f"{enriched}. {logo_guard}"
                        logger.info(
                            "Logo preservation guard injected into prompt "
                            "(watermark keyword detected, customer has logo)"
                        )
        except Exception:
            logger.warning("Customer context enhancement failed — using defaults")

        # ── Step 6: Language text instruction & preservation ─────────────────
        # Injected outside profile check so it always applies to any prompt.
        lang_instruction = build_language_instruction(target_lang)
        if lang_instruction:
            enriched = f"{enriched}. {lang_instruction}"
            logger.debug("Language text instruction injected into prompt: %s", target_lang)

        quoted_texts = extract_quoted_texts(prompt)
        exact_text_instruction = build_exact_text_instruction(quoted_texts, target_lang)
        if exact_text_instruction:
            enriched = f"{enriched}. {exact_text_instruction}"
            logger.debug("Preserve quoted text instruction injected")

        # ── Step 7: General professional layout standards ───────────────────
        # Append standard guidelines to keep layout clean, minimal, and uncluttered
        enriched = f"{enriched}. {build_layout_instruction(target_lang)}"

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
