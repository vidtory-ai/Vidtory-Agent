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
    # Jewelry & Watches
    "jewelry": (
        "luxury jewelry photography, macro detail on gemstones, reflective dark surface or "
        "white marble, single soft key light with subtle rim, specular highlights on metal, "
        "Cartier/Tiffany catalog standard, ultra-sharp 8K"
    ),
    # Candle & Home Decor
    "candle_decor": (
        "candle and home decor photography, warm candlelight glow with soft bokeh, "
        "rustic or minimal props, cozy lifestyle mood, warm amber tones, editorial quality"
    ),
    # Kids & Baby
    "kids_product": (
        "children's product photography, bright cheerful colors, playful props and soft background, "
        "natural soft window light, clean safe aesthetic, warm inviting mood"
    ),
    # Fitness & Sport
    "fitness": (
        "fitness product photography, clean white or gym background, dramatic side lighting, "
        "muscular confidence aesthetic, bold saturated colors, health editorial quality"
    ),
    # Pet
    "pet": (
        "pet photography, soft natural window light, adorable candid expression, "
        "clean minimal background, warm and playful mood, sharp eye focus"
    ),
    # Wildlife & Nature
    "wildlife_nature": (
        "professional wildlife photography, shot on telephoto lens, soft natural lighting, "
        "natural environment context, ultra-sharp details, shallow depth of field, National Geographic quality"
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
    # New categories
    "jewelry": "jewelry",
    "candle": "candle_decor",
    "kids": "kids_product",
    "fitness": "fitness",
    "pet": "pet",
    "wildlife": "wildlife_nature",
}

# ── Universal quality suffixes always appended ───────────────────────────────
_UNIVERSAL_QUALITY_SUFFIX = (
    "editorial photography, professional camera shot, sharp focus, natural textures, "
    "balanced exposure, clean composition, no watermark, no text overlay"
)

_UNIVERSAL_QUALITY_SUFFIX_VI = (
    "nhiếp ảnh thương mại chuyên nghiệp, chụp bằng máy ảnh cao cấp, nét sắc, kết cấu tự nhiên, "
    "phơi sáng cân bằng, bố cục sạch, không có watermark, không có chữ ngẫu nhiên"
)

