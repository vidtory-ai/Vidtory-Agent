from __future__ import annotations

from nanobot.utils.image_delivery import build_image_delivery


def test_build_image_delivery_uses_brand_product_channel_and_memory() -> None:
    profile = {
        "business": {
            "name": "Vidtory",
            "industry": "technology",
            "description": "Nền tảng sáng tạo nội dung cho doanh nghiệp",
        },
        "brand": {
            "style": "tối giản hiện đại",
            "moodKeywords": ["chuyên nghiệp", "thân thiện"],
            "colorPalette": {"primary": "#102A43", "accent": "#2EC4B6"},
        },
        "contentChannels": {"primary": ["facebook"]},
        "learningData": {
            "commonFeedback": ["chữ quá nhỏ"],
            "bestPerformingPrompts": ["bố cục tối giản cao cấp, ánh sáng tự nhiên"],
        },
    }

    delivery = build_image_delivery(
        prompt=(
            "Ghép 2 linh vật thành ảnh quảng bá công ty chuyên nghiệp, "
            "có tiêu đề lớn và chữ dễ đọc"
        ),
        profile=profile,
        reference_count=2,
    )

    message = delivery["message"]
    assert "Đã kết hợp 2 ảnh tham chiếu" in message
    assert "Vidtory" in message
    assert "Design note:" in message
    assert "chữ quá nhỏ" in message
    assert "1️⃣" in message
    assert "2️⃣" in message
    assert "3️⃣" in message
    assert "Facebook" in message
    assert "Nền tảng sáng tạo nội dung cho doanh nghiệp" in message
    assert len(delivery["suggestions"]) == 3


def test_build_image_delivery_falls_back_cleanly_without_profile() -> None:
    delivery = build_image_delivery(
        prompt="Tạo một ảnh sản phẩm cao cấp",
        profile=None,
        reference_count=0,
    )

    assert "Đã tạo ảnh" in delivery["message"]
    assert "Design note:" in delivery["message"]
    assert len(delivery["suggestions"]) == 3


def test_delivery_uses_one_generic_strategy_for_unseen_subjects() -> None:
    profile = {
        "business": {
            "name": "Atelier Mới",
            "description": "Không gian thử nghiệm vật liệu và văn hóa",
        },
        "contentChannels": {"primary": ["instagram"]},
    }

    delivery = build_image_delivery(
        prompt="Tạo key visual cho triển lãm gốm sinh học siêu thực",
        profile=profile,
        reference_count=0,
    )

    message = delivery["message"]
    assert "Atelier Mới" in message
    assert "Không gian thử nghiệm vật liệu và văn hóa" in message
    assert "Instagram" in message
    assert "linh vật" not in message
    assert "sản phẩm là điểm nhìn chính" not in message
    assert "da tự nhiên" not in message
