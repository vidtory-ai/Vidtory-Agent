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

**Sử dụng module Python `nanobot.utils.customer_profile`** (KHÔNG dùng write_file trực tiếp).

Agent không gọi trực tiếp được Python module — thay vào đó dùng `exec` tool:

```python
import sys, json
sys.path.insert(0, 'C:/Users/vidto/Documents/Vidtory-Agent')
from nanobot.utils.customer_profile import update_learning
update_learning(
    user_id="{telegram_user_id}",
    rating="approved",      # hoặc "rejected"
    prompt="{original_prompt}",
    feedback_text="{comment}",
    generation_id="{gen_id}",
)
print("OK")
```

**Feedback entry format** (tự động ghi vào `feedback.jsonl`):
```json
{
  "timestamp": "2026-06-08T11:30:00Z",
  "generationId": "gen-1234567890",
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

### Medium-term — Auto-update profile (SILENT, không thông báo user):
- ≥ 2 identical complaints → `update_learning()` tự thêm vào `commonFeedback`
- ≥ 2 identical visual complaints → tự thêm vào `avoidList` trong profile
- ≥ 3 approvals of same style prompt → add to `bestPerformingPrompts`
- Tất cả cập nhật **âm thầm** — không thông báo cho user

### Long-term (global patterns):
- ≥ 5 khách khác nhau phàn nàn giống nhau → Flag cho admin review
- Admin cập nhật Vidtory Knowledge templates dựa trên patterns

## Proactive Improvement

After every 10 generations for a customer, analyze:
- Approval rate: If < 70%, suggest updating brand guidelines
- Common complaints: Proactively address before generating
- Best performing prompts: Reuse patterns for similar requests
