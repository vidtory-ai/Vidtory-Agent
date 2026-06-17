"""CLI Apps WebUI API stub.

The full CLI Apps subsystem was removed from Vidtory. These stubs satisfy
imports from websocket.py.
"""
from __future__ import annotations

import re
from typing import Any

QueryParams = dict[str, list[str]]

_CLI_APP_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$", re.IGNORECASE)
_CLI_APP_ATTACHMENT_KEYS = (
    "name",
    "display_name",
    "category",
    "entry_point",
    "logo_url",
    "brand_color",
)


class CliAppError(Exception):
    def __init__(self, msg: str = "", status: int = 400):
        self.status = status
        super().__init__(msg)


def _clip_ws_string(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:limit] if value else None


def normalize_cli_app_mentions(raw: Any) -> list[dict[str, str]]:
    """Sanitize legacy structured mentions before they reach session metadata."""
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw[:8]:
        if not isinstance(item, dict):
            continue
        name = _clip_ws_string(item.get("name"), 64)
        if not name or _CLI_APP_NAME_RE.fullmatch(name) is None:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        row = {"name": key}
        for field in _CLI_APP_ATTACHMENT_KEYS[1:]:
            limit = 512 if field == "logo_url" else 160
            value = _clip_ws_string(item.get(field), limit)
            if value:
                row[field] = value
        normalized.append(row)
    return normalized


def cli_apps_payload() -> dict[str, Any]:
    return {"apps": [], "installed": []}


def cli_apps_action(action: str, query: QueryParams) -> dict[str, Any]:
    raise CliAppError("CLI Apps not available", status=404)
