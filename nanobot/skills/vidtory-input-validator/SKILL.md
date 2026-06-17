---
name: vidtory-input-validator
description: Validates creative request completeness and asks smart follow-up questions.
always: true
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
- **KHÔNG BAO GIỜ** tự bịa logo, tên thương hiệu, slogan, màu sắc
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

### Rule 7: Phân biệt Subject vs Purpose — BẮT BUỘC HỎI KHI MÔ TẢ MƠ HỒ

Khi khách chỉ nêu mục đích/chủ đề chung chung mà CHƯA có subject cụ thể — ví dụ:
- "tạo ảnh tuyển sinh", "ảnh quảng cáo", "ảnh thu hút khách"
- "tạo ảnh vinh danh thầy cô", "ảnh tri ân", "ảnh kỷ niệm"
- "tạo ảnh sự kiện", "ảnh hội nghị", "ảnh khai giảng"
- "ảnh chào mừng", "ảnh giải thưởng", "ảnh thành tích"

→ **BẮT BUỘC DỪNG và hỏi** về hình ảnh cụ thể muốn thể hiện. KHÔNG được tự ý tạo.

**Format câu hỏi chuẩn:**
```
Để tạo ảnh [mục đích] đẹp và đúng ý, bạn muốn hình ảnh thể hiện gì?

1️⃣ [Gợi ý hướng A — ví dụ cụ thể]
2️⃣ [Gợi ý hướng B — ví dụ cụ thể]
3️⃣ [Gợi ý hướng C — ví dụ cụ thể]

Nếu muốn, trả lời theo mẫu:
• Hướng ảnh: ...
• Dòng chữ trên ảnh: ...
• Tỷ lệ: 1:1 / 9:16 / 16:9
```

**Điều kiện ĐƯỢC phép tạo ngay** (không cần hỏi thêm):
- Khách đã mô tả chủ thể cụ thể (nhân vật, vật thể, cảnh vật) trong yêu cầu
- Khách cung cấp ảnh tham khảo kèm yêu cầu
- Khách đã trả lời câu hỏi follow-up của bot trước đó trong cùng cuộc hội thoại

### Rule 8: TUYỆT ĐỐI KHÔNG gợi ý /brand, /setlogo trong phản hồi thông thường

**KHÔNG BAO GIỜ** thêm đoạn footer kiểu:
```
❌ "Nhân tiện, mình đang dùng nhận diện [tên] có sẵn. Bạn có thể dùng /brand để..."
❌ "Nếu muốn cập nhật logo chuẩn hơn, bạn dùng /setlogo..."
❌ "Bạn có thể xem brand profile bằng /brand..."
```

Các lệnh `/brand`, `/setlogo`, `/profile` CHỈ được nhắc đến khi:
- Khách HỎI về brand hoặc logo
- Khách YÊU CẦU cập nhật thông tin thương hiệu
- Hệ thống phát hiện thiếu logo và đã hỏi trước (qua onboarding gate)

**Lý do:** Những footer này gây cảm giác bot chưa hiểu đủ thông tin, trông thiếu chuyên nghiệp và làm khách mất tập trung vào kết quả chính.

## Natural Language → API Mapping

When customer uses casual language, map to API values:
- "vuông", "feed IG", "1:1" → `IMAGE_ASPECT_RATIO_SQUARE`
- "dọc", "story", "reels", "tiktok", "9:16" → `IMAGE_ASPECT_RATIO_PORTRAIT`
- "ngang", "youtube", "landscape", "16:9" → `IMAGE_ASPECT_RATIO_LANDSCAPE`
- "studio" → prompt includes "ánh sáng studio, nền sạch"
- "ngoài trời" → prompt includes "ngoài trời, ánh sáng tự nhiên"
- "thời trang" → load fashion industry knowledge
