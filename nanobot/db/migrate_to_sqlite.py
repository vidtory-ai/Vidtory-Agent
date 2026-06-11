"""
Migration script: Import existing JSON files into SQLite database.

Run once (idempotent — safe to run multiple times):
    uv run python -m nanobot.db.migrate_to_sqlite

What it migrates:
  - ~/.vidtoryagent/telegram_keys.json      -> api_keys table
  - ~/.vidtoryagent/customers/*/profile.json -> customer_profiles table
  - ~/.vidtoryagent/customers/*/feedback.jsonl -> feedback table
  - ~/.vidtoryagent/customers/*/generation-history.jsonl -> generation_history table
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def migrate(data_dir: Path | None = None, verbose: bool = True, db=None) -> dict[str, int]:
    """Run full migration. Returns counts of migrated records per table.
    
    Args:
        data_dir: Override for data directory (useful in tests).
        verbose: Print progress to stdout.
        db: CustomerDatabase instance to use (default: get_db() singleton).
    """
    from nanobot.config.paths import get_data_dir
    from nanobot.db.customer_db import get_db

    base = data_dir or get_data_dir()
    db = db or get_db()
    counts = {
        "api_keys": 0,
        "profiles": 0,
        "feedback": 0,
        "generations": 0,
        "errors": 0,
    }

    def log(msg: str) -> None:
        if verbose:
            print(f"  {msg}")

    print("\n🔄 Vidtory-Agent: Migrating JSON → SQLite")
    print(f"   Source: {base}")

    # ------------------------------------------------------------------
    # 1. API Keys
    # ------------------------------------------------------------------
    print("\n📦 Migrating API keys...")
    keys_file = base / "telegram_keys.json"
    if keys_file.exists():
        try:
            keys = json.loads(keys_file.read_text(encoding="utf-8"))
            existing = db.get_all_api_keys()
            for uid, key in keys.items():
                if uid and key and uid not in existing:
                    db.set_api_key(uid, key)
                    counts["api_keys"] += 1
                    log(f"  key: {uid[:8]}...")
            log(f"Imported {counts['api_keys']} new API keys (skipped existing)")
        except Exception as e:
            print(f"  ⚠️  Error reading telegram_keys.json: {e}")
            counts["errors"] += 1
    else:
        log("telegram_keys.json not found — skipping")

    # ------------------------------------------------------------------
    # 2. Customer Profiles + Feedback + Generation History
    # ------------------------------------------------------------------
    customers_dir = base.parent / "customers"
    if not customers_dir.exists():
        customers_dir = base / "customers"

    if customers_dir.exists():
        user_dirs = [d for d in customers_dir.iterdir() if d.is_dir()]
        print(f"\n👥 Found {len(user_dirs)} customer directories...")

        for user_dir in user_dirs:
            uid = user_dir.name

            # Profile
            profile_file = user_dir / "profile.json"
            if profile_file.exists():
                try:
                    profile = json.loads(profile_file.read_text(encoding="utf-8"))
                    if isinstance(profile, dict):
                        if not db.profile_exists(uid):
                            db.save_profile(uid, profile)
                            counts["profiles"] += 1
                            biz = profile.get("business", {})
                            log(f"  profile: {uid} ({biz.get('name', 'unknown')})")
                        else:
                            log(f"  profile: {uid} already exists — skipping")
                except Exception as e:
                    print(f"  ⚠️  Error reading profile for {uid}: {e}")
                    counts["errors"] += 1

            # Feedback
            feedback_file = user_dir / "feedback.jsonl"
            if feedback_file.exists():
                try:
                    lines = feedback_file.read_text(encoding="utf-8").splitlines()
                    imported = 0
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            db.append_feedback(
                                uid,
                                generation_id=entry.get("generationId", ""),
                                content_type=entry.get("contentType", "image"),
                                original_prompt=entry.get("originalPrompt", ""),
                                enhanced_prompt=entry.get("enhancedPrompt", ""),
                                rating=entry.get("rating", ""),
                                comment=entry.get("comment", ""),
                                adjustments=entry.get("adjustments", ""),
                            )
                            imported += 1
                        except Exception:
                            counts["errors"] += 1
                    counts["feedback"] += imported
                    if imported:
                        log(f"  feedback: {uid} — {imported} records")
                except Exception as e:
                    print(f"  ⚠️  Error reading feedback for {uid}: {e}")
                    counts["errors"] += 1

            # Generation history
            history_file = user_dir / "generation-history.jsonl"
            if history_file.exists():
                try:
                    lines = history_file.read_text(encoding="utf-8").splitlines()
                    imported = 0
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            db.record_generation(
                                uid,
                                content_type=entry.get("contentType", "image"),
                                prompt=entry.get("originalPrompt", ""),
                                enhanced_prompt=entry.get("enhancedPrompt", ""),
                                model=entry.get("model", ""),
                                result_url=entry.get("resultUrl", ""),
                            )
                            imported += 1
                        except Exception:
                            counts["errors"] += 1
                    counts["generations"] += imported
                    if imported:
                        log(f"  history: {uid} — {imported} records")
                except Exception as e:
                    print(f"  ⚠️  Error reading history for {uid}: {e}")
                    counts["errors"] += 1
    else:
        log(f"Customers directory not found at {customers_dir}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n✅ Migration complete!")
    print(f"   API keys migrated  : {counts['api_keys']}")
    print(f"   Profiles migrated  : {counts['profiles']}")
    print(f"   Feedback records   : {counts['feedback']}")
    print(f"   Generation records : {counts['generations']}")
    if counts["errors"]:
        print(f"   ⚠️  Errors         : {counts['errors']}")

    stats = get_db().get_stats()
    print(f"\n📊 Database totals:")
    print(f"   Users         : {stats['total_users']}")
    print(f"   Keys          : {stats['users_with_api_key']}")
    print(f"   Generations   : {stats['total_generations']}")
    print(f"   Feedback rows : {stats['total_feedback']}")
    print(f"   DB file       : {stats['db_path']}\n")

    return counts


if __name__ == "__main__":
    counts = migrate()
    if counts["errors"] > 0:
        sys.exit(1)


def migrate_profile_json_for_user(uid: str, data_dir: Path | None = None, db=None) -> bool:
    """Migrate a single user's profile.json → SQLite if the JSON has richer data.

    This is called at message-processing time to auto-import legacy profile.json
    files for users who were onboarded before the SQLite migration.

    Rules:
    - If no profile exists in DB → import from JSON.
    - If profile exists but business.name is empty → overwrite with JSON data.
    - If profile exists and has a business.name → skip (DB is source of truth).

    Returns True if migration was applied.
    """
    from nanobot.config.paths import get_data_dir
    from nanobot.db.customer_db import get_db as _get_db

    base = data_dir or get_data_dir()
    db = db or _get_db()

    # Look for legacy file at ~/.vidtoryagent/customers/{uid}/profile.json
    # Check both possible parent directories and use the one that has the file.
    candidates = [
        base / "customers" / uid / "profile.json",    # ~/.vidtoryagent/customers/{uid}/
        base.parent / "customers" / uid / "profile.json",  # ~/.customers/{uid}/ (unusual)
    ]
    profile_file = next((p for p in candidates if p.exists()), None)
    if profile_file is None:
        return False

    try:
        json_profile = json.loads(profile_file.read_text(encoding="utf-8"))
        if not isinstance(json_profile, dict):
            return False

        json_biz_name = (json_profile.get("business") or {}).get("name", "").strip()
        if not json_biz_name:
            return False  # JSON file also has no data — nothing to import

        # Check existing DB profile
        existing = db.load_profile(uid)
        if existing:
            db_biz_name = (existing.get("business") or {}).get("name", "").strip()
            if db_biz_name:
                return False  # DB already has rich data — trust DB

            # DB profile is empty/minimal — overwrite with JSON data
            db.save_profile(uid, json_profile)
            import logging
            logging.getLogger(__name__).info(
                "Auto-migrated profile.json for user %s (%s) → overwrote empty DB profile",
                uid, json_biz_name,
            )
        else:
            # No DB profile at all — create from JSON
            db.save_profile(uid, json_profile)
            import logging
            logging.getLogger(__name__).info(
                "Auto-migrated profile.json for user %s (%s) → created DB profile",
                uid, json_biz_name,
            )
        return True

    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "Auto-migration of profile.json failed for user %s: %s", uid, exc
        )
        return False


# ---------------------------------------------------------------------------
# Brand Memory Migration
# ---------------------------------------------------------------------------

def migrate_profile_to_brand_memory(uid: str, db=None) -> bool:
    """Split existing profile_json data into brand_memory table rows.

    Called for each user to populate the layered brand memory from their
    legacy flat profile. Idempotent — existing entries are overwritten.

    Maps:
        profile.brand.colorPalette.{primary,secondary,accent} → core layer
        profile.brand.logoUrl                                  → core layer
        profile.brand.style                                    → style layer (aesthetic)
        profile.brand.moodKeywords                             → style layer (mood_reference)
        profile.brand.photographyStyle                         → style layer
        profile.brand.avoidList                                → style layer (avoid_*)
        profile.learningData.commonFeedback                    → preference layer
        profile.learningData.bestPerformingPrompts             → preference layer

    Returns True if any entries were migrated.
    """
    from nanobot.db.customer_db import get_db as _get_db

    db = db or _get_db()
    profile = db.load_profile(uid)
    if not profile:
        return False

    source = "migration:profile_json"
    migrated = 0

    brand = profile.get("brand") or {}

    # ── Core layer ─────────────────────────────────────────────────────
    palette = brand.get("colorPalette") or {}
    for color_key in ("primary", "secondary", "accent"):
        val = palette.get(color_key, "").strip()
        if val:
            db.set_memory(uid, layer="core", key=f"color_{color_key}",
                          value=val, source=source, force=True)
            migrated += 1

    logo = (brand.get("logoUrl") or "").strip()
    if logo:
        db.set_memory(uid, layer="core", key="logo",
                      value=logo, source=source, force=True)
        migrated += 1

    # ── Style layer ────────────────────────────────────────────────────
    style = (brand.get("style") or "").strip()
    if style:
        db.set_memory(uid, layer="style", key="aesthetic",
                      value=style, source=source, force=True)
        migrated += 1

    mood = brand.get("moodKeywords") or []
    if mood:
        db.set_memory(uid, layer="style", key="mood_reference",
                      value=", ".join(str(m) for m in mood),
                      source=source, force=True)
        migrated += 1

    photo_style = (brand.get("photographyStyle") or "").strip()
    if photo_style:
        db.set_memory(uid, layer="style", key="photography_style",
                      value=photo_style, source=source, force=True)
        migrated += 1

    avoid = brand.get("avoidList") or []
    for i, item in enumerate(avoid[:10]):
        if isinstance(item, str) and item.strip():
            db.set_memory(uid, layer="style", key=f"avoid_{i}",
                          value=item.strip(), source=source, force=True)
            migrated += 1

    # ── Preference layer ───────────────────────────────────────────────
    learning = profile.get("learningData") or {}

    for fb in (learning.get("commonFeedback") or [])[:10]:
        if isinstance(fb, str) and fb.strip():
            key = f"feedback_{fb.strip().lower()[:30].replace(' ', '_')}"
            db.set_memory(uid, layer="preference", key=key,
                          value=fb.strip()[:100], source=source, confidence=0.8)
            migrated += 1

    for p in (learning.get("bestPerformingPrompts") or [])[:10]:
        if isinstance(p, str) and p.strip():
            key = f"good_prompt_{hash(p[:50]) % 10000:04d}"
            db.set_memory(uid, layer="preference", key=key,
                          value=p[:150], source=source, confidence=0.7)
            migrated += 1

    return migrated > 0


def migrate_all_profiles_to_brand_memory(verbose: bool = True, db=None) -> dict[str, int]:
    """Migrate all existing customer profiles into brand_memory table.

    This should be run once after upgrading to the layered memory architecture.
    Safe to run multiple times (idempotent via UPSERT).

    Usage:
        python -c "from nanobot.db.migrate_to_sqlite import migrate_all_profiles_to_brand_memory; migrate_all_profiles_to_brand_memory()"
    """
    from nanobot.db.customer_db import get_db as _get_db

    db = db or _get_db()
    counts = {"migrated": 0, "skipped": 0, "errors": 0}

    # Get all user IDs from customer_profiles
    import sqlite3
    with db._conn() as conn:
        rows = conn.execute("SELECT user_id FROM customer_profiles").fetchall()

    user_ids = [row["user_id"] for row in rows]
    if verbose:
        print(f"\n🔄 Migrating {len(user_ids)} profiles to brand_memory...")

    for uid in user_ids:
        try:
            if migrate_profile_to_brand_memory(uid, db=db):
                counts["migrated"] += 1
                if verbose:
                    mem_count = db.count_memory(uid)
                    print(f"  ✅ {uid}: {mem_count} memory entries created")
            else:
                counts["skipped"] += 1
        except Exception as e:
            counts["errors"] += 1
            if verbose:
                print(f"  ⚠️  {uid}: {e}")

    if verbose:
        print(f"\n✅ Brand memory migration complete!")
        print(f"   Migrated : {counts['migrated']}")
        print(f"   Skipped  : {counts['skipped']}")
        print(f"   Errors   : {counts['errors']}")

    return counts
