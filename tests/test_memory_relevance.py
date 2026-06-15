from __future__ import annotations

from nanobot.utils.memory_relevance import (
    load_relevant_memory,
    profile_learning_entries,
    select_relevant_memory,
)


def test_relevant_project_and_feedback_beat_unrelated_memory() -> None:
    entries = [
        {
            "layer": "core",
            "key": "color_primary",
            "value": "#102A43",
            "confidence": 1.0,
            "is_locked": 1,
        },
        {
            "layer": "project",
            "key": "old_menu",
            "value": "Thực đơn mùa hè cho nhà hàng",
            "confidence": 1.0,
        },
        {
            "layer": "project",
            "key": "launch_hanoi",
            "value": "Sự kiện ra mắt tại Hà Nội, phong cách triển lãm tinh tế",
            "confidence": 0.9,
        },
        {
            "layer": "preference",
            "key": "common_feedback_0",
            "value": "Chữ từng bị quá nhỏ, cần ưu tiên khả năng đọc",
            "confidence": 0.9,
        },
        {
            "layer": "insight",
            "key": "unrelated",
            "value": "Khách từng thích ảnh món ăn chụp cận cảnh",
            "confidence": 1.0,
        },
    ]

    selected = select_relevant_memory(
        entries,
        query="Thiết kế poster sự kiện ra mắt tại Hà Nội, chữ phải dễ đọc",
        max_chars=260,
        max_entries=4,
    )

    keys = [entry["key"] for entry in selected]
    assert "color_primary" in keys
    assert "launch_hanoi" in keys
    assert "common_feedback_0" in keys
    assert "old_menu" not in keys
    assert "unrelated" not in keys


def test_unrelated_learned_prompt_does_not_bias_a_new_topic() -> None:
    selected = select_relevant_memory(
        [
            {
                "layer": "preference",
                "key": "best_prompt_0",
                "value": "Cận cảnh món ăn với hơi nóng và màu đỏ",
                "confidence": 0.95,
            },
            {
                "layer": "style",
                "key": "aesthetic",
                "value": "tinh tế tối giản",
                "confidence": 0.8,
            },
        ],
        query="Thiết kế không gian triển lãm vật liệu sinh học",
        max_chars=200,
    )

    keys = [entry["key"] for entry in selected]
    assert "best_prompt_0" not in keys
    assert "aesthetic" in keys


def test_memory_selection_respects_context_budget() -> None:
    entries = [
        {
            "layer": "preference",
            "key": f"preference_{index}",
            "value": f"Chi tiết sở thích số {index} " + ("rất dài " * 20),
            "confidence": 0.8,
        }
        for index in range(20)
    ]

    selected = select_relevant_memory(
        entries,
        query="Thiết kế mới",
        max_chars=180,
        max_entries=20,
    )

    serialized = "\n".join(
        f"{entry['layer']}:{entry['key']}={entry['value']}" for entry in selected
    )
    assert len(serialized) <= 180
    assert len(selected) < len(entries)


def test_profile_learning_is_normalized_into_rankable_memory() -> None:
    profile = {
        "learningData": {
            "commonFeedback": ["Chữ quá nhỏ", "Màu quá chói"],
            "bestPerformingPrompts": ["Ánh sáng tự nhiên, bố cục thoáng"],
        }
    }

    entries = profile_learning_entries(profile)

    assert {entry["key"] for entry in entries} == {
        "common_feedback_0",
        "common_feedback_1",
        "best_prompt_0",
    }
    assert all(entry["layer"] == "preference" for entry in entries)


def test_customer_context_uses_query_and_stays_within_budget() -> None:
    from nanobot.utils.customer_context import format_customer_context_lines

    profile = {
        "business": {
            "name": "Studio Không Giới Hạn",
            "description": "Thiết kế cho nhiều lĩnh vực khác nhau",
        },
        "brand": {"style": "tinh tế", "colorPalette": {"primary": "#123456"}},
        "learningData": {
            "commonFeedback": [
                "Ảnh món ăn trước đây bị tối",
                "Poster sự kiện trước đây có chữ quá nhỏ, cần dễ đọc",
                "Ảnh thời trang trước đây quá bão hòa",
            ],
            "bestPerformingPrompts": [
                "Bố cục thoáng, ánh sáng tự nhiên, điểm nhìn rõ"
            ],
        },
    }

    lines = format_customer_context_lines(
        profile,
        query="Thiết kế poster sự kiện với chữ dễ đọc",
        max_chars=420,
    )
    joined = "\n".join(lines)

    assert len(joined) <= 420
    assert "[CUSTOMER_MEMORY_DATA]" in joined
    assert "chữ quá nhỏ" in joined
    assert "Ảnh món ăn" not in joined


def test_prompt_brand_suffix_uses_relevant_learning_without_industry_rules() -> None:
    from nanobot.utils.customer_context import build_prompt_brand_suffix

    profile = {
        "business": {"industry": "một lĩnh vực chưa từng biết"},
        "brand": {"style": "tinh tế", "avoidList": []},
        "learningData": {
            "commonFeedback": ["Chữ trên poster sự kiện quá nhỏ"],
            "bestPerformingPrompts": ["Bố cục sự kiện thoáng, phân cấp rõ"],
        },
    }

    suffix = build_prompt_brand_suffix(
        profile,
        query="Tạo poster cho một sự kiện mới",
        max_chars=260,
    )

    assert len(suffix) <= 260
    assert "Bố cục sự kiện thoáng" in suffix
    assert "Chữ trên poster sự kiện quá nhỏ" in suffix


def test_memory_loading_uses_bounded_database_candidates() -> None:
    class FakeDB:
        def __init__(self) -> None:
            self.limit = 0

        def get_memory_candidates(self, user_id: str, limit: int = 0):
            self.limit = limit
            return [
                {
                    "layer": "core",
                    "key": "color_primary",
                    "value": "#123456",
                    "confidence": 1.0,
                }
            ]

        def get_all_memory(self, user_id: str):
            raise AssertionError("unbounded memory read must not be used")

    db = FakeDB()
    selected = load_relevant_memory(
        {"telegramUserId": "123"},
        query="Thiết kế mới",
        db=db,
    )

    assert db.limit == 200
    assert selected[0]["key"] == "color_primary"


def test_database_candidates_are_bounded_and_prioritize_locked_core(tmp_path) -> None:
    from nanobot.db.customer_db import CustomerDatabase

    db = CustomerDatabase(tmp_path / "memory.db")
    db.set_memory(
        "123",
        layer="preference",
        key="recent_preference",
        value="Một sở thích mới",
        confidence=1.0,
    )
    db.set_memory(
        "123",
        layer="core",
        key="color_primary",
        value="#123456",
        confidence=0.7,
        force=True,
    )

    candidates = db.get_memory_candidates("123", limit=1)

    assert len(candidates) == 1
    assert candidates[0]["layer"] == "core"
    assert candidates[0]["key"] == "color_primary"
