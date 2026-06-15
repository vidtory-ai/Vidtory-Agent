---
name: image-generation
description: Native image generation skill using the generate_image tool.
---

# Image Generation

Use the `generate_image` tool when the user asks to create an image, photo, or any visual artwork.

## Guidelines

1. **Detailed Prompting**: Mở rộng yêu cầu ngắn thành prompt chi tiết. Bao gồm chủ thể, phong cách, ánh sáng, bố cục.
2. **Aspect Ratio**: Mặc định ảnh vuông (`1:1`). Story/reels/tiktok dùng `9:16`. Youtube/desktop dùng `16:9`.
3. **Artifact Handling**: Tool `generate_image` trả về đường dẫn. PHẢI dùng tool `message` để gửi file ảnh cho user.
4. **Reference Images**: Nếu user upload/gửi ảnh và yêu cầu chỉnh sửa hoặc tạo dựa trên ảnh (vd: "tạo ảnh quảng cáo cho con gấu trong hình" hay "làm giống ảnh này"), PHẢI truyền đường dẫn ảnh (xuất hiện dạng `[image: /path/to/file.jpg]` trong tin nhắn) vào tham số `reference_images` dưới dạng list.
   - Nếu user reply một ảnh cũ để sửa, ảnh reply là ảnh nguồn chính và phải đứng đầu `reference_images`.
   - Nếu user vừa reply ảnh cũ vừa gửi thêm ảnh mới, truyền tất cả theo thứ tự: ảnh reply, ảnh gửi mới.
   - Không đưa logo profile vào `reference_images`; tool tự gắn logo như asset thương hiệu cuối cùng.

### ⚠️ QUY TẮC NGÔN NGỮ — BẮT BUỘC
5. **Prompt tiếng Việt**: Khi ngôn ngữ giao tiếp là tiếng Việt, prompt PHẢI viết **100% tiếng Việt**. KHÔNG được lẫn lộn tiếng Anh.
6. **Thuật ngữ kỹ thuật**: Giữ nguyên thuật ngữ quốc tế (bokeh, 8K, HDR, f/2.8) nhưng mô tả phải bằng tiếng Việt.
7. **KHÔNG tự bịa thông tin**: KHÔNG tự thêm tên thương hiệu, logo, slogan vào prompt nếu không có trong Customer Profile. Nếu thiếu → hỏi khách cung cấp.
8. **Prompt gọn, không lặp luật hệ thống**: Chỉ mô tả phần giữ lại, phần cần thay đổi, chuỗi chữ chính xác, bố cục và phong cách. Không tự thêm chỉ dẫn logo dài, cảnh báo song ngữ hoặc tiêu chuẩn bố cục chung; tool sẽ áp dụng một lần.

### ⚠️ QUY TẮC XÁC NHẬN TRƯỚC KHI TẠO — BẮT BUỘC
9. **Yêu cầu mơ hồ → Hỏi trước, tạo sau**: Nếu yêu cầu chỉ có mục đích/chủ đề chung (ví dụ: "tạo ảnh vinh danh thầy cô", "ảnh tuyển sinh", "ảnh kỷ niệm", "ảnh sự kiện") mà KHÔNG có mô tả chủ thể cụ thể → **DỪNG, hỏi xác nhận** theo format của vidtory-input-validator Rule 7 trước khi gọi `generate_image`.
10. **Điều kiện được tạo ngay**: Yêu cầu có đủ chủ thể (người, vật, cảnh) + phong cách + mục đích. Ví dụ: "tạo ảnh nhóm sinh viên đứng trước campus PTIT phong cách hiện đại" → đủ thông tin, tạo ngay.

### ⚠️ QUY TẮC PHẢN HỒI — BẮT BUỘC
11. **KHÔNG thêm footer gợi ý lệnh**: Sau khi gửi ảnh, TUYỆT ĐỐI KHÔNG thêm các đoạn như:
    - "Nhân tiện, mình đang dùng nhận diện [tên] có sẵn..."
    - "Nếu muốn cập nhật logo, dùng /setlogo..."
    - "Bạn có thể xem brand profile bằng /brand..."
    
    Chỉ được gợi ý các biến thể ảnh tiếp theo (tỷ lệ khác, có chữ, màu khác) hoặc hỏi nếu cần thêm gì.

## Example

```text
generate_image(
  prompt="Ảnh quảng cáo giày sneaker cao cấp cực kỳ chi tiết và đẹp, ánh sáng động, 8K, siêu thực",
  reference_images=["C:\\Users\\vidto\\.gemini\\antigravity-ide\\nanobot\\media\\telegram\\file_0.jpg"],
  aspect_ratio="1:1"
)
```
