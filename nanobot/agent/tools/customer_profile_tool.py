"""Customer profile update tool — lets the agent persist brand & business info to the DB."""

from __future__ import annotations

import re
from typing import Any

from nanobot.agent.tools.base import Tool, tool_parameters
from nanobot.agent.tools.schema import (
    ArraySchema,
    BooleanSchema,
    StringSchema,
    tool_parameters_schema,
)
from nanobot.utils.context_vars import telegram_customer_profile


# ---------------------------------------------------------------------------
# Brand style normalization
# ---------------------------------------------------------------------------

# Known preset values supported by the image generation pipeline.
_BRAND_STYLE_PRESETS = frozenset({
    "luxury", "playful", "corporate", "natural", "minimalist",
})

# Mapping: Vietnamese / informal phrases → canonical preset
_BRAND_STYLE_ALIAS: dict[str, str] = {
    # luxury
    "sang trọng": "luxury", "cao cấp": "luxury", "hạng sang": "luxury",
    "premium": "luxury", "high-end": "luxury", "upscale": "luxury",
    "xa xỉ": "luxury", "elite": "luxury",
    # playful
    "vui tươi": "playful", "trẻ trung": "playful", "năng động": "playful",
    "funny": "playful", "fun": "playful", "creative": "playful",
    "gen z": "playful", "trendy": "playful", "colorful": "playful",
    # corporate
    "chuyên nghiệp": "corporate", "doanh nghiệp": "corporate",
    "business": "corporate", "formal": "corporate", "enterprise": "corporate",
    "b2b": "corporate",
    # natural
    "thiên nhiên": "natural", "organic": "natural", "eco": "natural",
    "green": "natural", "sustainable": "natural", "xanh": "natural",
    "tự nhiên": "natural", "handmade": "natural",
    # minimalist
    "tối giản": "minimalist", "sạch sẽ": "minimalist", "clean": "minimalist",
    "simple": "minimalist", "đơn giản": "minimalist", "modern": "minimalist",
    "contemporary": "minimalist", "hiện đại": "minimalist",
}

# Partial keyword → preset (applied only if no alias match)
_BRAND_STYLE_KEYWORD: list[tuple[str, str]] = [
    ("luxur", "luxury"), ("premium", "luxury"), ("high end", "luxury"),
    ("play", "playful"), ("fun", "playful"), ("youth", "playful"),
    ("corp", "corporate"), ("business", "corporate"), ("formal", "corporate"),
    ("natur", "natural"), ("organic", "natural"), ("eco", "natural"),
    ("minim", "minimalist"), ("clean", "minimalist"), ("simple", "minimalist"),
]


def _normalize_brand_style(value: str) -> str:
    """Normalize a free-text brand style value to a canonical preset when possible.

    - If the value exactly matches a preset → return it.
    - If there is an alias match → return the preset.
    - If a keyword matches → return the preset.
    - Otherwise → store the raw value as-is (future-proof for custom styles).
    """
    v = value.strip().lower()
    if v in _BRAND_STYLE_PRESETS:
        return v
    if v in _BRAND_STYLE_ALIAS:
        return _BRAND_STYLE_ALIAS[v]
    for kw, preset in _BRAND_STYLE_KEYWORD:
        if kw in v:
            return preset
    # Store as-is — useful for custom styles like "vintage y2k", "brutalist", etc.
    return value.strip()


# ---------------------------------------------------------------------------
# Color name → HEX normalization
# ---------------------------------------------------------------------------

