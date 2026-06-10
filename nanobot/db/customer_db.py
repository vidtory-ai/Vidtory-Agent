"""
SQLite-backed customer database for Vidtory-Agent.

Features:
- WAL journal mode: concurrent reads don't block writes
- Thread-safe: single connection per thread via threading.local
- Schema auto-migration: schema version tracked, upgrades applied automatically
- Atomic writes: all mutations in transactions
- Zero config: DB file created automatically in ~/.vidtoryagent/
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

from loguru import logger

# ---------------------------------------------------------------------------
# Schema version — increment when adding tables/columns
# ---------------------------------------------------------------------------
_SCHEMA_VERSION = 3

_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;
PRAGMA cache_size=-8000;

CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER NOT NULL,
    applied_at  TEXT    NOT NULL
);

-- API keys: one row per Telegram user
CREATE TABLE IF NOT EXISTS api_keys (
    user_id     TEXT PRIMARY KEY,
    api_key     TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Customer profiles: full JSON blob + indexed hot fields
CREATE TABLE IF NOT EXISTS customer_profiles (
    user_id         TEXT PRIMARY KEY,
    username        TEXT NOT NULL DEFAULT '',
    business_name   TEXT NOT NULL DEFAULT '',
    industry        TEXT NOT NULL DEFAULT '',
    brand_style     TEXT NOT NULL DEFAULT '',
    onboarding_status TEXT NOT NULL DEFAULT 'none',
    logo_url        TEXT NOT NULL DEFAULT '',
    profile_json    TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Feedback log: append-only audit trail
CREATE TABLE IF NOT EXISTS feedback (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT    NOT NULL,
    generation_id   TEXT    NOT NULL DEFAULT '',
    content_type    TEXT    NOT NULL DEFAULT 'image',
    original_prompt TEXT    NOT NULL DEFAULT '',
    enhanced_prompt TEXT    NOT NULL DEFAULT '',
    rating          TEXT    NOT NULL,
    comment         TEXT    NOT NULL DEFAULT '',
    adjustments     TEXT    NOT NULL DEFAULT '',
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_feedback_user ON feedback(user_id);
CREATE INDEX IF NOT EXISTS idx_feedback_rating ON feedback(user_id, rating);

-- Generation history: per-user content log
CREATE TABLE IF NOT EXISTS generation_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT    NOT NULL,
    generation_id   TEXT    NOT NULL UNIQUE,
    content_type    TEXT    NOT NULL DEFAULT 'image',
    original_prompt TEXT    NOT NULL DEFAULT '',
    enhanced_prompt TEXT    NOT NULL DEFAULT '',
    model           TEXT    NOT NULL DEFAULT '',
    result_url      TEXT    NOT NULL DEFAULT '',
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_gen_history_user ON generation_history(user_id);
"""

_V2_MIGRATION = """
-- V2: Add merchant_id column to customer_profiles
ALTER TABLE customer_profiles ADD COLUMN merchant_id TEXT NOT NULL DEFAULT '';
"""

_V3_MIGRATION = """
-- V3: Add logo_url column to customer_profiles
ALTER TABLE customer_profiles ADD COLUMN logo_url TEXT NOT NULL DEFAULT '';
"""


