"""Public customer-context API.

The query-aware formatting and prompt-selection logic lives in
``customer_memory_context`` so this module stays focused on profile loading and
channel defaults.
"""

from __future__ import annotations

from typing import Any

from nanobot.utils.customer_memory_context import (
    build_prompt_brand_suffix,
    format_customer_context_lines,
)


def load_customer_profile(telegram_user_id: str) -> dict[str, Any] | None:
    """Load a validated customer profile by Telegram user ID."""
    uid = telegram_user_id.split("|")[0].strip()
    if not uid.isdigit():
        return None
    try:
        from nanobot.utils.customer_profile import load_profile

        return load_profile(uid)
    except Exception:
        return None


def get_default_aspect_ratio_for_channel(
    profile: dict[str, Any],
    channel_hint: str | None = None,
) -> str | None:
    """Return the configured aspect ratio for a hinted or primary channel."""
    if not isinstance(profile, dict):
        return None
    channels = profile.get("contentChannels")
    if not isinstance(channels, dict):
        return None
    formats = channels.get("defaultFormats")
    if not isinstance(formats, dict):
        formats = {}

    if channel_hint and channel_hint in formats:
        hinted = formats.get(channel_hint)
        if isinstance(hinted, dict):
            return hinted.get("aspectRatio")

    primary = channels.get("primary") or []
    if isinstance(primary, str):
        primary = [primary]
    if not isinstance(primary, list):
        return None

    channel_map = {
        "instagram": "instagram_feed",
        "facebook": "facebook_post",
        "youtube": "youtube_thumbnail",
        "tiktok": "tiktok_video_cover",
        "website": "website_hero",
        "zalo": "zalo",
        "linkedin": "linkedin_post",
        "print": "print_a4",
    }
    for channel in primary:
        channel_name = str(channel).lower()
        format_key = channel_map.get(channel_name, channel_name)
        configured = formats.get(format_key)
        if isinstance(configured, dict) and configured.get("aspectRatio"):
            return configured["aspectRatio"]
    return None


def get_customer_logo_url(profile: dict[str, Any]) -> str | None:
    """Return the customer's configured logo URL, if present."""
    if not isinstance(profile, dict):
        return None
    brand = profile.get("brand")
    if not isinstance(brand, dict):
        return None
    logo_url = str(brand.get("logoUrl") or "").strip()
    return logo_url or None


__all__ = [
    "build_prompt_brand_suffix",
    "format_customer_context_lines",
    "get_customer_logo_url",
    "get_default_aspect_ratio_for_channel",
    "load_customer_profile",
]
