"""Vidtory Knowledge — global creative prompt library and professional guidelines.

This module is the single source of truth for Vidtory's creative standards.
It provides two public interfaces:

1. ``get_system_knowledge_block()`` — injects professional guidelines into the
   LLM's system prompt every turn, giving the agent deep creative expertise.

2. ``build_professional_prompt_suffix(prompt, content_type)`` — enhances any
   image generation prompt with world-class technical specifications selected
   by content category.

The content layer lives in ``_STYLES`` and ``_PLATFORM_SPECS`` below.
Each section is a plain dict so non-engineers can extend or override entries
without touching logic.

Customization:
    Override at runtime by loading an external YAML/JSON config and calling
    ``override_library(data)`` before the agent starts.
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Content Layer — editable without touching logic
# ---------------------------------------------------------------------------

# ── Photography & Design style presets ───────────────────────────────────────
# Each key has a tuple: (en_style, vi_style)
# Both are kept inline so callers only need one dict lookup.
_STYLES: dict[str, tuple[str, str]] = {
    # ── Product ──────────────────────────────────────────────────────────────
    "product_hero": (
        "product hero shot, 8K commercial photography, pure white or gradient studio backdrop, "
        "three-point studio lighting (key light + fill light + rim light), specular highlights on surface, "
        "ultra-sharp focus with shallow depth of field, color calibrated, brand-ready",
        "ảnh hero sản phẩm, chất lượng thương mại 8K, nền studio trắng hoặc chuyển màu, "
        "ánh sáng studio ba điểm (chính + phụ + viền), phản xạ trên bề mặt, "
        "nét sắc siêu rõ với độ sâu trường ảnh nông, màu sắc chuẩn, sẵn sàng cho thương hiệu",
    ),
    "product_lifestyle": (
        "lifestyle product photography, natural environment context, soft ambient window light, "
        "warm color palette, shallow depth of field f/2.8, editorial quality, aspirational mood",
        "ảnh sản phẩm phong cách sống, bối cảnh môi trường tự nhiên, ánh sáng cửa sổ mềm dịu, "
        "gam màu ấm, độ sâu trường ảnh nông f/2.8, chất lượng editorial, không khí khát vọng",
    ),
    "product_packshot": (
        "professional packshot, perfectly centered, pure white background, "
        "shadow on base, clean shadows, retouched, 100% sharp, e-commerce ready",
        "ảnh packshot chuyên nghiệp, cân đối chính giữa, nền trắng tinh, "
        "bóng đổ nhẹ chân đế, đã retouch, sắc nét 100%, sẵn sàng thương mại điện tử",
    ),
    # ── Fashion ──────────────────────────────────────────────────────────────
    "fashion_editorial": (
        "high-fashion editorial photography, Vogue-quality, dramatic directional lighting, "
        "textured backdrop, cinematic color grade, sharp couture detail, luxury aesthetic",
        "ảnh thời trang editorial cao cấp, chất lượng Vogue, ánh sáng định hướng kịch tính, "
        "phông nền có kết cấu, tông màu điện ảnh, chi tiết sắc nét thời trang cao cấp, thẩm mỹ sang trọng",
    ),
    "fashion_lookbook": (
        "fashion lookbook photography, clean minimal background, balanced studio lighting, "
        "full or three-quarter body frame, professional model pose, commercial catalog quality",
        "ảnh lookbook thời trang, nền tối giản sạch, ánh sáng studio cân bằng, "
        "khung toàn thân hoặc 3/4, tư thế người mẫu chuyên nghiệp, chất lượng catalog thương mại",
    ),
    "fashion_street": (
        "street fashion photography, urban environment, golden hour backlight, "
        "bokeh background, candid energy, high contrast editing, Gen-Z aesthetic",
        "ảnh thời trang đường phố, bối cảnh đô thị, ánh sáng hoàng hôn ngược sáng, "
        "nền bokeh, năng lượng tự nhiên, tương phản cao, thẩm mỹ trẻ trung",
    ),
    # ── Food & Beverage ───────────────────────────────────────────────────────
    "food_hero": (
        "food hero photography, overhead flat-lay or 45° angle, steam wisps visible, "
        "fresh glistening textures, complementary props, natural diffused window light, "
        "vibrant saturated colors, professional food stylist finish",
        "ảnh hero đồ ăn, góc chụp từ trên xuống hoặc 45°, hơi nước bốc lên, "
        "kết cấu tươi mọn lấp lánh, đạo cụ phụ hợp, ánh sáng cửa sổ khuếch tán tự nhiên, "
        "màu sắc sống động bão hòa, hoàn thiện kiểu food stylist chuyên nghiệp",
    ),
    "food_beverage": (
        "beverage photography, condensation droplets on glass, ice cubes with clarity, "
        "backlit translucent liquid, dark moody background, macro detail, premium lifestyle",
        "ảnh đồ uống, giọt nước ngưng tụ trên ly, viên đá trong suốt, "
        "chất lỏng trong suốt được hắt sáng từ phía sau, nền tối tâm trạng, chi tiết macro, phong cách cao cấp",
    ),
    "food_restaurant": (
        "restaurant plating photography, chef's table presentation, warm candlelight tone, "
        "bokeh ambiance, fine dining quality, editorial food magazine standard",
        "ảnh bày biện món ăn nhà hàng, trình bày kiểu bếp trưởng, tông ánh nến ấm, "
        "không khí bokeh, chất lượng fine dining, chuẩn tạp chí ẩm thực",
    ),
    # ── Cosmetics & Beauty ────────────────────────────────────────────────────
    "beauty_product": (
        "beauty product photography, marble or luxury texture surface, macro detail of texture, "
        "pastel or monochrome color scheme, soft diffused light, premium glossy finish, "
        "Sephora/LVMH catalog standard",
        "ảnh sản phẩm làm đẹp, bề mặt đá cẩm thạch hoặc kết cấu cao cấp, chi tiết macro kết cấu, "
        "gam màu pastel hoặc đơn sắc, ánh sáng khuếch tán mềm, bề mặt bóng cao cấp, "
        "chuẩn catalog mỹ phẩm thượng hạng",
    ),
    "beauty_portrait": (
        "beauty portrait photography, catchlights in eyes, flawless skin retouching, "
        "butterfly lighting or Rembrandt lighting, clean neutral background, "
        "high-end retouching, Harper's Bazaar quality",
        "ảnh chân dung làm đẹp, điểm sáng trong mắt, da hoàn hảo retouch, "
        "ánh sáng bướm hoặc Rembrandt, nền sạch trung tính, "
        "retouch cao cấp, chất lượng tạp chí thời trang hàng đầu",
    ),
    # ── Real Estate & Architecture ────────────────────────────────────────────
    "interior_design": (
        "interior architecture photography, wide angle 16-24mm lens perspective, "
        "natural window light balanced with ambient fill, straight verticals corrected, "
        "rich warm tones, Architectural Digest quality",
        "ảnh kiến trúc nội thất, góc rộng ống kính 16-24mm, "
        "ánh sáng cửa sổ tự nhiên cân bằng với ánh sáng phụ, đường dọc thẳng chuẩn, "
        "tông màu ấm giàu, chất lượng tạp chí kiến trúc",
    ),
    "real_estate": (
        "real estate photography, twilight exterior, HDR balanced exposure, "
        "warm interior lights glowing, blue-hour sky, professional drone or ground angle",
        "ảnh bất động sản, ngoại thất hoàng hôn, phơi sáng HDR cân bằng, "
        "đèn nội thất tỏa ánh ấm, bầu trời giờ xanh, góc máy chuyên nghiệp",
    ),
    # ── Lifestyle & Portrait ──────────────────────────────────────────────────
    "portrait_professional": (
        "professional business portrait, clean neutral background, soft box even lighting, "
        "sharp eyes with catchlights, confident expression, LinkedIn/executive quality",
        "chân dung chuyên nghiệp doanh nhân, nền trung tính sạch, ánh sáng softbox đều, "
        "mắt sắc nét với điểm sáng, biểu cảm tự tin, chất lượng ảnh doanh nghiệp/LinkedIn",
    ),
    "lifestyle_authentic": (
        "lifestyle photography, authentic candid moment, golden hour natural light, "
        "shallow depth of field, warm film-like color grade, emotionally resonant",
        "ảnh phong cách sống, khoảnh khắc tự nhiên chân thực, ánh sáng hoàng hôn tự nhiên, "
        "độ sâu trường ảnh nông, tông màu ấm kiểu phim, giàu cảm xúc",
    ),
    # ── Technology ────────────────────────────────────────────────────────────
    "tech_product": (
        "technology product photography, dark gradient background, neon accent lighting, "
        "reflection on surface, futuristic atmosphere, Verge/TechCrunch editorial quality",
        "ảnh sản phẩm công nghệ, nền tối gradient, ánh sáng neon điểm nhấn, "
        "phản chiếu trên bề mặt, không khí tương lai, chất lượng editorial công nghệ",
    ),
    # ── Jewelry & Watches ─────────────────────────────────────────────────────
    "jewelry": (
        "luxury jewelry photography, macro detail on gemstones, reflective dark surface or "
        "white marble, single soft key light with subtle rim, specular highlights on metal, "
        "Cartier/Tiffany catalog standard, ultra-sharp 8K",
        "ảnh trang sức cao cấp, chi tiết macro đá quý, bề mặt tối phản chiếu hoặc "
        "đá cẩm thạch trắng, ánh sáng chính đơn mềm với viền sáng tinh tế, phản xạ kim loại, "
        "chuẩn catalog trang sức hàng đầu, siêu sắc nét 8K",
    ),
    # ── Candle & Home Decor ───────────────────────────────────────────────────
    "candle_decor": (
        "candle and home decor photography, warm candlelight glow with soft bokeh, "
        "rustic or minimal props, cozy lifestyle mood, warm amber tones, editorial quality",
        "ảnh nến và trang trí nhà, ánh sáng nến ấm áp với bokeh mềm, "
        "đạo cụ mộc mạc hoặc tối giản, không khí ấm cúng, tông màu hổ phách ấm, chất lượng editorial",
    ),
    # ── Kids & Baby ───────────────────────────────────────────────────────────
    "kids_product": (
        "children's product photography, bright cheerful colors, playful props and soft background, "
        "natural soft window light, clean safe aesthetic, warm inviting mood",
        "ảnh sản phẩm trẻ em, màu sắc tươi sáng vui tươi, đạo cụ vui nhộn và nền mềm, "
        "ánh sáng cửa sổ tự nhiên mềm, thẩm mỹ sạch an toàn, không khí ấm áp hấp dẫn",
    ),
    # ── Fitness & Sport ───────────────────────────────────────────────────────
    "fitness": (
        "fitness product photography, clean white or gym background, dramatic side lighting, "
        "muscular confidence aesthetic, bold saturated colors, health editorial quality",
        "ảnh sản phẩm thể hình, nền trắng sạch hoặc phòng gym, ánh sáng bên kịch tính, "
        "thẩm mỹ cơ bắp tự tin, màu sắc đậm bão hòa, chất lượng editorial sức khỏe",
    ),
    # ── Pet ───────────────────────────────────────────────────────────────────
    "pet": (
        "pet photography, soft natural window light, adorable candid expression, "
        "clean minimal background, warm and playful mood, sharp eye focus",
        "ảnh thú cưng, ánh sáng cửa sổ tự nhiên mềm, biểu cảm đáng yêu tự nhiên, "
        "nền tối giản sạch, không khí ấm áp vui tươi, nét sắc vào mắt",
    ),
    # ── Wildlife & Nature ─────────────────────────────────────────────────────
    "wildlife_nature": (
        "professional wildlife photography, shot on telephoto lens, soft natural lighting, "
        "natural environment context, ultra-sharp details, shallow depth of field, National Geographic quality",
        "nhiếp ảnh động vật tự nhiên chuyên nghiệp, chụp bằng ống kính tele, ánh sáng tự nhiên mềm, "
        "bối cảnh môi trường tự nhiên, chi tiết siêu sắc nét, độ sâu trường ảnh nông, chất lượng National Geographic",
    ),

    # ── ✨ CINEMATIC POSTER styles (new) ─────────────────────────────────────
    "cinematic_action": (
        "cinematic action movie poster, dramatic wide-angle composition, explosive environment "
        "with fire, smoke, dust particles floating, intense directional rim lighting, "
        "bold oversized sans-serif metallic title typography with rust and scratch texture, "
        "sharp shadow cast on background, 8K ultra-resolution, Hollywood blockbuster quality",
        "poster phim hành động điện ảnh hoành tráng, bố cục góc rộng kịch tính, "
        "môi trường khói lửa, bụi bặm và hạt ánh sáng lấp lánh, viền sáng rọi mạnh, "
        "chữ tiêu đề sans-serif dày mạnh mẽ chất liệu kim loại rỉ sét và trầy xước chân thực, "
        "bóng đổ sắc nét xuống nền, phân giải 8K, chất lượng Hollywood",
    ),
    "cinematic_fantasy": (
        "epic fantasy movie poster, mystical ancient forest or floating island setting, "
        "ethereal hazy light with magical golden rays, ornate serif title typography "
        "carved from ancient glowing amber stone, organic vines and roots naturally wrapping "
        "letters in perfect 3D depth, world-class art direction, breathtakingly beautiful",
        "poster phim kỳ ảo đỉnh cao, khung cảnh rừng cổ thụ huyền bí hoặc hòn đảo bay, "
        "ánh sáng huyền ảo mờ sương với luồng sáng thần tiên vàng, "
        "chữ serif nghệ thuật như đá cổ đại phát ánh vàng hổ phách, "
        "dây leo và rễ cây quấn quanh chữ tự nhiên tạo chiều sâu 3D, nghệ thuật choáng ngợp",
    ),
    "cinematic_horror": (
        "psychological horror movie poster, dark minimalist composition, dominant black and deep crimson tones, "
        "subject emerging from shadow with single-sided dramatic raking light casting long mysterious shadows, "
        "asymmetric tension-building layout, handwritten-style jagged uneven title typography "
        "made of thick viscous dripping liquid with glossy wet edges, "
        "premium cinematic art direction, unsettling yet deeply artistic",
        "poster phim kinh dị tâm lý, nền tối tối giản tông đen và đỏ thẫm, "
        "chủ thể ẩn hiện trong bóng tối mờ ảo với ánh sáng rọi một phía, "
        "bóng đổ dài bí ẩn, bố cục bất đối xứng căng thẳng, "
        "chữ viết tay bất đối xứng sắc nhọn chất liệu chất lỏng đặc quánh đang nhỏ giọt, "
        "điện ảnh cao cấp, rùng rợn nhưng vô cùng nghệ thuật",
    ),

    # ── ✨ PREMIUM ADVERTISING styles (new) ──────────────────────────────────
    "luxury_ad": (
        "international luxury brand advertising, ultra-minimalist neutral monochrome backdrop, "
        "polished quartz surface reflecting like a mirror beneath the hero product, "
        "soft studio light wrapping the subject, elegant thin modern serif or sans-serif typography "
        "with perfect letter-spacing crafted from 24k matte gold or polished chrome, "
        "studio reflections glowing softly, supreme high-end and opulent feel",
        "quảng cáo thương hiệu xa xỉ đẳng cấp quốc tế, nền tối giản đơn sắc trung tính cao cấp, "
        "bề mặt đá thạch anh phẳng lặng phản chiếu như gương, ánh sáng studio mềm mại, "
        "chữ typography thanh lịch mỏng hiện đại khoảng cách hoàn hảo, "
        "chất liệu vàng mờ 24k hoặc chrome bóng loáng phản chiếu ánh sáng studio, "
        "cảm giác vô cùng đắt tiền và thượng lưu",
    ),
    "tech_futuristic_ad": (
        "futuristic technology advertising design, digital space background with laser energy streaks "
        "and glowing circuit networks, hero product floating mid-air, "
        "dynamic diagonal layout with motion blur in background for speed, "
        "futuristic angular glassmorphism title typography with neon-glowing borders, "
        "sharp professional high-tech cinematic quality",
        "thiết kế quảng cáo công nghệ tương lai, nền không gian số với dải laser và mạch vi mạch phát sáng, "
        "sản phẩm lơ lửng giữa không trung, bố cục góc chéo động với motion blur hậu cảnh, "
        "chữ tiêu đề futuristic glassmorphism xuyên thấu viền neon rực rỡ, "
        "sắc nét chuyên nghiệp hi-tech điện ảnh",
    ),
    "fashion_magazine": (
        "high-fashion luxury magazine cover advertisement, abstract artistic geometric shapes "
        "with sharp studio shadows, large creative typographic elements with varied letterform scale "
        "semi-transparent intersecting through objects for 3D depth illusion, "
        "bold avant-garde art direction, premium curated color palette, "
        "visually commanding instant attention",
        "quảng cáo tạp chí thời trang cao cấp, các mảng hình học nghệ thuật trừu tượng, "
        "chữ nghệ thuật lớn kích thước đan xen sáng tạo bán trong suốt lồng ghép qua vật thể tạo 3D, "
        "màu sắc nghệ thuật cao cấp, bố cục phá cách, thị giác cực mạnh thu hút ngay lập tức",
    ),
    "streetwear_ad": (
        "streetwear and urban fashion advertising, rough concrete wall background with graffiti splashes, "
        "high contrast bold saturated gradient colors, oversized 3D bubble or glossy plastic typography "
        "in vibrant hot-tone gradient, extremely high contrast, "
        "modern global pop-culture Gen-Z energy",
        "thiết kế quảng cáo streetwear đường phố, nền tường bê tông thô ráp với vệt graffiti, "
        "chữ 3D nhựa bóng dẻo hoặc phao phồng gradient nóng rực rỡ, "
        "độ tương phản cực cao, hơi thở văn hóa pop hiện đại toàn cầu Gen-Z",
    ),
    "organic_eco": (
        "premium organic eco-friendly product advertising, natural sunlight filtering through lush green leaves, "
        "early morning dew droplets glistening, hero product centered in organic setting, "
        "brand typography naturally carved from solid oak wood with visible grain texture "
        "or formed from living wet green moss, "
        "fresh pure clean premium organic feel",
        "quảng cáo sản phẩm thuần chay sinh thái cao cấp, ánh nắng tự nhiên qua tán lá xanh mướt, "
        "hạt sương sớm lung linh, chữ thương hiệu điêu khắc từ gỗ sồi vân gỗ rõ "
        "hoặc tạo từ thảm rêu xanh ẩm ướt chân thực, "
        "bố cục trong lành tinh khiết sạch sẽ cao cấp",
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

# ── Content-type → style key mapping ────────────────────────────────────────
_CONTENT_TYPE_TO_STYLE: dict[str, str] = {
    "recruitment": "portrait_professional",
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
    "jewelry": "jewelry",
    "candle": "candle_decor",
    "kids": "kids_product",
    "fitness": "fitness",
    "pet": "pet",
    "wildlife": "wildlife_nature",
    # Cinematic / Poster
    "cinematic_action": "cinematic_action",
    "cinematic_fantasy": "cinematic_fantasy",
    "cinematic_horror": "cinematic_horror",
    # Premium Advertising
    "luxury_ad": "luxury_ad",
    "tech_futuristic_ad": "tech_futuristic_ad",
    "fashion_magazine": "fashion_magazine",
    "streetwear_ad": "streetwear_ad",
    "organic_eco": "organic_eco",
}

# ── Audience & communication insights per content type ───────────────────────
# Format: { key: (en_insight, vi_insight) }
_CONTENT_INSIGHTS: dict[str, tuple[str, str]] = {
    "recruitment": (
        "make the role feel credible and aspirational, show authentic team energy, clear information hierarchy, mobile-readable typography zones",
        "insight ứng viên: vị trí phải đáng tin và đáng khao khát, thể hiện năng lượng đội ngũ chân thực, phân cấp thông tin rõ, vùng chữ dễ đọc trên điện thoại",
    ),
    "product": (
        "make the main benefit visually obvious at first glance, prioritize product recognition and purchase confidence",
        "insight mua hàng: lợi ích chính phải hiểu ngay từ cái nhìn đầu tiên, sản phẩm dễ nhận diện và tạo cảm giác đáng tin để ra quyết định",
    ),
    "fashion": (
        "sell identity and self-expression through silhouette, attitude, styling coherence, and editorial visual rhythm",
        "insight thời trang: bán bản sắc và khả năng thể hiện cá tính qua phom dáng, thần thái, phối đồ và nhịp hình editorial",
    ),
    "food": (
        "trigger appetite through freshness, texture, steam or gloss, generous portions, and an immediately recognizable hero dish",
        "insight ẩm thực: kích thích vị giác bằng độ tươi, kết cấu, hơi nóng hoặc độ bóng, khẩu phần hấp dẫn và món chính nhận ra ngay",
    ),
    "beverage": (
        "communicate refreshment through temperature cues, condensation, liquid clarity, and a strong flavor signal",
        "insight đồ uống: truyền cảm giác mát hoặc ấm qua nhiệt độ, giọt ngưng tụ, độ trong của chất lỏng và tín hiệu hương vị",
    ),
    "cosmetic": (
        "build trust through cleanliness, texture evidence, ingredient or efficacy cues, and premium tactile detail",
        "insight làm đẹp: xây niềm tin bằng cảm giác sạch, bằng chứng kết cấu, thành phần hoặc công dụng và chi tiết cao cấp",
    ),
    "portrait": (
        "create human trust through natural expression, confident posture, clear eye contact, and believable skin texture",
        "insight con người: tạo niềm tin qua biểu cảm tự nhiên, tư thế tự tin, ánh mắt rõ và kết cấu da chân thực",
    ),
    "interior": (
        "help viewers imagine living in the space through scale, circulation, daylight, material warmth, and functional zones",
        "insight không gian: giúp người xem hình dung mình đang sống ở đó qua tỷ lệ, lối đi, ánh sáng, vật liệu và công năng",
    ),
    "real_estate": (
        "increase perceived value through spaciousness, natural light, accurate geometry, lifestyle context, and trustworthy detail",
        "insight bất động sản: tăng giá trị cảm nhận bằng độ thoáng, ánh sáng tự nhiên, hình học chính xác và bối cảnh sống đáng tin",
    ),
    "tech": (
        "make innovation understandable through one clear use case, precise materials, functional detail, and controlled futuristic accents",
        "insight công nghệ: làm đổi mới trở nên dễ hiểu bằng một tình huống sử dụng rõ, vật liệu chính xác và chi tiết chức năng",
    ),
    "jewelry": (
        "signal craftsmanship and rarity through gemstone fire, metal finish, scale clarity, and restrained luxury",
        "insight trang sức: thể hiện tay nghề và độ hiếm qua ánh đá, hoàn thiện kim loại, tỷ lệ rõ và sự sang trọng tiết chế",
    ),
    "kids": (
        "communicate safety, joy, age suitability, and simple product interaction in a warm parent-trusted setting",
        "insight trẻ em: truyền tải an toàn, niềm vui, độ phù hợp lứa tuổi và cách sử dụng đơn giản trong bối cảnh phụ huynh tin cậy",
    ),
    "fitness": (
        "show attainable progress, controlled movement, product utility, and energetic but credible performance",
        "insight thể thao: cho thấy tiến bộ có thể đạt được, chuyển động chuẩn, công dụng rõ và năng lượng đáng tin",
    ),
    "pet": (
        "create affection and trust through expressive eyes, natural behavior, safety, and a clean caring environment",
        "insight thú cưng: tạo yêu mến và tin cậy qua ánh mắt, hành vi tự nhiên, sự an toàn và môi trường chăm sóc sạch",
    ),
    "wildlife": (
        "preserve authentic behavior, habitat context, natural light, and respectful documentary realism",
        "insight thiên nhiên: giữ hành vi chân thực, bối cảnh sinh cảnh, ánh sáng tự nhiên và tinh thần tư liệu tôn trọng",
    ),
    # Cinematic / Poster insights
    "cinematic_action": (
        "deliver adrenaline and scale — the hero must feel invincible against overwhelming odds; every element amplifies power and momentum",
        "truyền tải adrenaline và sức mạnh — nhân vật chính phải cảm giác bất khả chiến bại; mọi yếu tố khuếch đại lực và nhịp điệu",
    ),
    "cinematic_fantasy": (
        "evoke wonder and otherworldly belief — the world must feel ancient, vast, and filled with hidden magic that rewards slow looking",
        "gợi sự kỳ diệu và thế giới khác — thế giới phải cảm giác cổ xưa, rộng lớn và chứa đựng phép màu ẩn giấu",
    ),
    "cinematic_horror": (
        "build dread through what is NOT shown — shadow, implication, and asymmetry are more terrifying than explicit gore",
        "xây dựng nỗi sợ qua những gì KHÔNG được hiện ra — bóng tối, ẩn ý và bố cục bất đối xứng đáng sợ hơn bạo lực trực tiếp",
    ),
    # Premium advertising insights
    "luxury_ad": (
        "communicate exclusivity through restraint — negative space, precise typography, and flawless materials do more than ornament",
        "truyền tải sự độc quyền qua tiết chế — khoảng trắng, typography chính xác và vật liệu hoàn hảo nói lên đẳng cấp hơn trang trí",
    ),
    "tech_futuristic_ad": (
        "make the future feel attainable today — one clear hero feature, precise materials, and controlled energy signal progress without confusion",
        "làm tương lai trở nên có thể chạm tới ngay hôm nay — một tính năng rõ, vật liệu chính xác và năng lượng kiểm soát tín hiệu tiến bộ",
    ),
    "fashion_magazine": (
        "provoke desire through unexpected visual tension — scale, transparency, and geometric interplay make viewers stop scrolling",
        "gợi ham muốn qua sự căng thẳng thị giác bất ngờ — tỷ lệ, độ trong và hình học đan xen khiến người xem phải dừng lại",
    ),
    "streetwear_ad": (
        "radiate authentic street credibility — raw texture, bold color, and unapologetic type convey culture-first identity",
        "tỏa ra sự tín nhiệm đường phố chân thực — kết cấu thô, màu táo bạo và chữ không xin lỗi truyền tải bản sắc culture-first",
    ),
    "organic_eco": (
        "earn trust through visible naturalness — real wood grain, living moss, honest daylight signal integrity and purity",
        "xây dựng niềm tin qua sự tự nhiên hữu hình — vân gỗ thật, rêu sống, ánh sáng ban ngày chân thật truyền tải sự trong sạch",
    ),
}

# ── Universal quality suffix (appended to all prompts) ───────────────────────
_UNIVERSAL_QUALITY_SUFFIX = (
    "editorial photography, professional camera shot, sharp focus, natural textures, "
    "balanced exposure, clean composition, no watermark, no text overlay"
)

_UNIVERSAL_QUALITY_SUFFIX_VI = (
    "nhiếp ảnh thương mại chuyên nghiệp, chụp bằng máy ảnh cao cấp, nét sắc, kết cấu tự nhiên, "
    "phơi sáng cân bằng, bố cục sạch, không có watermark, không có chữ ngẫu nhiên"
)

# ── Content type keyword detection ───────────────────────────────────────────
_CONTENT_TYPE_KEYWORDS: dict[str, list[str]] = {
    "recruitment": [
        "recruitment", "hiring", "job opening", "career", "candidate",
        "tuyển dụng", "tuyển nhân sự", "việc làm", "ứng viên", "vị trí tuyển",
    ],
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
        "wildlife", "bird", "nature", "landscape", "forest", "lake", "mountain", "river", "sea", "duck",
        "động vật hoang dã", "chim", "thiên nhiên", "phong cảnh", "rừng", "hồ", "núi", "sông", "biển", "vịt",
    ],
    "product": [
        "product", "item", "object", "sản phẩm", "hàng hóa", "mặt hàng",
    ],
    # ── Cinematic / Poster keywords ────────────────────────────────────────
    "cinematic_action": [
        "action movie", "action poster", "cinematic action", "blockbuster",
        "hero poster", "war poster", "explosion",
        "phim hành động", "poster hành động", "phim hanh dong", "poster hanh dong",
        "poster chiến tranh", "poster chien tranh",
    ],
    "cinematic_fantasy": [
        "fantasy movie", "fantasy poster", "fantasy art", "epic poster", "magical poster",
        "elf", "dragon",
        "phim kỳ ảo", "poster kỳ ảo", "phim ky ao", "poster ky ao",
        "phim thần thoại", "poster thần thoại", "phim than thoai", "poster than thoai",
        "phép thuật", "rồng",
    ],
    "cinematic_horror": [
        "horror movie", "horror poster", "thriller poster", "dark psychological", "ghost poster",
        "phim kinh dị", "poster kinh dị", "phim kinh di", "poster kinh di",
        "tâm lý kinh dị", "tam ly kinh di", "ma",
    ],
    # ── Premium advertising keywords ──────────────────────────────────────
    "luxury_ad": [
        "luxury ad", "luxury brand", "luxury perfume", "luxury watch",
        "premium ad", "high-end ad",
        "thương hiệu xa xỉ", "thuong hieu xa xi", "quảng cáo xa xỉ", "quang cao xa xi",
        "quảng cáo cao cấp", "quang cao cao cap",
        "đồng hồ cao cấp", "nước hoa cao cấp", "chai nước hoa",
    ],
    "tech_futuristic_ad": [
        "tech ad", "futuristic ad", "hi-tech poster", "sci-fi ad", "neon tech", "digital ad",
        "quảng cáo công nghệ", "quang cao cong nghe",
        "quảng cáo tương lai", "quang cao tuong lai", "công nghệ tương lai",
    ],
    "fashion_magazine": [
        "fashion magazine", "magazine cover", "avant-garde",
        "editorial fashion ad", "high fashion ad", "vogue style ad",
        "tạp chí thời trang", "tap chi thoi trang", "bìa tạp chí", "bia tap chi",
    ],
    "streetwear_ad": [
        "streetwear", "street style ad", "urban fashion", "graffiti style",
        "hypebeast", "sneaker culture", "skateboard", "skate brand",
        "quảng cáo đường phố", "quang cao duong pho",
        "thời trang đường phố", "thoi trang duong pho",
    ],
    "organic_eco": [
        "organic", "eco", "natural product", "green ad", "sustainable",
        "eco-friendly", "vegan product", "organic beauty",
        "sản phẩm hữu cơ", "san pham huu co",
        "quảng cáo xanh", "quang cao xanh", "thuần chay", "thuan chay",
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
                "my_custom_style": ("en style...", "vi style...")
            }
        })
    """
    _overrides.update(data)


