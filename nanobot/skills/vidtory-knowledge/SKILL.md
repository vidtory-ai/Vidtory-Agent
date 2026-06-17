---
name: vidtory-knowledge
description: Global design knowledge base with industry templates, prompt engineering guides, and quality standards. Used to enhance every creative output.
always: false
---

# Vidtory Knowledge — Design Intelligence

## Purpose

This is the shared knowledge base for ALL customers. It contains professional design principles, prompt templates by industry, platform specifications, and quality standards that the Agent uses to produce premium-quality outputs.

## Knowledge Directory

Located at `~/.vidtoryagent/knowledge/`. Load relevant files based on:
- Customer's **industry** → `industries/{industry}/`
- Content **type** (image/video/audio) → `prompt-engineering/`
- Target **platform** → `platform-specs/`

## How to Use Knowledge

### When enhancing a prompt:

1. **Identify industry** from Customer Knowledge → Load `industries/{industry}/prompt-templates.md`
2. **Identify content type** → Load `prompt-engineering/{type}-prompt-guide.md`
3. **Identify platform** → Load `platform-specs/{platform}.md`
4. **Apply quality standards** → Reference `quality-standards/`

### Enhancement Pipeline:

```
Raw customer input
  → + Subject details (from conversation)
  → + Customer brand context (from Customer Knowledge)
  → + Industry template (from Vidtory Knowledge)
  → + Platform optimization (from platform specs)
  → + Quality keywords (from quality standards)
  = Professional prompt ready for B2B API
```

### Example — Fashion Image:

Customer says: "tạo ảnh áo dài"

1. Load Customer Knowledge: brand=minimalist, colors=#000/#D4AF37
2. Load `industries/fashion/prompt-templates.md` → Product Shot template
3. Load `platform-specs/instagram.md` → 1:1 format, 1080x1080
4. Apply quality keywords

Enhanced prompt:
"Vietnamese Ao Dai dress, silk fabric, elegant model, minimalist composition, black and gold color accent, studio lighting with softbox key, clean white backdrop, full body shot, commercial fashion photography, Instagram-optimized square format, sharp focus, 8K detail"

## Knowledge Categories

### Industries
Each industry folder contains:
- `prompt-templates.md` — Prompt templates specific to the industry
- `photography-rules.md` — Photography guidelines
- Additional industry-specific files

### Prompt Engineering
- `image-prompt-guide.md` — How to write effective image prompts
- `video-prompt-guide.md` — Video prompt best practices
- `style-keywords-library.md` — Curated style keywords by mood

### Platform Specs
- `instagram.md` — IG feed (1:1), story (9:16), reels (9:16) specs
- `tiktok.md` — TikTok video specs (9:16, 15-60s)
- `facebook.md` — FB feed (16:9), story (9:16)
- `website.md` — Hero (16:9), product (3:4), banner sizes

### Quality Standards
- `image-checklist.md` — Pre-delivery quality checks for images
- `video-checklist.md` — Pre-delivery quality checks for videos
- `brand-consistency-rules.md` — Rules for maintaining brand consistency
