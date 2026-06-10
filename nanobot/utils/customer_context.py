"""Customer context loader for Vidtory-Agent.

Loads a customer's profile from ~/.vidtoryagent/customers/{user_id}/profile.json
and formats it into context lines that are injected into every LLM turn.

This enables the agent to automatically:
- Apply brand guidelines when generating media
- Use correct aspect ratios per content channel
- Optimize prompts with style keywords and photography preferences
- Personalize responses based on audience and language preference
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _get_customer_dir() -> Path:
    """Return the base directory for customer profiles."""
    from nanobot.config.paths import get_data_dir
    return get_data_dir().parent / "customers"


def load_customer_profile(telegram_user_id: str) -> dict[str, Any] | None:
    """Load a customer profile by Telegram user ID.

    Args:
        telegram_user_id: The numeric Telegram user ID (extracted from sender_id).

    Returns:
        Parsed profile dict, or None if not found / invalid.
    """
    # sender_id may be "12345" or "12345|username"
    uid = telegram_user_id.split("|")[0].strip()
    if not uid.isdigit():
        return None

    # Primary: load from SQLite DB (current architecture)
    try:
        from nanobot.utils.customer_profile import load_profile
        profile = load_profile(uid)
        if profile is not None:
            return profile
    except Exception:
        pass

    # Legacy fallback: try JSON file (migration may not have run)
    profile_path = _get_customer_dir() / uid / "profile.json"
    if not profile_path.is_file():
        return None

    try:
        return json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def format_customer_context_lines(profile: dict[str, Any]) -> list[str]:
    """Format a customer profile into runtime context lines for the LLM.

    Returns compact, actionable lines injected into every turn's runtime context.
    """
    lines: list[str] = []

    # Business context
    business = profile.get("business") or {}
    if business.get("name"):
        biz_desc = business.get("description") or ""
        lines.append(f"Customer Business: {business['name']}" + (f" — {biz_desc}" if biz_desc else ""))

    # Brand guidelines
    brand = profile.get("brand") or {}
    if brand:
        parts = []
        if brand.get("style"):
            parts.append(f"style={brand['style']}")
        keywords = brand.get("moodKeywords") or []
        if keywords:
            parts.append(f"mood={', '.join(keywords)}")
        if brand.get("photographyStyle"):
            parts.append(f"photo={brand['photographyStyle']}")
        palette = brand.get("colorPalette") or {}
        if palette:
            colors = ", ".join(f"{k}:{v}" for k, v in palette.items() if v)
            parts.append(f"colors={colors}")
        avoid = brand.get("avoidList") or []
        if avoid:
            parts.append(f"avoid=[{', '.join(avoid)}]")
        if parts:
            lines.append("Brand Guidelines: " + " | ".join(parts))

    # Target audience
    audience = profile.get("audience") or {}
    if audience:
        aud_parts = []
        if audience.get("ageRange"):
            aud_parts.append(f"age {audience['ageRange']}")
        if audience.get("segment"):
            aud_parts.append(f"segment={audience['segment']}")
        if audience.get("gender") and audience["gender"] != "all":
            aud_parts.append(f"gender={audience['gender']}")
        if aud_parts:
            lines.append("Target Audience: " + ", ".join(aud_parts))

    # Content channels & default formats
    channels = profile.get("contentChannels") or {}
    primary_channels = channels.get("primary") or []
    default_formats = channels.get("defaultFormats") or {}
    if primary_channels:
        channel_info = ", ".join(primary_channels)
        format_hints = []
        for ch_key, fmt in default_formats.items():
            ar = (fmt or {}).get("aspectRatio")
            if ar:
                format_hints.append(f"{ch_key}={ar}")
        if format_hints:
            channel_info += f" [formats: {', '.join(format_hints)}]"
        lines.append(f"Primary Channels: {channel_info}")

    # Communication preference
    prefs = profile.get("preferences") or {}
    lang = prefs.get("communicationLanguage")
    if lang:
        lines.append(f"User Language: {lang}")

    # Learning data (feedback history)
    learning = profile.get("learningData") or {}
    best_prompts = learning.get("bestPerformingPrompts") or []
    common_feedback = learning.get("commonFeedback") or []
    if best_prompts:
        lines.append(f"Best Performing Prompts: {'; '.join(str(p) for p in best_prompts[:3])}")
    if common_feedback:
        lines.append(f"Customer Feedback Preferences: {'; '.join(str(f) for f in common_feedback[:5])}")

    # Logo URL (if available)
    logo_url = (brand.get("logoUrl") or "").strip()
    if logo_url:
        lines.append(f"Brand Logo: {logo_url}")

    return lines


def build_prompt_brand_suffix(profile: dict[str, Any]) -> str:
    """Build a compact brand suffix to append to image/video generation prompts.

    Used by generate_image tool to auto-apply brand guidelines.
    Returns empty string if no relevant brand data.
    """
    brand = profile.get("brand") or {}
    if not brand:
        return ""

    parts: list[str] = []

    style = brand.get("style")
    if style:
        parts.append(style)

    keywords = brand.get("moodKeywords") or []
    if keywords:
        parts.extend(keywords[:3])

    photo_style = brand.get("photographyStyle")
    if photo_style:
        parts.append(photo_style)

    palette = brand.get("colorPalette") or {}
    if palette.get("primary"):
        parts.append(f"primary color {palette['primary']}")

    avoid = brand.get("avoidList") or []
    avoid_str = ""
    if avoid:
        avoid_str = f", avoid: {', '.join(avoid)}"

    if not parts:
        return ""
    suffix = ", ".join(parts) + avoid_str

    # Note about logo availability (LLM can decide to incorporate)
    logo_url = (brand.get("logoUrl") or "").strip()
    if logo_url:
        suffix += f", brand has logo available"

    return suffix


def get_default_aspect_ratio_for_channel(
    profile: dict[str, Any],
    channel_hint: str | None = None,
) -> str | None:
    """Return the best aspect ratio for the customer's primary channel.

    Args:
        profile: Customer profile dict.
        channel_hint: Optional hint like "instagram_story", "website".

    Returns:
        Aspect ratio string like "1:1", "9:16", "16:9", or None.
    """
    channels = profile.get("contentChannels") or {}
    formats = channels.get("defaultFormats") or {}

    if channel_hint and channel_hint in formats:
        return (formats[channel_hint] or {}).get("aspectRatio")

    primary = channels.get("primary") or []
    if not primary:
        return None

    # Map primary channel to default format key
    channel_map = {
        "instagram": "instagram_feed",
        "facebook": "instagram_feed",
        "youtube": "website",
        "tiktok": "instagram_story",
    }
    for ch in primary:
        key = channel_map.get(ch.lower(), ch)
        if key in formats:
            ar = (formats[key] or {}).get("aspectRatio")
            if ar:
                return ar

    return None
