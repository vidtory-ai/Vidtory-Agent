from __future__ import annotations

from io import BytesIO

from PIL import Image

from nanobot.utils.brand_intelligence import (
    analyze_logo_bytes,
    build_adaptive_onboarding_step,
    build_creative_suggestions,
    detect_brand_update_intent,
    get_profile_gaps,
    should_offer_onboarding,
)


def _profile(*, industry: str = "food") -> dict:
    return {
        "business": {"name": "Vidtory", "industry": industry, "description": ""},
        "brand": {
            "style": "",
            "moodKeywords": [],
            "colorPalette": {},
            "photographyStyle": "",
            "logoUrl": "",
        },
        "audience": {"gender": "all", "ageRange": "", "segment": "mid"},
        "contentChannels": {"primary": [], "defaultFormats": {}},
        "preferences": {"communicationLanguage": "vi"},
        "learningData": {"totalGenerations": 0},
    }


def test_detects_natural_language_brand_update_without_slash_command():
    assert detect_brand_update_intent(
        "Từ nay hãy đổi phong cách thương hiệu sang tối giản, cao cấp cho tôi"
    )


def test_does_not_steal_an_image_edit_request():
    assert not detect_brand_update_intent(
        "Sửa phong cách ảnh này sang tối giản và thêm chữ khuyến mãi"
    )


def test_profile_gaps_prioritize_visual_identity_after_business_fields():
    gaps = get_profile_gaps(_profile())
    assert gaps[:3] == ["business_description", "logo", "brand_style"]


def test_adaptive_onboarding_uses_industry_specific_choices():
    profile = _profile(industry="food")
    profile["business"]["description"] = "Nhà hàng món Việt hiện đại"
    step = build_adaptive_onboarding_step(profile)

    assert step["field"] == "logo"
    assert "logo" in step["prompt"].lower()
    assert step["buttons"] == [["Gửi logo", "Nhập website"], ["Chưa có logo"]]


def test_logo_analysis_extracts_palette_and_dynamic_style():
    image = Image.new("RGB", (100, 100), "#E53935")
    for x in range(65, 100):
        for y in range(100):
            image.putpixel((x, y), (253, 216, 53))
    payload = BytesIO()
    image.save(payload, format="PNG")

    result = analyze_logo_bytes(payload.getvalue())

    assert result["colorPalette"]["primary"] == "#E53935"
    assert result["colorPalette"]["secondary"] == "#FDD835"
    assert result["style"] == "playful"
    assert result["confidence"] >= 0.8


def test_creative_suggestions_follow_request_instead_of_generic_styles():
    suggestions = build_creative_suggestions(
        "Thiết kế story tuyển dụng lập trình viên tại Hà Nội",
        industry="technology",
    )

    assert suggestions == [
        "Công nghệ chuyên nghiệp",
        "Trẻ trung năng động",
        "Tối giản dễ đọc",
    ]


def test_onboarding_reminder_is_progressive_instead_of_every_turn():
    profile = _profile()
    profile["learningData"]["totalGenerations"] = 4
    assert not should_offer_onboarding(profile, "Tạo ảnh sản phẩm mới")

    profile["learningData"]["totalGenerations"] = 10
    assert should_offer_onboarding(profile, "Tạo ảnh sản phẩm mới")


def test_onboarding_completeness_reaches_hundred_only_when_no_gaps():
    from nanobot.utils.customer_profile import get_onboarding_completeness

    profile = _profile()
    profile["business"]["description"] = "Nền tảng sáng tạo cho doanh nghiệp"
    profile["brand"].update({
        "logoUrl": "https://cdn.example/logo.png",
        "style": "corporate",
        "moodKeywords": ["tin cậy"],
        "photographyStyle": "clean commercial",
        "colorPalette": {"primary": "#1565C0"},
    })
    profile["audience"]["ageRange"] = "25-44"
    profile["contentChannels"]["primary"] = ["facebook"]

    assert get_profile_gaps(profile) == []
    assert get_onboarding_completeness(profile) == 100


def test_agent_context_routes_brand_update_and_exposes_button_suggestions():
    from nanobot.agent.loop import AgentLoop
    from nanobot.bus.events import InboundMessage

    profile = _profile(industry="technology")
    message = InboundMessage(
        channel="telegram",
        sender_id="u1",
        chat_id="c1",
        content="Từ nay đổi phong cách thương hiệu sang tối giản hiện đại",
        metadata={"onboarding_status": "minimal", "customer_profile": profile},
    )

    lines = AgentLoop._build_customer_context_lines(message)
    joined = "\n".join(lines)
    assert "[BRAND_UPDATE_INTENT]" in joined
    assert "update_customer_profile" in joined
    assert "KHÔNG tạo ảnh" in joined


def test_prompt_knowledge_adds_topic_specific_customer_insight():
    from nanobot.utils.vidtory_knowledge import (
        build_professional_prompt_suffix,
        detect_content_type,
    )

    prompt = "Thiết kế story tuyển dụng lập trình viên tại Hà Nội"
    assert detect_content_type(prompt) == "recruitment"
    suffix = build_professional_prompt_suffix(prompt, lang="vi")
    assert "ứng viên" in suffix
    assert "dễ đọc trên điện thoại" in suffix
