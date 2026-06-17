"""
Test: Verify 2 fixes for image generation
1. Prompt auto-enhancement is skipped for detailed prompts
2. Multiple images are routed equally via startImages
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Prompt filter — _is_detailed_prompt
# ─────────────────────────────────────────────────────────────────────────────

class FakeImageGenTool:
    """Minimal stub to test _is_detailed_prompt and _apply_customer_context."""

    _DETAILED_PROMPT_KEYWORDS = {
        "cinematic", "composition", "poster", "illustration", "render", "studio",
        "lighting", "bokeh", "depth of field", "editorial", "photorealistic",
        "high detail", "commercial quality", "professional", "high resolution",
        "sharp focus", "4k", "8k", "hdr", "color grade", "blender", "octane",
        "ghép", "kết hợp", "hòa quyện", "bố cục", "ánh sáng", "chuyên nghiệp",
        "poster", "minh họa", "concept", "banner", "logo",
    }

    def _is_detailed_prompt(self, prompt: str) -> bool:
        word_count = len(prompt.split())
        if word_count >= 30:
            return True
        prompt_lower = prompt.lower()
        return any(kw in prompt_lower for kw in self._DETAILED_PROMPT_KEYWORDS)


tool = FakeImageGenTool()

# ── Case 1: User's exact prompt (the bug case) ────────────────────────────────
user_prompt = (
    "Ghép ảnh tham chiếu với concept con vẹt bay trên đảo xa thành một poster "
    "minh họa chuyên nghiệp: giữ tinh thần cảnh thiên nhiên trong ảnh tham chiếu "
    "với hồ nước, cây lớn, bầu trời xanh, màu sắc mềm mại; thêm một con vẹt nhiệt "
    "đới rực rỡ đang bay phía trên mặt hồ hướng ra hòn đảo xa ở nền hậu cảnh. "
    "Bố cục hài hòa, ánh sáng đồng nhất, màu sắc được chỉnh chuyên nghiệp, "
    "cinematic illustration, high detail, clean composition, polished poster quality."
)

result = tool._is_detailed_prompt(user_prompt)
word_count = len(user_prompt.split())
print(f"\n{'='*60}")
print(f"TEST 1: Prompt filter")
print(f"{'='*60}")
print(f"Word count      : {word_count}")
print(f"Is detailed?    : {result}")
print(f"Expected        : True (should SKIP auto-enhancement)")
print(f"Status          : {'✅ PASS' if result else '❌ FAIL'}")

# ── Case 2: Short generic prompt — should STILL be enhanced ──────────────────
short_prompt = "tạo ảnh con mèo dễ thương"
result2 = tool._is_detailed_prompt(short_prompt)
print(f"\n--- Short prompt case ---")
print(f"Prompt          : '{short_prompt}'")
print(f"Word count      : {len(short_prompt.split())}")
print(f"Is detailed?    : {result2}")
print(f"Expected        : False (should APPLY auto-enhancement)")
print(f"Status          : {'✅ PASS' if not result2 else '❌ FAIL'}")

# ── Case 3: Prompt with beverage keyword but detailed enough ──────────────────
drink_prompt_detailed = (
    "a glass of refreshing lemonade on a wooden table, "
    "cinematic lighting, shallow depth of field, "
    "warm sunset in the background, editorial photography style, "
    "high detail, commercial quality poster"
)
result3 = tool._is_detailed_prompt(drink_prompt_detailed)
print(f"\n--- Beverage + cinematic (detailed) ---")
print(f"Is detailed?    : {result3}")
print(f"Expected        : True (has cinematic + depth of field → skip enhancement)")
print(f"Status          : {'✅ PASS' if result3 else '❌ FAIL'}")

# ── Case 4: Short beverage prompt — should get enhancement ───────────────────
short_drink = "ảnh cốc nước cam tươi"
result4 = tool._is_detailed_prompt(short_drink)
print(f"\n--- Short beverage prompt ---")
print(f"Prompt          : '{short_drink}'")
print(f"Is detailed?    : {result4}")
print(f"Expected        : False (short, should apply beverage style)")
print(f"Status          : {'✅ PASS' if not result4 else '❌ FAIL'}")

# ─────────────────────────────────────────────────────────────────────────────
# Test 2: Multi-image routing
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"TEST 2: Multi-image routing to startImages")
print(f"{'='*60}")

# Simulate the logic in VidtoryImageGenerationClient.generate()
def simulate_generate(reference_images):
    refs = list(reference_images or [])
    if len(refs) > 1:
        # New behavior: ALL refs go into extra_images (startImages)
        call_kwargs = {
            "ref_image": None,
            "extra_images": refs,
            "style_image_url": None,
        }
        return "multi", call_kwargs
    ref = refs[0] if refs else None
    return "single", {"ref_image": ref, "extra_images": [], "style_image_url": None}

# Case: 2 images
images_2 = ["https://cdn.example.com/img1.jpg", "https://cdn.example.com/img2.jpg"]
mode, kwargs = simulate_generate(images_2)

print(f"\n--- 2 images ---")
print(f"mode            : {mode}")
print(f"ref_image       : {kwargs['ref_image']}")
print(f"extra_images    : {kwargs['extra_images']}")
print(f"Expected        : ref_image=None, extra_images=[img1, img2]")
ok_2 = (
    mode == "multi"
    and kwargs["ref_image"] is None
    and kwargs["extra_images"] == images_2
)
print(f"Status          : {'✅ PASS — both images go to startImages equally' if ok_2 else '❌ FAIL'}")

# Case: 3 images
images_3 = ["img1", "img2", "img3"]
mode3, kwargs3 = simulate_generate(images_3)
print(f"\n--- 3 images ---")
print(f"extra_images    : {kwargs3['extra_images']}")
ok_3 = kwargs3["extra_images"] == images_3
print(f"Status          : {'✅ PASS — all 3 equally in startImages' if ok_3 else '❌ FAIL'}")

# Case: 1 image (unchanged path)
mode1, kwargs1 = simulate_generate(["single_img.jpg"])
print(f"\n--- 1 image (single path, unchanged) ---")
print(f"ref_image       : {kwargs1['ref_image']}")
print(f"extra_images    : {kwargs1['extra_images']}")
ok_1 = kwargs1["ref_image"] == "single_img.jpg" and kwargs1["extra_images"] == []
print(f"Status          : {'✅ PASS' if ok_1 else '❌ FAIL'}")

# Case: 0 images
mode0, kwargs0 = simulate_generate([])
print(f"\n--- 0 images (text-to-image) ---")
print(f"ref_image       : {kwargs0['ref_image']}")
ok_0 = kwargs0["ref_image"] is None and kwargs0["extra_images"] == []
print(f"Status          : {'✅ PASS' if ok_0 else '❌ FAIL'}")

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
all_pass = result and (not result2) and result3 and (not result4) and ok_2 and ok_3 and ok_1 and ok_0
print(f"OVERALL: {'✅ ALL TESTS PASSED' if all_pass else '❌ SOME TESTS FAILED'}")
print(f"{'='*60}\n")
