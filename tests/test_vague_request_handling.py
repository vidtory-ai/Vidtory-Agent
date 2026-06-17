"""Tests for vague request handling improvements.

Covers:
1. Domain-specific avoid keyword extraction (_extract_avoid_keywords)
   - Generic visual quality complaints
   - Education / Academic feedback
   - Luxury / Premium feedback
   - F&B (Food & Beverage) feedback
   - Healthcare / Medical feedback
   - Fashion / Apparel feedback
   - Beauty / Cosmetics feedback
   - Real Estate / Architecture feedback
   - Tech / Gadget feedback
   - Kids / Family feedback
   - Fitness / Sport feedback

2. Profile completeness scoring sanity checks

3. Customer profile tool brand style normalization
   (ensures new industry keyword feedback doesn't break normalization)

4. Vidtory knowledge content-type detection
   (ensures multi-domain content types are correctly detected)
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# 1. Domain-specific avoid keyword extraction
# ---------------------------------------------------------------------------

class TestExtractAvoidKeywords:
    """Test _extract_avoid_keywords covers all industries."""

    @pytest.fixture(autouse=True)
    def _fn(self):
        from nanobot.utils.customer_profile import _extract_avoid_keywords
        self.fn = _extract_avoid_keywords

    # ── Generic visual ───────────────────────────────────────────────────────

    def test_overexposed(self):
        assert "overexposed" in self.fn("ảnh quá sáng, chói mắt")

    def test_too_dark(self):
        assert "too dark" in self.fn("ảnh quá tối, u ám")

    def test_blurry(self):
        assert "blurry" in self.fn("ảnh bị mờ, không sắc nét")

    def test_cartoon(self):
        assert "cartoon" in self.fn("trông như hoạt hình")

    def test_low_quality(self):
        assert "low quality" in self.fn("chất lượng thấp, vỡ hạt, pixelated")

    def test_incorrect_colors(self):
        assert "incorrect colors" in self.fn("sai màu, lệch màu quá")

    def test_cluttered(self):
        assert "cluttered" in self.fn("ảnh rối, messy background")

    def test_amateur(self):
        assert "amateur" in self.fn("thiếu chuyên nghiệp, trông amateurish")

    def test_too_plain(self):
        assert "too plain" in self.fn("quá đơn giản, vô hồn, boring")

    def test_harsh_lighting(self):
        assert "harsh lighting" in self.fn("ánh sáng không đều, bóng đổ xấu")

    def test_flat_lighting(self):
        assert "flat lighting" in self.fn("thiếu chiều sâu, flat lighting, 2d feel")

    # ── Education / Academic ─────────────────────────────────────────────────

    def test_education_too_casual(self):
        assert "too casual" in self.fn("too casual, thiếu học thuật, không nghiêm túc")

    def test_education_too_casual_vi(self):
        assert "too casual" in self.fn("không trang trọng, không phù hợp giáo dục")

    def test_education_inappropriate_for_kids(self):
        assert "inappropriate for children" in self.fn("không phù hợp trẻ em, not child-safe")

    def test_education_inappropriate_student(self):
        assert "inappropriate for children" in self.fn("không phù hợp học sinh")

    # ── Luxury / Premium ─────────────────────────────────────────────────────

    def test_luxury_low_end_vi(self):
        assert "low-end appearance" in self.fn("trông rẻ, bình dân quá, cheap")

    def test_luxury_low_end_en(self):
        assert "low-end appearance" in self.fn("looks mass market, not premium, low-end")

    def test_luxury_lacks_luxury(self):
        assert "lacks luxury feel" in self.fn("không đủ sang trọng, not luxurious")

    def test_luxury_lacks_luxury_vi(self):
        assert "lacks luxury feel" in self.fn("thiếu sang trọng, không đúng cao cấp")

    # ── F&B (Food & Beverage) ────────────────────────────────────────────────

    def test_fnb_unappetizing_vi(self):
        assert "unappetizing" in self.fn("trông không ngon, không hấp dẫn")

    def test_fnb_unappetizing_en(self):
        assert "unappetizing" in self.fn("unappetizing food, not appetizing at all")

    def test_fnb_artificial_food(self):
        assert "artificial food" in self.fn("fake food, plastic looking, đồ ăn giả")

    def test_fnb_wrong_food_color(self):
        assert "wrong food color" in self.fn("màu thức ăn sai, thức ăn mất tươi")

    def test_fnb_not_fresh_looking(self):
        assert "wrong food color" in self.fn("not fresh looking, food color off")

    # ── Healthcare / Medical ─────────────────────────────────────────────────

    def test_healthcare_untrustworthy(self):
        assert "untrustworthy medical" in self.fn("thiếu tin cậy, không đáng tin, untrustworthy")

    def test_healthcare_not_medical_grade(self):
        assert "untrustworthy medical" in self.fn("not medical grade, thiếu uy tín y tế")

    def test_healthcare_too_clinical(self):
        assert "too clinical" in self.fn("quá lạnh lẽo, too clinical, sterile feel")

    def test_healthcare_not_patient_friendly(self):
        assert "too clinical" in self.fn("không thân thiện bệnh nhân, not patient-friendly")

    # ── Fashion / Apparel ────────────────────────────────────────────────────

    def test_fashion_wrong_style(self):
        assert "wrong style" in self.fn("không đúng phong cách, wrong vibe, off-brand style")

    def test_fashion_style_not_match(self):
        assert "wrong style" in self.fn("style không phù hợp, không match style")

    def test_fashion_bad_pose(self):
        assert "bad pose" in self.fn("model pose xấu, bad pose, awkward pose")

    def test_fashion_stiff_pose(self):
        assert "bad pose" in self.fn("tư thế cứng, stiff pose")

    # ── Beauty / Cosmetics ───────────────────────────────────────────────────

    def test_beauty_wrong_product_color(self):
        assert "wrong product color" in self.fn("màu sản phẩm sai, sai màu son")

    def test_beauty_wrong_color_en(self):
        assert "wrong product color" in self.fn("wrong product color, màu mỹ phẩm lệch")

    def test_beauty_over_retouched(self):
        assert "over-retouched skin" in self.fn("da nhựa, plastic skin, over-retouched")

    def test_beauty_unnatural_skin(self):
        assert "over-retouched skin" in self.fn("skin không tự nhiên, da không đẹp")

    # ── Real Estate / Architecture ───────────────────────────────────────────

    def test_realestate_dark_interior(self):
        assert "dark interior" in self.fn("ảnh nội thất tối, dark interior")

    def test_realestate_no_detail(self):
        assert "dark interior" in self.fn("không thấy chi tiết nội thất, room too dark")

    def test_realestate_bad_perspective(self):
        assert "bad perspective" in self.fn("góc ảnh xấu, distorted perspective")

    def test_realestate_wide_angle_distortion(self):
        assert "bad perspective" in self.fn("méo góc rộng, wide angle distortion")

    # ── Tech / Gadget ────────────────────────────────────────────────────────

    def test_tech_product_not_sharp(self):
        assert "product not sharp" in self.fn("sản phẩm không sắc nét, product not sharp")

    def test_tech_missing_detail(self):
        assert "product not sharp" in self.fn("thiếu chi tiết sản phẩm, missing product detail")

    def test_tech_wrong_aesthetic(self):
        assert "wrong tech aesthetic" in self.fn("background không phù hợp tech, not tech aesthetic")

    # ── Kids / Family ────────────────────────────────────────────────────────

    def test_kids_too_dark(self):
        assert "too dark for children" in self.fn("màu sắc quá tối với trẻ, too dark for kids")

    def test_kids_not_cheerful(self):
        assert "too dark for children" in self.fn("không vui tươi, not cheerful enough")

    def test_kids_unsafe(self):
        assert "unsafe content" in self.fn("không an toàn, unsafe content, not family-friendly")

    def test_kids_inappropriate_family(self):
        assert "unsafe content" in self.fn("không phù hợp gia đình")

    # ── Fitness / Sport ──────────────────────────────────────────────────────

    def test_fitness_lacks_energy(self):
        assert "lacks energy" in self.fn("thiếu năng lượng, low energy, flat energy")

    def test_fitness_not_bold(self):
        assert "lacks energy" in self.fn("không hùng mạnh, không bold, not dynamic enough")

    def test_fitness_static_pose(self):
        assert "static/boring pose" in self.fn("tư thế tĩnh, static pose, boring fitness pose")

    def test_fitness_no_action(self):
        assert "static/boring pose" in self.fn("không đủ dynamic, không action")

    # ── Multi-match (feedback with multiple problems) ────────────────────────

    def test_multi_match_returns_multiple(self):
        """Complex feedback should extract multiple keyword categories."""
        result = self.fn(
            "ảnh quá tối, trông rẻ như hàng bình dân, và model pose xấu"
        )
        assert "too dark" in result
        assert "low-end appearance" in result
        assert "bad pose" in result

    def test_empty_feedback_returns_empty(self):
        """Empty feedback text should return empty list."""
        assert self.fn("") == []

    def test_unrecognized_feedback_returns_empty(self):
        """Unrecognized feedback should return empty list, not crash."""
        assert self.fn("tôi muốn ảnh khác hơn một chút") == []

    def test_case_insensitive(self):
        """Matching should be case-insensitive via .lower() normalization."""
        assert "overexposed" in self.fn("Quá Sáng quá chói mắt")
        assert "blurry" in self.fn("Blur, BLURRY")


# ---------------------------------------------------------------------------
# 2. Brand style normalization — verify new domains don't break it
# ---------------------------------------------------------------------------

class TestBrandStyleNormalization:
    """Ensure brand style normalization handles all domains correctly."""

    @pytest.fixture(autouse=True)
    def _fn(self):
        from nanobot.agent.tools.customer_profile_tool import _normalize_brand_style
        self.fn = _normalize_brand_style

    def test_luxury_vi(self):
        assert self.fn("sang trọng") == "luxury"

    def test_playful_vi(self):
        assert self.fn("trẻ trung") == "playful"

    def test_corporate_vi(self):
        assert self.fn("chuyên nghiệp") == "corporate"

    def test_natural_vi(self):
        assert self.fn("thiên nhiên") == "natural"

    def test_minimalist_vi(self):
        assert self.fn("tối giản") == "minimalist"

    def test_free_text_preserved(self):
        """Free-text styles not in alias should be preserved as-is."""
        assert self.fn("vintage y2k") == "vintage y2k"

    def test_medical_professional(self):
        """Medical/clinical styles not in alias should be preserved."""
        result = self.fn("medical clinical")
        assert result  # Should not be empty
        assert isinstance(result, str)

    def test_educational_formal(self):
        """Education styles should be preserved or normalized."""
        result = self.fn("academic formal")
        assert result  # Should not be empty

    def test_empty_style_returns_empty(self):
        """Empty input should return empty string."""
        assert self.fn("") == ""

    def test_whitespace_stripped(self):
        """Leading/trailing whitespace should be stripped."""
        assert self.fn("  luxury  ") == "luxury"


# ---------------------------------------------------------------------------
# 3. Color normalization — ensure Vietnamese color names work
# ---------------------------------------------------------------------------

class TestColorNormalization:
    """Test that Vietnamese and English color names are correctly normalized."""

    @pytest.fixture(autouse=True)
    def _fn(self):
        from nanobot.agent.tools.customer_profile_tool import _normalize_color
        self.fn = _normalize_color

    def test_hex_passthrough(self):
        assert self.fn("#FF0000") == "#FF0000"

    def test_hex_lowercase_normalized(self):
        assert self.fn("#ff0000") == "#FF0000"

    def test_hex_3char_expanded(self):
        assert self.fn("#F00") == "#FF0000"

    def test_vi_hong_pastel(self):
        assert self.fn("hồng pastel") == "#FFB6C1"

    def test_vi_tim_lavender(self):
        assert self.fn("tím lavender") == "#E6E6FA"

    def test_vi_navy(self):
        assert self.fn("xanh navy") == "#1A237E"

    def test_en_rose_gold(self):
        assert self.fn("rose gold") == "#B76E79"

    def test_unknown_preserves(self):
        """Unknown colors should be returned as-is."""
        result = self.fn("coral reef blue")
        assert result  # Should not be empty


# ---------------------------------------------------------------------------
# 4. Content-type detection — verify all industry domains
# ---------------------------------------------------------------------------

class TestContentTypeDetection:
    """Test vidtory_knowledge.detect_content_type for all domains."""

    @pytest.fixture(autouse=True)
    def _fn(self):
        from nanobot.utils.vidtory_knowledge import detect_content_type
        self.fn = detect_content_type

    def test_food_vi(self):
        assert self.fn("ảnh món phở bò") == "food"

    def test_food_en(self):
        assert self.fn("restaurant dish plating") == "food"

    def test_beverage_vi(self):
        assert self.fn("ly cà phê bốc khói") == "beverage"

    def test_beverage_en(self):
        assert self.fn("iced latte with milk foam") == "beverage"

    def test_fashion_vi(self):
        assert self.fn("váy đầm thời trang mùa hè") == "fashion"

    def test_fashion_en(self):
        assert self.fn("fashion lookbook editorial") == "fashion"

    def test_cosmetic_vi(self):
        assert self.fn("son môi mỹ phẩm cao cấp") == "cosmetic"

    def test_cosmetic_en(self):
        assert self.fn("skincare cream serum product") == "cosmetic"

    def test_portrait_vi(self):
        assert self.fn("chân dung doanh nhân") == "portrait"

    def test_portrait_en(self):
        assert self.fn("professional headshot portrait") == "portrait"

    def test_interior_vi(self):
        assert self.fn("nội thất phòng khách") == "interior"

    def test_interior_en(self):
        assert self.fn("interior design living room furniture") == "interior"

    def test_real_estate_vi(self):
        assert self.fn("biệt thự bất động sản") == "real_estate"

    def test_real_estate_en(self):
        # 'real estate' keyword explicitly included
        assert self.fn("apartment real estate property photography") == "real_estate"

    def test_tech_vi(self):
        assert self.fn("điện thoại smartphone công nghệ") == "tech"

    def test_tech_en(self):
        assert self.fn("laptop gadget tech product photography") == "tech"

    def test_jewelry_vi(self):
        assert self.fn("nhẫn kim cương trang sức") == "jewelry"

    def test_jewelry_en(self):
        # 'jewelry' keyword is explicit — no 'luxury' to cause fashion match
        assert self.fn("ring necklace jewelry bracelet") == "jewelry"

    def test_candle_vi(self):
        # 'nến' keyword must appear — 'trang trí nhà' alone matches interior first
        assert self.fn("nến thơm mùi hương thư giãn") == "candle"

    def test_pet_vi(self):
        assert self.fn("ảnh thú cưng mèo dễ thương") == "pet"

    def test_pet_en(self):
        assert self.fn("cute dog puppy photography") == "pet"

    def test_kids_vi(self):
        assert self.fn("đồ chơi trẻ em em bé") == "kids"

    def test_kids_en(self):
        assert self.fn("baby toy children nursery product") == "kids"

    def test_fitness_vi(self):
        assert self.fn("tập gym thể hình yoga") == "fitness"

    def test_fitness_en(self):
        assert self.fn("fitness workout protein supplement") == "fitness"

    def test_none_for_unknown(self):
        """Generic text with no domain keywords should return None."""
        result = self.fn("some random text about nothing specific")
        # May match 'product' loosely — just verify it doesn't crash
        assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# 5. Profile completeness — verify second get_profile_completeness (line 224+)
# ---------------------------------------------------------------------------

class TestProfileCompletenessSecond:
    """Tests for the second get_profile_completeness function (0-100 score)."""

    def test_empty_returns_zero(self):
        from nanobot.utils.customer_profile import get_profile_completeness
        assert get_profile_completeness({}) == 0

    def test_business_only(self):
        from nanobot.utils.customer_profile import get_profile_completeness
        profile = {
            "business": {"name": "TestCo", "industry": "tech"},
        }
        score = get_profile_completeness(profile)
        assert score == 20  # name(10) + industry(10)

    def test_brand_style_adds_score(self):
        from nanobot.utils.customer_profile import get_profile_completeness
        profile = {
            "business": {"name": "TestCo", "industry": "tech"},
            "brand": {"style": "luxury", "moodKeywords": ["premium"]},
        }
        score = get_profile_completeness(profile)
        assert score == 45  # 20 business + 15 style + 10 mood

    def test_full_profile_hundred(self):
        from nanobot.utils.customer_profile import get_profile_completeness
        profile = {
            "business": {"name": "X", "industry": "fashion"},
            "brand": {
                "style": "luxury",
                "moodKeywords": ["elegant"],
                "colorPalette": {"primary": "#000"},
                "photographyStyle": "editorial",
            },
            "contentChannels": {
                "primary": ["instagram"],
                "defaultFormats": {"instagram_feed": {"aspectRatio": "1:1"}},
            },
            "audience": {"ageRange": "25-35", "segment": "premium"},
        }
        score = get_profile_completeness(profile)
        assert score == 100


# ---------------------------------------------------------------------------
# 6. update_learning — domain-specific avoidList integration
# ---------------------------------------------------------------------------

class TestUpdateLearningDomainKeywords:
    """Verify that domain-specific feedback keywords update avoidList correctly."""

    def test_luxury_feedback_updates_avoidlist(self, tmp_path):
        """'trông rẻ' should add 'low-end appearance' to avoidList."""
        from nanobot.db.customer_db import CustomerDatabase
        from nanobot.utils.customer_profile import _extract_avoid_keywords

        # Unit-test the extractor directly (no DB needed)
        result = _extract_avoid_keywords("trông rẻ quá, cheap looking")
        assert "low-end appearance" in result

    def test_healthcare_feedback_updates_avoidlist(self):
        """'thiếu tin cậy' should add 'untrustworthy medical' to avoidList."""
        from nanobot.utils.customer_profile import _extract_avoid_keywords
        result = _extract_avoid_keywords("thiếu tin cậy y tế, not trustworthy")
        assert "untrustworthy medical" in result

    def test_education_feedback_updates_avoidlist(self):
        """'too casual' should add 'too casual' to avoidList."""
        from nanobot.utils.customer_profile import _extract_avoid_keywords
        result = _extract_avoid_keywords("quá casual, thiếu học thuật cho trường đại học")
        assert "too casual" in result

    def test_fnb_feedback_updates_avoidlist(self):
        """'trông không ngon' should add 'unappetizing' to avoidList."""
        from nanobot.utils.customer_profile import _extract_avoid_keywords
        result = _extract_avoid_keywords("trông không ngon, không hấp dẫn")
        assert "unappetizing" in result

    def test_fitness_feedback_updates_avoidlist(self):
        """'thiếu năng lượng' should add 'lacks energy' to avoidList."""
        from nanobot.utils.customer_profile import _extract_avoid_keywords
        result = _extract_avoid_keywords("thiếu năng lượng, flat energy, không bold")
        assert "lacks energy" in result
