from nanobot.agent.loop import extract_numbered_choice_buttons


def test_extract_numbered_choice_buttons_from_keycap_options() -> None:
    content = (
        "Bạn muốn tiếp tục theo hướng nào?\n"
        "1️⃣ Tạo poster tuyển dụng\n"
        "2️⃣ Chuyển mẫu cũ sang Vidtory\n"
        "3️⃣ Tạo banner công nghệ"
    )

    assert extract_numbered_choice_buttons(content) == [["1", "2", "3"]]


def test_extract_numbered_choice_buttons_from_four_keycap_options() -> None:
    content = (
        "Goi y nhanh:\n"
        "1\ufe0f\u20e3 TUYEN SINH DAI HOC 2026\n"
        "2\ufe0f\u20e3 PTIT 2026 - MO CUA TUONG LAI SO\n"
        "3\ufe0f\u20e3 KHAM PHA HANH TRINH CONG NGHE CUNG PTIT\n"
        "4\ufe0f\u20e3 Khong can chu, lam anh nen truoc"
    )

    assert extract_numbered_choice_buttons(content) == [["1", "2", "3"], ["4"]]


def test_extract_numbered_choice_buttons_from_plain_numbered_choices() -> None:
    content = (
        "Chọn một phương án:\n"
        "1. Giữ bảng màu hiện tại\n"
        "2. Tăng độ tương phản\n"
        "3. Nhập cấu hình riêng"
    )

    assert extract_numbered_choice_buttons(content) == [["1", "2", "3"]]


def test_extract_numbered_choice_buttons_ignores_instruction_steps() -> None:
    content = (
        "Cách cấu hình API key:\n"
        "1. Mở trang cài đặt\n"
        "2. Sao chép API key\n"
        "3. Gửi lệnh /apikey"
    )

    assert extract_numbered_choice_buttons(content) == []
