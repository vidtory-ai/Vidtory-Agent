"""File-edit progress events for the filesystem tools retained after cleanup."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

TRACKED_FILE_EDIT_TOOLS = frozenset({"write_file", "edit_file"})
_MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024


@dataclass(slots=True)
class FileSnapshot:
    path: Path
    exists: bool
    text: str | None
    binary: bool = False
    unreadable: bool = False
    oversized: bool = False

    @property
    def countable(self) -> bool:
        return (
            self.text is not None
            and not self.binary
            and not self.unreadable
            and not self.oversized
        )


@dataclass(slots=True)
class FileEditTracker:
    call_id: str
    tool: str
    path: Path
    display_path: str
    before: FileSnapshot


def _resolve_path(tool: Any, workspace: Path | None, raw_path: str) -> Path | None:
    resolver = getattr(tool, "_resolve", None)
    if callable(resolver):
        try:
            resolved = resolver(raw_path)
            return resolved if isinstance(resolved, Path) else Path(resolved)
        except Exception:
            return None
    if workspace is None:
        return Path(raw_path).expanduser().resolve()
    return (workspace / raw_path).expanduser().resolve()


def _display_path(path: Path, workspace: Path | None) -> str:
    if workspace is not None:
        try:
            return path.resolve().relative_to(workspace.resolve()).as_posix()
        except (OSError, ValueError):
            pass
    return path.as_posix()


def _snapshot(path: Path) -> FileSnapshot:
    try:
        if not path.exists() or not path.is_file():
            return FileSnapshot(path=path, exists=False, text="")
        if path.stat().st_size > _MAX_SNAPSHOT_BYTES:
            return FileSnapshot(path=path, exists=True, text=None, oversized=True)
        raw = path.read_bytes()
    except OSError:
        return FileSnapshot(path=path, exists=path.exists(), text=None, unreadable=True)
    if b"\0" in raw:
        return FileSnapshot(path=path, exists=True, text=None, binary=True)
    try:
        text = raw.decode("utf-8").replace("\r\n", "\n")
    except UnicodeDecodeError:
        return FileSnapshot(path=path, exists=True, text=None, binary=True)
    return FileSnapshot(path=path, exists=True, text=text)


def _line_count(text: str) -> int:
    return len(text.splitlines()) if text else 0


def _diff_stats(before: str | None, after: str | None) -> tuple[int, int]:
    if before is None or after is None:
        return 0, 0
    if before == "":
        return _line_count(after), 0
    added = deleted = 0
    matcher = difflib.SequenceMatcher(
        a=before.replace("\r\n", "\n").splitlines(),
        b=after.replace("\r\n", "\n").splitlines(),
        autojunk=False,
    )
    for tag, start_a, end_a, start_b, end_b in matcher.get_opcodes():
        if tag in {"replace", "delete"}:
            deleted += end_a - start_a
        if tag in {"replace", "insert"}:
            added += end_b - start_b
    return added, deleted


def _predicted_text(
    tool_name: str,
    params: dict[str, Any],
    before: FileSnapshot,
) -> str | None:
    if not before.countable:
        return None
    current = before.text or ""
    if tool_name == "write_file":
        content = params.get("content")
        return content if isinstance(content, str) else ""
    old_text = params.get("old_text")
    new_text = params.get("new_text")
    if not isinstance(old_text, str) or not isinstance(new_text, str):
        return None
    if old_text == "":
        return new_text if not before.exists else current
    if old_text not in current:
        return None
    if params.get("replace_all"):
        return current.replace(old_text, new_text)
    return current.replace(old_text, new_text, 1)


def prepare_file_edit_tracker(
    *,
    call_id: str,
    tool_name: str,
    tool: Any,
    workspace: Path | None,
    params: dict[str, Any] | None,
) -> FileEditTracker | None:
    trackers = prepare_file_edit_trackers(
        call_id=call_id,
        tool_name=tool_name,
        tool=tool,
        workspace=workspace,
        params=params,
    )
    return trackers[0] if trackers else None


def prepare_file_edit_trackers(
    *,
    call_id: str,
    tool_name: str,
    tool: Any,
    workspace: Path | None,
    params: dict[str, Any] | None,
) -> list[FileEditTracker]:
    if tool_name not in TRACKED_FILE_EDIT_TOOLS or not isinstance(params, dict):
        return []
    raw_path = params.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return []
    path = _resolve_path(tool, workspace, raw_path)
    if path is None:
        return []
    return [FileEditTracker(
        call_id=str(call_id or ""),
        tool=tool_name,
        path=path,
        display_path=_display_path(path, workspace),
        before=_snapshot(path),
    )]


def _event(
    tracker: FileEditTracker,
    *,
    phase: str,
    status: str,
    added: int,
    deleted: int,
    approximate: bool,
) -> dict[str, Any]:
    return {
        "version": 1,
        "call_id": tracker.call_id,
        "tool": tracker.tool,
        "path": tracker.display_path,
        "absolute_path": tracker.path.resolve().as_posix(),
        "phase": phase,
        "added": max(0, int(added)),
        "deleted": max(0, int(deleted)),
        "approximate": approximate,
        "status": status,
    }


def build_file_edit_start_event(
    tracker: FileEditTracker,
    params: dict[str, Any] | None,
) -> dict[str, Any]:
    predicted = _predicted_text(tracker.tool, params or {}, tracker.before)
    added, deleted = _diff_stats(tracker.before.text, predicted)
    return _event(
        tracker,
        phase="start",
        status="editing",
        added=added,
        deleted=deleted,
        approximate=True,
    )


def build_file_edit_end_event(
    tracker: FileEditTracker,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    after = _snapshot(tracker.path)
    if tracker.before.countable and after.countable:
        added, deleted = _diff_stats(tracker.before.text, after.text)
    else:
        predicted = _predicted_text(tracker.tool, params or {}, tracker.before)
        added, deleted = _diff_stats(tracker.before.text, predicted)
    return _event(
        tracker,
        phase="end",
        status="done",
        added=added,
        deleted=deleted,
        approximate=False,
    )


def build_file_edit_error_event(
    tracker: FileEditTracker,
    error: str | None = None,
) -> dict[str, Any]:
    payload = _event(
        tracker,
        phase="error",
        status="error",
        added=0,
        deleted=0,
        approximate=False,
    )
    if error:
        payload["error"] = error.strip()[:240]
    return payload


def _extract_string(source: str, key: str, *, require_closed: bool) -> str | None:
    match = re.search(rf'"{re.escape(key)}"\s*:\s*"', source)
    if match is None:
        return None
    output: list[str] = []
    index = match.end()
    escaped = False
    while index < len(source):
        char = source[index]
        if escaped:
            escaped = False
            output.append({"n": "\n", "r": "\r", "t": "\t"}.get(char, char))
        elif char == "\\":
            escaped = True
        elif char == '"':
            return "".join(output)
        else:
            output.append(char)
        index += 1
    return None if require_closed else "".join(output)


@dataclass(slots=True)
class _StreamState:
    key: str
    call_id: str = ""
    name: str = ""
    arguments: str = ""
    tracker: FileEditTracker | None = None
    path: str | None = None
    last_counts: tuple[int, int] = (-1, -1)

    def matches(self, tool_call: Any) -> bool:
        if getattr(tool_call, "id", None) == self.call_id and self.call_id:
            return True
        if getattr(tool_call, "name", None) != self.name:
            return False
        arguments = getattr(tool_call, "arguments", None)
        return isinstance(arguments, dict) and arguments.get("path") == self.path


class StreamingFileEditTracker:
    """Emit approximate progress while write/edit JSON arguments stream."""

    def __init__(
        self,
        *,
        workspace: Path | None,
        tools: Any,
        emit: Callable[[list[dict[str, Any]]], Awaitable[None]],
    ) -> None:
        self._workspace = workspace
        self._tools = tools
        self._emit = emit
        self._states: dict[str, _StreamState] = {}

    async def update(self, delta: dict[str, Any]) -> None:
        index = delta.get("index")
        key = f"idx:{index}" if index is not None else f"id:{delta.get('call_id', '')}"
        if key in {"idx:None", "id:"}:
            return
        state = self._states.setdefault(key, _StreamState(key=key))
        if isinstance(delta.get("call_id"), str) and delta["call_id"]:
            state.call_id = delta["call_id"]
        if isinstance(delta.get("name"), str) and delta["name"]:
            state.name = delta["name"]
        if isinstance(delta.get("arguments"), str):
            state.arguments = delta["arguments"]
        if isinstance(delta.get("arguments_delta"), str):
            state.arguments += delta["arguments_delta"]
        if state.name not in TRACKED_FILE_EDIT_TOOLS:
            return

        state.path = state.path or _extract_string(
            state.arguments, "path", require_closed=True
        )
        if state.path is None:
            return
        if state.tracker is None:
            tool = self._tools.get(state.name) if hasattr(self._tools, "get") else None
            state.tracker = prepare_file_edit_tracker(
                call_id=state.call_id or state.key,
                tool_name=state.name,
                tool=tool,
                workspace=self._workspace,
                params={"path": state.path},
            )
        if state.tracker is None:
            return

        if state.name == "write_file":
            content = _extract_string(state.arguments, "content", require_closed=False) or ""
            counts = (_line_count(content), 0)
        else:
            old_text = _extract_string(state.arguments, "old_text", require_closed=False) or ""
            new_text = _extract_string(state.arguments, "new_text", require_closed=False) or ""
            counts = (_line_count(new_text), _line_count(old_text))
        if counts == state.last_counts:
            return
        state.last_counts = counts
        await self._emit([_event(
            state.tracker,
            phase="start",
            status="editing",
            added=counts[0],
            deleted=counts[1],
            approximate=True,
        )])

    async def flush(self) -> None:
        return None

    def apply_final_call_ids(self, tool_calls: list[Any]) -> None:
        for tool_call in tool_calls:
            for state in self._states.values():
                if state.matches(tool_call) and state.call_id:
                    tool_call.id = state.call_id
                    break

    async def error_unmatched(self, tool_calls: list[Any], message: str) -> None:
        events = [
            build_file_edit_error_event(state.tracker, message)
            for state in self._states.values()
            if state.tracker is not None
            and not any(state.matches(tool_call) for tool_call in tool_calls)
        ]
        if events:
            await self._emit(events)
