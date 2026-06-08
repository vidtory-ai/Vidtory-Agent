---
name: vidtory-onboarding
description: Manages onboarding flow for new customers.
---

# Customer Onboarding Flow

When a NEW customer messages for the first time (no customer profile found), guide them through onboarding.

## Detection

A customer is "new" if no file exists at `~/.vidtoryagent/customers/{telegram_user_id}/profile.json`.

## Onboarding Steps

### Step 1: WELCOME
```
🎬 Xin chào! Tôi là Vidtory AI — trợ lý sáng tạo thông minh của bạn.

Tôi có thể tạo ảnh, video, audio chuyên nghiệp cho thương hiệu của bạn, ngay trên Telegram.

🎯 Để phục vụ tốt nhất, hãy dành 2-3 phút trả lời vài câu hỏi nhé!

Hoặc gõ "dùng ngay" nếu muốn bỏ qua.
```

### Step 2: BUSINESS INFO
Ask:
1. Tên thương hiệu / công ty?
2. Lĩnh vực? (Fashion, F&B, Beauty, Tech, Real Estate, Education, Other)

### Step 3: BRAND VISUAL
Ask:
1. Phong cách? (Minimalist, Luxury, Playful, Corporate, Natural)
2. Màu sắc chủ đạo? (hoặc gửi logo để phân tích)

### Step 4: BRAND ASSETS
Request:
- Logo (bắt buộc)
- 2-3 ảnh sản phẩm mẫu (khuyến khích)
- Ảnh phong cách tham khảo (tùy chọn)

Upload received images via the `exec` tool (Python httpx to POST /media/upload) and save returned URLs to profile.

### Step 5: TARGET AUDIENCE
Ask:
1. Giới tính khách hàng? (Nữ / Nam / Cả hai)
2. Độ tuổi? (18-25 / 25-35 / 35-50 / 50+)
3. Phân khúc? (Phổ thông / Trung cấp / Cao cấp)

### Step 6: CONTENT GOALS
Ask: Kênh phân phối chính? (Instagram, TikTok, Facebook, Website, Zalo, Print)

### Step 7: DEMO + COMPLETE
1. Summarize the profile
2. Generate a demo image using their brand guidelines
3. Ask for approval
4. Save profile to `~/.vidtoryagent/customers/{telegram_user_id}/profile.json`

## Skip Onboarding

If customer says "dùng ngay", "skip", or similar:
1. Ask only: Tên thương hiệu + Ngành
2. Save minimal profile with `onboarding.status = "minimal"`
3. After 5-10 interactions, suggest completing full onboarding

## Profile Storage

Save to: `~/.vidtoryagent/customers/{telegram_user_id}/profile.json`

Schema: See implementation plan Section 4.4 for full JSON schema.

## B2B Account Binding

During onboarding, ask if they have an existing Vidtory account:
- If YES: Ask for email → Use to look up their merchant via B2B API
- If NO: Offer to create one via `POST /auth/signup`

Save the resulting API key or credentials in the customer profile.

## Rules
- Never ask more than 3 questions per message
- Always provide suggested options (numbered list)
- If customer says "tuỳ bạn" or "gì cũng được", use smart defaults
- Be warm, professional, and encouraging throughout
