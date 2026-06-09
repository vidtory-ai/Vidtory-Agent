"""Customer Profile Manager for Vidtory-Agent.

This module is the **authoritative** code layer for all customer profile operations.
It replaces ad-hoc ``read_file``/``write_file`` LLM tool calls with reliable,
schema-validated Python functions.

Public API
----------
- :func:`profile_exists` — check before triggering onboarding
- :func:`load_profile` — load + validate, with schema migration
- :func:`save_profile` — atomic write with backup
- :func:`get_onboarding_status` — returns current onboarding state
- :func:`get_profile_completeness` — 0-100 score for input validation
- :func:`append_feedback` — append-only feedback log
- :func:`record_generation` — log generation + update counters
- :func:`update_learning` — process feedback, auto-update profile if pattern emerges
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _customer_dir(user_id: str) -> Path:
    """Return ~/.vidtoryagent/customers/{user_id}/."""
    from nanobot.config.paths import get_data_dir
    uid = user_id.split("|")[0].strip()
    return get_data_dir().parent / "customers" / uid


def _profile_path(user_id: str) -> Path:
    return _customer_dir(user_id) / "profile.json"


def _feedback_path(user_id: str) -> Path:
    return _customer_dir(user_id) / "feedback.jsonl"


def _history_path(user_id: str) -> Path:
    return _customer_dir(user_id) / "generation-history.jsonl"


# ---------------------------------------------------------------------------
# Profile existence & loading
# ---------------------------------------------------------------------------

def profile_exists(user_id: str) -> bool:
    """Return True if a profile.json exists and is valid JSON for this user."""
    path = _profile_path(user_id)
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return isinstance(data, dict)
    except Exception:
        return False


def get_onboarding_status(user_id: str) -> str:
    """Return onboarding status: 'none' | 'minimal' | 'in_progress' | 'completed'."""
    if not profile_exists(user_id):
        return "none"
    profile = load_profile(user_id)
    if not profile:
        return "none"
    return (profile.get("onboarding") or {}).get("status", "none")


def load_profile(user_id: str) -> dict[str, Any] | None:
    """Load and validate a customer profile.

    Performs lightweight schema migration (adds missing top-level keys).
    Returns ``None`` if the file does not exist or cannot be parsed.
    """
    path = _profile_path(user_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to parse customer profile for {}: {}", user_id, exc)
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

    # Remove sensitive key from profile — API key is managed by TelegramKeyStore
    data.pop("apiKey", None)

    return data


# ---------------------------------------------------------------------------
# Profile saving
# ---------------------------------------------------------------------------

def save_profile(user_id: str, profile: dict[str, Any]) -> bool:
    """Atomically write a customer profile.

    Creates the customer directory if needed. Makes a ``.bak`` backup of any
    existing profile before overwriting. Returns True on success.
    """
    path = _profile_path(user_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)

        # Backup existing file before overwriting
        if path.is_file():
            path.replace(path.with_suffix(".json.bak"))

        # Remove API key before saving (security)
        clean = {k: v for k, v in profile.items() if k != "apiKey"}

        # Write to temp file first, then rename (atomic on same FS)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

        logger.debug("Saved customer profile for {}", user_id)
        return True
    except Exception as exc:
        logger.error("Failed to save customer profile for {}: {}", user_id, exc)
        return False


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
    rating: str,  # "approved" | "rejected"
    comment: str = "",
    adjustments: str = "",
) -> bool:
    """Append a feedback entry to the customer's feedback.jsonl log.

    This is append-only — entries are never deleted, providing a complete
    audit trail.
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "generationId": generation_id or f"gen-{int(time.time())}",
        "contentType": content_type,
        "originalPrompt": original_prompt,
        "enhancedPrompt": enhanced_prompt,
        "rating": rating,
        "comment": comment,
        "adjustments": adjustments,
    }
    path = _feedback_path(user_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return True
    except Exception as exc:
        logger.error("Failed to append feedback for {}: {}", user_id, exc)
        return False


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
    gen_id = f"gen-{int(time.time())}"
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "generationId": gen_id,
        "contentType": content_type,
        "originalPrompt": prompt,
        "enhancedPrompt": enhanced_prompt,
        "model": model,
        "resultUrl": result_url,
    }
    path = _history_path(user_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("Failed to log generation history for {}: {}", user_id, exc)

    # Increment counter
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
    - APPROVED: increment approvedCount. If prompt score ≥ 3 approvals, add to bestPerformingPrompts.
    - REJECTED: increment rejectedCount. If same feedback appears ≥ 2 times → add to commonFeedback.
    - REJECTED with specific complaint → analyze and potentially update avoidList.
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
        learning["approvedCount"] = learning.get("approvedCount", 0) + 1
        # Track best performing prompt
        if prompt:
            best = learning.setdefault("bestPerformingPrompts", [])
            # Count how many times this prompt (or similar) was approved
            similar = [p for p in best if isinstance(p, str) and p[:50] == prompt[:50]]
            if not similar and len(best) < 10:
                best.append(prompt[:200])
                changed = True
        logger.debug("Learning: approved recorded for {}", user_id)

    elif rating == "rejected":
        learning["rejectedCount"] = learning.get("rejectedCount", 0) + 1

        if feedback_text:
            # Count occurrences of this feedback in recent history
            occurrence_count = _count_feedback_occurrences(user_id, feedback_text)

            common = learning.setdefault("commonFeedback", [])

            # ≥ 2 same complaints → add to commonFeedback (silent auto-update)
            if occurrence_count >= 2:
                normalized = feedback_text.strip().lower()[:100]
                existing = [str(f).lower()[:100] for f in common]
                if normalized not in existing and len(common) < 10:
                    common.append(feedback_text.strip()[:100])
                    changed = True
                    logger.info(
                        "Learning: pattern '{}' detected ≥2x for {} — added to commonFeedback",
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


def _count_feedback_occurrences(user_id: str, feedback_text: str) -> int:
    """Count how many times similar feedback has been logged in feedback.jsonl."""
    path = _feedback_path(user_id)
    if not path.is_file():
        return 1  # This is the first occurrence

    needle = feedback_text.strip().lower()[:60]
    count = 0
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
                comment = str(entry.get("comment", "")).strip().lower()[:60]
                if comment and comment == needle:
                    count += 1
            except Exception:
                continue
    except Exception:
        pass
    return max(count, 1)


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
