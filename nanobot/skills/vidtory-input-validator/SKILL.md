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
| subject | ✅ REQUIRED | What to create (product, person, scene...) |
| purpose | ✅ REQUIRED | Where it will be used (Instagram, website, ad...) |
| style/mood | 🔶 RECOMMENDED | Visual style (minimalist, luxury, vibrant...) |
| aspect_ratio | 🔶 RECOMMENDED | Frame ratio (1:1, 9:16, 16:9...) |
| reference_image | 🔸 OPTIONAL | Reference photo for style or product |
| text_overlay | 🔸 OPTIONAL | Text to display on image |

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

## Natural Language → API Mapping

When customer uses casual language, map to API values:
- "vuông", "feed IG", "1:1" → `IMAGE_ASPECT_RATIO_SQUARE`
- "dọc", "story", "reels", "tiktok", "9:16" → `IMAGE_ASPECT_RATIO_PORTRAIT`
- "ngang", "youtube", "landscape", "16:9" → `IMAGE_ASPECT_RATIO_LANDSCAPE`
- "studio" → prompt includes "studio lighting, clean backdrop"
- "ngoài trời" → prompt includes "outdoor, natural light"
- "thời trang" → load fashion industry knowledge