# ── Vietnamese photography style presets ─────────────────────────────────────
_PHOTOGRAPHY_STYLES_VI: dict[str, str] = {
    # Sản phẩm
    "product_hero": (
        "ảnh hero sản phẩm, chất lượng thương mại 8K, nền studio trắng hoặc chuyển màu, "
        "ánh sáng studio ba điểm (chính + phụ + viền), phản xạ trên bề mặt, "
        "nét sắc siêu rõ với độ sâu trường ảnh nông, màu sắc chuẩn, sẵn sàng cho thương hiệu"
    ),
    "product_lifestyle": (
        "ảnh sản phẩm phong cách sống, bối cảnh môi trường tự nhiên, ánh sáng cửa sổ mềm dịu, "
        "gam màu ấm, độ sâu trường ảnh nông f/2.8, chất lượng editorial, không khí khát vọng"
    ),
    "product_packshot": (
        "ảnh packshot chuyên nghiệp, cân đối chính giữa, nền trắng tinh, "
        "bóng đổ nhẹ chân đế, đã retouch, sắc nét 100%, sẵn sàng thương mại điện tử"
    ),
    # Thời trang
    "fashion_editorial": (
        "ảnh thời trang editorial cao cấp, chất lượng Vogue, ánh sáng định hướng kịch tính, "
        "phông nền có kết cấu, tông màu điện ảnh, chi tiết sắc nét thời trang cao cấp, thẩm mỹ sang trọng"
    ),
    "fashion_lookbook": (
        "ảnh lookbook thời trang, nền tối giản sạch, ánh sáng studio cân bằng, "
        "khung toàn thân hoặc 3/4, tư thế người mẫu chuyên nghiệp, chất lượng catalog thương mại"
    ),
    "fashion_street": (
        "ảnh thời trang đường phố, bối cảnh đô thị, ánh sáng hoàng hôn ngược sáng, "
        "nền bokeh, năng lượng tự nhiên, tương phản cao, thẩm mỹ trẻ trung"
    ),
    # Đồ ăn & Đồ uống
    "food_hero": (
        "ảnh hero đồ ăn, góc chụp từ trên xuống hoặc 45°, hơi nước bốc lên, "
        "kết cấu tươi mọn lấp lánh, đạo cụ phụ hợp, ánh sáng cửa sổ khuếch tán tự nhiên, "
        "màu sắc sống động bão hòa, hoàn thiện kiểu food stylist chuyên nghiệp"
    ),
    "food_beverage": (
        "ảnh đồ uống, giọt nước ngưng tụ trên ly, viên đá trong suốt, "
        "chất lỏng trong suốt được hắt sáng từ phía sau, nền tối tâm trạng, chi tiết macro, phong cách cao cấp"
    ),
    "food_restaurant": (
        "ảnh bày biện món ăn nhà hàng, trình bày kiểu bếp trưởng, tông ánh nến ấm, "
        "không khí bokeh, chất lượng fine dining, chuẩn tạp chí ẩm thực"
    ),
    # Mỹ phẩm & Làm đẹp
    "beauty_product": (
        "ảnh sản phẩm làm đẹp, bề mặt đá cẩm thạch hoặc kết cấu cao cấp, chi tiết macro kết cấu, "
        "gam màu pastel hoặc đơn sắc, ánh sáng khuếch tán mềm, bề mặt bóng cao cấp, "
        "chuẩn catalog mỹ phẩm thượng hạng"
    ),
    "beauty_portrait": (
        "ảnh chân dung làm đẹp, điểm sáng trong mắt, da hoàn hảo retouch, "
        "ánh sáng bướm hoặc Rembrandt, nền sạch trung tính, "
        "retouch cao cấp, chất lượng tạp chí thời trang hàng đầu"
    ),
    # Bất động sản & Kiến trúc
    "interior_design": (
        "ảnh kiến trúc nội thất, góc rộng ống kính 16-24mm, "
        "ánh sáng cửa sổ tự nhiên cân bằng với ánh sáng phụ, đường dọc thẳng chuẩn, "
        "tông màu ấm giàu, chất lượng tạp chí kiến trúc"
    ),
    "real_estate": (
        "ảnh bất động sản, ngoại thất hoàng hôn, phơi sáng HDR cân bằng, "
        "đèn nội thất tỏa ánh ấm, bầu trời giờ xanh, góc máy chuyên nghiệp"
    ),
    # Chân dung & Phong cách sống
    "portrait_professional": (
        "chân dung chuyên nghiệp doanh nhân, nền trung tính sạch, ánh sáng softbox đều, "
        "mắt sắc nét với điểm sáng, biểu cảm tự tin, chất lượng ảnh doanh nghiệp/LinkedIn"
    ),
    "lifestyle_authentic": (
        "ảnh phong cách sống, khoảnh khắc tự nhiên chân thực, ánh sáng hoàng hôn tự nhiên, "
        "độ sâu trường ảnh nông, tông màu ấm kiểu phim, giàu cảm xúc"
    ),
    # Công nghệ & SaaS
    "tech_product": (
        "ảnh sản phẩm công nghệ, nền tối gradient, ánh sáng neon điểm nhấn, "
        "phản chiếu trên bề mặt, không khí tương lai, chất lượng editorial công nghệ"
    ),
    # Trang sức & Đồng hồ
    "jewelry": (
        "ảnh trang sức cao cấp, chi tiết macro đá quý, bề mặt tối phản chiếu hoặc "
        "đá cẩm thạch trắng, ánh sáng chính đơn mềm với viền sáng tinh tế, phản xạ kim loại, "
        "chuẩn catalog trang sức hàng đầu, siêu sắc nét 8K"
    ),
    # Nến & Trang trí nhà
    "candle_decor": (
        "ảnh nến và trang trí nhà, ánh sáng nến ấm áp với bokeh mềm, "
        "đạo cụ mộc mạc hoặc tối giản, không khí ấm cúng, tông màu hổ phách ấm, chất lượng editorial"
    ),
    # Trẻ em & Em bé
    "kids_product": (
        "ảnh sản phẩm trẻ em, màu sắc tươi sáng vui tươi, đạo cụ vui nhộn và nền mềm, "
        "ánh sáng cửa sổ tự nhiên mềm, thẩm mỹ sạch an toàn, không khí ấm áp hấp dẫn"
    ),
    # Thể hình & Thể thao
    "fitness": (
        "ảnh sản phẩm thể hình, nền trắng sạch hoặc phòng gym, ánh sáng bên kịch tính, "
        "thẩm mỹ cơ bắp tự tin, màu sắc đậm bão hòa, chất lượng editorial sức khỏe"
    ),
    # Thú cưng
    "pet": (
        "ảnh thú cưng, ánh sáng cửa sổ tự nhiên mềm, biểu cảm đáng yêu tự nhiên, "
        "nền tối giản sạch, không khí ấm áp vui tươi, nét sắc vào mắt"
    ),
    # Động vật & Tự nhiên
    "wildlife_nature": (
        "nhiếp ảnh động vật tự nhiên chuyên nghiệp, chụp bằng ống kính tele, ánh sáng tự nhiên mềm, "
        "bối cảnh môi trường tự nhiên, chi tiết siêu sắc nét, độ sâu trường ảnh nông, chất lượng National Geographic"
    ),
}

