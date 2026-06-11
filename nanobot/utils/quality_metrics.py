"""Quality metrics for Vidtory Resident Designer.

Tracks and evaluates agent performance across the lifecycle:
- FPAR (First-Pass Acceptance Rate)
- Revision convergence trend
- Stage gate evaluation
- Brand competence score

Public API
----------
- :func:`get_lifecycle_stage` — current lifecycle stage for a user
- :func:`set_lifecycle_stage` — update lifecycle stage
- :func:`check_stage_gate` — evaluate whether a user qualifies for stage advancement
- :func:`calculate_brand_competence` — 0-100 brand competence score
- :func:`get_quality_summary` — compact quality summary for runtime context
"""

from __future__ import annotations

from typing import Any

from loguru import logger


# ---------------------------------------------------------------------------
# Lifecycle stages
# ---------------------------------------------------------------------------

LIFECYCLE_STAGES = [
    "new_user",     # First contact — not yet started
    "testing",      # Stage 0: WOW demo (minimal input → portfolio)
    "onboarding",   # Stage 1: structured interview, brand profile
    "probation",    # Stage 2: feedback loop, learning preferences
    "official",     # Stage 3: low-touch, regression testing
]


def _db():
    from nanobot.db.customer_db import get_db
    return get_db()


def get_lifecycle_stage(user_id: str, *, db=None) -> str:
    """Return current lifecycle stage for a user.

    Maps from legacy onboarding_status if no explicit lifecycle stage is set.
    """
    from nanobot.utils.customer_profile import load_profile
    _database = db or _db()
    profile = _database.load_profile(user_id)
    if not profile:
        return "new_user"

    onboarding = profile.get("onboarding") or {}

    # Check for new lifecycle_stage field first
    stage = onboarding.get("lifecycle_stage")
    if stage and stage in LIFECYCLE_STAGES:
        return stage

    # Legacy mapping
    status = onboarding.get("status", "none")
    legacy_map = {
        "none": "new_user",
        "minimal": "testing",
        "in_progress": "onboarding",
        "completed": "probation",  # Conservative: completed onboarding → probation (not official)
    }
    return legacy_map.get(status, "new_user")


def set_lifecycle_stage(user_id: str, stage: str, *, db=None) -> bool:
    """Set lifecycle stage for a user.

    Persists in the profile's ``onboarding.lifecycle_stage`` field.
    """
    if stage not in LIFECYCLE_STAGES:
        logger.warning("set_lifecycle_stage: invalid stage '{}' for {}", stage, user_id)
        return False

    _database = db or _db()
    profile = _database.load_profile(user_id)
    if not profile:
        logger.warning("set_lifecycle_stage: no profile for {}", user_id)
        return False

    onboarding = profile.setdefault("onboarding", {})
    old_stage = onboarding.get("lifecycle_stage", "unknown")
    onboarding["lifecycle_stage"] = stage

    # Also update legacy status for backward compatibility
    stage_to_legacy = {
        "new_user": "none",
        "testing": "minimal",
        "onboarding": "in_progress",
        "probation": "completed",
        "official": "completed",
    }
    onboarding["status"] = stage_to_legacy.get(stage, onboarding.get("status", "none"))

    success = _database.save_profile(user_id, profile)
    if success:
        logger.info(
            "Lifecycle stage changed: {} → {} for user {}",
            old_stage, stage, user_id,
        )
    return success


# ---------------------------------------------------------------------------
# Stage gate evaluation
# ---------------------------------------------------------------------------

# Gate thresholds
_PROBATION_TO_OFFICIAL_FPAR = 70.0       # Minimum FPAR to graduate
_PROBATION_TO_OFFICIAL_REVISIONS = 1.5   # Max average revisions
_PROBATION_TO_OFFICIAL_COMPLIANCE = 85.0  # Min brand compliance %
_PROBATION_MIN_TASKS = 5                  # Minimum tasks before gate evaluation


