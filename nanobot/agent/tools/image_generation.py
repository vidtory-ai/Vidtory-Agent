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
from nanobot.agent.tools.message import record_generated_media_delivery
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


def extract_replacement_texts(prompt: str) -> list[str]:
    """Extract exact copy requested by Vietnamese text-replacement commands."""
    pattern = re.compile(
        r"(?:sửa|thay|đổi|chỉnh)\s+"
        r"(?:(?:dòng|nội\s+dung)\s+)?chữ\b.*?\bthành\s+"
        r"(?:[\"“'](?P<quoted>[^\"”'\n]+)[\"”']|(?P<plain>[^,;.\n]+))",
        flags=re.IGNORECASE,
    )
    replacements: list[str] = []
    for match in pattern.finditer(prompt):
        value = (match.group("quoted") or match.group("plain") or "").strip()
        value = value.strip("\"'“”‘’ ")
        if value:
            replacements.append(value)
    return replacements


def _is_numbered_followup_choice(content: str) -> bool:
    """Return True for a typed or tapped creative choice such as 1 or 'chọn 2'."""
    return bool(
        re.fullmatch(
            r"\s*(?:(?:chọn|phương\s+án|hướng)\s*)?[1-3]\s*",
            content or "",
            flags=re.IGNORECASE,
        )
    )


# Supported output aspect ratios that customers commonly request as variants.
_EXPORT_VARIANT_RATIOS = frozenset(["4:3", "3:4", "9:16", "16:9", "1:1", "3:2", "2:3"])


def _is_export_variant_prompt(content: str) -> bool:
    """Return True when the user is asking for an aspect-ratio variant of the
    just-generated image (e.g. 'xuất bản 4:3', 'tỉ lệ 9:16 nhé', '4:3 đi').

    Distinct from _is_numbered_followup_choice — these are natural-language
    ratio requests, not tapped numbered buttons.  Both cases must resolve to
    the last GENERATED image, not the original uploaded source images.
    """
    content_lower = (content or "").lower()
    # Fast path: check for any ratio token (e.g. '4:3', '9:16') in the text
    if not any(ratio in content_lower for ratio in _EXPORT_VARIANT_RATIOS):
        return False
    # Guard: a bare ratio token is enough to qualify — the context already
    # established this is a follow-up turn (called only from _merge_revision_references
    # which has already gated on _is_revision_prompt or similar).
    return True


def _is_revision_prompt(prompt: str) -> bool:
    """Check if the user's prompt is a revision or edit request."""
    prompt_lower = prompt.lower()
    revision_keywords = [
        "sửa", "sửa lại", "chỉnh lại", "thay đổi", "ghép", "lồng",
        "từ ảnh", "ảnh trên", "ảnh trước", "ảnh vừa tạo", "tinh chỉnh", "tối ưu",
        "edit", "modify", "change", "add", "revision", "fix", "update", "replace",
        "chèn logo", "thêm logo", "bỏ logo", "xóa logo", "đặt logo",
        "dựa theo", "dựa trên", "dựa vào", "giống ảnh", "như ảnh", "giống bản", "như bản",
        "thiết kế trên", "thiết kế trước", "bản trước", "bản trên", "bản cũ", "ảnh cũ",
        "như trên", "như cũ", "cùng layout", "cùng style", "cùng phong cách", "đồng bộ",
        "biến thể", "phiên bản", "làm tiếp", "giữ nguyên"
    ]
    return any(kw in prompt_lower for kw in revision_keywords)


def _references_latest_image(prompt: str) -> bool:
    """Return True when the request explicitly points to the most recent image."""
    prompt_lower = prompt.lower()
    latest_image_markers = (
        "ảnh trên",
        "hình trên",
        "ảnh vừa tạo",
        "hình vừa tạo",
        "ảnh vừa rồi",
        "hình vừa rồi",
        "bản trên",
        "bản vừa tạo",
        "như trên",
        "above image",
        "image above",
        "last image",
        "latest image",
    )
    return any(marker in prompt_lower for marker in latest_image_markers)


