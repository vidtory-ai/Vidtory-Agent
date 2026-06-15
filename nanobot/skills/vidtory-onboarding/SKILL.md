---
name: vidtory-onboarding
description: Quan ly luong onboarding 5 buoc tinh gon cho khach hang moi, lay logo/website truoc, fetch web, suy luan thong tin va su dung buttons de chon style.
always: false
---

# Customer Onboarding Flow — Simplified & Visual (5 Steps)

Kích hoạt khi Runtime Context chứa:
- `Onboarding Status: NEW_USER` hoặc `Onboarding Status: in_progress`
- `Lifecycle: new_user` hoặc `Lifecycle: testing` or `Lifecycle: onboarding`

---

## 🛡️ NGUYÊN TẮC THIẾT KẾ UX (TẬP TRUNG VÀO KHÁCH HÀNG)

- **Gọi người dùng là "bạn" (hoặc "quý khách")** trong mọi câu chào và phản hồi để đảm bảo sự lịch sự, chuyên nghiệp và trang trọng. Tuyệt đối không dùng các từ xưng hô suồng sã hoặc thân mật quá mức (như "anh chai").
- **Trực quan, dễ sử dụng cho khách hàng lười:** Mọi gợi ý hoặc lựa chọn phải được thiết kế dưới dạng nút bấm (buttons) trong công cụ `message` để người dùng có thể click chọn nhanh thay vì gõ chữ.
- **Trung thực và Thông minh:** 
  - KHÔNG được nói dối là đã lấy được thông tin/logo/màu sắc từ website nếu công cụ `web_fetch` không hoạt động hoặc không trả về kết quả đó.
  - Khi người dùng gửi link website, BẮT BUỘC phải gọi công cụ `web_fetch` trước.
  - Nếu `web_fetch` thất bại (lỗi kết nối, Cloudflare chặn, v.v.) hoặc không lấy được thông tin, hãy sử dụng **dữ liệu tri thức có sẵn của LLM** để tự động nhận diện thương hiệu nổi tiếng (ví dụ: PTIT là Học viện Công nghệ Bưu chính Viễn thông, màu chủ đạo Đỏ + Vàng).
  - Nếu nhận diện được từ tri thức có sẵn, hãy khéo léo nói: *"Mình chưa kết nối trực tiếp với website lúc này được (để bảo mật tối đa cho bạn), nhưng mình biết rất rõ [Tên thương hiệu] nổi bật với tông màu [Màu sắc] và phong cách [Style]! Mình đã tự động thiết lập brand profile theo các thông tin này cho bạn rồi nhé. Bạn xem có đúng ý không ạ?"*
  - Nếu không có thông tin từ cả web lẫn tri thức, hãy khéo léo phản hồi: *"Để hỗ trợ bạn tốt nhất và chính xác nhất, bạn có thể chọn tông màu chủ đạo bên dưới hoặc gửi ảnh logo trực tiếp để mình tự động nhận diện nhé!"* kèm các nút chọn màu sắc hoặc phong cách phổ biến.

---

## Luồng Onboarding 5 Bước

### Bước 1: Thu thập Logo / Brand Signal (Logo First)

- **Mục tiêu:** Nhận diện thương hiệu tự động từ tín hiệu của khách hàng.
- **Hành vi của Agent:**
  - Chào khách hàng và đề xuất thực hiện onboarding. Dùng công cụ `message` gửi tin nhắn kèm 2 nút bấm: `[["Khai báo ngay 🎨", "Dùng profile cơ bản ⚡"]]`.
  - Khi khách hàng gửi logo (ảnh) hoặc link website:
    - Nếu là link website:
      1. BẮT BUỘC gọi công cụ `web_fetch` với URL đó.
      2. Nếu thành công: Phân tích tên thương hiệu, mô tả, màu sắc chủ đạo, và tìm link ảnh logo tiềm năng.
      3. Nếu thất bại hoặc không lấy được dữ liệu: 
         - Tìm kiếm trong tri thức sẵn có của LLM về tên miền hoặc thương hiệu đó.
         - Nếu thương hiệu nổi tiếng và có sẵn thông tin: Cập nhật profile và phản hồi khéo léo (như nguyên tắc thiết kế UX ở trên).
         - Nếu không tìm thấy: Phản hồi khéo léo và hiển thị nút chọn nhanh tông màu chủ đạo: `[["Đỏ 🔴", "Vàng 🟡", "Xanh dương 🔵"], ["Xanh lá 🟢", "Đen ⚫", "Khác/Tự nhập 🎨"]]`.
    - Nếu là ảnh logo: Tự động phân tích màu sắc và phong cách từ ảnh.
    - Gọi ngay `update_customer_profile` để lưu các thông tin đã phân tích hoặc suy luận được (`business_name`, `color_primary`, `color_secondary`, `logo_url`, v.v.).
    - Chuyển sang Bước 2.

---

### Bước 2: Xác định Bối cảnh doanh nghiệp (Business Context)

