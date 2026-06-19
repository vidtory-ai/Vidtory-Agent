"""
Tests for UpdateCustomerProfileTool — brand info parsing & normalization.

Covers:
- Color name → HEX normalization (Vietnamese + English)
- Brand style free-text normalization (aliases + keywords)
- All new fields: color_accent, logo_url, onboarding_complete
- Bulk onboarding scenario (many fields at once)
- Partial update doesn't overwrite existing data
- No-op when no fields provided
"""

from __future__ import annotations

import pytest

from nanobot.agent.tools.customer_profile_tool import (
    _normalize_brand_style,
    _normalize_color,
)


# ===========================================================================
# _normalize_color
# ===========================================================================

class TestNormalizeColor:
    """Unit tests for the color name → HEX normalization helper."""

    def test_valid_hex_6_chars(self):
        assert _normalize_color("#1A2B3C") == "#1A2B3C"
        assert _normalize_color("1A2B3C") == "#1A2B3C"

    def test_valid_hex_lowercase(self):
        assert _normalize_color("#ff0000") == "#FF0000"

    def test_valid_hex_3_chars_expanded(self):
        result = _normalize_color("#FFF")
        assert result == "#FFFFFF"
        result2 = _normalize_color("#000")
        assert result2 == "#000000"

    def test_english_color_names(self):
        assert _normalize_color("white") == "#FFFFFF"
        assert _normalize_color("black") == "#000000"
        assert _normalize_color("navy") == "#1A237E"
        assert _normalize_color("gold") == "#FFC107"

    def test_vietnamese_color_names(self):
        assert _normalize_color("trắng") == "#FFFFFF"
        assert _normalize_color("đen") == "#000000"
        assert _normalize_color("tím") == "#8E24AA"
        assert _normalize_color("hồng") == "#E91E8C"
        assert _normalize_color("xanh navy") == "#1A237E"

    def test_pastel_colors(self):
        result = _normalize_color("tím pastel")
        assert result == "#C9A8E0"
        result2 = _normalize_color("hồng pastel")
        assert result2 == "#FFB6C1"
        result3 = _normalize_color("pastel pink")
        assert result3 == "#FFB6C1"

    def test_special_colors(self):
        assert _normalize_color("rose gold") == "#B76E79"
        assert _normalize_color("vàng gold") == "#FFC107"
        assert _normalize_color("xanh ngọc") == "#00897B"

    def test_case_insensitive(self):
        assert _normalize_color("NAVY") == "#1A237E"
        assert _normalize_color("Navy Blue") == "#1A237E"
        assert _normalize_color("TÍM PASTEL") == "#C9A8E0"

    def test_unknown_color_returned_asis(self):
        """Unknown colors should be returned as-is, not silently dropped."""
        result = _normalize_color("electric fuchsia")
        assert result == "electric fuchsia"

    def test_partial_match(self):
        """Partial keyword match should still resolve."""
        result = _normalize_color("xanh lá nhạt")
        # Should match 'xanh' keyword
        assert result.startswith("#")

    def test_whitespace_stripped(self):
        assert _normalize_color("  navy  ") == "#1A237E"


# ===========================================================================
# _normalize_brand_style
# ===========================================================================

