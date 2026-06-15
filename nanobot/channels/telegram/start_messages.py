from __future__ import annotations

from telegram.error import BadRequest


async def reply_with_markdown_fallback(message, text: str, **kwargs) -> None:
    """Reply with Markdown, then retry as plain text on entity parse errors."""
    try:
        await message.reply_text(text, **kwargs)
    except BadRequest:
        fallback_kwargs = dict(kwargs)
        fallback_kwargs.pop("parse_mode", None)
        await message.reply_text(text, **fallback_kwargs)


def api_key_setup_message(first_name: str) -> str:
    return (
        f"👋 *Xin chào {first_name}! Chào mừng bạn đến với Vidtory AI.*\n\n"
        "🤖 *Vidtory AI* là hệ thống trợ lý thiết kế tự động, đồng hành cùng doanh nghiệp và thương hiệu để tạo ra các ấn phẩm hình ảnh tiếp thị "
        "(ảnh sản phẩm, banner quảng cáo, bài viết mạng xã hội) đồng bộ thương hiệu chỉ trong vài giây.\n\n"
        "💡 *Giải pháp thiết kế từ Vidtory AI mang lại:*\n"
        "• *Đồng nhất thương hiệu:* Tự động nhận diện logo và màu sắc chủ đạo để áp dụng đồng bộ vào mọi ấn phẩm.\n"
        "• *Tối ưu hình ảnh tiếp thị:* Định hình phong cách thiết kế riêng biệt cho từng chiến dịch.\n"
        "• *Nhanh chóng và tiết kiệm:* Tạo hình ảnh chất lượng cao mà không cần quy trình chỉnh sửa phức tạp.\n\n"
        "🔑 *Để bắt đầu, vui lòng kết nối Vidtory API Key:*\n"
        "1. Truy cập: https://app.vidtory.net/settings/api\n"
        "2. Sao chép API Key của bạn\n"
        "3. Gửi lệnh: `/apikey YOUR_API_KEY`\n\n"
        "_Thiết lập này chỉ cần thực hiện một lần và hoàn toàn bảo mật._"
    )


def returning_customer_message(first_name: str) -> str:
    return (
        f"👋 *Chào mừng quay trở lại, {first_name}!* Vidtory AI đã sẵn sàng.\n\n"
        "Bạn muốn thực hiện công việc nào tiếp theo?\n"
        "• `/brand` - Xem và quản lý cấu hình thương hiệu.\n"
        "• `/new` - Khởi tạo một phiên thiết kế mới.\n"
        "• `/help` - Xem danh sách lệnh và hướng dẫn.\n\n"
        "Hãy gửi yêu cầu hoặc chọn lệnh để bắt đầu."
    )


def onboarding_choice_message(first_name: str) -> str:
    return (
        f"👋 *Xin chào {first_name}! Chào mừng bạn đến với Vidtory AI.*\n\n"
        "🤖 Vidtory AI giúp doanh nghiệp tạo hình ảnh tiếp thị đồng bộ thương hiệu "
        "như ảnh sản phẩm, banner quảng cáo và nội dung mạng xã hội.\n\n"
        "🚀 *Hãy bắt đầu thiết lập nhanh:*\n"
        "• Chọn *Bắt đầu khai báo* để thiết lập Brand Profile trong khoảng một phút.\n"
        "• Chọn *Dùng ngay* để gửi yêu cầu thiết kế trực tiếp."
    )
