# Adaptive Brand Intelligence

## Mục tiêu

Hệ thống phải phục vụ ngay, học dần và không bắt khách nhớ lệnh. Mọi thay đổi
thương hiệu đều là partial update; không reset dữ liệu không liên quan.

## Luồng quyết định

1. Phân loại ý định trước khi chọn tool.
2. Yêu cầu đổi tên, ngành, phong cách, màu, audience, kênh hoặc logo được route
   sang `update_customer_profile`, trừ khi người dùng đang mô tả một sản phẩm
   sáng tạo cụ thể.
3. Khi đổi logo, giữ nguyên business/audience/channels; suy luận lại palette,
   style, mood và photography style. Trường người dùng chỉ định trong cùng yêu
   cầu luôn thắng suy luận.
4. Onboarding là progressive và non-blocking. Chỉ hỏi trường thiếu có giá trị
   cao nhất; chấp nhận button, text, URL và file.
5. Sau mỗi ảnh, cung cấp `Đúng ý`, `Cần chỉnh`, `Tạo biến thể`. Feedback gắn với
   task gần nhất và có provenance.

## Quy tắc học

- Một approval chỉ là tín hiệu, chưa phải mẫu bền vững.
- Ba approval cùng prompt mới vào `bestPerformingPrompts`.
- Hai complaint giống nhau mới trở thành pattern.
- Core/style chỉ thay đổi từ input rõ ràng của khách hoặc suy luận logo có ghi
  `source` và `confidence`.
- Preference có thể học âm thầm; không tự sửa tên thương hiệu, logo hoặc thông
  tin kinh doanh từ suy đoán.
- Complaint giống nhau từ ít nhất năm khách được đưa vào báo cáo global pattern
  để admin review, không tự động sửa prompt toàn hệ thống.

## Kiến trúc prompt

Prompt được ghép theo thứ tự:

1. Ý định và subject cụ thể.
2. Brand core và preference đã học.
3. Topic insight: điều người xem cần hiểu/cảm nhận và bằng chứng thị giác.
4. Bố cục, hierarchy, platform và safe zones.
5. Exact text, ngôn ngữ hiện tại và logo/reference constraints.
6. Ánh sáng, chất liệu, camera và quality constraints.

Không lặp cùng một chỉ dẫn bằng cả tiếng Anh và tiếng Việt. Ngôn ngữ của yêu
cầu hiện tại thắng preference cũ; preference chỉ là fallback cho brief trung
tính hoặc quá ngắn.

## Tiêu chí chấp nhận

- “Đổi phong cách thương hiệu…” cập nhật profile, không tạo ảnh.
- “Sửa phong cách ảnh này…” vẫn là image edit.
- Đổi logo cập nhật visual identity nhưng giữ business/audience.
- `/brand` hiển thị onboarding completeness, gaps và nút hành động; score
  generation readiness cũ vẫn giữ contract riêng.
- Media không caption được giữ lại khi khách bấm hoặc gõ mục đích.
- Gợi ý sáng tạo thay đổi theo chủ đề/yêu cầu, không dùng ba style chung cho mọi
  trường hợp.
- Feedback button tạo dữ liệu học thật và task score truy vết được.