class TestNormalizeBrandStyle:
    """Unit tests for the brand style normalization helper."""

    def test_preset_values_pass_through(self):
        for style in ["luxury", "playful", "corporate", "natural", "minimalist"]:
            assert _normalize_brand_style(style) == style

    def test_vietnamese_luxury_aliases(self):
        assert _normalize_brand_style("sang trọng") == "luxury"
        assert _normalize_brand_style("cao cấp") == "luxury"
        assert _normalize_brand_style("hạng sang") == "luxury"
        assert _normalize_brand_style("xa xỉ") == "luxury"

    def test_vietnamese_playful_aliases(self):
        assert _normalize_brand_style("vui tươi") == "playful"
        assert _normalize_brand_style("trẻ trung") == "playful"
        assert _normalize_brand_style("năng động") == "playful"

    def test_vietnamese_minimalist_aliases(self):
        assert _normalize_brand_style("tối giản") == "minimalist"
        assert _normalize_brand_style("sạch sẽ") == "minimalist"
        assert _normalize_brand_style("đơn giản") == "minimalist"

    def test_english_aliases(self):
        assert _normalize_brand_style("premium") == "luxury"
        assert _normalize_brand_style("high-end") == "luxury"
        assert _normalize_brand_style("fun") == "playful"
        assert _normalize_brand_style("creative") == "playful"
        assert _normalize_brand_style("business") == "corporate"
        assert _normalize_brand_style("formal") == "corporate"
        assert _normalize_brand_style("organic") == "natural"
        assert _normalize_brand_style("clean") == "minimalist"
        assert _normalize_brand_style("simple") == "minimalist"

    def test_keyword_match(self):
        assert _normalize_brand_style("ultra-luxury brand") == "luxury"
        assert _normalize_brand_style("minimalistic design") == "minimalist"
        assert _normalize_brand_style("eco-friendly") == "natural"

    def test_custom_style_preserved(self):
        """Unknown styles should be kept as-is."""
        assert _normalize_brand_style("vintage y2k") == "vintage y2k"
        assert _normalize_brand_style("brutalist") == "brutalist"
        assert _normalize_brand_style("cyberpunk neon") == "cyberpunk neon"

    def test_case_insensitive(self):
        assert _normalize_brand_style("LUXURY") == "luxury"
        assert _normalize_brand_style("Sang Trọng") == "luxury"

    def test_whitespace_stripped(self):
        assert _normalize_brand_style("  luxury  ") == "luxury"


# ===========================================================================
# UpdateCustomerProfileTool.execute() — integration tests
# ===========================================================================

@pytest.fixture
def mock_profile() -> dict:
    """Minimal profile dict for testing tool.execute()."""
    return {
        "telegramUserId": "test_user_42",
        "telegramUsername": "testuser",
        "onboarding": {"status": "minimal"},
        "business": {"name": "Old Name"},
        "brand": {
            "style": "corporate",
            "moodKeywords": ["old"],
            "colorPalette": {"primary": "#000000"},
            "avoidList": [],
            "logoUrl": "",
        },
        "audience": {},
        "contentChannels": {},
        "learningData": {},
    }


@pytest.fixture
def tool_with_profile(mock_profile, tmp_path, monkeypatch):
    """Return a configured UpdateCustomerProfileTool with mocked DB."""
    from nanobot.db.customer_db import CustomerDatabase
    db = CustomerDatabase(tmp_path / "test.db")
    db.save_profile("test_user_42", mock_profile)

    # Patch the process-wide singleton so customer_profile._db() returns our test DB
    monkeypatch.setattr("nanobot.db.customer_db._db_instance", db)

    from nanobot.utils.context_vars import telegram_customer_profile
    token = telegram_customer_profile.set(mock_profile)

    from nanobot.agent.tools.customer_profile_tool import UpdateCustomerProfileTool
    tool = UpdateCustomerProfileTool()

    yield tool, db

    telegram_customer_profile.reset(token)
    db.close()



