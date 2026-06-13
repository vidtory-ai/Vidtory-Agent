"""CLI Apps helpers stub.

The full CLI Apps subsystem was removed from Vidtory. These stubs satisfy
imports from agent/loop.py without any behavioral impact.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping


def session_extra(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """Preserve sanitized attachment metadata for transcript compatibility."""
    cli_apps = metadata.get("cli_apps") if isinstance(metadata, Mapping) else None
    return {"cli_apps": cli_apps} if isinstance(cli_apps, list) and cli_apps else {}


def runtime_lines(message: Any, workspace: Path, *, skip: bool = False) -> list[str]:
    """No-op: no CLI app annotations."""
    return []
