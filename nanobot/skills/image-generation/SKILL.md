---
name: image-generation
description: Native image generation skill using the generate_image tool.
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

### ⚠️ QUY TẮC NGÔN NGỮ — BẮT BUỘC
5. **Prompt tiếng Việt**: Khi ngôn ngữ giao tiếp là tiếng Việt, prompt PHẢI viết **100% tiếng Việt**. KHÔNG được lẫn lộn tiếng Anh.
6. **Thuật ngữ kỹ thuật**: Giữ nguyên thuật ngữ quốc tế (bokeh, 8K, HDR, f/2.8) nhưng mô tả phải bằng tiếng Việt.
7. **KHÔNG tự bịa thông tin**: KHÔNG tự thêm tên thương hiệu, logo, slogan vào prompt nếu không có trong Customer Profile. Nếu thiếu → hỏi khách cung cấp.

## Example

```text
generate_image(
  prompt="Ảnh quảng cáo giày sneaker cao cấp cực kỳ chi tiết và đẹp, ánh sáng động, 8K, siêu thực",
  reference_images=["C:\\Users\\vidto\\.gemini\\antigravity-ide\\nanobot\\media\\telegram\\file_0.jpg"],
  aspect_ratio="1:1"
)
```
