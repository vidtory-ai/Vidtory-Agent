---
name: prompt-enhancer
description: Automatically enhances raw customer prompts into professional-grade prompts using brand context and design knowledge.
always: false
---

# Prompt Enhancement Engine

## Purpose

Transform simple, casual customer requests into detailed, professional prompts that produce high-quality outputs. This is the core differentiator that makes Vidtory AI produce better results than competitors.

## Enhancement Pipeline

```
Layer 1: Raw Input → Extract intent and subject
Layer 2: + Customer Knowledge → Brand colors, style, mood
Layer 3: + Industry Templates → Professional techniques
Layer 4: + Platform Specs → Format optimization
Layer 5: + Quality Keywords → Technical excellence
Layer 6: + Feedback Adjustments → Learned preferences
Layer 7: + Language Normalization → Thống nhất ngôn ngữ
```

## ⚠️ QUY TẮC NGÔN NGỮ — BẮT BUỘC

1. **Prompt cuối PHẢI thống nhất một ngôn ngữ** — không lẫn lộn
2. Khi khách giao tiếp bằng tiếng Việt → prompt PHẢI 100% tiếng Việt
3. Thuật ngữ kỹ thuật quốc tế giữ nguyên: "bokeh", "8K", "HDR", "f/2.8"
4. **KHÔNG BAO GIỌ** tự thêm tên thương hiệu, logo, slogan vào prompt nếu không có trong Customer Profile
5. Nếu thiếu thông tin thương hiệu → TRẢ VỀ cho agent để HỎI KHÁCH, không tự bịa

## Enhancement Rules

### For IMAGE prompts:

Always include these elements in the enhanced prompt:
1. **Chủ thể** — Mô tả chi tiết đối tượng chính của ảnh
2. **Phong cách** — Phong cách thị giác từ brand guidelines
3. **Bố cục** — Góc chụp, framing, quy tắc phần ba
4. **Ánh sáng** — Loại ánh sáng phù hợp với chủ thể
5. **Gam màu** — Màu thương hiệu tích hợp tự nhiên
6. **Chất lượng** — "nét sắc", "độ phân giải cao", "chuyên nghiệp"
7. **Tâm trạng** — Cảm xúc từ brand keywords

Template:
```
{chủ_thể_chi_tiết}, phong cách {style}, {bố_cục}, {ánh_sáng},
gam màu {bảng_màu}, không khí {tâm_trạng},
ảnh {ngành} chuyên nghiệp, nét sắc, độ phân giải cao
```

### For VIDEO prompts:

Always include:
1. **Scene description** — What happens in the video
2. **Motion** — Camera or subject movement
3. **Duration context** — Pacing appropriate for length
4. **Transition style** — Smooth, dynamic, or static
5. **Mood/music cue** — Emotional direction

### For AUDIO prompts:

Always consider:
1. **Tone** — Professional, warm, energetic
2. **Pacing** — Speed appropriate for content
3. **Emphasis** — Key words or phrases to stress
4. **Language nuance** — Natural Vietnamese/English flow

## Feedback-Based Adjustments

Before finalizing any prompt, check customer's `learningData.commonFeedback`:
- If pattern "nền quá sáng" exists → Add "dark/moody background" keywords
- If pattern "chữ khó đọc" exists → Add "high contrast text overlay"
- If pattern "quá đơn giản" exists → Add more detail and complexity
- Apply all adjustments with count ≥ 2

## Examples

### Input: "tạo ảnh áo dài"
### Customer: Hana Boutique (fashion, minimalist, đen+vàng)
### Output:
"Áo dài Việt Nam vải lụa cao cấp, người mẫu nữ thanh lịch, bố cục tối giản với khoảng trống âm, ánh sáng studio softbox chính và viền sáng tinh tế, điểm nhấn màu đen và vàng trên nền trắng sạch, chụp 3/4 người, góc máy hơi cao, ảnh thời trang thương mại cho Instagram, nét sắc, độ phân giải cao, cảm giác sang trọng cao cấp"

### Input: "làm video giới thiệu sản phẩm mới"  
### Customer: Tương tự như trên
### Output:
"Cảnh mở hộp sản phẩm áo dài Việt Nam điện ảnh, camera xoay chậm quanh trang phục trên mô hình, ánh sáng kịch tính chuyển từ bóng tối sang spotlight, hình ảnh đen và vàng chủ đạo, chuyển động camera đẩy mượt mà, phong cách quảng cáo thời trang cao cấp, thời lượng 8 giây, định dạng dọc 9:16 cho Instagram Reels"
