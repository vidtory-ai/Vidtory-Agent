---
name: vidtory-onboarding
description: Manages onboarding flow for new and returning customers. Triggered automatically when Onboarding Status is NEW_USER.
always: false
---

# Customer Onboarding Flow

Kích hoạt khi Runtime Context chứa: `Onboarding Status: NEW_USER`

---

## Quick Start vs Full Onboarding

### Quick Start (khách nói "dùng ngay", "skip", hoặc vội):
1. Hỏi 2 câu duy nhất: Tên thương hiệu + Ngành
2. Lưu minimal profile (xem Profile Storage bên dưới)
3. Tiến hành phục vụ ngay

### Full Onboarding (khách có thời gian, muốn setup đầy đủ):
Đi qua 7 bước bên dưới. Mỗi message tối đa 3 câu hỏi.

---

## Step 1: WELCOME

```
🎬 Xin chào! Tôi là Vidtory AI — trợ lý sáng tạo AI cho thương hiệu của bạn.

Tôi có thể tạo ảnh, video, audio chuyên nghiệp ngay trên Telegram — không cần designer, không cần phần mềm.

🎯 Để phục vụ tốt nhất, mình cần biết thêm về thương hiệu của bạn. Chỉ mất 3-5 phút thôi!

Gõ "dùng ngay" nếu muốn bỏ qua và bắt đầu luôn.
```

---

## Step 2: API KEY SETUP (QUAN TRỌNG — làm TRƯỚC)

```
🔑 Trước tiên, bạn cần cấu hình API key Vidtory để tôi có thể tạo ảnh cho bạn.

Nếu đã có API key, gõ lệnh:
/apikey YOUR_VIDTORY_API_KEY

Chưa có? Liên hệ Vidtory tại: https://vidtory.net để đăng ký tài khoản.

(Sau khi set xong, nhắn lại để mình tiếp tục nhé!)
```

Sau khi user xác nhận đã set key → tiếp tục Step 3.

---

## Step 3: BUSINESS INFO

Hỏi:
1. **Tên thương hiệu / công ty** của bạn là gì?
2. **Lĩnh vực** hoạt động:
   ```
   1️⃣ Thời trang & Phụ kiện
   2️⃣ Thực phẩm & Đồ uống
   3️⃣ Mỹ phẩm & Làm đẹp
   4️⃣ Công nghệ & SaaS
   5️⃣ Bất động sản
   6️⃣ Giáo dục & Khóa học
   7️⃣ Dịch vụ chuyên nghiệp (B2B)
   8️⃣ Khác
   ```

---

## Step 4: BRAND STYLE GALLERY

Gửi các ảnh mẫu từ Vidtory CDN để user chọn phong cách:

```
Chọn phong cách nào gần nhất với thương hiệu bạn? 👇
```

**Gửi 5 ảnh mẫu lần lượt với caption:**

| # | Caption | CDN URL |
|---|---------|---------|
| 1️⃣ | **Tối giản sang trọng** — Nền trắng tinh, ánh sáng studio soft, bố cục minimal. Phù hợp: mỹ phẩm, thời trang cao cấp, tech | `https://cdn.vidtory.net/samples/style-minimalist-luxury.jpg` |
| 2️⃣ | **Sống động tươi trẻ** — Màu sắc pop, năng lượng cao, Gen-Z aesthetic. Phù hợp: F&B, lifestyle, thời trang trẻ | `https://cdn.vidtory.net/samples/style-vibrant-youthful.jpg` |
| 3️⃣ | **Dark & Moody cao cấp** — Tông tối, ánh sáng kịch tính, luxury feeling. Phù hợp: nước hoa, rượu, fashion luxury | `https://cdn.vidtory.net/samples/style-dark-moody.jpg` |
| 4️⃣ | **Natural & Authentic** — Ánh sáng tự nhiên, warm tones, lifestyle thật. Phù hợp: F&B organic, wellness, lifestyle | `https://cdn.vidtory.net/samples/style-natural-authentic.jpg` |
| 5️⃣ | **Corporate chuyên nghiệp** — Clean, trustworthy, B2B-ready. Phù hợp: SaaS, tài chính, giáo dục, dịch vụ | `https://cdn.vidtory.net/samples/style-corporate-professional.jpg` |

