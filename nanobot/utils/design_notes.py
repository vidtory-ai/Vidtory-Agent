"""Design notes builder for Vidtory Resident Designer.

Each generation output is accompanied by a "design note" — a structured
explanation of *why* the agent made specific creative choices. Notes
reference the exact memory layer (core/style/preference) that influenced
each decision, creating transparency and building client trust.

This is the core differentiator: the agent doesn't just produce images,
it *explains its reasoning* like a real in-house designer would.

Public API
----------
- :func:`build_design_note` — main entry: produces a design note for a generation
- :func:`format_design_note_for_chat` — format for Telegram display
"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger


def build_design_note(
    *,
    user_id: str,
    original_prompt: str,
    enhanced_prompt: str,
    content_type: str | None = None,
    model_used: str = "",
    aspect_ratio: str | None = None,
    db=None,
) -> str:
    """Build a structured design note explaining creative decisions.

    Reads from brand_memory layers to cite exactly which rule or preference
    influenced each aspect of the output.

    Returns:
        A multi-line design note string ready for storage and display.
    """
    try:
        if db is None:
            from nanobot.db.customer_db import get_db
            db = get_db()
    except Exception:
        logger.debug("design_notes: could not access DB, returning minimal note")
        return _minimal_note(content_type, model_used)

    uid = user_id.split("|")[0].strip()
    all_memory = db.get_all_memory(uid)

    notes: list[str] = []

    # ── Core layer references ───────────────────────────────────────────
    core = {m["key"]: m for m in all_memory.get("core", [])}
    if core:
        core_refs = []
        if "color_primary" in core:
            core_refs.append(f"Màu chủ đạo: {core['color_primary']['value']} (Brand Core)")
        if "color_secondary" in core:
            core_refs.append(f"Màu phụ: {core['color_secondary']['value']} (Brand Core)")
        if "color_accent" in core:
            core_refs.append(f"Màu accent: {core['color_accent']['value']} (Brand Core)")
        if "tone_of_voice" in core:
            core_refs.append(f"Tone: {core['tone_of_voice']['value']} (Brand Core)")
        if "logo" in core:
            core_refs.append("Logo thương hiệu đã được tham chiếu (Brand Core)")
        if "typography" in core:
            core_refs.append(f"Typography: {core['typography']['value']} (Brand Core)")
        if core_refs:
            notes.append("🏛️ **Brand Core:**")
            notes.extend(f"  • {ref}" for ref in core_refs)

    # ── Style layer references ──────────────────────────────────────────
    style = {m["key"]: m for m in all_memory.get("style", [])}
    if style:
        style_refs = []
        if "aesthetic" in style:
            style_refs.append(f"Phong cách: {style['aesthetic']['value']} (Style Memory)")
        if "mood_reference" in style:
            style_refs.append(f"Mood: {style['mood_reference']['value']} (Style Memory)")
        if "lighting_preference" in style:
            style_refs.append(f"Ánh sáng: {style['lighting_preference']['value']} (Style Memory)")
        if "composition_style" in style:
            style_refs.append(f"Bố cục: {style['composition_style']['value']} (Style Memory)")
        if "must_look_like" in style:
            style_refs.append(f"Phải giống: {style['must_look_like']['value']} (Style Memory)")
        if "must_not_look_like" in style:
            style_refs.append(f"Không được giống: {style['must_not_look_like']['value']} (Style Memory)")
        if style_refs:
            notes.append("🎨 **Style Memory:**")
            notes.extend(f"  • {ref}" for ref in style_refs)

    # ── Preference layer references ─────────────────────────────────────
    prefs = all_memory.get("preference", [])
    if prefs:
        pref_refs = []
        for p in prefs[:5]:  # Cap at 5 most relevant
            source_info = f" (học từ {p['source']})" if p["source"] else ""
            pref_refs.append(f"{p['key']}: {p['value']}{source_info}")
        if pref_refs:
            notes.append("💡 **Preference Memory (tự học):**")
            notes.extend(f"  • {ref}" for ref in pref_refs)

    # ── Project context ─────────────────────────────────────────────────
    projects = all_memory.get("project", [])
    if projects:
        proj_refs = [f"{p['key']}: {p['value']}" for p in projects[:3]]
        if proj_refs:
            notes.append("📋 **Project Context:**")
            notes.extend(f"  • {ref}" for ref in proj_refs)

    # ── Technical details ───────────────────────────────────────────────
    tech = []
    if content_type:
        tech.append(f"Content type: {content_type}")
    if model_used:
        tech.append(f"Model: {model_used}")
    if aspect_ratio:
        tech.append(f"Aspect ratio: {aspect_ratio}")
    if tech:
        notes.append("⚙️ **Technical:**")
        notes.extend(f"  • {t}" for t in tech)

    if not notes:
        return _minimal_note(content_type, model_used)

    return "\n".join(notes)


def _minimal_note(content_type: str | None, model_used: str) -> str:
    """Fallback design note when no memory layers are available."""
    parts = ["📝 Design Note: Professional defaults applied"]
    if content_type:
        parts.append(f"  • Content type: {content_type}")
    if model_used:
        parts.append(f"  • Model: {model_used}")
    return "\n".join(parts)


def format_design_note_for_chat(note: str, *, max_lines: int = 8) -> str:
    """Format a design note for display in Telegram chat.

    Wraps the note in a compact format suitable for sending after
    the generated image. Truncates to *max_lines* to avoid cluttering chat.
    """
    if not note:
        return ""
    lines = note.strip().split("\n")
    if len(lines) > max_lines:
        lines = lines[:max_lines] + ["  ..."]
    body = "\n".join(lines)
    return f"───── Design Note ─────\n{body}\n───────────────────────"


def build_memory_citation(layer: str, key: str, value: str, source: str = "") -> str:
    """Build a single citation line for use in LLM context.

    Example: "color_primary=#1A2B3C (Brand Core, confirmed 2026-06-10)"
    """
    layer_labels = {
        "core": "Brand Core",
        "style": "Style Memory",
        "preference": "Preference Memory",
        "project": "Project Context",
        "insight": "Insight Bank",
    }
    label = layer_labels.get(layer, layer)
    source_tag = f", {source}" if source else ""
    return f"{key}={value} ({label}{source_tag})"
