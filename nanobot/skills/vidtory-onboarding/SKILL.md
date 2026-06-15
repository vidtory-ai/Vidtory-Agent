---
name: vidtory-onboarding
description: Quan ly luong onboarding 5 buoc tinh gon cho khach hang moi, lay logo/website truoc va su dung buttons de chon style.
always: false
---

# Customer Onboarding Flow — Simplified & Visual (5 Steps)

Kích hoạt khi Runtime Context chứa:
- `Onboarding Status: NEW_USER` hoặc `Onboarding Status: in_progress`
- `Lifecycle: new_user` hoặc `Lifecycle: testing` hoặc `Lifecycle: onboarding`

---

## 🛡️ NGUYÊN TẮC THIẾT KẾ UX (TẬP TRUNG VÀO KHÁCH HÀNG)

- **Gọi người dùng là "bạn"** (hoặc xưng hô lịch sự theo ngữ cảnh) trong mọi câu chào và phản hồi.
- **Ít chữ, trực quan, dễ hiểu:** Thay thế các form điền chữ dài dòng bằng câu hỏi ngắn kèm button lựa chọn.
- **AI Tự Suy Luận:** Để khách gửi logo hoặc link website trước, AI tự phân tích ra màu sắc, phong cách và tạo bản nháp Snapshot, sau đó khách chỉ cần confirm hoặc chỉnh sửa nhẹ.

---

## Luồng Onboarding 5 Bước

### Bước 1: Thu thập Logo / Brand Signal (Logo First)

- **Mục tiêu:** Nhận diện thương hiệu tự động từ tín hiệu của khách hàng.
- **Hành vi của Agent:**
  - Chào bạn và yêu cầu gửi logo hoặc nhập link website.
  - Khi nhận được ảnh logo hoặc link website:
    - Phân tích màu sắc chủ đạo (Primary, Accent, Secondary).
    - Phân tích mood / phong cách ước lượng.
    - Gọi ngay `update_customer_profile` để lưu `logo_url` và các màu sắc phân tích được.
  - Chuyển sang Bước 2.

---

### Bước 2: Xác định Bối cảnh doanh nghiệp (Business Context)

- **Mục tiêu:** Hiểu rõ đối tượng phục vụ của Agent (Brand Marketing hay Fashion Studio).
- **Hành vi của Agent:**
  - Hỏi tên thương hiệu & ngành hàng của bạn (nếu chưa tự nhận diện được ở Bước 1).
  - Hỏi team nào sẽ sử dụng Designer này để thiết kế chính, hiển thị 3 button:
    1. **Brand Marketing 📢** (Tập trung chiến dịch, nhận diện thương hiệu, banner quảng cáo, social post)
    2. **Fashion Studio 👗** (Tập trung độ chi tiết sản phẩm, chất liệu vải, dáng người mẫu, lookbook thời trang)
    3. **Cả hai 🎯**
  - Khi bạn click chọn button hoặc trả lời, gọi `update_customer_profile` để lưu thông tin.
  - Chuyển sang Bước 3.

---

### Bước 3: Xác nhận Brand Snapshot (AI Snapshot)

- **Mục tiêu:** Cho khách xác nhận "bản đọc vị" của AI về thương hiệu.
- **Hành vi của Agent:**
  - Hiển thị một Brand Snapshot ngắn gọn dựa trên thông tin đã học:
    - **Brand Mood:** Tông màu và cảm xúc (Ví dụ: Sang trọng, tối giản, năng động).
    - **Bảng màu chủ đạo:** Các mã màu HEX phát hiện được.
    - **Layout & Image Rules:** Quy tắc bố cục (Ví dụ: Bố cục thoáng, ít chữ, tập trung sản phẩm).
    - **Avoid (Cần tránh):** Những thứ tuyệt đối không đưa vào ảnh (Ví dụ: Màu quá chói, hoạt hình, chữ rối mắt).
  - Hiển thị các nút bấm phản hồi nhanh:
    - `Looks right` (Đúng rồi)
    - `More premium` (Sang trọng hơn)
    - `More bold` (Táo bạo hơn)
    - `More playful` (Vui tươi hơn)
  - Nếu khách click nút điều chỉnh (Ví dụ: `More premium`), tự động cập nhật lại Snapshot trong `brand_guidelines` và `mood_keywords`.
  - Gọi `update_customer_profile` lưu snapshot vào `brand_guidelines`.
  - Chuyển sang Bước 4.

---

### Bước 4: Chọn Phong cách Thiết kế (Style Collage)

- **Mục tiêu:** Chọn style lane ban đầu bằng hình ảnh trực quan.
- **Hành vi của Agent:**
  - Gửi hình ảnh collage chứa 3 phong cách thiết kế mẫu: `https://cdn.vidtory.net/samples/onboarding-styles-collage.jpg`
  - Đưa ra 3 phím bấm chọn:
    - `1. Clean Premium` (Tối giản Sang trọng)
    - `2. Bold Performance` (Hiệu suất Đột phá)
    - `3. Editorial Fashion` (Thời trang Nghệ thuật)
  - Giải thích ngắn gọn mỗi phong cách dưới dạng 1-2 câu.
  - Khi bạn chọn phong cách, lưu phong cách đó vào field `brand_style` bằng cách gọi `update_customer_profile`.
  - Chuyển sang Bước 5.

---

### Bước 5: Tạo Thiết kế Đầu tiên & Báo Ready (Wow Payoff)

- **Mục tiêu:** Trình diễn kết quả thiết kế thực tế để hoàn tất.
- **Hành vi của Agent:**
  - Thông báo: *"Brand profile đã sẵn sàng! Tôi đang tạo 3 hướng thiết kế đầu tiên cho bạn..."*
  - Gọi công cụ `generate_image` tạo ra 3 hướng thiết kế mẫu:
    - **Safe Brand Fit:** Sát với brand guidelines nhất, an toàn.
    - **Performance Version:** Thiết kế giật gân, làm nổi bật thông điệp, hợp chạy quảng cáo/social.
    - **Creative Stretch:** Sáng tạo đột phá, mang tính bay bổng nghệ thuật.
  - Sau khi gửi ảnh thiết kế, hiển thị các button phản hồi dưới mỗi ảnh:
    - `Chọn làm mặc định`
    - `Chỉnh cho cao cấp hơn`
    - `Giảm bớt chữ`
  - Khi bạn chọn hướng ưng ý nhất hoặc bấm `Chọn làm mặc định`:
    - Gọi `update_customer_profile` with `onboarding_complete=True`.
    - Trạng thái profile sẽ tự chuyển sang **Probation**, hoàn tất quá trình onboard.
    - Gửi lời chúc mừng và chào đón bạn vào quá trình làm việc chính thức!

---

## ⚠️ Quy tắc Vận hành Kỹ thuật (Bắt buộc)

1. **Lưu dữ liệu liên tục:** Gọi `update_customer_profile` sau mỗi câu trả lời của bạn. Không đợi đến cuối mới lưu.
2. **Dual-write:** Tool `update_customer_profile` sẽ tự động ghi đồng thời vào bảng `profile_json` và bảng `brand_memory` (qua `set_memory`).
3. **Phím bấm thông minh:** Dùng các phím bấm có nhãn rõ ràng để bạn chỉ cần click chọn thay vì gõ chữ.