def _is_vague_text(prompt: str) -> str | None:
    """Helper to detect if a prompt is vague and return the matched purpose category."""
    prompt_lower = prompt.lower()
    
    # Define vague purpose patterns
    # Each pattern maps to the Vietnamese purpose term
    vague_patterns = [
        (r"\btuy\u1ec3n d\u1ee5ng\b|\btuy\u1ec3n v\u1ecb tr\xed\b|\btuy\u1ec3n k\u1ebf to\xe1n\b|\btuy\u1ec3n nh\xe2n vi\xean\b", "tuyển dụng"),
        (r"\btuy\u1ec3n sinh\b", "tuyển sinh"),
        (r"\bqu\u1ea3ng c\xe1o\b|\bthu h\xfat kh\xe1ch\b", "quảng cáo"),
        (r"\bvinh danh\b", "vinh danh"),
        (r"\btri \xe2n\b", "tri ân"),
        (r"\bk\u1ef7 ni\u1ec7m\b", "kỷ niệm"),
        (r"\bs\u1ef1 ki\u1ec7n\b|\bh\u1ed9i ngh\u1ecb\b|\bkhai gi\u1ea3ng\b", "sự kiện"),
        (r"\bch\xe0o m\u1eebng\b", "chào mừng"),
        (r"\bgi\u1ea3i th\u01b0\u1eddng\b|\bth\xe0nh t\xedch\b", "giải thưởng"),
    ]
    
    # Check for visual subject indicators that make the prompt clear.
    subject_indicators = (
        "con ", "chú ", "người ", "sinh viên", "học sinh", "thầy cô", "giáo viên",
        "bàn ", "ghế ", "máy tính", "laptop", "điện thoại", "sản phẩm", "ly ", "tách ",
        "đứng ", "ngồi ", "nằm ", "cười ", "nhìn ", "chụp ", "phong cách", "background",
        "nền ", "studio", "ngoài trời", "trong phòng", "vẽ ", "tô ", "màu "
    )
    
    words = [w for w in re.split(r"\s+", prompt) if w]
    
    for pattern, purpose in vague_patterns:
        if re.search(pattern, prompt_lower):
            has_subject = any(indicator in prompt_lower for indicator in subject_indicators)
            if not has_subject or len(words) < 8:
                return purpose
                
    if re.search(r"\b(?:t\u1ea1o \u1ea3nh|thi\u1ebft k\u1ebf|t\u1ea1o poster)\b", prompt_lower):
        if len(words) < 8 and not any(indicator in prompt_lower for indicator in subject_indicators):
            return "thiết kế"
            
    return None


def _ambiguous_image_request_clarification(prompt: str) -> str | None:
    """Require clarification for short role/brand acronyms with multiple meanings or general vague requests."""
    if not prompt or _is_revision_prompt(prompt):
        return None
    prompt_lower = prompt.lower()
    
    # 1. First, check if the prompt explicitly resolves the BE ambiguity
    be_resolved = any(
        resolved_term in prompt_lower
        for resolved_term in (
            "backend engineer",
            "thương hiệu be",
            "brand be",
        )
    )
    
    # 2. Check for BE acronym match and prompt keywords
    acronym_match = re.search(r"\bBE\b", prompt, flags=re.IGNORECASE)
    has_image_keywords = bool(re.search(
        r"\b(?:ảnh|hình|poster|banner|thiết kế|quảng cáo|tuyển dụng|image|design|ad)\b",
        prompt,
        flags=re.IGNORECASE,
    ))
    
    if acronym_match and has_image_keywords and not be_resolved:
        return (
            "Clarification required: Cụm viết tắt trong yêu cầu có thể được hiểu theo nhiều cách. "
            "Vui lòng hỏi khách chọn một hướng trước khi tạo ảnh:\n"
            "1. Poster tuyển dụng Backend Engineer\n"
            "2. Poster quảng cáo cho thương hiệu be\n"
            "3. Ý nghĩa khác, khách mô tả thêm"
        )
        
    # 3. Check for general vague requests
    # If the user explicitly resolved BE as Backend Engineer or brand be, it is a resolved request, not vague.
    vague_purpose = _is_vague_text(prompt) if not be_resolved else None
    if vague_purpose:
        from nanobot.utils.brand_intelligence import build_creative_suggestions
        industry = ""
        try:
            profile = telegram_customer_profile.get()
            if profile:
                industry = str((profile.get("business") or {}).get("industry") or "")
        except Exception:
            pass
            
        suggestions = build_creative_suggestions(prompt, industry)
        return (
            f"Để tạo ảnh {vague_purpose} đẹp và đúng ý, bạn muốn hình ảnh thể hiện gì?\n\n"
            f"1️⃣ {suggestions[0]}\n"
            f"2️⃣ {suggestions[1]}\n"
            f"3️⃣ {suggestions[2]}\n\n"
            "Nếu muốn, trả lời theo mẫu:\n"
            "• Hướng ảnh: ...\n"
            "• Dòng chữ trên ảnh: ...\n"
            "• Tỷ lệ: 1:1 / 9:16 / 16:9"
        )
        
    return None


