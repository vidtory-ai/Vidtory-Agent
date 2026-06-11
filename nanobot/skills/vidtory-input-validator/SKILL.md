---
name: vidtory-input-validator
description: Validates creative request completeness and asks smart follow-up questions.
---

# Input Validation & Smart Questioning

## Core Principle

NEVER generate content with insufficient input. Always validate first, ask targeted questions if needed, then generate.

## Input Requirements Matrix

### Image Generation
| Field | Status | Description |
|---|---|---|
| subject | ✅ REQUIRED | Chủ thể cụ thể (sản phẩm, nhân vật, cảnh vật, bố cục...) — Lưu ý: mục đích sử dụng ("tuyển sinh", "quảng cáo") KHÔNG phải là subject |
| purpose | ✅ REQUIRED | Nơi sử dụng (Instagram, website, ad...) |
| brand_assets | ✅ REQUIRED khi branding | Logo, ảnh thương hiệu — BẮT BUỘC khi nội dung liên quan đến thương hiệu/tổ chức cụ thể |
| style/mood | 🔶 RECOMMENDED | Phong cách thị giác (minimalist, luxury, vibrant...) |
| aspect_ratio | 🔶 RECOMMENDED | Tỉ lệ khung (1:1, 9:16, 16:9...) |
| reference_image | 🔸 OPTIONAL | Ảnh mẫu tham khảo |
| text_overlay | 🔸 OPTIONAL | Chữ cần hiển thị trên ảnh |

### Video Generation
| Field | Status | Description |
|---|---|---|
| subject | ✅ REQUIRED | What the video shows |
| purpose | ✅ REQUIRED | Platform/use case |
| duration | 🔶 RECOMMENDED | Length in seconds (default: 8) |
| motion_type | 🔶 RECOMMENDED | Camera movement (zoom, pan, static) |
| mode | 🔶 RECOMMENDED | t2v, i2v, or r2v |
| aspect_ratio | 🔶 RECOMMENDED | 16:9 or 9:16 |

### Audio Generation
| Field | Status | Description |
|---|---|---|
| script/text | ✅ REQUIRED | Content to speak |
| language | ✅ REQUIRED | Language code |
| purpose | ✅ REQUIRED | Voiceover, narration, ad... |
| voice_style | 🔶 RECOMMENDED | Warm, professional, energetic... |

## Completeness Scoring

Calculate completeness based on filled REQUIRED + RECOMMENDED fields:
- 🟢 ≥ 80% → Proceed to generation
- 🟡 40-79% → Ask TARGETED questions (only missing fields, max 3)
- 🔴 < 40% → Ask STRUCTURED questions (with numbered options)

## Questioning Rules

### Rule 1: Max 3 questions per message
Do not overwhelm the customer. Prioritize REQUIRED fields first.

### Rule 2: Always provide suggestions
```
❌ BAD: "Bạn muốn phong cách gì?"
✅ GOOD: "Phong cách nào phù hợp?
   1️⃣ Tối giản (Minimalist)
   2️⃣ Sang trọng (Luxury)
   3️⃣ Trẻ trung (Playful)
   Hoặc mô tả theo ý bạn"
```

### Rule 3: Smart fallback
When customer says "tuỳ bạn", "gì cũng được", "làm đẹp là được":
- Use Customer Knowledge preferences if available
- Otherwise use industry defaults from Vidtory Knowledge
- Tell the customer: "Tôi sẽ dùng phong cách [X]. Chỉnh sau nếu chưa ưng nhé!"

### Rule 4: Skip known info
If Customer Knowledge already has brand style, colors, and preferences:
- Do NOT ask about style, colors, or mood again
- Auto-apply from profile
- Only ask about subject-specific info (what product, what scene)

### Rule 5: KHÔNG tự bịa thông tin
Khi thiếu thông tin thương hiệu:
- **KHÔNG BAO GIỌ** tự bịa logo, tên thương hiệu, slogan, màu sắc
- Nếu yêu cầu nhắc đến tên thương hiệu/tổ chức mà không có trong Customer Profile → BẮT BUỘC hỏi:
```
Để tạo ảnh đúng nhận diện [tên], bạn gửi giúp mình:
📌 Logo (file ảnh, tốt nhất là PNG nền trong suốt)
📌 Màu thương hiệu chính
Hoặc dùng /setlogo để upload logo
```

### Rule 6: Ngôn ngữ thống nhất
- Prompt cuối cùng PHẢI thống nhất một ngôn ngữ
- Khi khách giao tiếp bằng tiếng Việt → prompt PHẢI 100% tiếng Việt
- KHÔNG lẫn lộn tiếng Anh và tiếng Việt trong cùng một prompt
- Thuật ngữ kỹ thuật quốc tế giữ nguyên: "bokeh", "8K", "HDR"

### Rule 7: Phân biệt Subject vs Purpose
Khi khách chỉ nêu mục đích sử dụng ("ảnh tuyển sinh", "ảnh quảng cáo", "ảnh thu hút khách"):
- Mục đích KHÔNG PHẢI là subject cụ thể
- BẮT BUỘC hỏi về hình ảnh cụ thể muốn thể hiện:
```
Để tạo ảnh [mục đích], bạn muốn hình ảnh thể hiện gì cụ thể?
1️⃣ [Gợi ý hướng A]
2️⃣ [Gợi ý hướng B]
3️⃣ [Gợi ý hướng C]
Hoặc mô tả thêm ý tưởng của bạn
```

## Natural Language → API Mapping

When customer uses casual language, map to API values:
- "vuông", "feed IG", "1:1" → `IMAGE_ASPECT_RATIO_SQUARE`
- "dọc", "story", "reels", "tiktok", "9:16" → `IMAGE_ASPECT_RATIO_PORTRAIT`
- "ngang", "youtube", "landscape", "16:9" → `IMAGE_ASPECT_RATIO_LANDSCAPE`
- "studio" → prompt includes "ánh sáng studio, nền sạch"
- "ngoài trời" → prompt includes "ngoài trời, ánh sáng tự nhiên"
- "thời trang" → load fashion industry knowledge
