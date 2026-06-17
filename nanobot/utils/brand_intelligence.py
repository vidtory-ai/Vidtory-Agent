"""Deterministic brand intelligence used by chat, onboarding, and logo updates."""

from __future__ import annotations

import colorsys
import re
import unicodedata
from io import BytesIO
from typing import Any

_BRAND_UPDATE_ACTIONS = (
    "cap nhat",
    "chinh lai",
    "chuyen sang",
    "doi",
    "thay doi",
    "tu nay",
    "thuong hieu cua toi",
)
_BRAND_FIELDS = (
    "brand",
    "logo",
    "thuong hieu",
    "nhan dien",
    "phong cach",
    "mau sac",
    "tone mau",
    "mood",
    "doi tuong",
    "khach hang",
)
_CREATIVE_OUTPUTS = (
    "anh nay",
    "hinh nay",
    "poster nay",
    "banner nay",
    "video nay",
    "tao anh",
    "thiet ke anh",
    "lam anh",
    "sua anh",
    "chinh anh",
    "them chu",
)


def _plain(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text.lower())
    return re.sub(r"\s+", " ", "".join(c for c in normalized if unicodedata.category(c) != "Mn")).strip()


def detect_brand_update_intent(text: str) -> bool:
    """Return True for profile updates, while leaving concrete creative edits alone."""
    value = _plain(text)
    if not value or any(marker in value for marker in _CREATIVE_OUTPUTS):
        return False
    return (
        any(action in value for action in _BRAND_UPDATE_ACTIONS)
        and any(field in value for field in _BRAND_FIELDS)
    )


def get_profile_gaps(profile: dict[str, Any]) -> list[str]:
    """Return missing profile fields in the order most useful for generation."""
    business = profile.get("business") if isinstance(profile.get("business"), dict) else {}
    brand = profile.get("brand") if isinstance(profile.get("brand"), dict) else {}
    audience = profile.get("audience") if isinstance(profile.get("audience"), dict) else {}
    channels = (
        profile.get("contentChannels")
        if isinstance(profile.get("contentChannels"), dict)
        else {}
    )
    palette_value = brand.get("colorPalette")
    palette = palette_value if isinstance(palette_value, dict) else {}
    preferences = profile.get("preferences") if isinstance(profile.get("preferences"), dict) else {}
    logo_skipped = bool(preferences.get("logoPromptSkipped"))
    inferred_from_logo = (brand.get("identityInference") or {}).get("source") == "logo"
    style_confirmed = bool(brand.get("styleConfirmed")) or (
        bool(str(brand.get("style") or "").strip()) and not inferred_from_logo
    )

    checks = (
        ("logo", logo_skipped or bool(str(brand.get("logoUrl") or "").strip())),
        ("brand_style", style_confirmed),
        ("business_name", bool(str(business.get("name") or "").strip())),
        (
            "industry",
            bool(str(business.get("industry") or "").strip())
            and business.get("industry") != "other",
        ),
        ("business_description", bool(str(business.get("description") or "").strip())),
        ("primary_color", bool(palette.get("primary"))),
        ("mood", bool(brand.get("moodKeywords"))),
        ("photography_style", bool(str(brand.get("photographyStyle") or "").strip())),
        ("audience_age", bool(str(audience.get("ageRange") or "").strip())),
        ("audience_segment", bool(str(audience.get("segment") or "").strip())),
        ("channels", bool(channels.get("primary"))),
    )
    return [field for field, present in checks if not present]