class TestUpdateCustomerProfileToolExecute:

    @pytest.mark.asyncio
    async def test_color_accent_field_saved(self, tool_with_profile):
        tool, db = tool_with_profile
        result = await tool.execute(color_accent="tím pastel")
        assert "color_accent" in result
        assert "#C9A8E0" in result

        profile = db.load_profile("test_user_42")
        assert profile["brand"]["colorPalette"]["accent"] == "#C9A8E0"

    @pytest.mark.asyncio
    async def test_color_primary_name_converted(self, tool_with_profile):
        tool, db = tool_with_profile
        result = await tool.execute(color_primary="navy blue")
        assert "#1A237E" in result

        profile = db.load_profile("test_user_42")
        assert profile["brand"]["colorPalette"]["primary"] == "#1A237E"

    @pytest.mark.asyncio
    async def test_brand_style_vietnamese_normalized(self, tool_with_profile):
        tool, db = tool_with_profile
        result = await tool.execute(brand_style="sang trọng")
        assert "luxury" in result

        profile = db.load_profile("test_user_42")
        assert profile["brand"]["style"] == "luxury"
        assert profile["brand"]["styleConfirmed"] is True

    @pytest.mark.asyncio
    async def test_brand_style_custom_preserved(self, tool_with_profile):
        tool, db = tool_with_profile
        await tool.execute(brand_style="vintage y2k")

        profile = db.load_profile("test_user_42")
        assert profile["brand"]["style"] == "vintage y2k"

    @pytest.mark.asyncio
    async def test_logo_url_saved(self, tool_with_profile):
        tool, db = tool_with_profile
        logo = "https://cdn.example.com/brand-logo.png"
        result = await tool.execute(logo_url=logo)
        assert "logo_url" in result

        profile = db.load_profile("test_user_42")
        assert profile["brand"]["logoUrl"] == logo

        # Also check indexed column
        assert db.get_logo_url("test_user_42") == logo

    @pytest.mark.asyncio
    async def test_onboarding_complete_flag(self, tool_with_profile):
        tool, db = tool_with_profile
        result = await tool.execute(
            business_name="FinalShop",
            onboarding_complete=True,
        )
        assert "Onboarding hoàn tất" in result

        profile = db.load_profile("test_user_42")
        assert profile["onboarding"]["status"] == "completed"
        assert "completedAt" in profile["onboarding"]

    @pytest.mark.asyncio
    async def test_partial_update_preserves_existing(self, tool_with_profile):
        """Updating one field should NOT erase other fields."""
        tool, db = tool_with_profile
        await tool.execute(business_name="NewName")

        profile = db.load_profile("test_user_42")
        # brand should be untouched
        assert profile["brand"]["style"] == "corporate"
        assert profile["brand"]["moodKeywords"] == ["old"]
        # business name should be updated
        assert profile["business"]["name"] == "NewName"

    @pytest.mark.asyncio
    async def test_no_fields_returns_error(self, tool_with_profile):
        tool, _ = tool_with_profile
        result = await tool.execute()
        assert "No fields provided" in result

    @pytest.mark.asyncio
    async def test_bulk_onboarding_all_fields(self, tool_with_profile):
        """Simulate user dumping all brand info at once."""
        tool, db = tool_with_profile
        result = await tool.execute(
            business_name="Bloom Shop",
            industry="fashion",
            business_description="Thời trang nữ gen Z",
            brand_style="vintage y2k",
            mood_keywords=["vintage", "y2k", "pastel", "trendy"],
            color_primary="hồng pastel",
            color_secondary="trắng",
            color_accent="tím lavender",
            photography_style="soft light, pastel tones, lifestyle",
            avoid_list=["ảnh tối", "brutal", "cartoon"],
            target_gender="female",
            age_range="18-25",
            segment="mid",
            channels=["instagram", "tiktok", "facebook"],
            logo_url="https://cdn.example.com/bloom-logo.png",
            onboarding_complete=True,
        )

        # Confirm success
        assert "✅" in result
        assert "Onboarding hoàn tất" in result

        profile = db.load_profile("test_user_42")

        # Business
        assert profile["business"]["name"] == "Bloom Shop"
        assert profile["business"]["industry"] == "fashion"

        # Brand
        assert profile["brand"]["style"] == "vintage y2k"
        assert "pastel" in profile["brand"]["moodKeywords"]
        palette = profile["brand"]["colorPalette"]
        assert palette["primary"] == "#FFB6C1"    # hồng pastel → HEX
        assert palette["secondary"] == "#FFFFFF"  # trắng → #FFFFFF
        assert palette["accent"] == "#E6E6FA"     # tím lavender → HEX
        assert "ảnh tối" in profile["brand"]["avoidList"]
        assert profile["brand"]["logoUrl"] == "https://cdn.example.com/bloom-logo.png"

        # Audience
        assert profile["audience"]["gender"] == "female"
        assert profile["audience"]["ageRange"] == "18-25"

        # Channels (all 3 registered)
        assert "instagram" in profile["contentChannels"]["primary"]
        assert "tiktok" in profile["contentChannels"]["primary"]
        assert "facebook" in profile["contentChannels"]["primary"]

        # Auto-formats
        fmt = profile["contentChannels"]["defaultFormats"]
        assert fmt["instagram_feed"]["aspectRatio"] == "1:1"
        assert fmt["tiktok"]["aspectRatio"] == "9:16"
        assert fmt["facebook"]["aspectRatio"] == "4:3"

        # Onboarding
        assert profile["onboarding"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_zalo_channel_format(self, tool_with_profile):
        """Zalo channel should auto-set 1:1 format."""
        tool, db = tool_with_profile
        await tool.execute(channels=["zalo"])
        profile = db.load_profile("test_user_42")
        assert profile["contentChannels"]["defaultFormats"]["zalo"]["aspectRatio"] == "1:1"

    @pytest.mark.asyncio
    async def test_color_accent_hex_passed_through(self, tool_with_profile):
        """Direct HEX codes should be normalized but not changed."""
        tool, db = tool_with_profile
        await tool.execute(color_accent="#FF5733")
        profile = db.load_profile("test_user_42")
        assert profile["brand"]["colorPalette"]["accent"] == "#FF5733"

    @pytest.mark.asyncio
    async def test_context_var_updated_after_save(self, tool_with_profile):
        """In-memory ContextVar should be updated immediately after save."""
        from nanobot.utils.context_vars import telegram_customer_profile
        tool, _ = tool_with_profile
        await tool.execute(business_name="ContextTest")
        updated = telegram_customer_profile.get()
        assert updated["business"]["name"] == "ContextTest"

    @pytest.mark.asyncio
    async def test_logo_local_path_upload(self, tool_with_profile, monkeypatch, tmp_path):
        """Passing a local path to logo_url should upload it to CDN first."""
        tool, db = tool_with_profile

        # Create a dummy logo file
        local_logo_path = tmp_path / "dummy_logo.png"
        local_logo_path.write_bytes(b"PNG dummy content")

        # Set API key for the user so upload authorization succeeds
        db.set_api_key("test_user_42", "dummy_key")

        # Mock upload_logo_to_cdn
        async def mock_upload(source, api_key, base_url, customer_id):
            assert str(source) == str(local_logo_path)
            return "https://cdn.example.com/uploaded-logo.png"

        monkeypatch.setattr(
            "nanobot.utils.logo_upload.upload_logo_to_cdn",
            mock_upload
        )

        result = await tool.execute(logo_url=str(local_logo_path))
        assert "logo_url" in result

        profile = db.load_profile("test_user_42")
        assert profile["brand"]["logoUrl"] == "https://cdn.example.com/uploaded-logo.png"
        assert db.get_logo_url("test_user_42") == "https://cdn.example.com/uploaded-logo.png"



# ===========================================================================
# logo_preference field — UpdateCustomerProfileTool
# ===========================================================================

class TestLogoPreferenceField:
    """Tests for the logo_preference parameter added in commit 38c9d46.

    Verifies that UpdateCustomerProfileTool correctly persists the logoSuppressed
    flag to the database for all valid and invalid input values.
    """

    @pytest.mark.asyncio
    async def test_logo_preference_disabled_sets_suppressed_true(self, tool_with_profile):
        """logo_preference='disabled' must persist logoSuppressed=True in DB."""
        tool, db = tool_with_profile

        result = await tool.execute(logo_preference="disabled")

        # Tool must report success and name the field
        assert "logoSuppressed" in result
        assert "True" in result

        # DB must have the flag set
        profile = db.load_profile("test_user_42")
        assert profile["preferences"]["logoSuppressed"] is True

    @pytest.mark.asyncio
    async def test_logo_preference_enabled_sets_suppressed_false(self, tool_with_profile):
        """logo_preference='enabled' must persist logoSuppressed=False in DB."""
        tool, db = tool_with_profile

        # Pre-seed suppressed=True to make the transition meaningful
        profile = db.load_profile("test_user_42")
        profile.setdefault("preferences", {})["logoSuppressed"] = True
        db.save_profile("test_user_42", profile)

        result = await tool.execute(logo_preference="enabled")

        assert "logoSuppressed" in result
        assert "False" in result

        updated = db.load_profile("test_user_42")
        assert updated["preferences"]["logoSuppressed"] is False

    @pytest.mark.asyncio
    async def test_logo_preference_invalid_value_is_ignored(self, tool_with_profile):
        """An unrecognised logo_preference value must not crash and must not change the DB."""
        tool, db = tool_with_profile

        # Confirm no preferences key exists before the call
        profile_before = db.load_profile("test_user_42")
        preferences_before = profile_before.get("preferences", {})

        # Should return the "no fields" message because only the invalid
        # logo_preference was passed and it is silently dropped.
        result = await tool.execute(logo_preference="maybe")

        assert "No fields provided" in result

        # DB must be unchanged
        profile_after = db.load_profile("test_user_42")
        assert profile_after.get("preferences", {}) == preferences_before

    @pytest.mark.asyncio
    async def test_logo_preference_round_trip_disabled_then_enabled(self, tool_with_profile):
        """Toggling disabled → enabled must correctly flip the flag both ways."""
        tool, db = tool_with_profile

        # Step 1: disable
        await tool.execute(logo_preference="disabled")
        profile = db.load_profile("test_user_42")
        assert profile["preferences"]["logoSuppressed"] is True

        # Step 2: re-enable
        await tool.execute(logo_preference="enabled")
        profile = db.load_profile("test_user_42")
        assert profile["preferences"]["logoSuppressed"] is False

    @pytest.mark.asyncio
    async def test_logo_preference_case_insensitive(self, tool_with_profile):
        """logo_preference value matching must be case-insensitive."""
        tool, db = tool_with_profile

        await tool.execute(logo_preference="DISABLED")
        profile = db.load_profile("test_user_42")
        assert profile["preferences"]["logoSuppressed"] is True

        await tool.execute(logo_preference="Enabled")
        profile = db.load_profile("test_user_42")
        assert profile["preferences"]["logoSuppressed"] is False

    @pytest.mark.asyncio
    async def test_logo_preference_does_not_overwrite_other_fields(self, tool_with_profile):
        """Setting logo_preference must not touch unrelated brand fields."""
        tool, db = tool_with_profile

        await tool.execute(logo_preference="disabled")

        profile = db.load_profile("test_user_42")
        # Brand fields from the mock_profile fixture must be untouched
        assert profile["brand"]["style"] == "corporate"
        assert profile["brand"]["moodKeywords"] == ["old"]
        assert profile["business"]["name"] == "Old Name"


# ===========================================================================
# Color normalization edge cases
# ===========================================================================

class TestColorNormalizationEdgeCases:

    def test_empty_string_returns_empty(self):
        # Empty input shouldn't crash
        result = _normalize_color("")
        assert result == ""

    def test_hex_without_hash(self):
        assert _normalize_color("FF5733") == "#FF5733"

    def test_3digit_hex_without_hash(self):
        assert _normalize_color("FFF") == "#FFFFFF"

    def test_all_vietnamese_pastels(self):
        pastels = {
            "tím pastel": "#C9A8E0",
            "hồng pastel": "#FFB6C1",
            "xanh pastel": "#AED6F1",
            "vàng pastel": "#FFF9A0",
            "cam pastel": "#FFDAB9",
        }
        for name, expected in pastels.items():
            result = _normalize_color(name)
            assert result == expected, f"Failed for '{name}': got {result}, expected {expected}"
