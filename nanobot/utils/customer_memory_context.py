"""Compact customer context and prompt memory for creative generation."""

from __future__ import annotations

from typing import Any

from nanobot.utils.memory_relevance import load_relevant_memory


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _append_budgeted(lines: list[str], value: Any, max_chars: int) -> None:
    clean = " ".join(str(value or "").split())
    if not clean:
        return
    used = sum(len(line) for line in lines) + max(0, len(lines) - 1)
    remaining = max_chars - used - (1 if lines else 0)
    if remaining < 20:
        return
    if len(clean) > remaining:
        clean = clean[: max(1, remaining - 1)].rstrip() + "…"
    lines.append(clean)


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    normalized: list[set[str]] = []
    for raw in values:
        value = " ".join(str(raw or "").split()).strip(" ,")
        words = set(value.casefold().split())
        if not words or any(words <= existing for existing in normalized):
            continue
        keep = [
            (old_value, old_words)
            for old_value, old_words in zip(result, normalized, strict=True)
            if not old_words < words
        ]
        result = [item[0] for item in keep]
        normalized = [item[1] for item in keep]
        result.append(value)
        normalized.append(words)
    return result


def format_customer_context_lines(
    profile: dict[str, Any],
    *,
    query: str = "",
    max_chars: int = 2200,
    include_quality: bool = False,
) -> list[str]:
    """Return high-signal customer context within a strict character budget."""
    if not isinstance(profile, dict) or max_chars <= 0:
        return []
    lines: list[str] = []
    user_id = str(profile.get("telegramUserId") or "").strip()

    if include_quality and user_id:
        try:
            from nanobot.utils.quality_metrics import get_quality_summary

            for quality_line in get_quality_summary(user_id):
                _append_budgeted(lines, quality_line, max_chars)
        except Exception:
            pass

    business = _as_dict(profile.get("business"))
    if business.get("name"):
        description = str(business.get("description") or "").strip()
        _append_budgeted(
            lines,
            f"Customer Business: {business['name']}"
            + (f" — {description}" if description else ""),
            max_chars,
        )

    brand = _as_dict(profile.get("brand"))
    brand_parts: list[str] = []
    if brand.get("style"):
        brand_parts.append(f"style={brand['style']}")
    moods = _as_list(brand.get("moodKeywords"))
    if moods:
        brand_parts.append(f"mood={', '.join(str(item) for item in moods[:4])}")
    if brand.get("photographyStyle"):
        brand_parts.append(f"photo={brand['photographyStyle']}")
    palette = _as_dict(brand.get("colorPalette"))
    if palette:
        colors = ", ".join(f"{key}:{value}" for key, value in palette.items() if value)
        if colors:
            brand_parts.append(f"colors={colors}")
    avoid = _as_list(brand.get("avoidList"))
    if avoid:
        brand_parts.append(f"avoid=[{', '.join(str(item) for item in avoid[:5])}]")
    if brand_parts:
        _append_budgeted(lines, "Brand Guidelines: " + " | ".join(brand_parts), max_chars)

    logo_url = str(brand.get("logoUrl") or "").strip()
    if logo_url:
        _append_budgeted(lines, f"Brand Logo: {logo_url}", max_chars)

    audience = _as_dict(profile.get("audience"))
    audience_parts = [
        value
        for value in (
            f"age={audience.get('ageRange')}" if audience.get("ageRange") else "",
            f"segment={audience.get('segment')}" if audience.get("segment") else "",
            (
                f"gender={audience.get('gender')}"
                if audience.get("gender") and audience.get("gender") != "all"
                else ""
            ),
        )
        if value
    ]
    if audience_parts:
        _append_budgeted(lines, "Target Audience: " + ", ".join(audience_parts), max_chars)

    channels = _as_dict(profile.get("contentChannels"))
    primary = _as_list(channels.get("primary"))
    if primary:
        _append_budgeted(
            lines,
            "Primary Channels: " + ", ".join(str(item) for item in primary[:5]),
            max_chars,
        )

    language = _as_dict(profile.get("preferences")).get("communicationLanguage")
    if language:
        _append_budgeted(lines, f"User Language: {language}", max_chars)

    memory_budget = min(800, max(120, max_chars // 3))
    selected = load_relevant_memory(
        profile,
        query=query,
        max_chars=memory_budget,
        max_entries=10,
    )
    existing = " ".join(lines).casefold()
    # Memory is injected as STYLE/PREFERENCE reference only.
    # LLM is told these are creative preferences — never object/scene descriptions.
    if selected:
        _append_budgeted(
            lines,
            (
                "[CUSTOMER_MEMORY_DATA] Creative style preferences only; "
                "do NOT re-use specific objects, subjects, or characters from past images "
                "unless the current user request explicitly mentions them."
            ),
            max_chars,
        )
    for entry in selected:
        key = str(entry.get("key") or "").strip().lower()
        value = str(entry.get("value") or "").strip()
        # Skip best_prompt/good_prompt entries: these are full prompt strings that
        # contain specific scene objects (e.g. 'rùa biển', 'Totoro') which must NOT
        # bleed into new, unrelated requests. Only style/mood/color/feedback is safe.
        if any(marker in key for marker in ("best_prompt", "good_prompt", "prompt_")):
            continue
        if not value or value.casefold() in existing:
            continue
        _append_budgeted(
            lines,
            (
                f"Relevant Memory [{entry.get('layer', 'memory')}] "
                f"{entry.get('key', 'item')}={value}"
            ),
            max_chars,
        )
        existing += " " + value.casefold()

    return lines


def build_prompt_brand_suffix(
    profile: dict[str, Any],
    *,
    query: str = "",
    max_chars: int = 900,
) -> str:
    """Return query-relevant brand and learning constraints for generation."""
    if not isinstance(profile, dict) or max_chars <= 0:
        return ""
    brand = _as_dict(profile.get("brand"))
    lang = _as_dict(profile.get("preferences")).get("communicationLanguage", "")
    labels = (
        {
            "primary": "màu chủ đạo",
            "secondary": "màu phụ",
            "accent": "màu điểm nhấn",
            "avoid": "tránh",
        }
        if lang == "vi"
        else {
            "primary": "primary color",
            "secondary": "secondary color",
            "accent": "accent color",
            "avoid": "avoid",
        }
    )

    selected = load_relevant_memory(
        profile,
        query=query,
        max_chars=min(650, max_chars),
        max_entries=10,
    )
    parts: list[str] = []
    constraints: list[str] = []
    memory_color_keys = {
        "color_primary": labels["primary"],
        "color_secondary": labels["secondary"],
        "color_accent": labels["accent"],
    }
    for entry in selected:
        key = str(entry.get("key") or "").strip().lower()
        value = str(entry.get("value") or "").strip()
        layer = str(entry.get("layer") or "").strip().lower()
        if not value or key == "logo":
            continue
        # Skip best_prompt/good_prompt entries: they contain full prompt strings
        # with specific objects/subjects from past sessions. Injecting them would
        # cause characters, animals, or scenes from old images to appear in new,
        # unrelated requests. Only style-neutral entries (colors, mood, feedback)
        # are safe to inject into the generation prompt.
        if any(marker in key for marker in ("best_prompt", "good_prompt", "prompt_")):
            continue
        if key in memory_color_keys:
            parts.append(f"{memory_color_keys[key]} {value}")
        elif any(marker in key for marker in ("avoid", "must_not", "feedback")):
            constraints.append(value)
        else:
            try:
                confidence = float(entry.get("confidence", 1.0))
            except (TypeError, ValueError):
                confidence = 0.5
            if layer in {"core", "style"} or confidence >= 0.65:
                parts.append(value)

    if brand.get("style"):
        parts.append(str(brand["style"]))
    parts.extend(str(item) for item in _as_list(brand.get("moodKeywords"))[:4])
    if brand.get("photographyStyle"):
        parts.append(str(brand["photographyStyle"]))
    palette = _as_dict(brand.get("colorPalette"))
    for key in ("primary", "secondary", "accent"):
        if palette.get(key):
            parts.append(f"{labels[key]} {palette[key]}")
    constraints.extend(str(item) for item in _as_list(brand.get("avoidList")))

    segments = _dedupe(parts)
    constraints = _dedupe(constraints)
    if constraints:
        segments.insert(
            min(3, len(segments)),
            f"{labels['avoid']}: {', '.join(constraints)}",
        )

    kept: list[str] = []
    used = 0
    for segment in segments:
        separator = 2 if kept else 0
        remaining = max_chars - used - separator
        if remaining < 12:
            break
        if len(segment) > remaining:
            segment = segment[: max(1, remaining - 1)].rstrip() + "…"
        kept.append(segment)
        used += separator + len(segment)
    return ", ".join(kept)