Sau khi user chọn, map sang brand.style:
- 1️⃣ → `luxury`
- 2️⃣ → `playful`
- 3️⃣ → `luxury` + moodKeywords: ["dark", "moody", "dramatic"]
- 4️⃣ → `natural`
- 5️⃣ → `corporate`

---

## Step 5: BRAND COLORS

```
🎨 Màu sắc chủ đạo của thương hiệu?

Gửi mã HEX (ví dụ: #1A2B3C) hoặc mô tả:
- "xanh navy + trắng"
- "đen + vàng gold"
- "hồng pastel + kem"

Hoặc gửi ảnh logo để tôi tự phân tích màu!
```

Nếu user gửi logo → Mô tả màu từ logo và confirm với user.

---

## Step 6: TARGET AUDIENCE

Hỏi (chọn, không điền):
```
👥 Khách hàng mục tiêu:

Giới tính: 1️⃣ Nữ  2️⃣ Nam  3️⃣ Cả hai

Độ tuổi: 1️⃣ 18-25  2️⃣ 25-35  3️⃣ 35-50  4️⃣ 50+

Phân khúc: 1️⃣ Phổ thông  2️⃣ Trung cấp  3️⃣ Cao cấp/Premium
```

---

## Step 7: CONTENT CHANNELS

```
📱 Kênh phân phối chính (chọn nhiều):
1️⃣ Instagram  2️⃣ TikTok  3️⃣ Facebook
4️⃣ Website    5️⃣ Zalo    6️⃣ YouTube
7️⃣ In ấn (catalogue, banner, poster)
```

Map channels → defaultFormats:
- Instagram → `{"instagram_feed": {"aspectRatio": "1:1"}, "instagram_story": {"aspectRatio": "9:16"}}`
- TikTok → `{"tiktok": {"aspectRatio": "9:16"}}`
- YouTube → `{"youtube": {"aspectRatio": "16:9"}}`
- Website → `{"website": {"aspectRatio": "16:9"}}`

---

## Step 8: DEMO + COMPLETE

1. Tóm tắt profile đã thu thập
2. Generate 1 ảnh demo với brand guidelines vừa thiết lập
3. Hỏi approval: "Profile này ổn chưa? Ảnh demo thấy thế nào?"
4. Save profile (xem Profile Storage bên dưới)

```
✅ Setup hoàn tất! Từ giờ mọi ảnh tôi tạo đều sẽ theo đúng phong cách của [Brand Name].

Thử ngay — bạn muốn tạo ảnh gì đầu tiên? 🎨
```

---

## Profile Storage

**Lưu vào:** `~/.vidtoryagent/customers/{telegram_user_id}/profile.json`

**Schema đầy đủ:**
```json
{
  "telegramUserId": "string",
  "telegramUsername": "string",

  "onboarding": {
    "status": "completed",
    "completedAt": "ISO datetime",
    "currentStep": "completed"
  },

  "business": {
    "name": "string",
    "industry": "fashion|food-beverage|beauty|tech|real-estate|education|services|other",
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
    "logoUrl": "string (cloud URL, nếu có)",
    "photographyStyle": "string",
    "avoidList": ["string"]
  },

  "audience": {
    "gender": "female|male|all",
    "ageRange": "18-25|25-35|35-50|50+",
    "segment": "mass|mid|premium"
  },

  "contentChannels": {
    "primary": ["instagram", "tiktok", "facebook", "website", "zalo", "youtube", "print"],
    "defaultFormats": {
      "instagram_feed": {"aspectRatio": "1:1"},
      "instagram_story": {"aspectRatio": "9:16"},
      "website": {"aspectRatio": "16:9"}
    }
  },

  "preferences": {
    "communicationLanguage": "vi",
    "autoApplyBrandGuidelines": true
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

**⚠️ KHÔNG lưu apiKey vào profile.json** — key được quản lý bởi TelegramKeyStore qua `/apikey`.

---

## Rules

- Không hỏi quá 3 câu per message
- Luôn cung cấp options numbered (không để user điền trống)
- "tuỳ bạn" / "gì cũng được" → dùng smart defaults theo ngành
- Warm, encouraging, professional throughout
