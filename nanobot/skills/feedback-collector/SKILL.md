---
name: feedback-collector
description: Collects customer feedback after every generation, learns preferences, and continuously improves output quality.
always: false
---

# Feedback Collection & Learning System

## When to Collect Feedback

After EVERY content generation, prompt the customer for feedback:

### Positive signals (mark as APPROVED):
- 👍, "đẹp", "ok", "được", "thích", "tuyệt", "perfect", "great"
- Customer uses the content (shares, downloads)

### Negative signals (mark as REJECTED):
- 👎, "chưa", "không", "xấu", "sai", "lại", "chỉnh"
- Customer asks for changes

### Specific feedback (ACTIONABLE):
- "nền quá sáng" → adjustment: use darker backgrounds
- "chữ nhỏ quá" → adjustment: increase text size
- "không đúng phong cách" → adjustment: re-check brand guidelines
- "thiếu logo" → adjustment: add logo overlay

## Feedback Response Flow

```
After sending output:
├── Wait for response
├── If POSITIVE → Log approved, save prompt as "golden example"
├── If NEGATIVE → Ask: "Bạn muốn chỉnh gì cụ thể?"
│   ├── If specific feedback → Log, adjust prompt, regenerate
│   └── If vague → Offer options: "Thử phong cách khác? Đổi nền? Thêm chi tiết?"
└── If NO response (5 min) → Gently ask: "Bạn thấy kết quả phù hợp không? 👍👎"
```

## Feedback Storage

Append to `~/.vidtoryagent/customers/{telegram_user_id}/feedback.jsonl`:

```json
{
  "timestamp": "2026-06-08T11:30:00Z",
  "generationId": "abc-123",
  "contentType": "image",
  "originalPrompt": "tạo ảnh áo dài",
  "enhancedPrompt": "Vietnamese Ao Dai dress...",
  "rating": "approved|rejected",
  "comment": "nền quá sáng",
  "adjustments": "darker background, lower exposure"
}
```

## Learning Rules

### Short-term (within session):
- Remember feedback from earlier in the conversation
- Apply corrections to subsequent generations in the same session

### Medium-term (per customer):
- After ≥ 2 similar complaints → Add to `commonFeedback` in profile
- Auto-apply these adjustments to ALL future prompts for this customer
- After ≥ 5 approvals of a specific style → Mark as "preferred"

### Long-term (global):
- If ≥ 5 different customers give same feedback → Flag for review
- Admin can update Vidtory Knowledge templates based on patterns

## Proactive Improvement

After every 10 generations for a customer, analyze:
- Approval rate: If < 70%, suggest updating brand guidelines
- Common complaints: Proactively address before generating
- Best performing prompts: Reuse patterns for similar requests