# ── Content type keyword detection ───────────────────────────────────────────
_CONTENT_TYPE_KEYWORDS: dict[str, list[str]] = {
    "food": [
        "food", "dish", "meal", "cuisine", "plate", "restaurant", "dessert",
        "snack", "cake", "bread", "noodle", "rice", "salad", "soup",
        "ăn", "món", "thức ăn", "bánh", "cơm", "phở", "bún", "hủ tiếu",
        "bữa", "nhà hàng", "quán ăn", "ẩm thực", "đồ ăn", "thực phẩm",
    ],
    "beverage": [
        "drink", "coffee", "tea", "juice", "cocktail", "wine", "beer",
        "boba", "smoothie", "latte", "espresso", "bubble tea", "matcha",
        "cà phê", "nước", "đồ uống", "trà", "sinh tố", "nước ép", "sữa",
        "trà sữa", "thức uống", "nước giải khát",
    ],
    "cosmetic": [
        "cosmetic", "makeup", "skincare", "cream", "serum", "lipstick",
        "perfume", "mascara", "foundation", "blush", "eyeshadow", "toner",
        "mỹ phẩm", "kem", "son", "nước hoa", "phấn", "chăm sóc da",
        "dưỡng da", "sữa rửa mặt", "trang điểm", "làm đẹp", "beauty",
    ],
    "fashion": [
        "fashion", "clothing", "outfit", "dress", "shoes", "bag", "luxury",
        "shirt", "pants", "jacket", "jeans", "sneaker", "heel", "handbag",
        "quần", "áo", "giày", "túi", "thời trang", "váy", "đầm", "áo khoác",
        "phụ kiện", "trang phục", "mặc", "style", "ootd", "lookbook",
    ],
    "portrait": [
        "portrait", "person", "model", "headshot", "face", "selfie",
        "người", "chân dung", "khuôn mặt", "nhân vật", "con người",
    ],
    "interior": [
        "interior", "room", "living room", "office", "bedroom", "kitchen",
        "furniture", "sofa", "desk", "decor",
        "phòng", "nội thất", "phòng khách", "phòng ngủ", "bàn ghế", "trang trí",
        "phòng làm việc", "không gian sống",
    ],
    "real_estate": [
        "house", "apartment", "villa", "building", "property", "real estate",
        "nhà", "căn hộ", "biệt thự", "bất động sản", "căn nhà", "tòa nhà",
    ],
    "tech": [
        "phone", "laptop", "device", "gadget", "tech", "electronic",
        "tablet", "smartwatch", "headphone", "camera", "speaker",
        "điện thoại", "máy tính", "thiết bị", "công nghệ", "điện tử",
        "tai nghe", "đồng hồ thông minh",
    ],
    "jewelry": [
        "jewelry", "ring", "necklace", "bracelet", "earring", "diamond",
        "gold", "silver", "gemstone", "watch",
        "trang sức", "nhẫn", "vòng cổ", "vòng tay", "bông tai", "kim cương",
        "đồng hồ", "dây chuyền",
    ],
    "candle": [
        "candle", "home decor", "scented", "wax", "aromatherapy", "diffuser",
        "nến", "nến thơm", "tinh dầu", "trang trí nhà", "decor nhà",
    ],
    "kids": [
        "kids", "baby", "toy", "children", "infant", "toddler", "nursery",
        "trẻ em", "em bé", "đồ chơi", "trẻ con", "sơ sinh", "mẹ và bé",
    ],
    "fitness": [
        "fitness", "gym", "sport", "workout", "yoga", "protein", "supplement",
        "thể dục", "thể hình", "tập gym", "thể thao", "yoga", "chạy bộ",
    ],
    "pet": [
        "pet", "dog", "cat", "animal", "puppy", "kitten",
        "thú cưng", "chó", "mèo", "vật nuôi",
    ],
    "wildlife": [
        "wildlife", "animal", "bird", "nature", "landscape", "forest", "lake", "mountain", "river", "sea", "duck",
        "động vật", "thú", "chim", "thiên nhiên", "phong cảnh", "rừng", "hồ", "núi", "sông", "biển", "vịt",
    ],
    "product": [
        "product", "item", "object", "sản phẩm", "hàng hóa", "mặt hàng",
    ],
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


def _get_universal_suffix_vi() -> str:
    return _overrides.get("universal_quality_suffix_vi", _UNIVERSAL_QUALITY_SUFFIX_VI)


def _get_styles_vi() -> dict[str, str]:
    return {**_PHOTOGRAPHY_STYLES_VI, **_overrides.get("photography_styles_vi", {})}


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
    lang: str | None = None,
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
        lang: Language code (e.g. ``'vi'`` for Vietnamese).
              When ``'vi'``, returns Vietnamese suffix.

    Returns:
        A suffix string ready to be appended to the prompt with ``", "``.
        Empty string if no enhancement is applicable.
    """
    if lang == "vi":
        return _build_professional_prompt_suffix_vi(prompt, content_type, platform)

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


def _build_professional_prompt_suffix_vi(
    prompt: str,
    content_type: str | None = None,
    platform: str | None = None,
) -> str:
    """Vietnamese version of build_professional_prompt_suffix."""
    detected = content_type or detect_content_type(prompt)

    # Get Vietnamese style if available, fallback to original English
    style: str | None = None
    if detected:
        style_key = _CONTENT_TYPE_TO_STYLE.get(detected)
        if style_key:
            styles_vi = _get_styles_vi()
            style = styles_vi.get(style_key) or _get_styles().get(style_key)

    parts: list[str] = []

    if style:
        parts.append(style)

    if platform:
        specs = _get_platform_specs().get(platform, {})
        style_note = specs.get("style_note")
        if style_note:
            parts.append(style_note)

    parts.append(_get_universal_suffix_vi())

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
