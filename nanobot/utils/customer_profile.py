"""Customer Profile Manager for Vidtory-Agent.

This module is the **authoritative** code layer for all customer profile operations.
All data is persisted in SQLite via ``nanobot.db.customer_db`` — no JSON files.

Public API (unchanged from file-based version)
----------
- :func:`profile_exists` — check before triggering onboarding
- :func:`load_profile` — load + validate, with schema migration
- :func:`save_profile` — atomic write (DB upsert)
- :func:`get_onboarding_status` — returns current onboarding state
- :func:`get_profile_completeness` — 0-100 score for input validation
- :func:`append_feedback` — append-only feedback log
- :func:`record_generation` — log generation + update counters
- :func:`update_learning` — process feedback, auto-update profile if pattern emerges
- :func:`create_minimal_profile` — quick-start profile for new users
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

from loguru import logger

# Configurable feedback pattern threshold (default: 2 same complaints → auto-update)
FEEDBACK_PATTERN_THRESHOLD = int(os.environ.get("VIDTORY_FEEDBACK_THRESHOLD", "2"))


# ---------------------------------------------------------------------------
# DB accessor (lazy to avoid circular imports at module load)
# ---------------------------------------------------------------------------

def _db():
    from nanobot.db.customer_db import get_db
    return get_db()


# ---------------------------------------------------------------------------
# Profile existence & loading
# ---------------------------------------------------------------------------

def profile_exists(user_id: str) -> bool:
    """Return True if a profile exists for this user."""
    return _db().profile_exists(user_id)


def get_onboarding_status(user_id: str) -> str:
    """Return onboarding status: 'none' | 'minimal' | 'in_progress' | 'completed'."""
    if not profile_exists(user_id):
        return "none"
    profile = load_profile(user_id)
    if not profile:
        return "none"
    return (profile.get("onboarding") or {}).get("status", "none")


def get_logo_url(user_id: str) -> str:
    """Return the logo URL for this user, or empty string."""
    return _db().get_logo_url(user_id)


def set_logo_url(user_id: str, url: str) -> bool:
    """Set or update the logo URL for this user.

    Updates both the indexed DB column and brand.logoUrl in profile_json.
    Returns True on success.
    """
    return _db().set_logo_url(user_id, url)


def clear_logo(user_id: str) -> bool:
    """Remove the logo URL for this user."""
    return _db().set_logo_url(user_id, "")


def load_profile(user_id: str) -> dict[str, Any] | None:
    """Load and validate a customer profile.

    Performs lightweight schema migration (adds missing top-level keys).
    Returns ``None`` if no profile found.
    """
    data = _db().load_profile(user_id)
    if data is None:
        return None

    if not isinstance(data, dict):
        return None

    # ── Schema migration — add missing top-level sections ──────────────────
    data.setdefault("onboarding", {"status": "minimal"})
    data.setdefault("learningData", {
        "totalGenerations": 0,
        "approvedCount": 0,
        "rejectedCount": 0,
        "commonFeedback": [],
        "bestPerformingPrompts": [],
    })

    # Remove sensitive key from profile — API key is managed by DB api_keys table
    data.pop("apiKey", None)

    return data


# ---------------------------------------------------------------------------
# Profile saving
# ---------------------------------------------------------------------------

def save_profile(user_id: str, profile: dict[str, Any]) -> bool:
    """Atomically save a customer profile to the database.

    Returns True on success.
    """
    return _db().save_profile(user_id, profile)


def create_minimal_profile(
    user_id: str,
    username: str | None = None,
    business_name: str | None = None,
    industry: str | None = None,
) -> dict[str, Any]:
    """Create and save a minimal profile for quick-start onboarding."""
    profile: dict[str, Any] = {
        "telegramUserId": user_id.split("|")[0].strip(),
        "telegramUsername": username or "",
        "onboarding": {
            "status": "minimal",
            "startedAt": datetime.now(timezone.utc).isoformat(),
            "currentStep": "minimal_complete",
        },
        "business": {
            "name": business_name or "",
            "industry": industry or "other",
            "description": "",
        },
        "brand": {
            "style": "",
            "moodKeywords": [],
            "colorPalette": {},
            "photographyStyle": "",
            "logoUrl": "",
            "avoidList": [],
        },
        "audience": {"gender": "all", "ageRange": "", "segment": "mid"},
        "contentChannels": {"primary": [], "defaultFormats": {}},
        "preferences": {"communicationLanguage": "vi", "autoApplyBrandGuidelines": True},
        "learningData": {
            "totalGenerations": 0,
            "approvedCount": 0,
            "rejectedCount": 0,
            "commonFeedback": [],
            "bestPerformingPrompts": [],
        },
    }
    save_profile(user_id, profile)
    return profile


# ---------------------------------------------------------------------------
# Profile completeness
# ---------------------------------------------------------------------------

def get_profile_completeness(profile: dict[str, Any]) -> int:
    """Return a completeness score 0-100 for a customer profile.

    Used by the input validator to determine if onboarding is complete enough
    for high-quality generation.
    """
    score = 0
    business = profile.get("business") or {}
    brand = profile.get("brand") or {}
    channels = profile.get("contentChannels") or {}
    audience = profile.get("audience") or {}

    # Business (20 pts)
    if business.get("name"):
        score += 10
    if business.get("industry") and business["industry"] != "other":
        score += 10

    # Brand (40 pts)
    if brand.get("style"):
        score += 15
    if brand.get("moodKeywords"):
        score += 10
    if brand.get("colorPalette", {}).get("primary"):
        score += 10
    if brand.get("photographyStyle"):
        score += 5

    # Channels (20 pts)
    if channels.get("primary"):
        score += 10
    if channels.get("defaultFormats"):
        score += 10

    # Audience (20 pts)
    if audience.get("ageRange"):
        score += 10
    if audience.get("segment"):
        score += 10

    return min(score, 100)


# ---------------------------------------------------------------------------
# Feedback & Learning
# ---------------------------------------------------------------------------

def append_feedback(
    user_id: str,
    *,
    generation_id: str | None = None,
    content_type: str = "image",
    original_prompt: str = "",
    enhanced_prompt: str = "",
    rating: str,
    comment: str = "",
    adjustments: str = "",
) -> bool:
    """Append a feedback entry to the database.

    This is append-only — entries are never deleted, providing a complete
    audit trail.
    """
    return _db().append_feedback(
        user_id,
        generation_id=generation_id or f"gen-{int(time.time())}",
        content_type=content_type,
        original_prompt=original_prompt,
        enhanced_prompt=enhanced_prompt,
        rating=rating,
        comment=comment,
        adjustments=adjustments,
    )


def record_generation(
    user_id: str,
    *,
    content_type: str = "image",
    prompt: str = "",
    enhanced_prompt: str = "",
    model: str = "",
    result_url: str = "",
) -> str:
    """Log a generation event and increment totalGenerations counter.

    Returns a generation ID that can be used later to record feedback.
    """
    gen_id = _db().record_generation(
        user_id,
        content_type=content_type,
        prompt=prompt,
        enhanced_prompt=enhanced_prompt,
        model=model,
        result_url=result_url,
    )
    # Increment counter in profile learningData
    _increment_counter(user_id, "totalGenerations")
    return gen_id


def update_learning(
    user_id: str,
    *,
    rating: str,  # "approved" | "rejected"
    prompt: str = "",
    feedback_text: str = "",
    generation_id: str | None = None,
) -> None:
    """Process feedback and silently update the customer profile if a pattern emerges.

    Learning rules (silent auto-update):
    - APPROVED: increment approvedCount. If prompt score >= 3 approvals, add to bestPerformingPrompts.
    - REJECTED: increment rejectedCount. If same feedback appears >= 2 times -> add to commonFeedback.
    - REJECTED with specific complaint -> analyze and potentially update avoidList.
    """
    profile = load_profile(user_id)
    if not profile:
        logger.warning("update_learning: no profile found for {}", user_id)
        return

    learning = profile.setdefault("learningData", {
        "totalGenerations": 0,
        "approvedCount": 0,
        "rejectedCount": 0,
        "commonFeedback": [],
        "bestPerformingPrompts": [],
    })

    changed = False

    if rating == "approved":
        # Always reload learning data fresh to avoid stale read-then-write
        fresh = load_profile(user_id)
        learning = fresh.get("learningData", learning) if fresh else learning
        learning["approvedCount"] = learning.get("approvedCount", 0) + 1
        profile["learningData"] = learning
        # Track best performing prompt
        if prompt:
            best = learning.setdefault("bestPerformingPrompts", [])
            similar = [p for p in best if isinstance(p, str) and p[:50] == prompt[:50]]
            if not similar and len(best) < 10:
                best.append(prompt[:200])
                changed = True
        if not changed:
            # Still need to save the incremented counter
            changed = True
        logger.debug("Learning: approved recorded for {}", user_id)

    elif rating == "rejected":
        # Always reload learning data fresh to avoid stale read-then-write
        fresh = load_profile(user_id)
        learning = fresh.get("learningData", learning) if fresh else learning
        learning["rejectedCount"] = learning.get("rejectedCount", 0) + 1
        profile["learningData"] = learning
        changed = True  # always save the incremented counter

        if feedback_text:
            occurrence_count = _db().count_feedback_occurrences(user_id, feedback_text)

            common = learning.setdefault("commonFeedback", [])

            # >= FEEDBACK_PATTERN_THRESHOLD same complaints -> add to commonFeedback (silent auto-update)
            if occurrence_count >= FEEDBACK_PATTERN_THRESHOLD:
                normalized = feedback_text.strip().lower()[:100]
                existing = [str(f).lower()[:100] for f in common]
                if normalized not in existing and len(common) < 10:
                    common.append(feedback_text.strip()[:100])
                    changed = True
                    logger.info(
                        "Learning: pattern '{}' detected >=2x for {} — added to commonFeedback",
                        normalized[:40], user_id,
                    )

            # Update avoidList if complaint maps to a visual keyword
            avoid_keywords = _extract_avoid_keywords(feedback_text)
            if avoid_keywords:
                brand = profile.setdefault("brand", {})
                avoid = brand.setdefault("avoidList", [])
                for kw in avoid_keywords:
                    if kw not in avoid:
                        avoid.append(kw)
                        changed = True
                        logger.info(
                            "Learning: added '{}' to avoidList for {} (silent)", kw, user_id
                        )

    if changed:
        profile["learningData"] = learning
        save_profile(user_id, profile)

    # Always append to feedback log
    append_feedback(
        user_id,
        generation_id=generation_id,
        rating=rating,
        comment=feedback_text,
        original_prompt=prompt,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _increment_counter(user_id: str, field: str) -> None:
    """Safely increment a counter in learningData."""
    profile = load_profile(user_id)
    if not profile:
        return
    learning = profile.setdefault("learningData", {})
    learning[field] = learning.get(field, 0) + 1
    save_profile(user_id, profile)


def _extract_avoid_keywords(feedback_text: str) -> list[str]:
    """Map Vietnamese/English feedback complaints to visual avoid keywords.

    This is a rule-based extractor — no LLM needed for common patterns.
    """
    text = feedback_text.lower()
    mappings: list[tuple[list[str], str]] = [
        (["quá sáng", "sáng quá", "chói", "overexposed", "too bright"], "overexposed"),
        (["quá tối", "tối quá", "dark", "too dark"], "too dark"),
        (["mờ", "blur", "blurry", "không sắc nét"], "blurry"),
        (["cartoon", "hoạt hình", "toon", "animated"], "cartoon"),
        (["xấu", "thô", "low quality", "chất lượng thấp"], "low quality"),
        (["sai màu", "màu sai", "wrong color", "lệch màu"], "incorrect colors"),
        (["quá phức tạp", "rối", "cluttered", "messy"], "cluttered"),
        (["thiếu chuyên nghiệp", "không chuyên", "amateur"], "amateur"),
        (["quá đơn giản", "nhạt", "plain", "boring"], "too plain"),
    ]
    found: list[str] = []
    for triggers, keyword in mappings:
        if any(t in text for t in triggers):
            found.append(keyword)
    return found
