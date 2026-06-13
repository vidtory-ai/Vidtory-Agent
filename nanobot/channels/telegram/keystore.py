class TelegramKeyStore:
    """Secure SQLite-backed storage mapping sender_ids to their configured API keys.

    Falls back to importing the legacy JSON file on first use if the DB is empty,
    providing automatic migration without any manual intervention.
    """

    def __init__(self) -> None:
        self._migrated = False

    def _db(self):
        from nanobot.db.customer_db import get_db
        return get_db()

    def _ensure_migrated(self) -> None:
        """One-time import of legacy telegram_keys.json into SQLite (if needed)."""
        if self._migrated:
            return
        self._migrated = True
        try:
            from nanobot.config.paths import get_data_dir
            legacy_path = get_data_dir() / "telegram_keys.json"
            if not legacy_path.exists():
                return
            # Only migrate if DB is empty
            if self._db().get_all_api_keys():
                return
            import json
            with open(legacy_path, encoding="utf-8") as f:
                keys: dict = json.load(f)
            count = 0
            for uid, key in keys.items():
                if uid and key:
                    self._db().set_api_key(uid, key)
                    count += 1
            if count:
                import logging
                logging.getLogger(__name__).info(
                    "Migrated %d API keys from telegram_keys.json to SQLite", count
                )
        except Exception:
            pass  # Non-critical — never block startup

    def get_key(self, sender_id: str) -> str | None:
        self._ensure_migrated()
        return self._db().get_api_key(sender_id)

    def set_key(self, sender_id: str, key: str) -> None:
        self._ensure_migrated()
        self._db().set_api_key(sender_id, key)

    def remove_key(self, sender_id: str) -> None:
        self._ensure_migrated()
        self._db().remove_api_key(sender_id)