class CustomerDatabase:
    """
    Thread-safe SQLite database for all customer-related data.

    One instance is shared per process. Connections are per-thread via
    threading.local() so concurrent async tasks running in the same
    thread executor each get their own connection.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._local = threading.local()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # Initialize schema on first connection
        with self._conn() as conn:
            self._apply_schema(conn)

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        """Return the thread-local connection, creating it if needed."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                isolation_level=None,  # autocommit — we manage transactions manually
                timeout=10.0,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA cache_size=-8000")
            self._local.conn = conn
        return conn

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        """Yield the thread-local connection (no transaction)."""
        yield self._get_connection()

    @contextmanager
    def _tx(self) -> Generator[sqlite3.Connection, None, None]:
        """Yield a connection inside an explicit transaction."""
        conn = self._get_connection()
        conn.execute("BEGIN")
        try:
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def close(self) -> None:
        """Close the thread-local connection."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------

    def _apply_schema(self, conn: sqlite3.Connection) -> None:
        """Create tables and apply pending migrations."""
        # Execute DDL statements one by one
        for stmt in _DDL.split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(stmt)

        # Check current schema version
        row = conn.execute(
            "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
        ).fetchone()
        current_version = row["version"] if row else 0

        if current_version < 2:
            try:
                conn.execute(_V2_MIGRATION.strip())
                logger.info("Applied DB migration v2: added merchant_id column")
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    logger.warning("V2 migration skipped: {}", e)

        if current_version < 3:
            try:
                conn.execute(_V3_MIGRATION.strip())
                logger.info("Applied DB migration v3: added logo_url column")
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    logger.warning("V3 migration skipped: {}", e)

        if current_version < _SCHEMA_VERSION:
            conn.execute(
                "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                (_SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()),
            )
            logger.info("DB schema initialized/upgraded to version {}", _SCHEMA_VERSION)

    # ------------------------------------------------------------------
    # API Keys
    # ------------------------------------------------------------------

    def get_api_key(self, user_id: str) -> str | None:
        """Return the stored API key for *user_id*, or None."""
        uid = user_id.split("|")[0].strip()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT api_key FROM api_keys WHERE user_id = ?", (uid,)
            ).fetchone()
        return row["api_key"] if row else None

    def set_api_key(self, user_id: str, api_key: str) -> None:
        """Upsert an API key for *user_id*."""
        uid = user_id.split("|")[0].strip()
        now = datetime.now(timezone.utc).isoformat()
        with self._tx() as conn:
            conn.execute(
                """
                INSERT INTO api_keys (user_id, api_key, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    api_key = excluded.api_key,
                    updated_at = excluded.updated_at
                """,
                (uid, api_key, now, now),
            )
        logger.debug("API key saved for user {}", uid)

    def remove_api_key(self, user_id: str) -> None:
        """Delete the API key for *user_id*."""
        uid = user_id.split("|")[0].strip()
        with self._tx() as conn:
            conn.execute("DELETE FROM api_keys WHERE user_id = ?", (uid,))
        logger.debug("API key removed for user {}", uid)

    # Alias for backward compatibility with tests
    def remove_key(self, user_id: str) -> None:
        """Alias for remove_api_key."""
        return self.remove_api_key(user_id)

    def get_all_api_keys(self) -> dict[str, str]:
        """Return all user_id → api_key mappings (for backup/migration)."""
        with self._conn() as conn:
            rows = conn.execute("SELECT user_id, api_key FROM api_keys").fetchall()
        return {row["user_id"]: row["api_key"] for row in rows}

    # ------------------------------------------------------------------
    # Customer Profiles
    # ------------------------------------------------------------------

    def load_profile(self, user_id: str) -> dict[str, Any] | None:
        """Load and return a customer profile dict, or None if not found."""
        uid = user_id.split("|")[0].strip()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT profile_json FROM customer_profiles WHERE user_id = ?", (uid,)
            ).fetchone()
        if not row:
            return None
        try:
            data = json.loads(row["profile_json"])
            # Remove API key from profile data (security)
            data.pop("apiKey", None)
            return data
        except Exception as exc:
            logger.warning("Failed to parse profile for {}: {}", uid, exc)
            return None

    def save_profile(self, user_id: str, profile: dict[str, Any]) -> bool:
        """Upsert a customer profile. Returns True on success."""
        uid = user_id.split("|")[0].strip()
        # Remove sensitive data before storing
        clean = {k: v for k, v in profile.items() if k != "apiKey"}
        now = datetime.now(timezone.utc).isoformat()

        # Extract indexed fields for fast querying
        username = str(profile.get("telegramUsername") or "")
        business = profile.get("business") or {}
        business_name = str(business.get("name") or "")
        industry = str(business.get("industry") or "")
        brand = profile.get("brand") or {}
        brand_style = str(brand.get("style") or "")
        logo_url = str(brand.get("logoUrl") or "")
        onboarding = profile.get("onboarding") or {}
        onboarding_status = str(onboarding.get("status") or "none")
        merchant_id = str(profile.get("merchantId") or "")

        try:
            profile_json = json.dumps(clean, ensure_ascii=False)
        except Exception as exc:
            logger.error("Failed to serialize profile for {}: {}", uid, exc)
            return False

        try:
            with self._tx() as conn:
                conn.execute(
                    """
                    INSERT INTO customer_profiles
                        (user_id, username, business_name, industry, brand_style,
                         logo_url, onboarding_status, merchant_id, profile_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        username         = excluded.username,
                        business_name    = excluded.business_name,
                        industry         = excluded.industry,
                        brand_style      = excluded.brand_style,
                        logo_url         = excluded.logo_url,
                        onboarding_status = excluded.onboarding_status,
                        merchant_id      = excluded.merchant_id,
                        profile_json     = excluded.profile_json,
                        updated_at       = excluded.updated_at
                    """,
                    (uid, username, business_name, industry, brand_style,
                     logo_url, onboarding_status, merchant_id, profile_json, now, now),
                )
            logger.debug("Profile saved for user {}", uid)
            return True
        except Exception as exc:
            logger.error("Failed to save profile for {}: {}", uid, exc)
            return False

    def profile_exists(self, user_id: str) -> bool:
        """Return True if a profile exists for *user_id*."""
        uid = user_id.split("|")[0].strip()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM customer_profiles WHERE user_id = ?", (uid,)
            ).fetchone()
        return row is not None

    def get_logo_url(self, user_id: str) -> str:
        """Return the logo URL for *user_id*, or empty string."""
        uid = user_id.split("|")[0].strip()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT logo_url FROM customer_profiles WHERE user_id = ?", (uid,)
            ).fetchone()
        return row["logo_url"] if row else ""

    def set_logo_url(self, user_id: str, url: str) -> bool:
        """Update the logo URL for *user_id*. Also updates brand.logoUrl in profile_json."""
        uid = user_id.split("|")[0].strip()
        now = datetime.now(timezone.utc).isoformat()
        try:
            # First update the indexed column
            with self._tx() as conn:
                conn.execute(
                    "UPDATE customer_profiles SET logo_url = ?, updated_at = ? WHERE user_id = ?",
                    (url, now, uid),
                )
            # Then update the JSON blob
            profile = self.load_profile(uid)
            if profile:
                brand = profile.setdefault("brand", {})
                brand["logoUrl"] = url
                self.save_profile(uid, profile)
            logger.debug("Logo URL updated for user {}", uid)
            return True
        except Exception as exc:
            logger.error("Failed to set logo URL for {}: {}", uid, exc)
            return False

    def delete_profile(self, user_id: str) -> None:
        """Delete profile and all related data for *user_id*."""
        uid = user_id.split("|")[0].strip()
        with self._tx() as conn:
            conn.execute("DELETE FROM customer_profiles WHERE user_id = ?", (uid,))
            conn.execute("DELETE FROM api_keys WHERE user_id = ?", (uid,))
            conn.execute("DELETE FROM feedback WHERE user_id = ?", (uid,))
            conn.execute("DELETE FROM generation_history WHERE user_id = ?", (uid,))
        logger.info("All data deleted for user {}", uid)

    def list_users(self) -> list[dict[str, Any]]:
        """Return summary list of all users (for admin purposes)."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT user_id, username, business_name, industry,
                       logo_url, onboarding_status, updated_at
                FROM customer_profiles
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Feedback (append-only)
    # ------------------------------------------------------------------

    def append_feedback(
        self,
        user_id: str,
        *,
        generation_id: str = "",
        content_type: str = "image",
        original_prompt: str = "",
        enhanced_prompt: str = "",
        rating: str,
        comment: str = "",
        adjustments: str = "",
    ) -> bool:
        """Append a feedback record. Returns True on success."""
        uid = user_id.split("|")[0].strip()
        now = datetime.now(timezone.utc).isoformat()
        gen_id = generation_id or f"gen-{int(time.time())}"
        try:
            with self._tx() as conn:
                conn.execute(
                    """
                    INSERT INTO feedback
                        (user_id, generation_id, content_type, original_prompt,
                         enhanced_prompt, rating, comment, adjustments, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (uid, gen_id, content_type, original_prompt,
                     enhanced_prompt, rating, comment, adjustments, now),
                )
            return True
        except Exception as exc:
            logger.error("Failed to append feedback for {}: {}", uid, exc)
            return False

    def count_feedback_occurrences(self, user_id: str, feedback_text: str) -> int:
        """Count how many times similar feedback has been recorded."""
        uid = user_id.split("|")[0].strip()
        needle = feedback_text.strip().lower()[:60]
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) as cnt FROM feedback
                WHERE user_id = ?
                  AND LOWER(SUBSTR(comment, 1, 60)) = ?
                """,
                (uid, needle),
            ).fetchone()
        return max(row["cnt"] if row else 0, 1)

    def get_feedback_list(self, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Return recent feedback records for *user_id*."""
        uid = user_id.split("|")[0].strip()
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM feedback WHERE user_id = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (uid, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Generation History
    # ------------------------------------------------------------------

    def record_generation(
        self,
        user_id: str,
        *,
        content_type: str = "image",
        prompt: str = "",
        enhanced_prompt: str = "",
        model: str = "",
        result_url: str = "",
    ) -> str:
        """Log a generation event. Returns the generated generation_id."""
        uid = user_id.split("|")[0].strip()
        # Use uuid4 to guarantee uniqueness even in rapid-fire test scenarios
        gen_id = f"gen-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._tx() as conn:
                conn.execute(
                    """
                    INSERT INTO generation_history
                        (user_id, generation_id, content_type, original_prompt,
                         enhanced_prompt, model, result_url, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (uid, gen_id, content_type, prompt,
                     enhanced_prompt, model, result_url, now),
                )
        except Exception as exc:
            logger.warning("Failed to log generation for {}: {}", uid, exc)
        return gen_id

    def get_generation_count(self, user_id: str) -> int:
        """Return total generation count for *user_id*."""
        uid = user_id.split("|")[0].strip()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM generation_history WHERE user_id = ?",
                (uid,),
            ).fetchone()
        return row["cnt"] if row else 0

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Return basic stats for health/admin purposes."""
        with self._conn() as conn:
            users = conn.execute(
                "SELECT COUNT(*) as cnt FROM customer_profiles"
            ).fetchone()["cnt"]
            keys = conn.execute(
                "SELECT COUNT(*) as cnt FROM api_keys"
            ).fetchone()["cnt"]
            gens = conn.execute(
                "SELECT COUNT(*) as cnt FROM generation_history"
            ).fetchone()["cnt"]
            fb = conn.execute(
                "SELECT COUNT(*) as cnt FROM feedback"
            ).fetchone()["cnt"]
        return {
            "total_users": users,
            "users_with_api_key": keys,
            "total_generations": gens,
            "total_feedback": fb,
            "db_path": str(self.db_path),
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_db_instance: CustomerDatabase | None = None
_db_lock = threading.Lock()


def get_db() -> CustomerDatabase:
    """Return the process-wide singleton CustomerDatabase instance."""
    global _db_instance
    if _db_instance is None:
        with _db_lock:
            if _db_instance is None:
                from nanobot.config.paths import get_data_dir
                db_path = get_data_dir() / "customers.db"
                _db_instance = CustomerDatabase(db_path)
                logger.info("CustomerDatabase initialized at {}", db_path)
    return _db_instance
