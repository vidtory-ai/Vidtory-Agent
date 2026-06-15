from nanobot.utils.brand_profile_view import render_brand_profile


def test_render_brand_profile_is_safe_for_html_and_legacy_field_types() -> None:
    profile = {
        "business": {
            "name": "Vidtory & Co",
            "industry": "technology <AI>",
            "description": "Nền tảng sáng tạo nội dung",
        },
        "brand": {
            "style": "modern",
            "moodKeywords": "hiện đại",
            "colorPalette": "#17250D",
            "photographyStyle": "clean tech",
            "logoUrl": "https://example.com/logo.png?size=2&mode=fit",
            "avoidList": None,
        },
        "audience": {"ageRange": "18-35", "segment": "B2B"},
        "contentChannels": {"primary": "LinkedIn"},
        "onboarding": {"status": "in_progress"},
        "learningData": {
            "totalGenerations": "unknown",
            "approvedCount": "1",
            "rejectedCount": 0,
        },
    }

    view = render_brand_profile(profile)

    assert "Vidtory &amp; Co" in view.text
    assert "technology &lt;AI&gt;" in view.text
    assert "#17250D" in view.text
    assert 'href="https://example.com/logo.png?size=2&amp;mode=fit"' in view.text
    assert "Hiệu suất:" not in view.text
    assert "Trạng thái:" not in view.text
    assert "Độ hoàn thiện:" not in view.text
    assert view.show_logo_preview is True
    assert view.buttons


def test_render_brand_profile_uses_professional_compact_copy() -> None:
    profile = {
        "business": {
            "name": "Vidtory",
            "industry": "technology",
            "description": "Công ty công nghệ hiện đại",
        },
        "brand": {
            "style": "minimalist",
            "moodKeywords": ["hiện đại", "công nghệ"],
            "colorPalette": {
                "primary": "#17250D",
                "secondary": "#152A16",
                "accent": "#162F1E",
            },
            "photographyStyle": "modern clean tech aesthetic",
            "logoUrl": "https://example.com/logo.png",
            "avoidList": ["quá hoạt hình", "quá rối"],
        },
        "audience": {"ageRange": "", "segment": "mid"},
        "contentChannels": {"primary": []},
        "onboarding": {"status": "minimal"},
        "learningData": {},
    }

    view = render_brand_profile(profile)

    assert "<b>Brand Profile</b>" in view.text
    assert "Hiệu suất:" not in view.text
    assert "Trạng thái:" not in view.text
    assert "Độ hoàn thiện:" not in view.text
    assert "Có thể bổ sung:" in view.text
    assert "Nếu tiện" not in view.text
    assert view.buttons == [
        ["Bổ sung profile", "Để sau"],
        ["Thay logo", "Tạo thiết kế"],
    ]