def _prompt_requests_no_logo(prompt: str) -> bool:
    """Check if the user explicitly requested to omit the logo.

    Covers common Vietnamese/English phrasings.  Any new variant reported in
    production should be added here — this is the single source of truth for
    no-logo intent detection.
    """
    prompt_lower = prompt.lower()
    return any(kw in prompt_lower for kw in [
        # Direct negative constructions
        "không logo", "không cần logo", "không có logo", "không chèn logo",
        "không sử dụng logo", "không dùng logo", "không gắn logo",
        "không đặt logo", "không hiện logo", "không hiển thị logo",
        # Removal / hiding
        "bỏ logo", "xóa logo", "tắt logo", "ẩn logo", "loại bỏ logo",
        # English
        "no logo", "without logo", "remove logo", "hide logo",
        "no brand logo", "without brand logo",
    ])


# Keywords indicating the user wants the logo re-enabled after a no-logo request.
# Checked in _update_logo_preference to set preferences.logoSuppressed = False,
# re-enabling logo injection for all subsequent image generation requests.
_WANT_LOGO_KEYWORDS: tuple[str, ...] = (
    "chèn logo", "thêm logo", "đặt logo", "có logo", "logo lại",
    "logo trở lại", "dùng logo", "với logo", "kèm logo", "hiện logo",
    "add logo", "with logo", "include logo", "show logo", "logo back",
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
    _MISSING_USER_VIDTORY_KEY = (
        "Error: Vidtory API key is not configured. "
        "Dùng /apikey YOUR_VIDTORY_KEY để cấu hình trước khi tạo ảnh."
    )
    _LOGO_REMINDER_FIRST_GENERATION = 3
    _LOGO_REMINDER_BUTTONS = [["Có, tôi sẽ gửi logo", "Chưa, nhắc sau"]]

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
            provider_snapshot_loader=getattr(ctx, "provider_snapshot_loader", None),
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
        provider_snapshot_loader: Callable[[], Any] | None = None,
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
        self.provider_snapshot_loader = provider_snapshot_loader

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

    def _request_user_api_key(self) -> str:
        from nanobot.utils.context_vars import telegram_vidtory_api_key

        user_key = (telegram_vidtory_api_key.get() or "").strip()
        if user_key:
            return user_key
        ctx = _image_gen_request_ctx.get()
        if ctx and isinstance(ctx.metadata, dict):
            return str(ctx.metadata.get("user_api_key") or "").strip()
        return ""

    def _requires_telegram_user_vidtory_key(self) -> bool:
        ctx = _image_gen_request_ctx.get()
        return bool(
            self.config.provider == "vidtory"
            and ctx
            and ctx.channel == "telegram"
            and isinstance(ctx.metadata, dict)
            and "user_api_key" in ctx.metadata
        )

    def _provider_client(self) -> ImageGenerationProvider | None:
        user_key = self._request_user_api_key()
        provider = self._provider_config()
        cls = get_image_gen_provider(self.config.provider)
        if cls is None:
            return None
        # SECURITY: Never fall back to system api_key.
        # Every generation request MUST use the user's own Vidtory key.
        # Passing None when user_key is absent lets the provider raise a
        # descriptive error (missing_key_message) rather than silently
        # consuming system quota.
        kwargs = {
            "api_key": user_key or None,
            "api_base": provider.api_base if provider else None,
            "extra_headers": provider.extra_headers if provider else None,
            "extra_body": provider.extra_body if provider else None,
        }
        return cls(**kwargs)

    @staticmethod
    def _profile_logo_url(profile: dict[str, Any] | None, user_id: str = "") -> str:
        try:
            if user_id:
                from nanobot.db.customer_db import get_db

                indexed = (get_db().get_logo_url(user_id) or "").strip()
                if indexed:
                    return indexed
        except Exception:
            pass
        brand = (profile or {}).get("brand") if isinstance(profile, dict) else {}
        return str((brand or {}).get("logoUrl") or "").strip()

    async def _maybe_send_logo_reminder_after_generation(self, user_id: str) -> None:
        if not user_id or not self._send_callback:
            return
        ctx = _image_gen_request_ctx.get()
        if not ctx:
            return
        try:
            from nanobot.db.customer_db import get_db
            from nanobot.utils.customer_profile import load_profile, save_profile

            profile = load_profile(user_id)
            if not profile or self._profile_logo_url(profile, user_id):
                return

            preferences = profile.setdefault("preferences", {})
            if preferences.get("logoReminderAwaitingUpload"):
                return

            count = get_db().get_generation_count(user_id)
            next_at = int(
                preferences.get("logoReminderNextGeneration")
                or self._LOGO_REMINDER_FIRST_GENERATION
            )
            if count < next_at:
                return

            preferences["logoReminderAwaitingUpload"] = True
            save_profile(user_id, profile)
            await self._send_callback(
                OutboundMessage(
                    channel=ctx.channel,
                    chat_id=ctx.chat_id,
                    content=(
                        "Bạn đã tạo vài sản phẩm khi chưa có logo thương hiệu.\n\n"
                        "Nếu gửi logo, các ảnh tiếp theo sẽ bám màu sắc và nhận diện tốt hơn. "
                        "Bạn muốn gửi logo ngay không?"
                    ),
                    metadata=dict(ctx.metadata or {}),
                    buttons=self._LOGO_REMINDER_BUTTONS,
                )
            )
        except Exception as exc:
            logger.debug("Logo reminder check failed: {}", exc)

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

    async def _check_vague_request_with_llm(self, prompt: str) -> str | None:
        """Call the LLM dynamically to analyze request vagueness and generate suggestions."""
        if not self.provider_snapshot_loader:
            return None

        try:
            profile_info = ""
            try:
                profile = telegram_customer_profile.get()
                if profile:
                    biz = profile.get("business") or {}
                    brand = profile.get("brand") or {}
                    profile_info = (
                        f"- Tên thương hiệu: {biz.get('businessName') or biz.get('name') or ''}\n"
                        f"- Ngành nghề: {biz.get('industry') or ''}\n"
                        f"- Phong cách thương hiệu: {brand.get('brandStyle') or brand.get('style') or ''}\n"
                        f"- Màu sắc: {brand.get('colorPalette') or ''}\n"
                    )
            except Exception:
                pass

            snapshot = self.provider_snapshot_loader()
            llm = snapshot.provider
            model = snapshot.model

            system_prompt = (
                "Bạn là chuyên gia thiết kế và phân tích yêu cầu thiết kế đồ họa của Vidtory.\n"
                "Nhiệm vụ của bạn là đánh giá xem yêu cầu tạo ảnh/thiết kế của khách hàng có bị MƠ HỒ (vague) hay không.\n\n"
                "Thông tin thương hiệu khách hàng (sử dụng để đề xuất cho phù hợp ngữ cảnh):\n"
                f"{profile_info}\n"
                "Tiêu chuẩn đánh giá:\n"
                "- Mơ hồ (vague): Khách chỉ nêu mục đích/chủ đề sử dụng chung chung (ví dụ: 'tạo ảnh tuyển sinh', 'poster quảng cáo', 'ảnh tuyển kế toán', 'ảnh kỷ niệm', 'ảnh tri ân') "
                "mà CHƯA có bất kỳ mô tả hình ảnh, chủ thể cụ thể nào (nhân vật, đồ vật, hành động, cảnh vật, bố cục, style cụ thể).\n"
                "- Rõ ràng: Khách đã nêu chủ thể cụ thể (ví dụ: 'một chú mèo nằm trên ghế sofa', 'nhóm nhân viên công sở đang họp trước màn hình', 'ly cà phê latte art bốc khói').\n\n"
                "Nếu yêu cầu của khách là RÕ RÀNG, hoặc là yêu cầu chỉnh sửa ảnh cũ (revision/edit như 'sửa ảnh trên', 'chỉnh ảnh vừa rồi'), hoặc khách chỉ trả lời ngắn chọn phương án, hãy trả về JSON với `is_vague: false`.\n\n"
                "Nếu yêu cầu MƠ HỒ (vague):\n"
                "1. Xác định mục đích sử dụng (ví dụ: 'tuyển dụng', 'quảng cáo', 'tuyển sinh', 'tri ân').\n"
                "2. Đề xuất 3 hướng/phong cách sáng tạo cụ thể (ngắn gọn, tối đa 5-7 từ mỗi hướng, thích hợp hiển thị làm nút bấm) để khách lựa chọn, dựa trên thông tin thương hiệu của khách hàng nêu trên nếu có.\n\n"
                "Phản hồi của bạn PHẢI là một chuỗi JSON hợp lệ duy nhất có cấu trúc sau, không kèm bất kỳ giải thích nào:\n"
                "{\n"
                "  \"is_vague\": true,\n"
                "  \"purpose\": \"mục đích sử dụng (tiếng Việt)\",\n"
                "  \"suggestions\": [\"Gợi ý 1\", \"Gợi ý 2\", \"Gợi ý 3\"]\n"
                "}"
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Yêu cầu khách hàng: \"{prompt}\""}
            ]

            response = await llm.chat(
                messages=messages,
                model=model,
                temperature=0.1,
                max_tokens=300
            )

            content = (response.content or "").strip()
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\n", "", content)
                content = re.sub(r"\n```$", "", content)

            data = json.loads(content)
            if data.get("is_vague"):
                purpose = data.get("purpose") or "thiết kế"
                suggs = data.get("suggestions") or []
                if len(suggs) < 3:
                    suggs = suggs + ["Tối giản tinh tế", "Hiện đại chuyên nghiệp", "Năng động sáng tạo"][:3-len(suggs)]

                return (
                    f"Để tạo ảnh {purpose} đẹp và đúng ý, bạn muốn hình ảnh thể hiện gì?\n\n"
                    f"1️⃣ {suggs[0]}\n"
                    f"2️⃣ {suggs[1]}\n"
                    f"3️⃣ {suggs[2]}\n\n"
                    "Nếu muốn, trả lời theo mẫu:\n"
                    "• Hướng ảnh: ...\n"
                    "• Dòng chữ trên ảnh: ...\n"
                    "• Tỷ lệ: 1:1 / 9:16 / 16:9"
                )
        except Exception as e:
            logger.warning("LLM vague request check failed or timed out: {}", e)

        return None

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

        ctx = _image_gen_request_ctx.get()
        original_user_content = (
            str(ctx.metadata.get("original_user_content") or "").strip()
            if ctx
            else ""
        )
        has_request_media = bool(
            ctx
            and (
                self._valid_context_media(ctx.metadata.get("reply_media"))
                or self._valid_context_media(ctx.metadata.get("current_media"))
                or self._valid_context_media(ctx.metadata.get("media"))
            )
        )
        if original_user_content and not has_request_media:
            # 1. Try intelligent context-aware check using LLM first
            clarification = await self._check_vague_request_with_llm(original_user_content)
            
            # 2. Fall back to local rules if LLM didn't return a clarification
            if not clarification:
                clarification = _ambiguous_image_request_clarification(
                    original_user_content
                )
                
            if clarification:
                logger.info(
                    "Image generation blocked pending clarification of original request: {}",
                    original_user_content,
                )
                return clarification

        if self._requires_telegram_user_vidtory_key() and not self._request_user_api_key():
            return self._MISSING_USER_VIDTORY_KEY

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

        # Persist any explicit logo preference (no-logo / want-logo) from the user
        # message BEFORE _apply_customer_context reads the profile flag.
        self._update_logo_preference(original_user_content)

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
            customer_user_id = ""
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
                    customer_user_id = user_id
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
                    )
                    await self._send_callback(outbound)
                    record_generated_media_delivery(delivery_paths)
                    await self._maybe_send_logo_reminder_after_generation(customer_user_id)
                    logger.info(
                        "ImageGenerationTool: auto-sent {} image(s) to {}:{}",
                        len(delivery_paths), ctx.channel, ctx.chat_id,
                    )
                    result = {
                        "status": "sent",
                        "count": len(delivery_paths),
                        "artifacts": artifacts,
                        "next_step": (
                            "The image is already delivered. Do not send the artifact media again. "
                            "Reply with a short completion note, the design note, and exactly three "
                            "numbered follow-up options formatted as 1️⃣, 2️⃣, 3️⃣ so the UI renders buttons. "
                            "If the customer has no logo, end with one short line reminding them to upload a logo "
                            "for better brand consistency."
                        ),
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
            await self._maybe_send_logo_reminder_after_generation(customer_user_id)
            if task_id:
                result["task_id"] = task_id
            if design_note:
                result["design_note"] = design_note
            return json.dumps(result, ensure_ascii=False)
        except (ArtifactError, ImageGenerationError, OSError) as exc:
            err_msg = str(exc)
            if "401" in err_msg or "403" in err_msg or "is not configured" in err_msg:
                return json.dumps({
                    "status": "error",
                    "error_type": "authentication",
                    "message": "Lỗi xác thực API Key",
                    "next_step": (
                        "Khéo léo thông báo với khách hàng rằng: 'Hệ thống cần xác thực API Key để tạo ảnh "
                        "và lưu trữ trên không gian riêng tư của bạn. Bạn vui lòng cung cấp API Key bằng lệnh "
                        "/apikey YOUR_KEY nhé.' TUYỆT ĐỐI KHÔNG nói đây là lỗi hệ thống."
                    )
                }, ensure_ascii=False)
                
            return json.dumps({
                "status": "error",
                "error_type": "system",
                "message": err_msg,
                "next_step": (
                    f"Đã xảy ra vấn đề: {err_msg}. Hãy thông báo khéo léo với khách hàng rằng: "
                    "'Hệ thống đang gặp chút vấn đề cần giải quyết, bạn chờ một chút để mình tìm rõ nguyên nhân nhé!' "
                    "TUYỆT ĐỐI KHÔNG dùng từ 'lỗi hệ thống' làm khách lo lắng."
                )
            }, ensure_ascii=False)

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

    def _update_logo_preference(self, user_message: str) -> None:
        """Persist the user's logo preference to their profile when they explicitly state it.

        Detects no-logo / want-logo intent in the raw user message and saves
        ``preferences.logoSuppressed`` to the profile.  The flag persists
        indefinitely until the user explicitly changes it again — there is no
        time-window limit (unlike the previous session-scan approach).

        Called early in execute() so the preference is always up-to-date before
        _apply_customer_context() reads it.
        """
        if not user_message:
            return
        user_msg_lower = user_message.lower()
        wants_no_logo = _prompt_requests_no_logo(user_message)
        wants_logo = any(kw in user_msg_lower for kw in _WANT_LOGO_KEYWORDS)
        if not wants_no_logo and not wants_logo:
            return  # No explicit logo preference in this message — leave flag unchanged
        try:
            profile = telegram_customer_profile.get()
            if not profile:
                return
            uid = str(
                profile.get("telegramUserId")
                or profile.get("telegram_user_id")
                or ""
            ).strip().split("|")[0]
            if not uid:
                return
            from nanobot.utils.customer_profile import load_profile, save_profile
            fresh = load_profile(uid)
            if not fresh:
                return
            prefs = fresh.setdefault("preferences", {})
            if wants_no_logo:
                prefs["logoSuppressed"] = True
                logger.info("Logo preference: suppressed (user said no-logo) — persisted for uid {}", uid)
            else:
                prefs["logoSuppressed"] = False
                logger.info("Logo preference: re-enabled (user said want-logo) — persisted for uid {}", uid)
            save_profile(uid, fresh)
        except Exception as exc:
            logger.debug("_update_logo_preference failed (non-fatal): {}", exc)


    def _find_last_generated_image(
        self,
        *,
        recent_turn_only: bool = False,
    ) -> str | None:
        ctx = _image_gen_request_ctx.get()
        if not ctx:
            logger.debug("Cannot find last generated image: request context not available")
            return None
        
        # Check 1: Did the user upload/reply with a media file in the current request?
        # Skip this shortcut when called for a numbered follow-up choice (recent_turn_only=True)
        # because we want the last GENERATED image, not the user's uploaded source images.
        if not recent_turn_only:
            media = ctx.metadata.get("media")
            if isinstance(media, list) and media:
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
            
            # Scan messages from the newest to oldest. For a bare 1/2/3
            # choice, stop at the prior user-turn boundary so an unrelated
            # older image is never pulled into a new clarification flow.
            user_boundaries = 0
            for msg in reversed(session.messages):
                role = msg.get("role")
                content = msg.get("content")
                if role == "user":
                    user_boundaries += 1
                    if recent_turn_only and user_boundaries >= 2:
                        break
                    if not recent_turn_only and msg.get("media"):
                        h_media = msg.get("media")
                        if isinstance(h_media, list) and h_media:
                            logger.info(
                                "Found previous user image from session media: {}",
                                h_media[-1],
                            )
                            return h_media[-1]
                    continue
                
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
        ctx = _image_gen_request_ctx.get()
        original_user_content = (
            str(ctx.metadata.get("original_user_content") or "").strip()
            if ctx
            else ""
        )
        numbered_choice = _is_numbered_followup_choice(original_user_content)
        export_variant = _is_export_variant_prompt(original_user_content)
        if not (
            _is_revision_prompt(prompt)
            or _is_revision_prompt(original_user_content)
            or numbered_choice
            or export_variant
        ):
            return reference_images

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

        # Numbered follow-up (user tapped 1/2/3) OR export-variant request
        # (e.g. 'xuất bản 4:3', 'tỉ lệ 9:16'): always use the last GENERATED
        # image, never the original uploaded source images that may still be
        # present in context.metadata['media'] from the initial upload turn.
        if numbered_choice or export_variant:
            last_img = self._find_last_generated_image(recent_turn_only=True)
            if last_img:
                logger.info(
                    "{} follow-up uses image from previous turn: {}",
                    "Numbered" if numbered_choice else "Export-variant",
                    last_img,
                )
                return [last_img]
            return merged or None

        if request_media:
            return merged

        if (
            _references_latest_image(prompt)
            or _references_latest_image(original_user_content)
        ):
            last_img = self._find_last_generated_image()
            if last_img:
                logger.info(
                    "Latest-image revision overrides model-selected references: {}",
                    last_img,
                )
                return [last_img]

        if merged:
            return merged

        last_img = self._find_last_generated_image()
        if last_img:
            logger.info("Revision uses latest generated image: {}", last_img)
            return [last_img]

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
        ctx = _image_gen_request_ctx.get()
        original_user_content = (
            str(ctx.metadata.get("original_user_content") or "").strip()
            if ctx
            else ""
        )
        language_source = (
            original_user_content
            if original_user_content
            and not _is_numbered_followup_choice(original_user_content)
            else prompt
        )
        target_lang = get_target_text_language(language_source, customer_lang)

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

                if not logo_url:
                    profile_logo = str(
                        ((profile.get("brand") or {}).get("logoUrl") or "")
                    ).strip()
                    if profile_logo:
                        logo_url = profile_logo
                        logger.info(
                            "Brand logo loaded from customer profile fallback: {}",
                            logo_url,
                        )

                # Persistent logo suppression flag — set/unset by _update_logo_preference()
                # earlier in execute().  Read fresh from DB using the uid already resolved
                # above so we always see the flag written in this same turn.
                # Also honour an inline override if the LLM embeds the instruction
                # directly in the tool prompt (belt-and-suspenders).
                logo_suppressed = False
                try:
                    if uid:
                        from nanobot.utils.customer_profile import load_profile as _lp
                        _fresh = _lp(uid)
                        logo_suppressed = bool(
                            (_fresh or {}).get("preferences", {}).get("logoSuppressed", False)
                        )
                except Exception:
                    pass
                if logo_url and (
                    logo_suppressed
                    or _prompt_requests_no_logo(prompt)
                    or _prompt_requests_no_logo(original_user_content)
                ):
                    logger.info(
                        "No-logo preference: suppressing logo "
                        "(profile_flag={}, prompt={}, user_content={})",
                        logo_suppressed,
                        _prompt_requests_no_logo(prompt),
                        _prompt_requests_no_logo(original_user_content),
                    )
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

        exact_texts = list(
            dict.fromkeys(
                extract_quoted_texts(prompt)
                + extract_replacement_texts(prompt)
                + extract_quoted_texts(original_user_content)
                + extract_replacement_texts(original_user_content)
            )
        )
        exact_text_instruction = build_exact_text_instruction(exact_texts, target_lang)
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