def _get_styles() -> dict[str, tuple[str, str]]:
    return {**_STYLES, **_overrides.get("photography_styles", {})}


def _get_platform_specs() -> dict[str, dict[str, str]]:
    return {**_PLATFORM_SPECS, **_overrides.get("platform_specs", {})}


def _get_content_keywords() -> dict[str, list[str]]:
    return {**_CONTENT_TYPE_KEYWORDS, **_overrides.get("content_type_keywords", {})}


def _get_universal_suffix(lang: str | None = None) -> str:
    if lang == "vi":
        return _overrides.get("universal_quality_suffix_vi", _UNIVERSAL_QUALITY_SUFFIX_VI)
    return _overrides.get("universal_quality_suffix", _UNIVERSAL_QUALITY_SUFFIX)


def _get_content_insights() -> dict[str, tuple[str, str]]:
    return {**_CONTENT_INSIGHTS, **_overrides.get("content_insights", {})}


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


def get_style_for_content(content_type: str | None, lang: str | None = None) -> str | None:
    """Return the photography style preset string for a content type.

    Args:
        content_type: Content type key, e.g. ``'food'``.
        lang: Language code. ``'vi'`` returns Vietnamese style string.

    Returns ``None`` if no mapping exists for ``content_type``.
    """
    if not content_type:
        return None
    style_key = _CONTENT_TYPE_TO_STYLE.get(content_type)
    if not style_key:
        return None
    style_tuple = _get_styles().get(style_key)
    if not style_tuple:
        return None
    # style_tuple is (en, vi); fall back to en when lang is not vi
    return style_tuple[1] if lang == "vi" else style_tuple[0]


