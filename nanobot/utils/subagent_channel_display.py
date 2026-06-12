"""Stub subagent channel display helpers.

The full subagent display module was removed as part of the Vidtory
refactoring. These stubs satisfy imports from websocket.py and
session/manager.py without breaking those modules.
"""
from __future__ import annotations

from typing import Any


def scrub_subagent_announce_body(content: str) -> str:
    """No-op: return content unchanged."""
    return content


def scrub_subagent_messages_for_channel(
    messages: list[dict[str, Any]],
    *args: Any,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """No-op: return messages unchanged."""
    return messages
