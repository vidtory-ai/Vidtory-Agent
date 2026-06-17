"""Render a resilient, channel-ready view of a customer Brand Profile."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any

from nanobot.utils.brand_intelligence import get_profile_gaps


@dataclass(frozen=True)
class BrandProfileView:
    text: str
    buttons: list[list[str]]
    show_logo_preview: bool


_GAP_LABELS = {
    "business_name": "tên thương hiệu",
    "industry": "lĩnh vực hoạt động",
    "business_description": "mô tả sản phẩm/dịch vụ",
    "logo": "logo",
    "brand_style": "phong cách",
    "primary_color": "màu chủ đạo",
    "mood": "cảm xúc thương hiệu",
    "photography_style": "phong cách hình ảnh",
    "audience_age": "độ tuổi khách hàng",
    "audience_segment": "phân khúc khách hàng",
    "channels": "kênh nội dung",
}

def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any, default: str = "Chưa có") -> str:
    if value is None:
        return default
    rendered = str(value).strip()
    return rendered or default


def _list_text(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value if str(item).strip()]
        return ", ".join(items) if items else "Chưa có"
    return _text(value)


def _palette_text(value: Any) -> str:
    if isinstance(value, dict):
        colors = [
            str(value.get(key) or "").strip()
            for key in ("primary", "secondary", "accent")
        ]
        colors = [color for color in colors if color]
        return " · ".join(colors) if colors else "Chưa có"
    return _text(value)


def render_brand_profile(profile: dict[str, Any]) -> BrandProfileView:
    """Return escaped HTML copy and actions for the Telegram `/brand` command."""
    business = _mapping(profile.get("business"))
    brand = _mapping(profile.get("brand"))
    audience = _mapping(profile.get("audience"))
    channels = _mapping(profile.get("contentChannels"))

    gaps = get_profile_gaps(profile)
    logo = _text(brand.get("logoUrl"), "")
    valid_logo = logo.startswith(("http://", "https://"))

    lines = [
        "<b>Brand Profile</b>",
        "",
        f"<b>Thương hiệu:</b> {escape(_text(business.get('name')))}",
        f"<b>Lĩnh vực:</b> {escape(_text(business.get('industry')))}",
        f"<b>Phong cách:</b> {escape(_text(brand.get('style')))}",
        f"<b>Cảm xúc:</b> {escape(_list_text(brand.get('moodKeywords')))}",
        f"<b>Bảng màu:</b> {escape(_palette_text(brand.get('colorPalette')))}",
        f"<b>Hình ảnh:</b> {escape(_text(brand.get('photographyStyle')))}",
        f"<b>Cần tránh:</b> {escape(_list_text(brand.get('avoidList')))}",
        "",
        (
            "<b>Khách hàng:</b> "
            f"{escape(_text(audience.get('ageRange')))} · "
            f"{escape(_text(audience.get('segment')))}"
        ),
        f"<b>Kênh:</b> {escape(_list_text(channels.get('primary')))}",
    ]

    if valid_logo:
        lines.append(f'<b>Logo:</b> <a href="{escape(logo, quote=True)}">Xem logo</a>')
    elif logo:
        lines.append("<b>Logo:</b> Đường dẫn hiện tại không hợp lệ")
    else:
        lines.append("<b>Logo:</b> Chưa có")

    if gaps:
        gap_labels = [_GAP_LABELS.get(gap, gap) for gap in gaps[:4]]
        lines.extend(
            [
                "",
                f"<b>Có thể bổ sung:</b> {escape(', '.join(gap_labels))}.",
                "Bạn có thể chọn nút bên dưới hoặc nhập nội dung riêng.",
            ]
        )
        buttons = [
            ["Bổ sung profile", "Để sau"],
            ["Thay logo", "Tạo thiết kế"],
        ]
    else:
        lines.extend(["", "Profile đã đủ dữ liệu cốt lõi và đang được áp dụng tự động."])
        buttons = [
            ["Đổi phong cách", "Thay logo"],
            ["Tạo thiết kế"],
        ]

    return BrandProfileView(
        text="\n".join(lines),
        buttons=buttons,
        show_logo_preview=valid_logo,
    )