def get_content_insight(content_type: str | None, *, lang: str | None = None) -> str | None:
    """Return the audience/communication insight for a detected topic."""
    if not content_type:
        return None
    insight_tuple = _get_content_insights().get(content_type)
    if not insight_tuple:
        return None
    return insight_tuple[1] if lang == "vi" else insight_tuple[0]


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
    detected = content_type or detect_content_type(prompt)
    insight = get_content_insight(detected, lang=lang)
    style = get_style_for_content(detected, lang=lang)

    parts: list[str] = []

    if insight:
        parts.append(insight)

    if style:
        parts.append(style)

    if platform:
        specs = _get_platform_specs().get(platform, {})
        style_note = specs.get("style_note")
        if style_note:
            parts.append(style_note)

    parts.append(_get_universal_suffix(lang=lang))

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
    Compact format: enough signal for the LLM to understand full capabilities,
    minimal tokens wasted on redundant descriptions.
    """
    styles = _get_styles()
    platforms = list(_get_platform_specs().keys())

    # Group styles by category for better LLM comprehension
    photography_styles = [
        "product_hero", "product_lifestyle", "product_packshot",
        "fashion_editorial", "fashion_lookbook", "fashion_street",
        "food_hero", "food_beverage", "food_restaurant",
        "beauty_product", "beauty_portrait",
        "interior_design", "real_estate",
        "portrait_professional", "lifestyle_authentic",
        "tech_product", "jewelry", "candle_decor",
        "kids_product", "fitness", "pet", "wildlife_nature",
    ]
    cinematic_styles = [
        "cinematic_action", "cinematic_fantasy", "cinematic_horror",
    ]
    ad_styles = [
        "luxury_ad", "tech_futuristic_ad", "fashion_magazine",
        "streetwear_ad", "organic_eco",
    ]

    photo_list = "\n".join(
        f"  • {k}: {styles[k][0][:90]}…"
        for k in photography_styles if k in styles
    )
    cinematic_list = "\n".join(
        f"  • {k}: {styles[k][0][:90]}…"
        for k in cinematic_styles if k in styles
    )
    ad_list = "\n".join(
        f"  • {k}: {styles[k][0][:90]}…"
        for k in ad_styles if k in styles
    )
    platforms_str = ", ".join(platforms)

    return f"""## Vidtory Creative Knowledge

