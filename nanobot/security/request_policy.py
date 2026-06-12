"""Deterministic request and capability policy for restricted agent profiles."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

STANDARD_PROFILE = "standard"
RESIDENT_DESIGNER_PROFILE = "resident_designer"

RESIDENT_DESIGNER_TOOLS = frozenset({
    "generate_image",
    "generate_text",
    "generate_video",
    "message",
    "remove_watermark",
    "update_customer_profile",
})
RESIDENT_DESIGNER_ALLOWED_COMMANDS = frozenset({
    "/help",
    "/history",
    "/model",
    "/new",
    "/status",
    "/stop",
})

_REFUSAL_VI = {
    "prompt_override": (
        "Tôi không thể thay đổi hoặc bỏ qua quy tắc hệ thống. "
        "Hãy gửi brief sáng tạo trực tiếp, tôi sẽ tập trung làm ra hình ảnh, video hoặc nội dung thật tốt."
    ),
    "prompt_exfiltration": (
        "Tôi không thể chia sẻ cấu hình hay chỉ dẫn nội bộ. "
        "Tôi vẫn có thể giúp bạn biến mục tiêu kinh doanh thành concept, hình ảnh, video hoặc nội dung thương hiệu."
    ),
    "external_code_repository": (
        "Tôi không truy cập, phân tích hoặc triển khai kho mã. "
        "Bạn có thể gửi mô tả sản phẩm, ảnh chụp giao diện hoặc các điểm nổi bật; "
        "tôi sẽ chuyển chúng thành landing-page copy, key visual hoặc concept video."
    ),
    "system_command": (
        "Tôi không chạy hoặc cung cấp lệnh thao tác hệ thống. "
        "Nếu mục tiêu là truyền thông, tôi có thể làm infographic, poster cảnh báo hoặc nội dung giới thiệu ở mức an toàn."
    ),
    "technical_operation": (
        "Tôi không thực hiện hay hướng dẫn vận hành hệ thống. "
        "Tôi có thể chuyển chủ đề này thành nội dung truyền thông, hình minh hoạ, poster hoặc video concept."
    ),
    "role_override": (
        "Tôi vẫn giữ vai trò Vidtory Resident Designer. "
        "Bạn hoàn toàn có thể yêu cầu tôi tạo nhân vật developer, hacker hoặc chuyên gia bảo mật trong một concept sáng tạo."
    ),
    "disallowed_command": (
        "Lệnh này không khả dụng trong chế độ thiết kế. "
        "Hãy mô tả kết quả sáng tạo bạn cần, tôi sẽ xử lý trực tiếp."
    ),
    "default": (
        "Yêu cầu này nằm ngoài phạm vi thiết kế và sáng tạo nội dung của Vidtory AI. "
        "Tôi có thể hỗ trợ tạo ảnh, video hoặc nội dung thương hiệu."
    ),
}
_REFUSAL_EN = {
    "prompt_override": (
        "I cannot change or ignore the system rules. "
        "Send the creative brief directly and I will focus on producing strong images, video, or copy."
    ),
    "prompt_exfiltration": (
        "I cannot disclose internal configuration or hidden instructions. "
        "I can still turn the business goal into a concept, image, video, or brand content."
    ),
    "external_code_repository": (
        "I cannot access, analyze, or deploy a code repository. "
        "Share the product description, interface screenshots, or key benefits and I can create landing-page copy, "
        "a key visual, or a video concept."
    ),
    "system_command": (
        "I cannot run or provide system-operation commands. "
        "For communication goals, I can create an infographic, awareness poster, or safe high-level content."
    ),
    "technical_operation": (
        "I cannot perform or instruct system operations. "
        "I can turn the topic into marketing content, an illustration, a poster, or a video concept."
    ),
    "role_override": (
        "I will remain Vidtory Resident Designer. "
        "You can still ask me to depict a developer, hacker, or security expert inside a creative concept."
    ),
    "disallowed_command": (
        "That command is unavailable in design mode. "
        "Describe the creative outcome you need and I will work on it directly."
    ),
    "default": (
        "That request is outside Vidtory AI's design and creative-content scope. "
        "I can help with images, videos, or brand content."
    ),
}

_REPO_HOST_RE = re.compile(
    r"(?:https?(?:://|\s+))?(?:www(?:\.|\s+))?"
    r"(?:github(?:\.|\s+)com|gitlab(?:\.|\s+)com|bitbucket(?:\.|\s+)org)\b",
    re.IGNORECASE,
)
_COMMAND_RE = re.compile(
    r"\b(?:git\s+(?:clone|pull|push)|docker(?:\s+compose)?\s+"
    r"(?:up|run|build|pull)|kubectl|terraform|ansible-playbook|"
    r"(?:npm|pnpm|yarn|pip3?|apt(?:-get)?|yum|dnf|brew)\s+"
    r"(?:install|add)|curl\s+https?(?:://|\s+)|wget\s+https?(?:://|\s+))\b",
    re.IGNORECASE,
)
_PROMPT_OVERRIDE_RE = re.compile(
    r"\b(?:ignore|disregard|forget|override|bypass)\b.{0,80}"
    r"\b(?:previous|prior|system|developer|instruction|rule|policy|prompt)\b"
    r"|\b(?:bo qua|quen|ghi de|vo hieu hoa)\b.{0,80}"
    r"\b(?:chi dan|quy tac|he thong|system prompt|lenh truoc)\b",
    re.IGNORECASE | re.DOTALL,
)
_PROMPT_EXFIL_RE = re.compile(
    r"\b(?:show|reveal|print|dump|repeat|leak|extract)\b.{0,60}"
    r"\b(?:system prompt|developer message|hidden instructions?|soul(?:\.|\s+)md)\b"
    r"|\b(?:hien|tiet lo|in|doc|trich xuat)\b.{0,60}"
    r"\b(?:system prompt|cau hinh he thong|chi dan an|soul(?:\.|\s+)md)\b",
    re.IGNORECASE | re.DOTALL,
)
_ROLE_OVERRIDE_RE = re.compile(
    r"\b(?:act as|pretend to be|you are now|gia su ban la|dong vai)\b.{0,80}"
    r"\b(?:developer|programmer|coder|devops|sysadmin|hacker|pentester|"
    r"security expert|lap trinh vien|chuyen gia bao mat|dev)\b",
    re.IGNORECASE | re.DOTALL,
)
_TECH_ACTION_RE = re.compile(
    r"\b(?:clone|deploy|download|install|execute|run|fetch|analyze|audit|"
    r"configure|set up|setup|build|compile|debug|fix)\b.{0,50}"
    r"\b(?:repo(?:sitory)?|source code|codebase|script|command|"
    r"terminal|shell|server|vps|container|docker|kubernetes|package|"
    r"dependency|database|api|system)\b"
    r"|\b(?:clone|deploy|tai xuong|cai dat|thuc thi|chay|phan tich|"
    r"kiem thu|cau hinh|trien khai|sua)\b.{0,50}"
    r"\b(?:repo|ma nguon|source code|code|script|lenh|terminal|"
    r"shell|server|vps|container|docker|kubernetes|package|dependency|"
    r"co so du lieu|api|he thong)\b",
    re.IGNORECASE | re.DOTALL,
)
_CREATIVE_CONTEXT_RE = re.compile(
    r"\b(?:poster|banner|key visual|visual|image|illustration|infographic|"
    r"video|storyboard|thumbnail|caption|tagline|headline|copywriting|copy|"
    r"social post|landing page|article|blog|email|brochure|presentation|"
    r"pitch deck|campaign|advertisement|advertising|marketing|"
    r"brand content|creative concept|character|scene|moodboard|whitepaper|"
    r"anh|hinh minh hoa|thiet ke|quang cao|kich ban|noi dung|bai dang|"
    r"bai viet|viet bai|canh bao|warning|email|brochure|thuyet trinh|chien dich|y tuong sang tao|"
    r"nhan vat|boi canh|canh quay)\b",
    re.IGNORECASE,
)
_INSTRUCTIONAL_TECH_RE = re.compile(
    r"\b(?:how to|step by step|walkthrough|tutorial|instructions?|guide|"
    r"implementation|procedure|commands?|source code|code snippet|"
    r"huong dan|tung buoc|cac buoc|cach lam|quy trinh|cau lenh|doan code|ma nguon)\b"
    r".{0,120}\b(?:clone|deploy|download|install|execute|run|fetch|configure|"
    r"set up|setup|build|compile|debug|fix|git|docker|shell|terminal|server|"
    r"tai xuong|cai dat|thuc thi|chay|cau hinh|trien khai|sua)\b"
    r"|\b(?:clone|deploy|download|install|execute|run|fetch|configure|"
    r"set up|setup|build|compile|debug|fix|tai xuong|cai dat|thuc thi|"
    r"chay|cau hinh|trien khai|sua)\b.{0,120}"
    r"\b(?:step by step|walkthrough|tutorial|instructions?|commands?|"
    r"huong dan|tung buoc|cac buoc|cau lenh|doan code|ma nguon)\b",
    re.IGNORECASE | re.DOTALL,
)
_DIRECT_TECH_REQUEST_RE = re.compile(
    r"\b(?:please|can you|could you|would you|help me|i need you to|"
    r"hay|vui long|giup toi|lam on|thu|tien the|sau do|dong thoi)\b"
    r".{0,50}\b(?:clone|deploy|download|install|execute|run|fetch|analyze|audit|"
    r"configure|set up|setup|build|compile|debug|fix|tai xuong|cai dat|"
    r"thuc thi|chay|phan tich|kiem thu|cau hinh|trien khai|sua)\b"
    r"|(?:^|[.!?;,]\s*)"
    r"(?:clone|deploy|download|install|execute|run|fetch|analyze|audit|"
    r"configure|set up|setup|build|compile|debug|fix|tai xuong|cai dat|"
    r"thuc thi|chay|phan tich|kiem thu|cau hinh|trien khai|sua)\b",
    re.IGNORECASE | re.DOTALL,
)
_NEGATED_TECH_RE = re.compile(
    r"\b(?:do not|don't|dont|never|avoid|warning|warn users|"
    r"khong|dung|tranh|canh bao|nguy hiem)\b"
    r".{0,50}\b(?:clone|deploy|download|install|execute|run|fetch|"
    r"git|docker|shell|terminal|tai xuong|cai dat|thuc thi|chay|trien khai)\b",
    re.IGNORECASE | re.DOTALL,
)
_CREATIVE_ANALYSIS_RE = re.compile(
    r"\b(?:analyze|audit|review|evaluate|improve|refine|fix|"
    r"phan tich|danh gia|nhan xet|cai thien|toi uu|sua)\b"
    r".{0,100}\b(?:design|visual|brand|branding|copy|copywriting|landing page|"
    r"poster|banner|image|video|caption|marketing|campaign|storyboard|"
    r"ux|ui|layout|typography|color|"
    r"thiet ke|hinh anh|noi dung|thuong hieu|bo cuc|mau sac|chu)\b",
    re.IGNORECASE | re.DOTALL,
)
_TECHNICAL_ASSET_RE = re.compile(
    r"\b(?:repo(?:sitory)?|source code|codebase|script|shell|terminal|"
    r"server|vps|container|docker|kubernetes|database|system|"
    r"ma nguon|doan code|cau lenh|he thong)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    blocked: bool
    reason: str = ""
    response: str = ""
    redacted_text: str = ""


def normalize_profile(value: Any) -> str:
    """Return a known profile name; unknown values fail back to standard."""
    if not isinstance(value, str):
        return STANDARD_PROFILE
    normalized = value.strip().lower().replace("-", "_")
    if normalized == RESIDENT_DESIGNER_PROFILE:
        return normalized
    return STANDARD_PROFILE


def is_resident_designer_profile(value: Any) -> bool:
    return normalize_profile(value) == RESIDENT_DESIGNER_PROFILE


def is_tool_allowed(profile: Any, tool_name: str) -> bool:
    """Apply the hard capability allowlist for restricted profiles."""
    if not is_resident_designer_profile(profile):
        return True
    return tool_name in RESIDENT_DESIGNER_TOOLS


def refusal_for(text: str, reason: str = "default") -> str:
    """Return the fixed refusal in the apparent language of the request."""
    lowered = text.casefold()
    vietnamese_markers = (
        "bạn", "tôi", "hãy", "giả sử", "triển khai", "cài đặt", "yêu cầu",
        "tạo", "viết", "thiết kế", "không", "phân tích", "cảnh báo", "nội dung",
    )
    has_vietnamese_diacritic = bool(re.search(r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặ"
                                              r"éèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộ"
                                              r"ớờởỡợúùủũụứừửữựýỳỷỹỵ]", lowered))
    responses = (
        _REFUSAL_VI
        if has_vietnamese_diacritic or any(marker in lowered for marker in vietnamese_markers)
        else _REFUSAL_EN
    )
    return responses.get(reason, responses["default"])


def evaluate_request(profile: Any, text: str) -> PolicyDecision:
    """Block known prompt attacks and prohibited technical operations."""
    if not is_resident_designer_profile(profile) or not text:
        return PolicyDecision(False)

    normalized = _normalize_text(text)
    for reason, pattern in (("prompt_override", _PROMPT_OVERRIDE_RE), ("prompt_exfiltration", _PROMPT_EXFIL_RE)):
        if pattern.search(normalized):
            return PolicyDecision(True, reason, refusal_for(text, reason))

    creative_context = bool(_CREATIVE_CONTEXT_RE.search(normalized))
    warning_context = bool(
        re.search(r"\b(?:canh bao|warning|khong nen|khong chay|khong dung)\b", normalized)
    )
    creative_context = creative_context or warning_context
    instructional_tech = bool(_INSTRUCTIONAL_TECH_RE.search(normalized))
    direct_tech_request = bool(_DIRECT_TECH_REQUEST_RE.search(normalized))
    negated_tech = bool(_NEGATED_TECH_RE.search(normalized))

    command_decision = _evaluate_command(text)
    if command_decision.blocked:
        if creative_context and negated_tech:
            return PolicyDecision(False)
        if creative_context and not negated_tech:
            redacted = _sanitize_mixed_request(text)
            if redacted and redacted.strip() and redacted.strip() != text.strip():
                return PolicyDecision(False, "mixed_request", redacted_text=redacted)
        return command_decision

    if _ROLE_OVERRIDE_RE.search(normalized) and not creative_context:
        reason = "role_override"
        return PolicyDecision(True, reason, refusal_for(text, reason))

    actionable_tech = bool(
        _COMMAND_RE.search(normalized)
        or instructional_tech
        or direct_tech_request
        or _TECH_ACTION_RE.search(normalized)
    )
    repo_reference = bool(_REPO_HOST_RE.search(normalized))

    if actionable_tech or (repo_reference and (instructional_tech or direct_tech_request)):
        if creative_context and negated_tech:
            return PolicyDecision(False)
        if creative_context and not negated_tech:
            redacted = _sanitize_mixed_request(text)
            if redacted and redacted.strip() and redacted.strip() != text.strip():
                return PolicyDecision(False, "mixed_request", redacted_text=redacted)
        reason = "system_command" if _COMMAND_RE.search(normalized) else (
            "external_code_repository" if repo_reference else "technical_operation"
        )
        return PolicyDecision(True, reason, refusal_for(text, reason))

    if repo_reference and not creative_context:
        reason = "external_code_repository"
        return PolicyDecision(True, reason, refusal_for(text, reason))
    return PolicyDecision(False)


def _evaluate_command(text: str) -> PolicyDecision:
    """Block slash commands outside the restricted creative command set."""
    stripped = text.strip()
    if not stripped.startswith("/"):
        return PolicyDecision(False)
    command = stripped.split(None, 1)[0].split("@", 1)[0].lower()
    if command in RESIDENT_DESIGNER_ALLOWED_COMMANDS:
        return PolicyDecision(False)
    return PolicyDecision(
        True,
        "disallowed_command",
        refusal_for(text, "disallowed_command"),
    )


def _sanitize_mixed_request(text: str) -> str:
    """Drop operational clauses while keeping the creative brief."""
    sanitized = text
    for pattern in (
        _COMMAND_RE,
        _INSTRUCTIONAL_TECH_RE,
        _DIRECT_TECH_REQUEST_RE,
        _TECH_ACTION_RE,
        _REPO_HOST_RE,
    ):
        sanitized = pattern.sub(" ", sanitized)
    sanitized = re.sub(
        r"\b(?:clone|deploy|download|install|execute|run|fetch|analyze|audit|"
        r"configure|set up|setup|build|compile|debug|fix|git|docker|terminal|"
        r"shell|server|vps|container|kubernetes|repository|repo|source|codebase|"
        r"source code|code|triển khai|chạy|cài đặt|phân tích|kiểm thử|cấu hình|sửa)\b",
        " ",
        sanitized,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(r"\b(?:and|then|also|tiện thể|rồi|sau đó|và|tiếp theo)\b", " ", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"[\s,;:/\\|]+", " ", sanitized)
    sanitized = re.sub(r"\s+", " ", sanitized).strip(" .,-")
    return sanitized


def _normalize_text(text: str) -> str:
    """Normalize common obfuscation without trying to interpret user code."""
    nfkc = unicodedata.normalize("NFKC", text)
    visible = "".join(ch for ch in nfkc if unicodedata.category(ch) != "Cf")
    decomposed = unicodedata.normalize("NFKD", visible)
    ascii_like = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    ascii_like = ascii_like.casefold()
    ascii_like = re.sub(r"[\s._/\\|:+-]+", " ", ascii_like)
    return re.sub(r"\s+", " ", ascii_like).strip()
