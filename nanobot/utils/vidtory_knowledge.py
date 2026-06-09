"""Vidtory Knowledge — global creative prompt library and professional guidelines.

This module is the single source of truth for Vidtory's creative standards.
It provides two public interfaces:

1. ``get_system_knowledge_block()`` — injects professional guidelines into the
   LLM's system prompt every turn, giving the agent deep creative expertise.

2. ``build_professional_prompt_suffix(prompt, content_type)`` — enhances any
   image generation prompt with world-class technical specifications selected
   by content category.

The content layer lives in ``_PHOTOGRAPHY_STYLES``, ``_PROMPT_LIBRARY``, and
``_PLATFORM_SPECS`` below. Each section is a plain dict so non-engineers can
extend or override entries without touching logic.

Customization:
    Override at runtime by loading an external YAML/JSON config and calling
    ``override_library(data)`` before the agent starts.
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Content Layer — editable without touching logic
# ---------------------------------------------------------------------------

# ── Photography style presets ────────────────────────────────────────────────
_PHOTOGRAPHY_STYLES: dict[str, str] = {
    # Product
    "product_hero": (
        "product hero shot, 8K commercial photography, pure white or gradient studio backdrop, "
        "three-point studio lighting (key light + fill light + rim light), specular highlights on surface, "
        "ultra-sharp focus with shallow depth of field, color calibrated, brand-ready"
    ),
    "product_lifestyle": (
        "lifestyle product photography, natural environment context, soft ambient window light, "
        "warm color palette, shallow depth of field f/2.8, editorial quality, aspirational mood"
    ),
    "product_packshot": (
        "professional packshot, perfectly centered, pure white background, "
        "shadow on base, clean shadows, retouched, 100% sharp, e-commerce ready"
    ),
    # Fashion
    "fashion_editorial": (
        "high-fashion editorial photography, Vogue-quality, dramatic directional lighting, "
        "textured backdrop, cinematic color grade, sharp couture detail, luxury aesthetic"
    ),
    "fashion_lookbook": (
        "fashion lookbook photography, clean minimal background, balanced studio lighting, "
        "full or three-quarter body frame, professional model pose, commercial catalog quality"
    ),
    "fashion_street": (
        "street fashion photography, urban environment, golden hour backlight, "
        "bokeh background, candid energy, high contrast editing, Gen-Z aesthetic"
    ),
    # Food & Beverage
    "food_hero": (
        "food hero photography, overhead flat-lay or 45° angle, steam wisps visible, "
        "fresh glistening textures, complementary props, natural diffused window light, "
        "vibrant saturated colors, professional food stylist finish"
    ),
    "food_beverage": (
        "beverage photography, condensation droplets on glass, ice cubes with clarity, "
        "backlit translucent liquid, dark moody background, macro detail, premium lifestyle"
    ),
    "food_restaurant": (
        "restaurant plating photography, chef's table presentation, warm candlelight tone, "
        "bokeh ambiance, fine dining quality, editorial food magazine standard"
    ),
    # Cosmetics & Beauty
    "beauty_product": (
        "beauty product photography, marble or luxury texture surface, macro detail of texture, "
        "pastel or monochrome color scheme, soft diffused light, premium glossy finish, "
        "Sephora/LVMH catalog standard"
    ),
    "beauty_portrait": (
        "beauty portrait photography, catchlights in eyes, flawless skin retouching, "
        "butterfly lighting or Rembrandt lighting, clean neutral background, "
        "high-end retouching, Harper's Bazaar quality"
    ),
    # Real Estate & Architecture
    "interior_design": (
        "interior architecture photography, wide angle 16-24mm lens perspective, "
        "natural window light balanced with ambient fill, straight verticals corrected, "
        "rich warm tones, Architectural Digest quality"
    ),
    "real_estate": (
        "real estate photography, twilight exterior, HDR balanced exposure, "
        "warm interior lights glowing, blue-hour sky, professional drone or ground angle"
    ),
    # Lifestyle & Portrait
    "portrait_professional": (
        "professional business portrait, clean neutral background, soft box even lighting, "
        "sharp eyes with catchlights, confident expression, LinkedIn/executive quality"
    ),
    "lifestyle_authentic": (
        "lifestyle photography, authentic candid moment, golden hour natural light, "
        "shallow depth of field, warm film-like color grade, emotionally resonant"
    ),
    # Technology & SaaS
    "tech_product": (
        "technology product photography, dark gradient background, neon accent lighting, "
        "reflection on surface, futuristic atmosphere, Verge/TechCrunch editorial quality"
    ),
}

# ── Platform-specific output specifications ──────────────────────────────────
_PLATFORM_SPECS: dict[str, dict[str, str]] = {
    "instagram_feed": {
        "aspect_ratio": "1:1",
        "resolution_note": "1080×1080px minimum, vibrant colors pop on mobile",
        "style_note": "clean aesthetic, on-brand color palette, strong focal point",
    },
    "instagram_story": {
        "aspect_ratio": "9:16",
        "resolution_note": "1080×1920px, bold typography-friendly top/bottom zones",
        "style_note": "high contrast, emotionally punchy, mobile-first composition",
    },
    "instagram_reels_cover": {
        "aspect_ratio": "9:16",
        "resolution_note": "1080×1920px, safe zone center for subject",
        "style_note": "eye-catching thumbnail, bright and dynamic",
    },
    "youtube_thumbnail": {
        "aspect_ratio": "16:9",
        "resolution_note": "1280×720px minimum, readable at small size",
        "style_note": "bold contrast, face close-up or dramatic scene, 3-word rule",
    },
    "tiktok_video_cover": {
        "aspect_ratio": "9:16",
        "resolution_note": "1080×1920px, Gen-Z aesthetic, trend-aware",
        "style_note": "energetic, color pop, bold statement",
    },
    "facebook_post": {
        "aspect_ratio": "4:3",
        "resolution_note": "1200×900px, works on both mobile and desktop feed",
        "style_note": "warm engaging tones, community feel",
    },
    "website_hero": {
        "aspect_ratio": "16:9",
        "resolution_note": "2560×1440px, full-bleed capable",
        "style_note": "panoramic composition, text overlay zones on left or center",
    },
    "linkedin_post": {
        "aspect_ratio": "4:3",
        "resolution_note": "1200×900px, professional tone",
        "style_note": "clean corporate aesthetic, brand colors prominent",
    },
    "print_a4": {
        "aspect_ratio": "3:4",
        "resolution_note": "300DPI minimum, CMYK color space",
        "style_note": "high detail, no heavy digital effects that degrade in print",
    },
}

# ── Content-type → photography style mapping ────────────────────────────────
_CONTENT_TYPE_TO_STYLE: dict[str, str] = {
    "product": "product_hero",
    "fashion": "fashion_editorial",
    "food": "food_hero",
    "beverage": "food_beverage",
    "drink": "food_beverage",
    "cosmetic": "beauty_product",
    "beauty": "beauty_product",
    "portrait": "portrait_professional",
    "lifestyle": "lifestyle_authentic",
    "interior": "interior_design",
    "real_estate": "real_estate",
    "tech": "tech_product",
    "lookbook": "fashion_lookbook",
    "packshot": "product_packshot",
}

# ── Universal quality suffixes always appended ───────────────────────────────
_UNIVERSAL_QUALITY_SUFFIX = (
    "sharp focus, high resolution, professional grade, no watermark, no text overlay, "
    "photorealistic, commercial quality"
)

# ── Content type keyword detection ───────────────────────────────────────────
_CONTENT_TYPE_KEYWORDS: dict[str, list[str]] = {
    "food": ["food", "dish", "meal", "cuisine", "plate", "restaurant", "dessert",
             "ăn", "món", "thức ăn", "bánh", "cơm", "phở"],
    "beverage": ["drink", "coffee", "tea", "juice", "cocktail", "wine", "beer",
                 "boba", "smoothie", "cà phê", "nước", "đồ uống"],
    "cosmetic": ["cosmetic", "makeup", "skincare", "cream", "serum", "lipstick",
                 "perfume", "mỹ phẩm", "kem", "son"],
    "fashion": ["fashion", "clothing", "outfit", "dress", "shoes", "bag", "luxury",
                "quần", "áo", "giày", "túi", "thời trang"],
    "portrait": ["portrait", "person", "model", "headshot", "người", "chân dung"],
    "interior": ["interior", "room", "living room", "office", "phòng", "nội thất"],
    "tech": ["phone", "laptop", "device", "gadget", "tech", "electronic",
             "điện thoại", "máy tính"],
    "product": ["product", "item", "object", "sản phẩm"],
}


# ---------------------------------------------------------------------------
# Override mechanism (for runtime customization)
# ---------------------------------------------------------------------------

_overrides: dict[str, Any] = {}


def override_library(data: dict[str, Any]) -> None:
    """Override any part of the knowledge library at runtime.

    Args:
        data: Dict with optional keys: ``photography_styles``, ``platform_specs``,
              ``content_type_keywords``, ``universal_quality_suffix``.

    Example::

        vidtory_knowledge.override_library({
            "photography_styles": {
                "my_custom_style": "..."
            }
        })
    """
    _overrides.update(data)


def _get_styles() -> dict[str, str]:
    return {**_PHOTOGRAPHY_STYLES, **_overrides.get("photography_styles", {})}


def _get_platform_specs() -> dict[str, dict[str, str]]:
    return {**_PLATFORM_SPECS, **_overrides.get("platform_specs", {})}


def _get_content_keywords() -> dict[str, list[str]]:
    return {**_CONTENT_TYPE_KEYWORDS, **_overrides.get("content_type_keywords", {})}


def _get_universal_suffix() -> str:
    return _overrides.get("universal_quality_suffix", _UNIVERSAL_QUALITY_SUFFIX)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_content_type(prompt: str) -> str | None:
    """Detect content type from prompt text using keyword matching.

    Returns the content type key (e.g. ``'food'``, ``'fashion'``) or ``None``
    if no match is found.
    """
    prompt_lower = prompt.lower()
    for content_type, keywords in _get_content_keywords().items():
        if any(kw in prompt_lower for kw in keywords):
            return content_type
    return None


def get_style_for_content(content_type: str | None) -> str | None:
    """Return the photography style preset string for a content type.

    Returns ``None`` if no mapping exists for ``content_type``.
    """
    if not content_type:
        return None
    style_key = _CONTENT_TYPE_TO_STYLE.get(content_type)
    if not style_key:
        return None
    return _get_styles().get(style_key)


def build_professional_prompt_suffix(
    prompt: str,
    content_type: str | None = None,
    platform: str | None = None,
) -> str:
    """Build a professional suffix to append to image generation prompts.

    This is the core function that elevates amateur prompts to commercial grade.

    Args:
        prompt: The original prompt text (used for auto-detection if
                ``content_type`` is not supplied).
        content_type: Optional explicit content type key (e.g. ``'food'``).
                      Auto-detected from ``prompt`` if ``None``.
        platform: Optional platform key (e.g. ``'instagram_feed'``).
                  Adds platform-specific composition hints when supplied.

    Returns:
        A suffix string ready to be appended to the prompt with ``", "``.
        Empty string if no enhancement is applicable.
    """
    detected = content_type or detect_content_type(prompt)
    style = get_style_for_content(detected)

    parts: list[str] = []

    if style:
        parts.append(style)

    if platform:
        specs = _get_platform_specs().get(platform, {})
        style_note = specs.get("style_note")
        if style_note:
            parts.append(style_note)

    parts.append(_get_universal_suffix())

    return ", ".join(p for p in parts if p)


def get_platform_aspect_ratio(platform: str) -> str | None:
    """Return the recommended aspect ratio for a given platform key.

    Args:
        platform: Platform key (e.g. ``'instagram_story'``, ``'youtube_thumbnail'``).

    Returns:
        Aspect ratio string like ``'9:16'`` or ``None`` if unknown.
    """
    specs = _get_platform_specs().get(platform, {})
    return specs.get("aspect_ratio")


def list_available_styles() -> list[str]:
    """Return all registered photography style keys."""
    return list(_get_styles().keys())


def list_available_platforms() -> list[str]:
    """Return all registered platform keys."""
    return list(_get_platform_specs().keys())


def get_system_knowledge_block() -> str:
    """Return the Vidtory creative knowledge block for injection into the LLM system prompt.

    This block gives the agent deep expertise in creative direction, photography,
    and content production — injected once per session via the SOUL.md / system prompt.
    """
    styles_summary = "\n".join(
        f"- **{k}**: {v[:120]}..."
        for k, v in list(_get_styles().items())[:6]
    )
    platforms_summary = ", ".join(list(_get_platform_specs().keys()))

    return f"""## Vidtory Creative Knowledge

### Photography Style Library
Available style presets for professional image generation:
{styles_summary}
(+ {len(_get_styles()) - 6} more styles available)

### Supported Platforms
{platforms_summary}

### Professional Prompt Principles
1. **Subject** — Clearly describe the hero element (product/person/scene)
2. **Style** — Apply appropriate photography style from the library
3. **Lighting** — Specify light source, direction, and quality
4. **Composition** — Describe framing, angle, focal point
5. **Mood** — Color palette, atmosphere, emotional register
6. **Technical** — Resolution, sharpness, post-processing

### Auto-Enhancement
The `generate_image` tool automatically:
- Detects content type from the prompt
- Applies matching professional photography style
- Appends universal quality suffixes
- Selects customer's preferred aspect ratio
- Incorporates brand guidelines from customer profile
"""