### Style Library ({len(styles)} styles available)

**Photography & Commercial** ({len(photography_styles)} styles):
{photo_list}

**Cinematic Poster** ({len(cinematic_styles)} styles — action/fantasy/horror movie posters):
{cinematic_list}

**Premium Advertising** ({len(ad_styles)} styles — luxury/tech/streetwear/eco ads):
{ad_list}

### Supported Output Platforms
{platforms_str}

### Professional Prompt Principles
1. **Subject** — Clearly describe the hero element (product/person/scene/character)
2. **Style** — Apply style from library above matching the content type
3. **Lighting** — Specify light source, direction, quality (key/fill/rim/neon/candlelight)
4. **Composition** — Framing, angle, focal point, typography placement
5. **Mood** — Color palette, atmosphere, emotional register
6. **Typography** — For poster/ad: font style, material (metallic/wood/liquid/glass), placement
7. **Technical** — Resolution (8K/4K), sharpness, post-processing

### Auto-Enhancement Pipeline (applied automatically by generate_image tool)
1. Detect content type from prompt → select matching style from library
2. Apply audience insight (what viewers must feel at first glance)
3. Apply professional style preset (lighting, composition, texture language)
4. Append universal quality suffix
5. Inject customer brand guidelines (colors, logo, tone)
6. Select optimal aspect ratio for customer's primary channel

### When to Use Which Style
- User says "poster phim / movie poster" → cinematic_action / cinematic_fantasy / cinematic_horror
- User says "quảng cáo xa xỉ / luxury ad" → luxury_ad
- User says "quảng cáo tương lai / futuristic / hi-tech" → tech_futuristic_ad
- User says "đường phố / streetwear / graffiti" → streetwear_ad
- User says "hữu cơ / organic / eco / thuần chay" → organic_eco
- User says "tạp chí thời trang / fashion magazine" → fashion_magazine
"""