# Common color names → approximate HEX codes
# Covers frequent Vietnamese and English color descriptions.
_COLOR_NAME_HEX: dict[str, str] = {
    # Basic
    "white": "#FFFFFF", "trắng": "#FFFFFF",
    "black": "#000000", "đen": "#000000",
    "red": "#E53935", "đỏ": "#E53935",
    "blue": "#1E88E5", "xanh dương": "#1E88E5", "xanh lam": "#1E88E5",
    "green": "#43A047", "xanh lá": "#43A047", "xanh": "#43A047",
    "yellow": "#FDD835", "vàng": "#FDD835",
    "orange": "#FB8C00", "cam": "#FB8C00",
    "purple": "#8E24AA", "tím": "#8E24AA",
    "pink": "#E91E8C", "hồng": "#E91E8C",
    "brown": "#795548", "nâu": "#795548",
    "gray": "#757575", "grey": "#757575", "xám": "#757575",
    "gold": "#FFC107", "vàng gold": "#FFC107", "vàng đồng": "#B8860B",
    "silver": "#9E9E9E", "bạc": "#C0C0C0",
    "navy": "#1A237E", "navy blue": "#1A237E", "xanh navy": "#1A237E",
    # Pastel variants
    "pastel pink": "#FFB6C1", "hồng pastel": "#FFB6C1",
    "pastel blue": "#AED6F1", "xanh pastel": "#AED6F1",
    "pastel green": "#A9DFBF", "xanh lá pastel": "#A9DFBF",
    "pastel purple": "#C9A8E0", "tím pastel": "#C9A8E0",
    "pastel yellow": "#FFF9A0", "vàng pastel": "#FFF9A0",
    "pastel orange": "#FFDAB9", "cam pastel": "#FFDAB9",
    # Other popular brand colors
    "beige": "#F5F0E8", "kem": "#FFFDD0", "ivory": "#FFFFF0",
    "teal": "#00897B", "xanh ngọc": "#00897B",
    "coral": "#FF6B6B", "hồng san hô": "#FF7F7F",
    "mint": "#98FF98", "xanh mint": "#98FF98",
    "lavender": "#E6E6FA", "tím lavender": "#E6E6FA",
    "maroon": "#800000", "đỏ đậm": "#8B0000",
    "rose gold": "#B76E79", "vàng hồng": "#B76E79",
    "champagne": "#F7E7CE", "đồng": "#CD7F32",
}


def _normalize_color(value: str) -> str:
    """Normalize a color value to HEX format if possible.

    - If already a valid HEX code → return normalized (#RRGGBB uppercase).
    - If a known color name / Vietnamese color → return mapped HEX.
    - Otherwise → return the raw value (LLM may have generated a reasonable HEX).
    """
    v = value.strip()

    # Already a HEX code
    if re.match(r"^#?[0-9A-Fa-f]{3}$", v):
        # Expand 3-char HEX to 6-char
        h = v.lstrip("#")
        return "#" + "".join(c * 2 for c in h).upper()
    if re.match(r"^#?[0-9A-Fa-f]{6}$", v):
        return "#" + v.lstrip("#").upper()

    # Known color name lookup (case-insensitive)
    lower = v.lower()
    if lower in _COLOR_NAME_HEX:
        return _COLOR_NAME_HEX[lower]

    # Partial match: if value contains a known color name
    for name, hex_code in _COLOR_NAME_HEX.items():
        if name in lower and len(name) > 3:
            return hex_code

    # Unknown — return as-is so LLM can still store descriptive color names
    return v


# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------