def build_adaptive_onboarding_step(profile: dict[str, Any]) -> dict[str, Any]:
    """Build one progressive onboarding question from the highest-value gap."""
    gaps = get_profile_gaps(profile)
    field = gaps[0] if gaps else "completed"
    industry = _plain(str((profile.get("business") or {}).get("industry") or ""))

    if field == "business_name":
        return {"field": field, "prompt": "Tên thương hiệu của bạn là gì?", "buttons": []}
    if field == "industry":
        return {
            "field": field,
            "prompt": "Thương hiệu hoạt động trong lĩnh vực nào?",
            "buttons": [["Ẩm thực", "Thời trang", "Mỹ phẩm"], ["Công nghệ", "Bất động sản"]],
        }
    if field == "business_description":
        return {
            "field": field,
            "prompt": "Mô tả ngắn sản phẩm, dịch vụ và điểm khác biệt lớn nhất của thương hiệu nhé.",
            "buttons": [["Nhập mô tả", "Gửi website"], ["Tải hồ sơ thương hiệu"]],
        }
    if field == "logo":
        return {
            "field": field,
            "prompt": "Gửi logo để mình tự nhận diện màu sắc và phong cách thương hiệu nhé.",
            "buttons": [["Gửi logo", "Nhập website"], ["Chưa có logo"]],
        }
    if field == "brand_style":
        inferred_style = str((profile.get("brand") or {}).get("style") or "").strip()
        palette = (profile.get("brand") or {}).get("colorPalette") or {}
        colors = ", ".join(
            str(palette.get(key)) for key in ("primary", "secondary", "accent") if palette.get(key)
        )
        brand_read = ""
        if colors or inferred_style:
            brand_read = (
                f"Mình đọc logo có màu chủ đạo {colors or 'đang được nhận diện'} "
                f"và concept {inferred_style or 'đang được đề xuất'}. "
            )
        return {
            "field": field,
            "prompt": (
                f"{brand_read}Chọn style reference gần gu nhất; "
                "bạn cũng có thể gửi một ảnh tham chiếu riêng."
            ),
            "buttons": [["Clean Premium", "Bold Performance", "Editorial Fashion"]],
        }
    if field == "primary_color":
        return {
            "field": field,
            "prompt": "Màu chủ đạo của thương hiệu là màu nào? Bạn có thể nhập tên màu hoặc mã HEX.",
            "buttons": [["Theo logo", "Nhập mã màu"], ["Để AI đề xuất"]],
        }
    if field in {"mood", "photography_style"}:
        return {
            "field": field,
            "prompt": "Hình ảnh nên tạo cảm giác nào rõ nhất?",
            "buttons": [["Tin cậy", "Cao cấp", "Gần gũi"], ["Năng động", "Tinh tế"]],
        }
    if field.startswith("audience"):
        audience_choices = {
            "food": ["Gia đình trẻ", "Dân văn phòng", "Người yêu ẩm thực"],
            "technology": ["Doanh nghiệp", "Người trẻ yêu công nghệ", "Người dùng phổ thông"],
            "fashion": ["Gen Z", "Nữ công sở", "Khách hàng cao cấp"],
        }
        return {
            "field": field,
            "prompt": "Nhóm khách hàng quan trọng nhất của thương hiệu là ai?",
            "buttons": [audience_choices.get(industry, ["Gen Z", "Gia đình trẻ", "Khách hàng cao cấp"])],
        }
    if field == "channels":
        return {
            "field": field,
            "prompt": "Bạn thường đăng nội dung ở kênh nào?",
            "buttons": [["Facebook", "Instagram", "TikTok"], ["Website", "Zalo"]],
        }
    return {
        "field": "completed",
        "prompt": "Brand Profile đã đủ dữ liệu cốt lõi để tạo nội dung nhất quán.",
        "buttons": [["Tạo ảnh ngay", "Xem Brand Profile"]],
    }


def should_offer_onboarding(profile: dict[str, Any], user_text: str) -> bool:
    """Decide when to offer missing-profile help without prompting every turn."""
    if not get_profile_gaps(profile):
        return False
    value = _plain(user_text)
    if any(field in value for field in _BRAND_FIELDS):
        return True
    generations = int((profile.get("learningData") or {}).get("totalGenerations") or 0)
    return generations in {0, 3} or (generations > 0 and generations % 10 == 0)


