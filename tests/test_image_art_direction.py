from __future__ import annotations

from nanobot.utils.image_art_direction import build_art_direction_instruction


def test_art_direction_is_universal_for_unseen_topics() -> None:
    portrait = build_art_direction_instruction(
        "Chân dung một nữ doanh nhân trong văn phòng", lang="vi"
    )
    abstract_ceramics = build_art_direction_instruction(
        "Không gian trưng bày gốm sinh học siêu thực", lang="vi"
    )

    assert portrait == abstract_ceramics
    assert "Nếu có người thật" in portrait
    assert "Nếu là minh họa" in portrait
    assert "Nếu có chữ" in portrait


def test_universal_art_direction_covers_realism_illustration_and_typography() -> None:
    instruction = build_art_direction_instruction(
        "Một chủ đề hoàn toàn mới chưa có trong thư viện",
        lang="vi",
    )

    assert "kết cấu da tự nhiên" in instruction
    assert "không giống đồ chơi nhựa" in instruction
    assert "phân cấp chữ" in instruction
    assert "tiêu đề" in instruction
    assert "màu nhấn" in instruction
    assert "không dùng cùng một cỡ" in instruction
    assert "giới hạn lượng chữ" in instruction
