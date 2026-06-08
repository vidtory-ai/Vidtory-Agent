---
name: vidtory-b2b-bridge
description: Bridge to Vidtory B2B API using exec+Python for image generation. API calls. generate_image tool does NOT exist - always use exec.
---

# Vidtory B2B Bridge

## ⛔ KHÔNG có tool `generate_image`

Dùng `exec` với Python script để tạo ảnh.

## Thông tin cấu hình

- B2B API URL: `https://bapi.vidtory.net`
- API Key nguồn 1: Profile khách tại `C:\Users\vidto\.vidtoryagent\customers\{user_id}\profile.json` → field `apiKey`
- API Key nguồn 2 (fallback): `C:\Users\vidto\.vidtoryagent\b2b-config.json` → field `b2bApiKey`

## Template: Tạo ảnh (exec + Python)

Lưu script vào file tạm rồi chạy:

```python
# File: C:\Users\vidto\.vidtoryagent\tmp_gen.py
import sys, httpx, json, time
sys.stdout.reconfigure(encoding='utf-8')

API_KEY = "REPLACE_WITH_API_KEY"
PROMPT = "REPLACE_WITH_ENHANCED_PROMPT"
ASPECT = "IMAGE_ASPECT_RATIO_SQUARE"  # hoặc PORTRAIT, LANDSCAPE

headers = {"x-api-key": API_KEY, "Content-Type": "application/json"}
payload = {"prompt": PROMPT, "aspectRatio": ASPECT, "modelId": "gemini-3.1-flash-image-preview", "resolution": "1K"}

r = httpx.post("https://bapi.vidtory.net/generative-core/image", json=payload, headers=headers, timeout=30)
data = r.json()
if not data.get("data"):
    print(f"ERROR: {data}")
    sys.exit(1)

job_id = data["data"]["generationHistoryId"]
print(f"Job: {job_id}")

for i in range(24):
    time.sleep(5)
    r2 = httpx.get(f"https://bapi.vidtory.net/generative-core/jobs/{job_id}/status", headers=headers, timeout=15)
    d = r2.json().get("data", {})
    status = d.get("status", "")
    if status == "COMPLETED":
        url = d.get("result", {}).get("url", "")
        print(f"IMAGE_URL:{url}")
        break
    elif status == "FAILED":
        print(f"FAILED: {d}")
        break
    else:
        print(f"[{(i+1)*5}s] {status}")
```

Sau đó chạy bằng exec:
```
command: python
args: ["C:\\Users\\vidto\\.vidtoryagent\\tmp_gen.py"]
env: {"PYTHONIOENCODING": "utf-8"}
```

Sau khi exec xong, tìm dòng `IMAGE_URL:...` trong output → lấy URL → gửi qua `message` tool.

## Template: Kiểm tra balance

```python
import sys, httpx, json
sys.stdout.reconfigure(encoding='utf-8')
API_KEY = "REPLACE_WITH_API_KEY"
r = httpx.get("https://bapi.vidtory.net/merchant/info", headers={"x-api-key": API_KEY}, timeout=15)
d = r.json().get("data", {})
balance = d.get("balance", {}).get("currentBalance", 0)
print(f"BALANCE:{balance}")
print(f"MERCHANT:{d.get('businessName','')}")
```

## Template: Upload file (ảnh reference, logo)

```python
import sys, httpx
sys.stdout.reconfigure(encoding='utf-8')
API_KEY = "REPLACE_WITH_API_KEY"
FILE_PATH = "REPLACE_WITH_PATH"
with open(FILE_PATH, "rb") as f:
    r = httpx.post("https://bapi.vidtory.net/media/upload",
                   headers={"x-api-key": API_KEY},
                   files={"file": f}, timeout=60)
data = r.json()
url = data.get("url", "")
print(f"MEDIA_URL:{url}")
```

## Aspect Ratio Values

| Muốn | Dùng |
|---|---|
| 1:1 (Instagram feed, vuông) | `IMAGE_ASPECT_RATIO_SQUARE` |
| 9:16 (Story, Reels, TikTok) | `IMAGE_ASPECT_RATIO_PORTRAIT` |
| 16:9 (YouTube, Website) | `IMAGE_ASPECT_RATIO_LANDSCAPE` |
| 3:4 | `IMAGE_ASPECT_RATIO_PORTRAIT_THREE_FOUR` |
| 4:3 | `IMAGE_ASPECT_RATIO_LANDSCAPE_FOUR_THREE` |