def build_creative_suggestions(prompt: str, industry: str = "") -> list[str]:
    """Return three concise, request-specific directions suitable for buttons."""
    value = _plain(f"{prompt} {industry}")
    if any(term in value for term in ("tuyen dung", "tuyen vi tri", "tuyen", "viec lam", "ung vien", "recruit")):
        if any(term in value for term in ("cong nghe", "technology", "lap trinh", "developer")):
            return ["Công nghệ chuyên nghiệp", "Trẻ trung năng động", "Tối giản dễ đọc"]
        return ["Chuyên nghiệp tin cậy", "Con người gần gũi", "Tối giản dễ đọc"]
    if any(term in value for term in ("mon an", "nha hang", "food", "do uong", "ca phe")):
        return ["Cận cảnh ngon mắt", "Lifestyle bàn ăn", "Tối giản cao cấp"]
    if any(term in value for term in ("my pham", "beauty", "skincare", "serum")):
        return ["Sạch và khoa học", "Tinh tế cao cấp", "Mềm mại tự nhiên"]
    if any(term in value for term in ("thoi trang", "fashion", "quan ao")):
        return ["Editorial cao cấp", "Đường phố cá tính", "Tối giản hiện đại"]
    if any(term in value for term in ("bat dong san", "can ho", "real estate")):
        return ["Sang trọng tin cậy", "Thoáng sáng hiện đại", "Ấm áp đời sống"]
    return ["Tối giản cao cấp", "Lifestyle chân thực", "Năng động nổi bật"]


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def analyze_logo_bytes(data: bytes) -> dict[str, Any]:
    """Extract a useful palette and visual direction from a raster logo."""
    from PIL import Image

    with Image.open(BytesIO(data)) as source:
        image = source.convert("RGBA")
        image.thumbnail((256, 256))
        pixels = [
            (r, g, b)
            for r, g, b, alpha in image.get_flattened_data()
            if alpha >= 64 and not (r > 245 and g > 245 and b > 245)
        ]

    if not pixels:
        return {
            "colorPalette": {},
            "style": "minimalist",
            "moodKeywords": ["sạch sẽ", "tinh tế"],
            "photographyStyle": "clean commercial photography",
            "confidence": 0.4,
        }

    palette_image = Image.new("RGB", (len(pixels), 1))
    palette_image.putdata(pixels)
    quantized = palette_image.quantize(colors=5, method=Image.Quantize.MEDIANCUT)
    color_counts = sorted(quantized.getcolors() or [], reverse=True)
    raw_palette = quantized.getpalette() or []
    colors: list[tuple[int, int, int]] = []
    for _, index in color_counts:
        rgb = tuple(raw_palette[index * 3:index * 3 + 3])
        if len(rgb) == 3 and rgb not in colors:
            colors.append(rgb)

    colors = colors[:3]
    primary = colors[0]
    hsv = [colorsys.rgb_to_hsv(*(channel / 255 for channel in color)) for color in colors]
    avg_saturation = sum(item[1] for item in hsv) / len(hsv)
    avg_value = sum(item[2] for item in hsv) / len(hsv)
    dominant_hue = hsv[0][0]

    if avg_saturation >= 0.6 and len(colors) >= 2:
        style = "playful"
        moods = ["năng động", "nổi bật", "hiện đại"]
        photo = "bold dynamic commercial photography"
    elif avg_value < 0.42 and any(0.08 <= hue <= 0.18 for hue, _, _ in hsv):
        style = "luxury"
        moods = ["sang trọng", "cao cấp", "tinh tế"]
        photo = "premium editorial photography with dramatic controlled lighting"
    elif 0.22 <= dominant_hue <= 0.48:
        style = "natural"
        moods = ["tự nhiên", "gần gũi", "bền vững"]
        photo = "natural lifestyle photography with soft daylight"
    elif 0.5 <= dominant_hue <= 0.72 and avg_saturation >= 0.25:
        style = "corporate"
        moods = ["tin cậy", "chuyên nghiệp", "hiện đại"]
        photo = "clean professional commercial photography"
    else:
        style = "minimalist"
        moods = ["tối giản", "sạch sẽ", "tinh tế"]
        photo = "minimal clean commercial photography"

    palette = {"primary": _rgb_to_hex(primary)}
    if len(colors) > 1:
        palette["secondary"] = _rgb_to_hex(colors[1])
    if len(colors) > 2:
        palette["accent"] = _rgb_to_hex(colors[2])

    return {
        "colorPalette": palette,
        "style": style,
        "moodKeywords": moods,
        "photographyStyle": photo,
        "confidence": 0.9 if len(colors) >= 2 else 0.75,
    }


def apply_logo_identity(
    profile: dict[str, Any],
    analysis: dict[str, Any],
    *,
    logo_url: str,
) -> dict[str, Any]:
    """Apply logo-derived visual fields without resetting business or audience data."""
    brand = profile.setdefault("brand", {})
    brand["logoUrl"] = logo_url
    brand["styleConfirmed"] = False
    for key in ("style", "moodKeywords", "photographyStyle"):
        if analysis.get(key):
            brand[key] = analysis[key]
    if analysis.get("colorPalette"):
        brand["colorPalette"] = dict(analysis["colorPalette"])
    brand["identityInference"] = {
        "source": "logo",
        "confidence": analysis.get("confidence", 0.0),
    }
    return profile
