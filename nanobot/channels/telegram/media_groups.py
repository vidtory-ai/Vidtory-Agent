from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MediaGroupPart:
    message_id: int
    sender_id: str
    chat_id: str
    content: str
    media: list[str]
    metadata: dict[str, Any]
    session_key: str | None
    current_media: list[str]
    reply_media: list[str]


@dataclass
class MediaGroupTurn:
    parts: dict[int, MediaGroupPart] = field(default_factory=dict)
    inflight_parts: int = 0
    revision: int = 0

    def add_part(self, part: MediaGroupPart) -> None:
        self.parts[part.message_id] = part
        self.inflight_parts = max(0, self.inflight_parts - 1)
        self.revision += 1

    def to_message_kwargs(self) -> dict[str, Any]:
        ordered = [self.parts[key] for key in sorted(self.parts)]
        first = ordered[0]
        metadata = dict(first.metadata)
        metadata["current_media"] = _dedupe(
            path for part in ordered for path in part.current_media
        )
        metadata["reply_media"] = _dedupe(
            path for part in ordered for path in part.reply_media
        )
        return {
            "sender_id": first.sender_id,
            "chat_id": first.chat_id,
            "content": "\n".join(
                part.content
                for part in ordered
                if part.content and part.content != "[empty message]"
            ) or "[empty message]",
            "media": _dedupe(path for part in ordered for path in part.media),
            "metadata": metadata,
            "session_key": first.session_key,
        }


class TelegramMediaGroupCollector:
    """Collect Telegram album parts until all downloads have settled."""

    def __init__(self) -> None:
        self.groups: dict[str, MediaGroupTurn] = {}

    def begin_part(self, key: str) -> None:
        turn = self.groups.setdefault(key, MediaGroupTurn())
        turn.inflight_parts += 1
        turn.revision += 1

    def abort_part(self, key: str) -> None:
        turn = self.groups.get(key)
        if turn is None:
            return
        turn.inflight_parts = max(0, turn.inflight_parts - 1)
        turn.revision += 1

    def finish_part(self, key: str, part: MediaGroupPart) -> None:
        self.groups.setdefault(key, MediaGroupTurn()).add_part(part)

    async def wait_and_pop(
        self,
        key: str,
        *,
        quiet_period: float,
    ) -> dict[str, Any] | None:
        while True:
            turn = self.groups.get(key)
            if turn is None:
                return None
            observed_revision = turn.revision
            await asyncio.sleep(quiet_period)
            turn = self.groups.get(key)
            if turn is None:
                return None
            if turn.inflight_parts == 0 and turn.revision == observed_revision:
                self.groups.pop(key, None)
                return turn.to_message_kwargs() if turn.parts else None

    def clear(self) -> None:
        self.groups.clear()


def _dedupe(values) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
