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
```

## Enhancement Rules

### For IMAGE prompts:

Always include these elements in the enhanced prompt:
1. **Subject** — What the image shows (detailed description)
2. **Style** — Visual style from brand guidelines
3. **Composition** — Camera angle, framing, rule of thirds
4. **Lighting** — Lighting setup appropriate for the subject
5. **Color palette** — Brand colors integrated naturally
6. **Quality markers** — "sharp focus", "high resolution", "professional"
7. **Mood** — Emotional tone from brand keywords

Template:
```
{detailed_subject}, {style} style, {composition}, {lighting}, 
{color_palette} color scheme, {mood} atmosphere, 
professional {industry} photography, sharp focus, high resolution
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
### Customer: Hana Boutique (fashion, minimalist, black+gold)
### Output:
"Vietnamese Ao Dai dress, premium silk fabric, elegant woman model, minimalist composition with negative space, studio lighting with softbox key light and subtle rim light, black and gold color accents on clean white backdrop, three-quarter body shot, slightly elevated camera angle, commercial fashion photography for Instagram, sharp focus, high resolution, luxury premium feel"

### Input: "làm video giới thiệu sản phẩm mới"  
### Customer: Same as above
### Output:
"Cinematic product reveal of Vietnamese Ao Dai dress, slow camera orbit around the garment on a mannequin, dramatic lighting transitioning from shadow to spotlight, black and gold visual motifs, smooth dolly movement, luxury fashion commercial style, 8-second duration, 9:16 vertical format for Instagram Reels"