- **Mục tiêu:** Hiểu rõ đối tượng phục vụ của Agent (Brand Marketing hay Fashion Studio).
- **Hành vi của Agent:**
  - Hỏi tên thương hiệu & ngành hàng của khách hàng (nếu chưa tự nhận diện được ở Bước 1).
  - Hỏi team nào sẽ sử dụng Designer này để thiết kế chính. Phải sử dụng công cụ `message` để gửi 3 nút bấm:
    1. **Brand Marketing 📢** (Tập trung chiến dịch, nhận diện thương hiệu, banner quảng cáo, social post)
    2. **Fashion Studio 👗** (Tập trung độ chi tiết sản phẩm, chất liệu vải, dáng người mẫu, lookbook thời trang)
    3. **Cả hai 🎯**
  - Khi khách hàng click chọn button hoặc trả lời, gọi `update_customer_profile` để lưu thông tin.
  - Chuyển sang Bước 3.

---

### Bước 3: Xác nhận Brand Snapshot (AI Snapshot)

- **Mục tiêu:** Cho khách xác nhận "bản đọc vị" của AI về thương hiệu.
- **Hành vi của Agent:**
  - Hiển thị một Brand Snapshot ngắn gọn dựa trên thông tin đã lưu:
    - **Brand Mood:** Tông màu và cảm xúc (Ví dụ: Sang trọng, tối giản, năng động).
    - **Bảng màu chủ đạo:** Các mã màu HEX phát hiện được.
    - **Layout & Image Rules:** Quy tắc bố cục (Ví dụ: Bố cục thoáng, ít chữ, tập trung sản phẩm).
    - **Avoid (Cần tránh):** Những thứ tuyệt đối không đưa vào ảnh (Ví dụ: Màu quá chói, hoạt hình, chữ rối mắt).
  - Sử dụng công cụ `message` để hiển thị các nút bấm phản hồi nhanh:
    - `Looks right` (Đúng rồi 👍)
    - `More premium` (Sang trọng hơn ✨)
    - `More bold` (Táo bạo hơn 🔥)
    - `More playful` (Vui tươi hơn 🎉)
  - Nếu khách hàng click nút điều chỉnh (Ví dụ: `More premium`), tự động cập nhật lại Snapshot trong `brand_guidelines` và `mood_keywords`.
  - Gọi `update_customer_profile` lưu snapshot vào `brand_guidelines`.
  - Chuyển sang Bước 4.

---

### Bước 4: Chọn Phong cách Thiết kế (Style Collage)

- **Mục tiêu:** Chọn style lane ban đầu bằng hình ảnh trực quan.
- **Hành vi của Agent:**
  - Gửi hình ảnh collage chứa 3 phong cách thiết kế mẫu: `https://cdn.vidtory.net/samples/onboarding-styles-collage.jpg`
  - Đưa ra 3 phím bấm chọn thông qua công cụ `message`:
    - `1. Clean Premium` (Tối giản Sang trọng ✨)
    - `2. Bold Performance` (Hiệu suất Đột phá 💥)
    - `3. Editorial Fashion` (Thời trang Nghệ thuật 🎨)
  - Giải thích ngắn gọn mỗi phong cách dưới dạng 1-2 câu.
  - Khi khách hàng chọn phong cách, lưu phong cách đó vào field `brand_style` bằng cách gọi `update_customer_profile`.
  - Chuyển sang Bước 5.

---

### Bước 5: Tạo Thiết kế Đầu tiên & Báo Ready (Wow Payoff)

- **Mục tiêu:** Trình diễn kết quả thiết kế thực tế để hoàn tất.
- **Hành vi của Agent:**
  - Thông báo: *"Brand profile đã sẵn sàng! Mình đang tạo 3 hướng thiết kế đầu tiên cho bạn..."*
  - Gọi công cụ `generate_image` tạo ra 3 hướng thiết kế mẫu:
    - **Safe Brand Fit:** Sát với brand guidelines nhất, an toàn.
    - **Performance Version:** Thiết kế giật gân, làm nổi bật thông điệp, hợp chạy quảng cáo/social.
    - **Creative Stretch:** Sáng tạo đột phá, mang tính bay bổng nghệ thuật.
  - Sau khi gửi ảnh thiết kế, hiển thị các button phản hồi dưới mỗi ảnh:
    - `Chọn làm mặc định 🏆`
    - `Chỉnh cho cao cấp hơn 💎`
    - `Giảm bớt chữ 📝`
  - Khi khách hàng chọn hướng ưng ý nhất hoặc bấm `Chọn làm mặc định`:
    - Gọi `update_customer_profile` với `onboarding_complete=True`.
    - Trạng thái profile sẽ tự chuyển sang **Probation**, hoàn tất quá trình onboard.
    - Gửi lời chúc mừng và chào đón bạn vào quá trình làm việc chính thức!

---

## ⚠️ Quy tắc Vận hành Kỹ thuật (Bắt buộc)

1. **Lưu dữ liệu liên tục:** Gọi `update_customer_profile` sau mỗi câu trả lời của khách hàng. Không đợi đến cuối mới lưu.
2. **Dual-write:** Tool `update_customer_profile` sẽ tự động ghi đồng thời vào bảng `profile_json` và bảng `brand_memory` (qua `set_memory`).
3. **Phím bấm tương tác:** Luôn luôn gọi công cụ `message` với tham số `buttons` để hiển thị menu lựa chọn cho khách hàng.
