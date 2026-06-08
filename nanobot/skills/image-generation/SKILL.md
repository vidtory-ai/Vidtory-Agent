---
name: image-generation
description: Image generation is handled via Vidtory B2B API using exec+Python. The generate_image tool does NOT exist in this instance.
---

# Image Generation — Vidtory Mode

⛔ **`generate_image` tool KHÔNG tồn tại trong instance này.**

Để tạo ảnh, LUÔN dùng skill `vidtory-b2b-bridge`:
- Đọc API key từ customer profile (read_file)
- Lưu Python script vào `C:\Users\vidto\.vidtoryagent\tmp_gen.py`
- Chạy script bằng `exec` tool
- Tìm `IMAGE_URL:` trong output
- Gửi URL cho khách qua `message` tool

Xem chi tiết tại: `nanobot/skills/vidtory-b2b-bridge/SKILL.md`
