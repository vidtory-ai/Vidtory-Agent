"""Strip internal subagent instructions from user-facing channel output."""

from __future__ import annotations

from typing import Any

_SUBAGENT_CHANNEL_RESULT_MAX_CHARS = 800


def scrub_subagent_announce_body(content: str) -> str:
    stripped = content.replace("\r\n", "\n").strip()
    lines = stripped.splitlines()
    header = lines[0].strip() if lines and lines[0].startswith("[Subagent") else ""

    lowered = stripped.lower()
    marker = "\nresult:\n"
    result_index = lowered.find(marker)
    if result_index == -1:
        marker = "\nresult:"
        result_index = lowered.find(marker)
    if result_index == -1:
        return header or stripped

    body = stripped[result_index + len(marker):].lstrip()
    summary_index = body.lower().find("summarize this naturally")
    if summary_index != -1:
        body = body[:summary_index].rstrip()
    body = body.strip()
    if len(body) > _SUBAGENT_CHANNEL_RESULT_MAX_CHARS:
        body = body[: _SUBAGENT_CHANNEL_RESULT_MAX_CHARS - 3].rstrip() + "..."
    if header and body:
        return f"{header}\n\n{body}"
    return header or body or stripped


def scrub_subagent_messages_for_channel(messages: list[dict[str, Any]]) -> None:
    for message in messages:
        if not isinstance(message, dict):
            continue
        if message.get("injected_event") != "subagent_result":
            continue
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            message["content"] = scrub_subagent_announce_body(content)
