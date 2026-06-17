---
name: feedback-collector
description: Collects customer feedback after every generation, updates task scores, learns preferences, and continuously improves output quality through the brand memory system.
always: false
---

# Feedback Collection & Learning System

## When to Collect Feedback

After every content generation, use the built-in buttons:
`Đúng ý`, `Cần chỉnh`, `Tạo biến thể`. The same labels may be typed manually.
Do not add a second generic feedback question when the buttons are already shown.

### Key change: `task_id` tracking
After `generate_image` returns, you will see a `task_id` in the response (e.g. `gen-abc123def456`).
**Use this task_id when recording feedback** — it connects the feedback to the specific generation.

### Positive signals (mark as APPROVED):
- "Đúng ý", "ưng ý"
- 👍, "đẹp", "ok", "được", "thích", "tuyệt", "perfect", "great"
- Customer uses the content (shares, downloads)

### Negative signals (mark as REJECTED):
- "Cần chỉnh", "chưa đúng ý"
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
├── If POSITIVE → Log approved + task score, design note confirms approach works
├── If NEGATIVE → Ask: "Bạn muốn chỉnh gì cụ thể?"
│   ├── If specific feedback → Log, increment revision, adjust prompt, regenerate
│   └── If vague → Offer options: "Thử phong cách khác? Đổi nền? Thêm chi tiết?"
└── If NO response (5 min) → Gently ask: "Bạn thấy kết quả phù hợp không? 👍👎"
```

## Feedback Storage

**Sử dụng module Python `nanobot.utils.customer_profile`** (KHÔNG dùng write_file trực tiếp).

Agent dùng `exec` tool:

### Approved:
```python
import sys
sys.path.insert(0, 'C:/Users/vidto/Documents/Vidtory-Agent')
from nanobot.utils.customer_profile import update_learning
update_learning(
    user_id="{telegram_user_id}",
    rating="approved",
    prompt="{original_prompt}",
    feedback_text="",
    generation_id="{task_id}",  # from generate_image response
)
# Also update task score for FPAR tracking
from nanobot.db.customer_db import get_db
db = get_db()
db.update_task_score("{task_id}", score_brand_compliance=4.0, first_pass_accepted=True)
db.complete_task("{task_id}")
print("OK")
```

### Rejected (with specific feedback):
```python
import sys
sys.path.insert(0, 'C:/Users/vidto/Documents/Vidtory-Agent')
from nanobot.utils.customer_profile import update_learning
update_learning(
    user_id="{telegram_user_id}",
    rating="rejected",
    prompt="{original_prompt}",
    feedback_text="{specific_complaint}",
    generation_id="{task_id}",
)
# Increment revision count for FPAR tracking
from nanobot.db.customer_db import get_db
db = get_db()
db.increment_task_revisions("{task_id}")
print("OK")
```

## Learning Rules

### Short-term (within session):
- Remember feedback from earlier in the conversation
- Apply corrections to subsequent generations in the same session

### Medium-term — Auto-update profile (SILENT, không thông báo user):
- ≥ 2 identical complaints → `update_learning()` tự thêm vào `commonFeedback`
- ≥ 2 identical visual complaints → tự thêm vào `avoidList` trong profile
- ≥ 3 approvals of same style prompt → add to `bestPerformingPrompts`
- All updates write to **brand_memory preference layer** with source tracing
- Tất cả cập nhật **âm thầm** — không thông báo cho user

### Long-term (global patterns):
- ≥ 5 khách khác nhau phàn nàn giống nhau → Flag cho admin review
- Admin cập nhật Vidtory Knowledge templates dựa trên patterns

## Proactive Improvement

After every 10 generations for a customer, analyze:
- FPAR (First-Pass Acceptance Rate): If < 70%, suggest updating brand guidelines
- Common complaints: Proactively address before generating
- Best performing prompts: Reuse patterns for similar requests
- Lifecycle convergence: Track if quality is improving (probation → official gate)

## Design Note Citation

When delivering generated images to the user, include the `design_note` from the tool response.
This explains WHY certain design decisions were made, citing the memory layers:

Example:
```
🎨 Đây là kết quả! 

📋 Design note: Dùng tone warm natural theo Style Memory + màu #FFB6C1 theo Brand Core.
Tránh background sáng quá (học từ feedback trước).

Bạn thấy sao? 👍👎
```
