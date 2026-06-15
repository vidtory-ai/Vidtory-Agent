"""Customer-facing completion copy for generated images."""

from __future__ import annotations

import re
from typing import Any

from nanobot.utils.memory_relevance import load_relevant_memory


def _text(value: Any, *, limit: int = 100) -> str:
    if not isinstance(value, str):
        return ""
    clean = re.sub(r"\s+", " ", value).strip(" .,-")
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"


def _primary_channel(profile: dict[str, Any]) -> str:
    primary = ((profile.get("contentChannels") or {}).get("primary") or [])
    if isinstance(primary, str):
        value = primary
    elif isinstance(primary, list) and primary:
        value = str(primary[0])
    else:
        return "mạng xã hội"
    labels = {
        "facebook": "Facebook",
        "instagram": "Instagram",
        "tiktok": "TikTok",
        "linkedin": "LinkedIn",
        "website": "website",
        "zalo": "Zalo",
    }
    return labels.get(value.strip().lower(), value.strip())


def _success_line(
    *,
    reference_count: int,
    brand_name: str,
) -> str:
    brand_clause = f" cho {brand_name}" if brand_name else ""
    if reference_count > 1:
        return (
            f"Đã kết hợp {reference_count} ảnh tham chiếu thành một thiết kế{brand_clause} theo hướng "
            "chuyên nghiệp hơn rồi nhé ✅"
        )
    if reference_count == 1:
        return f"Đã hoàn thiện thiết kế từ ảnh tham chiếu{brand_clause} rồi nhé ✅"
    return f"Đã tạo ảnh{brand_clause} theo hướng chuyên nghiệp rồi nhé ✅"


def _profile_context(profile: dict[str, Any], prompt: str) -> dict[str, str]:
    business = profile.get("business") or {}
    brand = profile.get("brand") or {}
    palette = brand.get("colorPalette") or {}
    moods = brand.get("moodKeywords") or []
    selected_memory = load_relevant_memory(
        profile,
        query=prompt,
        max_chars=420,
        max_entries=5,
    )
    feedback = next(
        (
            str(entry["value"])
            for entry in selected_memory
            if "feedback" in str(entry.get("key") or "").lower()
            or "avoid" in str(entry.get("key") or "").lower()
            or "must_not" in str(entry.get("key") or "").lower()
        ),
        "",
    )
    best_prompt = next(
        (
            str(entry["value"])
            for entry in selected_memory
            if "best_prompt" in str(entry.get("key") or "").lower()
        ),
        "",
    )
    memory_focus = [
        str(entry["value"])
        for entry in selected_memory
        if str(entry.get("value") or "").strip()
        and str(entry.get("value")) not in {feedback, best_prompt}
    ][:2]

    colors = ", ".join(
        str(value) for value in palette.values() if isinstance(value, str) and value
    )
    return {
        "brand_name": _text(business.get("name") or brand.get("businessName"), limit=50),
        "business_description": _text(business.get("description"), limit=100),
        "brand_style": _text(brand.get("style"), limit=60),
        "moods": _text(", ".join(str(item) for item in moods[:3]), limit=80),
        "colors": _text(colors, limit=70),
        "feedback": _text(feedback, limit=90),
        "best_prompt": _text(best_prompt, limit=90),
        "memory_focus": _text(" · ".join(memory_focus), limit=150),
        "channel": _primary_channel(profile),
    }


def _design_notes(
    prompt: str,
    *,
    reference_count: int,
    context: dict[str, str],
) -> list[str]:
    notes: list[str] = []
    if reference_count > 1:
        notes.append(
            "Mình giữ các chi tiết nhận diện quan trọng từ từng ảnh tham chiếu rồi thống nhất "
            "ánh sáng, màu, tỷ lệ và không gian để tổng thể không còn cảm giác chắp ghép."
        )
    elif reference_count:
        notes.append(
            "Mình giữ các chi tiết nhận diện quan trọng từ ảnh tham chiếu và làm lại bố cục "
            "để chủ thể rõ, tự nhiên hơn."
        )
    else:
        notes.append(
            "Mình ưu tiên một điểm nhìn chính, ánh sáng có chủ đích và khoảng thở tốt để "
            "hình trông sạch, chuyên nghiệp."
        )

    brand_bits = [
        bit
        for bit in (context["brand_style"], context["moods"], context["colors"])
        if bit
    ]
    if brand_bits:
        notes.append(
            "Hướng hình được bám theo nhận diện thương hiệu: " + " · ".join(brand_bits) + "."
        )
    else:
        notes.append(
            "Mình tiết chế hiệu ứng, giữ vật liệu và ánh sáng tự nhiên để tránh cảm giác "
            "bóng nhựa hoặc quá giống ảnh AI."
        )

    if context["feedback"]:
        notes.append(
            f"Mình cũng đã chủ động tránh lặp lại góp ý trước của bạn: {context['feedback']}."
        )
    elif context["memory_focus"]:
        notes.append(f"Memory liên quan nhất đã được áp dụng: {context['memory_focus']}.")
    return notes[:3]


def _suggestions(prompt: str, context: dict[str, str]) -> list[str]:
    del prompt
    brand = context["brand_name"] or "thương hiệu"
    business_context = context["business_description"] or f"hoạt động của {brand}"
    channel = context["channel"]
    approved_hint = (
        f", kế thừa hướng từng được duyệt: {context['best_prompt']}"
        if context["best_prompt"]
        else ""
    )

    return [
        (
            f"Tinh gọn cao cấp – làm rõ điểm nhìn, nhịp bố cục và nhận diện {brand}"
            f"{approved_hint}"
        ),
        (
            "Bối cảnh chân thực – phát triển chủ thể trong không gian phù hợp với "
            f"{business_context}, ánh sáng và vật liệu tự nhiên hơn"
        ),
        (
            f"Phiên bản chiến dịch – tăng điểm nhấn, phân cấp thông tin và tối ưu khung hình "
            f"cho {channel}"
        ),
    ]


def universal_direction_labels() -> list[str]:
    """Return topic-neutral creative axes for clarification buttons."""
    return [
        "Tinh gọn cao cấp",
        "Bối cảnh chân thực",
        "Chiến dịch nổi bật",
    ]


def build_image_delivery(
    *,
    prompt: str,
    profile: dict[str, Any] | None,
    reference_count: int,
    design_note: str = "",
) -> dict[str, Any]:
    """Build a stable post-generation message from customer and memory context."""
    del design_note  # Stored technical note remains available separately for auditing.
    safe_profile = profile if isinstance(profile, dict) else {}
    context = _profile_context(safe_profile, prompt)
    notes = _design_notes(
        prompt,
        reference_count=reference_count,
        context=context,
    )

    lines = [
        _success_line(
            reference_count=reference_count,
            brand_name=context["brand_name"],
        ),
        "",
        "Design note:",
        *(f"• {note}" for note in notes),
    ]
    return {
        "message": "\n".join(lines),
        "design_notes": notes,
        "context": {
            key: value
            for key, value in context.items()
            if value and key not in {"feedback", "best_prompt"}
        },
    }
