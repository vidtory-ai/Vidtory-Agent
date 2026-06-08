---
name: image-generation
description: Native image generation skill using the generate_image tool.
---

# Image Generation

Use the `generate_image` tool when the user asks to create an image, photo, or any visual artwork.

## Guidelines

1. **Detailed Prompting**: Expand the user's short request into a detailed visual prompt. Include the main subject, style, lighting, and composition.
2. **Aspect Ratio**: By default, generate square images (`1:1`). If the user specifies for a story/reels/tiktok, use `9:16`. If for youtube/desktop, use `16:9`.
3. **Artifact Handling**: The `generate_image` tool will return a local path. You MUST use the `message` tool to send this media file back to the user.
4. **Reference Images**: If the user uploads/provides an image and asks to edit it or generate something inspired by it (e.g. "tạo ảnh quảng cáo cho con gấu trong hình" or "làm giống ảnh này"), you MUST pass the path of the user's image (which appears as `[image: /path/to/file.jpg]` in the user's message) to the `reference_images` parameter of `generate_image` as a list.

## Example

```text
generate_image(
  prompt="A highly detailed and beautiful advertisement photography of a premium sneaker shoe, dynamic lighting, 8k, photorealistic",
  reference_images=["C:\\Users\\vidto\\.gemini\\antigravity-ide\\nanobot\\media\\telegram\\file_0.jpg"],
  aspect_ratio="1:1"
)
```
