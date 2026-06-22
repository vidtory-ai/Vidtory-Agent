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

import hashlib
import os
import time
from datetime import datetime, timezone
from typing import Any

from loguru import logger

# Configurable feedback pattern threshold (default: 2 same complaints → auto-update)
FEEDBACK_PATTERN_THRESHOLD = int(os.environ.get("VIDTORY_FEEDBACK_THRESHOLD", "2"))
APPROVED_PROMPT_THRESHOLD = int(os.environ.get("VIDTORY_APPROVED_PROMPT_THRESHOLD", "3"))


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


async def set_logo_and_refresh_identity(
    user_id: str,
    url: str,
    *,
    image_bytes: bytes | None = None,
) -> dict[str, Any]:
    """Set a new logo and infer a fresh visual identity from it when possible."""
    saved = _db().set_logo_url(user_id, url)
    result = {"saved": saved, "identity_refreshed": False}
    if not saved or not url:
        return result

    data = image_bytes
    if data is None and "vidtory.net" in url.lower():
        try:
            import httpx

            async with httpx.AsyncClient(follow_redirects=True, timeout=5.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                if len(response.content) <= 5 * 1024 * 1024:
                    data = response.content
        except Exception as exc:
            logger.debug("Logo identity fetch skipped for {}: {}", user_id, exc)

    if not data:
        return result

    try:
        from nanobot.utils.brand_intelligence import analyze_logo_bytes, apply_logo_identity

        profile = load_profile(user_id)
        if not profile:
            return result
        analysis = analyze_logo_bytes(data)
        apply_logo_identity(profile, analysis, logo_url=url)
        if not save_profile(user_id, profile):
            return result

        source = f"logo_inference:{datetime.now(timezone.utc).isoformat()}"
        brand = profile.get("brand") or {}
        palette = brand.get("colorPalette") or {}
        for key in ("primary", "secondary", "accent"):
            if palette.get(key):
                _db().set_memory(
                    user_id,
                    layer="core",
                    key=f"color_{key}",
                    value=palette[key],
                    source=source,
                    force=True,
                )
        _db().set_memory(
            user_id, layer="core", key="logo", value=url, source=source, force=True
        )
        for key, value in (
            ("aesthetic", brand.get("style")),
            ("mood_reference", ", ".join(brand.get("moodKeywords") or [])),
            ("photography_style", brand.get("photographyStyle")),
        ):
            if value:
                _db().set_memory(
                    user_id,
                    layer="style",
                    key=key,
                    value=value,
                    source=source,
                    confidence=float(analysis.get("confidence", 0.0)),
                    force=True,
                )
        result["identity_refreshed"] = True
        result["analysis"] = analysis
    except Exception as exc:
        logger.warning("Failed to infer visual identity from logo for {}: {}", user_id, exc)
    return result


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
    platform: str = "telegram",
) -> dict[str, Any]:
    """Create and save a minimal profile for quick-start onboarding."""
    normalized_user_id = user_id.split("|")[0].strip()
    platform_value = (platform or "telegram").strip().lower()
    profile: dict[str, Any] = {
        "platform": platform_value,
        "platformUserId": normalized_user_id,
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
    if platform_value == "zalo":
        profile["zaloUserId"] = normalized_user_id
        profile["zaloUsername"] = username or ""
    else:
        profile["telegramUserId"] = normalized_user_id
        profile["telegramUsername"] = username or ""
    save_profile(user_id, profile)
    return profile


# ---------------------------------------------------------------------------
# Profile completeness
# ---------------------------------------------------------------------------

def get_profile_completeness(profile: dict[str, Any]) -> int:
    """Return a completeness score 0-100 for a customer profile.

    This is the legacy generation-readiness score used by validators.
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


def get_onboarding_completeness(profile: dict[str, Any]) -> int:
    """Return completeness for the adaptive onboarding fields."""
    from nanobot.utils.brand_intelligence import get_profile_gaps

    total_fields = 11
    missing = len(get_profile_gaps(profile))
    return round((total_fields - missing) / total_fields * 100)


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
    approval_occurrences = 0
    rejection_occurrences = 0

    if rating == "approved":
        # Always reload learning data fresh to avoid stale read-then-write
        fresh = load_profile(user_id)
        learning = fresh.get("learningData", learning) if fresh else learning
        learning["approvedCount"] = learning.get("approvedCount", 0) + 1
        profile["learningData"] = learning
        # Promote only repeated approvals. A single approval is useful evidence,
        # but not enough to become a durable best-performing pattern.
        if prompt:
            best = learning.setdefault("bestPerformingPrompts", [])
            similar = [p for p in best if isinstance(p, str) and p[:50] == prompt[:50]]
            prior_approvals = sum(
                1
                for item in _db().get_feedback_list(user_id)
                if item.get("rating") == "approved"
                and str(item.get("original_prompt") or "")[:200] == prompt[:200]
            )
            approval_occurrences = prior_approvals + 1
            if (
                approval_occurrences >= APPROVED_PROMPT_THRESHOLD
                and not similar
                and len(best) < 10
            ):
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
            rejection_occurrences = (
                _db().count_feedback_occurrences(user_id, feedback_text) + 1
            )

            common = learning.setdefault("commonFeedback", [])

            # >= FEEDBACK_PATTERN_THRESHOLD same complaints -> add to commonFeedback (silent auto-update)
            if rejection_occurrences >= FEEDBACK_PATTERN_THRESHOLD:
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
            if avoid_keywords and rejection_occurrences >= FEEDBACK_PATTERN_THRESHOLD:
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

        # ── Dual-write learned preferences to brand_memory ────────────────
        # This creates the traceable evidence trail:
        # each preference entry records the generation_id that triggered it.
        try:
            from nanobot.db.customer_db import get_db
            db = get_db()
            source = f"feedback:{generation_id or 'unknown'}"

            if rating == "rejected" and feedback_text:
                # Write avoid keywords to preference layer (learned, not locked)
                avoid_keywords = _extract_avoid_keywords(feedback_text)
                for kw in avoid_keywords:
                    db.set_memory(
                        user_id, layer="preference",
                        key=f"avoid_{kw.replace(' ', '_')}",
                        value=kw,
                        source=source,
                        confidence=min(
                            rejection_occurrences / 5.0,
                            1.0,
                        ),
                    )

                # Write common feedback pattern as preference
                normalized = feedback_text.strip().lower()[:100]
                db.set_memory(
                    user_id, layer="preference",
                    key=f"feedback_{normalized[:30].replace(' ', '_')}",
                    value=normalized,
                    source=source,
                    confidence=min(
                        rejection_occurrences / 5.0,
                        1.0,
                    ),
                )

            elif rating == "approved" and prompt:
                # Write approved prompt pattern as positive preference
                db.set_memory(
                    user_id, layer="preference",
                    key=(
                        "good_prompt_"
                        + hashlib.sha256(prompt[:50].encode("utf-8")).hexdigest()[:8]
                    ),
                    value=prompt[:150],
                    source=source,
                    confidence=min(
                        approval_occurrences / APPROVED_PROMPT_THRESHOLD,
                        1.0,
                    ),
                )
        except Exception:
            pass  # Non-fatal — profile_json remains source of truth

    # Always append to feedback log
    append_feedback(
        user_id,
        generation_id=generation_id,
        rating=rating,
        comment=feedback_text,
        original_prompt=prompt,
    )
    if rating == "rejected" and feedback_text:
        try:
            patterns = _db().get_global_feedback_patterns(min_users=5, limit=20)
            normalized = feedback_text.strip().lower()[:60]
            if any(item.get("feedback") == normalized for item in patterns):
                logger.warning(
                    "GLOBAL_FEEDBACK_PATTERN: '{}' reported by >=5 customers; "
                    "admin review required",
                    normalized,
                )
        except Exception:
            pass


def record_latest_task_feedback(
    user_id: str,
    *,
    rating: str,
    feedback_text: str = "",
) -> dict[str, Any]:
    """Attach a lightweight chat/button response to the user's latest task."""
    tasks = _db().get_recent_tasks(user_id, limit=1)
    if not tasks:
        return {"recorded": False, "reason": "no_recent_task"}

    task = tasks[0]
    task_id = str(task.get("task_id") or "")
    prompt = str(task.get("prompt_used") or task.get("brief") or "")
    update_learning(
        user_id,
        rating=rating,
        prompt=prompt,
        feedback_text=feedback_text,
        generation_id=task_id,
    )

    if rating == "approved":
        _db().update_task_score(
            task_id,
            score_brand_compliance=4.0,
            first_pass_accepted=True,
        )
        _db().complete_task(task_id)
    elif rating == "rejected":
        _db().increment_task_revisions(task_id)

    return {"recorded": True, "task_id": task_id, "rating": rating}


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
    Covers generic visual complaints + domain-specific feedback for:
    education, luxury/premium, F&B, healthcare, fashion, beauty,
    real estate, tech, kids/family, and fitness industries.
    """
    text = feedback_text.lower()
    mappings: list[tuple[list[str], str]] = [
        # ── Generic visual quality ────────────────────────────────────────────
        (["quá sáng", "sáng quá", "chói", "overexposed", "too bright"], "overexposed"),
        (["quá tối", "tối quá", "dark", "too dark", "u ám", "gloomy", "depressing"], "too dark"),
        (["mờ", "blur", "blurry", "không sắc nét", "out of focus"], "blurry"),
        (["cartoon", "hoạt hình", "toon", "animated", "illustration style"], "cartoon"),
        (["xấu", "thô", "low quality", "chất lượng thấp", "vỡ hạt", "pixelated"], "low quality"),
        (["sai màu", "màu sai", "wrong color", "lệch màu", "color cast"], "incorrect colors"),
        (["quá phức tạp", "rối", "cluttered", "messy", "busy background"], "cluttered"),
        (["thiếu chuyên nghiệp", "không chuyên", "amateur", "trông amateurish"], "amateur"),
        (["quá đơn giản", "nhạt", "plain", "boring", "vô hồn"], "too plain"),
        # ── Lighting & exposure ───────────────────────────────────────────────
        (["ánh sáng không đều", "uneven lighting", "harsh shadow", "bóng đổ xấu"], "harsh lighting"),
        (["thiếu chiều sâu", "flat lighting", "no depth", "2d feel"], "flat lighting"),
        # ── Education / Academic ──────────────────────────────────────────────
        (["too casual", "thiếu học thuật", "không nghiêm túc", "không trang trọng",
          "không phù hợp giáo dục", "childish for adult"], "too casual"),
        (["không phù hợp trẻ em", "không an toàn trẻ em", "inappropriate for kids",
          "not child-safe", "không phù hợp học sinh"], "inappropriate for children"),
        # ── Luxury / Premium ──────────────────────────────────────────────────
        (["không đủ sang", "trông rẻ", "cheap", "cheap-looking", "mass market",
          "bình dân quá", "không premium", "trông phổ thông", "low-end"], "low-end appearance"),
        (["không đúng luxury", "không đúng cao cấp", "không sang trọng",
          "thiếu sang trọng", "not luxurious"], "lacks luxury feel"),
        # ── F&B (Food & Beverage) ─────────────────────────────────────────────
        (["trông không ngon", "không hấp dẫn", "unappetizing", "not appetizing",
          "không kích thích vị giác", "nhạt nhẽo về thức ăn"], "unappetizing"),
        (["quá nhân tạo", "fake food", "plastic looking", "đồ ăn giả",
          "trông đồ ăn nhựa", "artificial food"], "artificial food"),
        (["màu thức ăn sai", "wrong food color", "thức ăn mất tươi",
          "food color off", "not fresh looking"], "wrong food color"),
        # ── Healthcare / Medical ──────────────────────────────────────────────
        (["thiếu tin cậy", "không đáng tin", "untrustworthy", "not trustworthy",
          "không chuyên nghiệp y tế", "not medical grade", "thiếu uy tín y tế"], "untrustworthy medical"),
        (["quá lạnh lẽo", "sterile feel", "không thân thiện bệnh nhân",
          "not patient-friendly", "too clinical"], "too clinical"),
        # ── Fashion / Apparel ─────────────────────────────────────────────────
        (["không đúng phong cách", "off-brand style", "không match style",
          "style không phù hợp", "wrong vibe"], "wrong style"),
        (["model pose xấu", "bad pose", "tư thế xấu", "awkward pose",
          "stiff pose", "tư thế cứng"], "bad pose"),
        # ── Beauty / Cosmetics ────────────────────────────────────────────────
        (["màu sản phẩm sai", "wrong product color", "sai màu son", "sai màu kem",
          "màu mỹ phẩm lệch"], "wrong product color"),
        (["da không đẹp", "bad skin retouch", "retouch quá", "over-retouched",
          "da nhựa", "plastic skin", "skin không tự nhiên"], "over-retouched skin"),
        # ── Real Estate / Architecture ────────────────────────────────────────
        (["ảnh nội thất tối", "dark interior", "thiếu ánh sáng phòng",
          "room too dark", "không thấy chi tiết nội thất"], "dark interior"),
        (["góc ảnh xấu", "bad angle", "perspective xấu", "distorted perspective",
          "wide angle distortion", "méo góc rộng"], "bad perspective"),
        # ── Tech / Gadget ─────────────────────────────────────────────────────
        (["sản phẩm không sắc nét", "product not sharp", "thiếu chi tiết sản phẩm",
          "missing product detail", "product blurry"], "product not sharp"),
        (["background không phù hợp tech", "background sai tech",
          "not tech aesthetic", "không hợp với tech"], "wrong tech aesthetic"),
        # ── Kids / Baby / Family ──────────────────────────────────────────────
        (["màu sắc quá tối với trẻ", "too dark for kids", "không vui tươi",
          "not cheerful enough", "không phù hợp trẻ", "màu tối với trẻ em"], "too dark for children"),
        (["không an toàn", "not safe", "unsafe content", "nội dung không an toàn",
          "không phù hợp gia đình", "not family-friendly"], "unsafe content"),
        # ── Fitness / Sport ───────────────────────────────────────────────────
        (["thiếu năng lượng", "không đủ energy", "low energy", "flat energy",
          "không hùng mạnh", "không bold"], "lacks energy"),
        (["không đủ dynamic", "static pose", "tư thế tĩnh", "không action",
          "boring fitness pose"], "static/boring pose"),
    ]
    found: list[str] = []
    for triggers, keyword in mappings:
        if any(t in text for t in triggers):
            found.append(keyword)
    return found