@tool_parameters(
    tool_parameters_schema(
        business_name=StringSchema(
            "Brand/company name, e.g. 'PTIT', 'Nike', 'Coffee House'.",
        ),
        industry=StringSchema(
            "Industry category. One of: fashion, food-beverage, beauty, tech, "
            "real-estate, education, services, other.",
        ),
        business_description=StringSchema(
            "Short description of the business (1-2 sentences).",
        ),
        brand_style=StringSchema(
            "Visual style. Preferred values: luxury, playful, corporate, natural, minimalist. "
            "Also accepts free-text like 'vintage y2k', 'brutalist', 'sang trọng', 'tối giản'.",
        ),
        mood_keywords=ArraySchema(
            StringSchema("A mood/aesthetic keyword, e.g. 'hiện đại', 'sang trọng', 'năng động'."),
            description="List of mood/aesthetic keywords that describe the brand feeling.",
        ),
        color_primary=StringSchema(
            "Primary brand color. Accepts HEX (#1A2B3C) or color names ('tím pastel', 'navy blue').",
        ),
        color_secondary=StringSchema(
            "Secondary brand color. Accepts HEX or color names. Leave empty if unknown.",
        ),
        color_accent=StringSchema(
            "Accent/highlight brand color. Accepts HEX or color names. Leave empty if unknown.",
        ),
        photography_style=StringSchema(
            "Photography/visual style description, e.g. 'professional, clean, modern tech aesthetic'.",
        ),
        avoid_list=ArraySchema(
            StringSchema("A visual style or element to avoid, e.g. 'cartoon', 'low quality'."),
            description="List of visual styles or elements the brand wants to avoid.",
        ),
        target_gender=StringSchema(
            "Target audience gender: 'female', 'male', or 'all'.",
        ),
        age_range=StringSchema(
            "Target audience age range: '18-25', '25-35', '35-50', or '50+'.",
        ),
        segment=StringSchema(
            "Market segment: 'mass', 'mid', or 'premium'.",
        ),
        channels=ArraySchema(
            StringSchema("Channel name, e.g. 'instagram', 'facebook', 'tiktok', 'website', 'zalo'."),
            description="Primary content distribution channels.",
        ),
        logo_url=StringSchema(
            "URL or local path of the brand logo image. "
            "Accepts: CDN URL (https://...), local file path, or Telegram CDN URL. "
            "Leave empty if no logo provided.",
        ),
        brand_guidelines=StringSchema(
            "Brand guidelines text extracted from uploaded documents (PDF, DOCX, etc.). "
            "Store key design rules, typography guidelines, tone of voice rules, "
            "do/don't lists, and other brand standards. Max 2000 chars — "
            "summarize if the original is longer.",
        ),
        onboarding_complete=BooleanSchema(
            description=(
                "Set to true when the user has provided enough brand information "
                "to consider onboarding complete. Default: false (partial update)."
            ),
            default=False,
        ),
        required=[],
    )
)
class UpdateCustomerProfileTool(Tool):
    """Update and persist customer brand profile to the database.

    Call this tool whenever the user provides brand information such as:
    - Business name, industry, or description
    - Visual style, mood keywords, or color palette (primary, secondary, accent)
    - Target audience (gender, age range, market segment)
    - Content channels (Instagram, TikTok, Facebook, etc.)
    - Items to avoid in visuals
    - Brand logo URL or file path

    ALWAYS call this tool after collecting brand info — never just acknowledge without saving.
    Partial updates are supported: only provide the fields you have new information for.

    COLOR NORMALIZATION: You may pass color names in Vietnamese or English
    ('tím pastel', 'navy blue', 'vàng gold') — they will be automatically
    converted to HEX codes.

    BRAND STYLE: Free-text styles like 'vintage y2k', 'sang trọng', 'tối giản'
    are accepted and auto-mapped to presets where possible.
    """

    @classmethod
    def create(cls, ctx: Any) -> "UpdateCustomerProfileTool":
        return cls()

    @property
    def name(self) -> str:
        return "update_customer_profile"

    @property
    def description(self) -> str:
        return (
            "Save or update the customer's brand profile in the database. "
            "MUST be called whenever the user shares brand information "
            "(business name, industry, style, colors, audience, channels, logo). "
            "Supports partial updates — only include fields that have new information. "
            "Accepts color names in Vietnamese/English — auto-converted to HEX. "
            "Accepts free-text brand styles — auto-normalized to presets when possible. "
            "After saving, the profile will automatically be applied to all future image generations."
        )

    async def execute(
        self,
        business_name: str | None = None,
        industry: str | None = None,
        business_description: str | None = None,
        brand_style: str | None = None,
        mood_keywords: list[str] | None = None,
        color_primary: str | None = None,
        color_secondary: str | None = None,
        color_accent: str | None = None,
        photography_style: str | None = None,
        avoid_list: list[str] | None = None,
        target_gender: str | None = None,
        age_range: str | None = None,
        segment: str | None = None,
        channels: list[str] | None = None,
        logo_url: str | None = None,
        brand_guidelines: str | None = None,
        onboarding_complete: bool = False,
        **kwargs: Any,
    ) -> str:
        # Get the user_id from the current context
        profile = telegram_customer_profile.get()
        if not profile:
            return "Error: No customer context found. User must be in a Telegram session."

        user_id = str(
            profile.get("telegramUserId")
            or profile.get("telegram_user_id")
            or ""
        ).strip()
        if not user_id:
            return "Error: Could not determine user ID from customer context."

        try:
            from nanobot.utils.customer_profile import load_profile, save_profile

            # Load fresh profile to avoid stale overwrites
            current = load_profile(user_id)
            if not current:
                return "Error: No profile found for this user. Profile must be initialized first."

            changed_fields: list[str] = []

            # ── Business section ──────────────────────────────────────────
            if business_name is not None and business_name.strip():
                current.setdefault("business", {})["name"] = business_name.strip()
                changed_fields.append("business_name")

            if industry is not None and industry.strip():
                current.setdefault("business", {})["industry"] = industry.strip().lower()
                changed_fields.append("industry")

            if business_description is not None and business_description.strip():
                current.setdefault("business", {})["description"] = business_description.strip()
                changed_fields.append("description")

            # ── Brand section ─────────────────────────────────────────────
            brand = current.setdefault("brand", {})

            if brand_style is not None and brand_style.strip():
                normalized = _normalize_brand_style(brand_style)
                brand["style"] = normalized
                changed_fields.append(f"style({normalized})")

            if mood_keywords is not None and len(mood_keywords) > 0:
                brand["moodKeywords"] = [kw.strip() for kw in mood_keywords if kw.strip()]
                changed_fields.append("moodKeywords")

            if color_primary is not None and color_primary.strip():
                hex_val = _normalize_color(color_primary)
                brand.setdefault("colorPalette", {})["primary"] = hex_val
                changed_fields.append(f"color_primary({hex_val})")

            if color_secondary is not None and color_secondary.strip():
                hex_val = _normalize_color(color_secondary)
                brand.setdefault("colorPalette", {})["secondary"] = hex_val
                changed_fields.append(f"color_secondary({hex_val})")

            if color_accent is not None and color_accent.strip():
                hex_val = _normalize_color(color_accent)
                brand.setdefault("colorPalette", {})["accent"] = hex_val
                changed_fields.append(f"color_accent({hex_val})")

            if photography_style is not None and photography_style.strip():
                brand["photographyStyle"] = photography_style.strip()
                changed_fields.append("photography_style")

            if avoid_list is not None and len(avoid_list) > 0:
                brand["avoidList"] = [item.strip() for item in avoid_list if item.strip()]
                changed_fields.append("avoidList")

            if logo_url is not None and logo_url.strip():
                brand["logoUrl"] = logo_url.strip()
                changed_fields.append("logo_url")
                # Also sync to the DB indexed column
                try:
                    from nanobot.db.customer_db import get_db
                    get_db().set_logo_url(user_id, logo_url.strip())
                except Exception:
                    pass  # Non-fatal — JSON blob is the source of truth

            if brand_guidelines is not None and brand_guidelines.strip():
                # Truncate to 2000 chars to keep profile size reasonable
                guidelines_text = brand_guidelines.strip()[:2000]
                brand["guidelines"] = guidelines_text
                changed_fields.append("brand_guidelines")

            # ── Audience section ──────────────────────────────────────────
            audience = current.setdefault("audience", {})

            if target_gender is not None and target_gender.strip():
                audience["gender"] = target_gender.strip().lower()
                changed_fields.append("target_gender")

            if age_range is not None and age_range.strip():
                audience["ageRange"] = age_range.strip()
                changed_fields.append("age_range")

            if segment is not None and segment.strip():
                audience["segment"] = segment.strip().lower()
                changed_fields.append("segment")

            # ── Channels section ──────────────────────────────────────────
            if channels is not None and len(channels) > 0:
                clean_channels = [c.strip().lower() for c in channels if c.strip()]
                current.setdefault("contentChannels", {})["primary"] = clean_channels
                # Auto-set common format defaults
                fmt = current["contentChannels"].setdefault("defaultFormats", {})
                if "instagram" in clean_channels and "instagram_feed" not in fmt:
                    fmt["instagram_feed"] = {"aspectRatio": "1:1"}
                    fmt["instagram_story"] = {"aspectRatio": "9:16"}
                if "tiktok" in clean_channels and "tiktok" not in fmt:
                    fmt["tiktok"] = {"aspectRatio": "9:16"}
                if "youtube" in clean_channels and "youtube" not in fmt:
                    fmt["youtube"] = {"aspectRatio": "16:9"}
                if "website" in clean_channels and "website" not in fmt:
                    fmt["website"] = {"aspectRatio": "16:9"}
                if "facebook" in clean_channels and "facebook" not in fmt:
                    fmt["facebook"] = {"aspectRatio": "4:3"}
                if "zalo" in clean_channels and "zalo" not in fmt:
                    fmt["zalo"] = {"aspectRatio": "1:1"}
                changed_fields.append("channels")

            if not changed_fields:
                return "No fields provided to update. Please specify at least one brand field."

            # ── Onboarding status ─────────────────────────────────────────
            onboarding = current.setdefault("onboarding", {})
            if onboarding_complete:
                onboarding["status"] = "completed"
                onboarding["completedAt"] = _utc_now()
                onboarding["currentStep"] = "completed"
            elif onboarding.get("status") in ("none", "minimal", ""):
                onboarding["status"] = "minimal"

            # Persist to DB
            ok = save_profile(user_id, current)
            if not ok:
                return "Error: Failed to save profile to database. Please try again."

            # Also update the in-memory ContextVar so the current turn uses fresh data
            telegram_customer_profile.set(current)

            # ── Dual-write to layered brand_memory ────────────────────────
            # Core/Style entries are written with force=True because they come
            # from explicit client input (onboarding interview or direct update).
            try:
                from nanobot.db.customer_db import get_db
                db = get_db()
                source = f"profile_update:{_utc_now()}"

                # Core layer: colors, logo, typography
                if color_primary and color_primary.strip():
                    db.set_memory(user_id, layer="core", key="color_primary",
                                  value=_normalize_color(color_primary), source=source, force=True)
                if color_secondary and color_secondary.strip():
                    db.set_memory(user_id, layer="core", key="color_secondary",
                                  value=_normalize_color(color_secondary), source=source, force=True)
                if color_accent and color_accent.strip():
                    db.set_memory(user_id, layer="core", key="color_accent",
                                  value=_normalize_color(color_accent), source=source, force=True)
                if logo_url and logo_url.strip():
                    db.set_memory(user_id, layer="core", key="logo",
                                  value=logo_url.strip(), source=source, force=True)

                # Style layer: aesthetic, mood, photography
                if brand_style and brand_style.strip():
                    db.set_memory(user_id, layer="style", key="aesthetic",
                                  value=_normalize_brand_style(brand_style), source=source, force=True)
                if photography_style and photography_style.strip():
                    db.set_memory(user_id, layer="style", key="photography_style",
                                  value=photography_style.strip(), source=source, force=True)
                if mood_keywords:
                    mood_str = ", ".join(kw.strip() for kw in mood_keywords if kw.strip())
                    if mood_str:
                        db.set_memory(user_id, layer="style", key="mood_reference",
                                      value=mood_str, source=source, force=True)
                if avoid_list:
                    for i, avoid_item in enumerate(avoid_list[:5]):
                        if avoid_item.strip():
                            db.set_memory(user_id, layer="style", key=f"avoid_{i}",
                                          value=avoid_item.strip(), source=source, force=True)
                if brand_guidelines and brand_guidelines.strip():
                    # Store guidelines summary in style layer for prompt enrichment
                    db.set_memory(user_id, layer="style", key="brand_guidelines",
                                  value=brand_guidelines.strip()[:500], source=source, force=True)
            except Exception:
                pass  # Non-fatal — profile_json is the primary source of truth

            # ── Lifecycle stage advancement ────────────────────────────────
            if onboarding_complete:
                try:
                    from nanobot.utils.quality_metrics import set_lifecycle_stage
                    set_lifecycle_stage(user_id, "probation")
                except Exception:
                    pass

            status_tag = " ✅ Onboarding hoàn tất!" if onboarding_complete else ""
            return (
                f"✅ Brand profile updated successfully.{status_tag} "
                f"Fields saved: {', '.join(changed_fields)}. "
                f"Profile will now be applied to all image generations."
            )

        except Exception as exc:
            return f"Error updating customer profile: {exc}"


def _utc_now() -> str:
    """Return current UTC time as ISO 8601 string."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