def check_stage_gate(user_id: str, *, db=None) -> dict[str, Any]:
    """Evaluate whether a user qualifies for stage advancement.

    Returns:
        Dict with can_advance, current_stage, recommended_stage, and details.
    """
    _database = db or _db()
    current = get_lifecycle_stage(user_id, db=_database)
    result: dict[str, Any] = {
        "current_stage": current,
        "can_advance": False,
        "recommended_stage": current,
        "blockers": [],
    }

    if current == "new_user":
        result["can_advance"] = True
        result["recommended_stage"] = "testing"
        result["reason"] = "New user detected, starting WOW demo"
        return result

    if current == "testing":
        result["reason"] = "Client must choose a style or express hiring intent"
        return result

    if current == "onboarding":
        from nanobot.utils.customer_profile import get_profile_completeness
        profile = _database.load_profile(user_id)
        if profile:
            completeness = get_profile_completeness(profile)
            result["profile_completeness"] = completeness
            if completeness >= 80:
                result["can_advance"] = True
                result["recommended_stage"] = "probation"
                result["reason"] = f"Profile completeness {completeness}% >= 80%"
            else:
                result["blockers"].append(f"profile_completeness: {completeness}% < 80%")
                result["reason"] = f"Profile completeness {completeness}% < 80%"
        return result

    if current == "probation":
        fpar_data = _database.calculate_fpar(user_id, last_n=10)
        result["fpar"] = fpar_data

        sample = fpar_data.get("sample_size", 0)
        if sample < _PROBATION_MIN_TASKS:
            result["blockers"].append(f"min_tasks: {sample}/{_PROBATION_MIN_TASKS}")
            result["reason"] = f"Insufficient data: {sample}/{_PROBATION_MIN_TASKS} tasks"
            return result

        fpar = fpar_data.get("fpar", 0.0)
        avg_rev = fpar_data.get("avg_revisions", 99.0)
        bc_avg = fpar_data.get("brand_compliance_avg")

        checks = {
            "fpar_pass": fpar >= _PROBATION_TO_OFFICIAL_FPAR,
            "revisions_pass": avg_rev <= _PROBATION_TO_OFFICIAL_REVISIONS,
            # brand_compliance_avg is on 0-5 scale → normalize to 0-100%
            "compliance_pass": bc_avg is not None and (bc_avg * 20) >= _PROBATION_TO_OFFICIAL_COMPLIANCE,
            "trend_pass": fpar_data.get("trend") in ("improving", "stable"),
        }
        result["checks"] = checks

        if all(checks.values()):
            result["can_advance"] = True
            result["recommended_stage"] = "official"
            result["reason"] = (
                f"All gates passed: FPAR={fpar}%, revisions={avg_rev}, "
                f"compliance={bc_avg}%, trend={fpar_data.get('trend')}"
            )
        else:
            failed = [k for k, v in checks.items() if not v]
            result["blockers"] = failed
            result["reason"] = f"Gates not met: {', '.join(failed)}"

    return result


# ---------------------------------------------------------------------------
# Brand competence score
# ---------------------------------------------------------------------------

def calculate_brand_competence(user_id: str, *, db=None) -> int:
    """Calculate a 0-100 brand competence score.

    This measures how well the agent "knows" the brand, based on:
    - Memory layer completeness (40 pts)
    - FPAR and convergence (30 pts)
    - Preference learning depth (30 pts)
    """
    _database = db or _db()
    uid = user_id.split("|")[0].strip()
    score = 0

    # Memory completeness (40 pts)
    core_count = _database.count_memory(uid, "core")
    style_count = _database.count_memory(uid, "style")
    pref_count = _database.count_memory(uid, "preference")

    # Core: up to 20 pts (4+ entries = max)
    score += min(core_count * 5, 20)
    # Style: up to 10 pts (2+ entries = max)
    score += min(style_count * 5, 10)
    # Preferences: up to 10 pts (5+ entries = max)
    score += min(pref_count * 2, 10)

    # FPAR & convergence (30 pts)
    fpar_data = _database.calculate_fpar(uid, last_n=10)
    fpar = fpar_data.get("fpar", 0.0)
    trend = fpar_data.get("trend", "insufficient_data")

    # FPAR contribution: up to 20 pts
    score += min(int(fpar / 5), 20)
    # Trend bonus: up to 10 pts
    trend_bonus = {"improving": 10, "stable": 7, "degrading": 2, "insufficient_data": 0}
    score += trend_bonus.get(trend, 0)

    # Preference learning depth (30 pts)
    # Based on total generations and feedback ratio
    profile = _database.load_profile(user_id)
    if profile:
        learning = profile.get("learningData") or {}
        total_gen = learning.get("totalGenerations", 0)
        approved = learning.get("approvedCount", 0)
        common_fb = len(learning.get("commonFeedback") or [])
        best_prompts = len(learning.get("bestPerformingPrompts") or [])

        # Generation volume: up to 10 pts (20+ gens = max)
        score += min(total_gen // 2, 10)
        # Approval ratio: up to 10 pts
        if total_gen > 0:
            ratio = approved / total_gen
            score += min(int(ratio * 10), 10)
        # Learned patterns: up to 10 pts
        score += min((common_fb + best_prompts) * 2, 10)

    return min(score, 100)


# ---------------------------------------------------------------------------
# Quality summary for runtime context injection
# ---------------------------------------------------------------------------

def get_quality_summary(user_id: str, *, db=None) -> list[str]:
    """Return compact quality metrics for injection into runtime context.

    Used by ContextBuilder to give the agent awareness of its own performance.
    """
    _database = db or _db()
    lines: list[str] = []

    stage = get_lifecycle_stage(user_id, db=_database)
    stage_labels = {
        "new_user": "🆕 New User",
        "testing": "🧪 Stage 0: Testing/WOW",
        "onboarding": "📋 Stage 1: Onboarding",
        "probation": "🔄 Stage 2: Probation",
        "official": "✅ Stage 3: Official",
    }
    lines.append(f"Lifecycle: {stage_labels.get(stage, stage)}")

    competence = calculate_brand_competence(user_id, db=_database)
    lines.append(f"Brand Competence: {competence}/100")

    try:
        fpar_data = _database.calculate_fpar(user_id, last_n=10)
        if fpar_data.get("sample_size", 0) > 0:
            lines.append(
                f"FPAR: {fpar_data['fpar']}% | "
                f"Avg Revisions: {fpar_data['avg_revisions']} | "
                f"Trend: {fpar_data['trend']}"
            )
    except Exception:
        pass

    return lines
