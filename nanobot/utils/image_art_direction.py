"""Prompt directives that keep generated images polished and believable."""

from __future__ import annotations

def build_art_direction_instruction(prompt: str, *, lang: str | None = None) -> str:
    """Return one medium-agnostic quality directive for every visual topic."""
    del prompt

    if lang == "vi":
        return (
            "Áp dụng chuẩn hoàn thiện phù hợp với nội dung thực tế của brief. Nếu có người thật: "
            "giữ kết cấu da tự nhiên, ánh mắt sống, bất đối xứng tự nhiên, tỷ lệ cơ thể và bàn tay "
            "đúng giải phẫu; tránh da sáp, da nhựa và làm mịn quá mức. Nếu là minh họa hoặc nhân vật: "
            "dùng ngôn ngữ hình khối rõ, silhouette dễ nhận diện, biểu cảm có chủ đích, phối màu và "
            "chiều sâu nhất quán; không giống đồ chơi nhựa hay 3D bóng loáng đại trà. Nếu là vật thể "
            "hoặc không gian: vật liệu, ánh sáng, bóng đổ và tỷ lệ phải hợp lý, tránh HDR giả và chi "
            "tiết ngẫu nhiên mang cảm giác AI. "
            "Nếu có chữ trên ảnh: GIỚI HẠN số lượng chữ ở mức tối thiểu cần thiết. "
            "Xây dựng phân cấp chữ rõ ràng: tiêu đề phải lớn hơn 2-3 lần so với nội dung phụ, "
            "dùng màu nhấn thương hiệu (không phải trắng thuần) cho tiêu đề — ví dụ: màu vàng gold, "
            "xanh neon, đỏ cam hoặc màu brand accent; thông tin phụ dùng màu nhạt hơn hoặc trắng nhỏ. "
            "Thêm hiệu ứng đẹp cho chữ: bóng mờ (drop shadow), viền sáng (outline/glow), gradient text, "
            "mảng nền bán trong suốt (frosted glass panel) hoặc dải màu gradient phía sau — "
            "tránh tuyệt đối chữ trắng thuần được đặt thẳng lên ảnh không có hiệu ứng gì. "
            "Giữ tương phản cao, căn lề cân đối, khoảng cách thoáng, vùng an toàn đủ đọc trên mobile."
        )
    return (
        "Apply the finish standard conditionally to the actual brief. If real people appear, preserve "
        "natural skin texture, lively eyes, natural asymmetry, and anatomically correct hands and body "
        "proportions; avoid waxy plastic skin and over-smoothing. If the work is illustrative, use "
        "intentional shape language, readable silhouettes, expressive posing, coherent color, and "
        "layered depth; avoid generic glossy 3D and plastic-toy materials. For objects or spaces, keep "
        "materials, scale, motivated light, and shadows physically plausible; avoid fake HDR and random "
        "AI artifacts. "
        "If text appears, keep copy minimal and build a CLEAR TYPOGRAPHIC HIERARCHY: headline must be "
        "2-3x larger than supporting copy; use brand accent colors (not plain white) for the headline — "
        "e.g. gold, brand orange, neon blue; apply visual effects: drop shadows, glows, gradient text, "
        "semi-transparent frosted panels or color gradient bands behind body text. "
        "NEVER place flat white text directly over the image with no treatment. "
        "Preserve high contrast, balanced alignment, generous spacing, and mobile-safe legibility."
    )
