---
name: customer-knowledge
description: Manages per-customer brand profiles, style preferences, and learning data. Auto-loads context for personalized outputs.
always: false
---

# Customer Knowledge System

## Purpose

Each customer (merchant) has a unique creative profile stored locally. This profile contains brand guidelines, style preferences, interaction history, and learned adjustments. The Agent automatically loads this context to personalize every output.

## Storage Location

All customer data is stored at:
```
~/.vidtoryagent/customers/{telegram_user_id}/
├── profile.json          # Core profile (brand, style, audience, channels)
├── feedback.jsonl        # Append-only feedback log
├── generation-history.jsonl  # History of all generations
└── assets/               # Uploaded brand assets (logo, references)
```

## Profile Schema (profile.json)

```json
{
  "telegramUserId": "string",
  "telegramUsername": "string",
  "merchantId": "string (from B2B API)",
  "apiKey": "string (x-api-key for B2B API)",
  
  "onboarding": {
    "status": "completed|minimal|in_progress",
    "completedAt": "ISO datetime",
    "currentStep": "string (if in_progress)"
  },
  
  "business": {
    "name": "string",
    "industry": "fashion|food-beverage|beauty|tech|real-estate|education|other",
    "description": "string"
  },
  
  "brand": {
    "style": "minimalist|luxury|playful|corporate|natural",
    "moodKeywords": ["string"],
    "colorPalette": {
      "primary": "#hex",
      "secondary": "#hex",
      "accent": "#hex"
    },
    "logoUrl": "string (cloud URL)",
    "referenceImages": ["string"],
    "photographyStyle": "string",
    "avoidList": ["string"]
  },
  
  "audience": {
    "gender": "female|male|all",
    "ageRange": "string",
    "segment": "mass|mid|premium"
  },
  
  "contentChannels": {
    "primary": ["instagram", "tiktok", "facebook", "website", "zalo"],
    "defaultFormats": {
      "instagram_feed": {"aspectRatio": "1:1"},
      "instagram_story": {"aspectRatio": "9:16"},
      "website": {"aspectRatio": "16:9"}
    }
  },
  
  "preferences": {
    "communicationLanguage": "vi",
    "autoApplyBrandGuidelines": true,
    "preferredVoiceId": "string"
  },
  
  "learningData": {
    "totalGenerations": 0,
    "approvedCount": 0,
    "rejectedCount": 0,
    "commonFeedback": [],
    "bestPerformingPrompts": []
  }
}
```

## How to Use

### When receiving a creative request:
1. Read `~/.vidtoryagent/customers/{telegram_user_id}/profile.json`
2. If file exists → Extract brand context for prompt enhancement
3. If file does NOT exist → Trigger onboarding flow

### When generating content:
- Automatically merge brand colors, style, mood, and photography preferences into the prompt
- Apply `avoidList` as negative constraints
- Use appropriate `defaultFormats` based on the mentioned platform

### When receiving feedback:
- Append to `feedback.jsonl` with format:
  ```json
  {"timestamp": "ISO", "generationId": "string", "rating": "approved|rejected", "comment": "string", "adjustments": "string"}
  ```
- Update `learningData` counters in `profile.json`
- If same complaint appears ≥ 2 times, add to `commonFeedback` for auto-adjustment

### Smart Context Injection
When building prompts, inject customer context like this:
```
[BRAND CONTEXT]
Brand: {business.name} | Industry: {business.industry}
Style: {brand.style} | Mood: {brand.moodKeywords}
Colors: {brand.colorPalette.primary}, {brand.colorPalette.secondary}
Photography: {brand.photographyStyle}
Avoid: {brand.avoidList}
Target: {audience.gender}, {audience.ageRange}, {audience.segment}
```
