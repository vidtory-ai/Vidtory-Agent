"""Stub file-edit event helpers.

The full WebUI file-edit streaming module was removed as part of the
Vidtory refactoring (Telegram-only).  These stubs satisfy imports from
runner.py and other modules without introducing dead code.
"""
from __future__ import annotations

from typing import Any, Callable, Awaitable


def build_file_edit_start_event(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {}


def build_file_edit_end_event(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {}


def build_file_edit_error_event(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {}


def prepare_file_edit_tracker(*args: Any, **kwargs: Any) -> None:
    return None


def prepare_file_edit_trackers(*args: Any, **kwargs: Any) -> list:
    return []


class StreamingFileEditTracker:
    """No-op stub for live file edit tracking."""

    def __init__(self, **kwargs: Any) -> None:
        pass

    async def update(self, delta: dict[str, Any]) -> None:
        pass

    async def flush(self) -> None:
        pass

    def apply_final_call_ids(self, tool_calls: list) -> None:
        pass

    async def error_unmatched(self, tool_calls: list, msg: str) -> None:
        pass
