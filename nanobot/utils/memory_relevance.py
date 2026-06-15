"""Budgeted, query-aware selection for customer and brand memory."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable

_LAYER_WEIGHT = {
    "core": 5.0,
    "style": 4.0,
    "preference": 2.5,
    "project": 2.0,
    "insight": 1.0,
}
_CONSTRAINT_MARKERS = (
    "avoid",
    "must_not",
    "never",
    "feedback",
    "complaint",
    "tranh",
    "khong_duoc",
)
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "with",
        "anh",
        "ban",
        "cac",
        "can",
        "cho",
        "cua",
        "duoc",
        "hay",
        "la",
        "lam",
        "mot",
        "nhung",
        "tao",
        "theo",
        "va",
        "voi",
    }
)


def _plain(text: Any) -> str:
    normalized = unicodedata.normalize("NFD", str(text or "").casefold())
    without_marks = "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    )
    return re.sub(r"\s+", " ", without_marks).strip()


def extract_keywords(text: Any, *, max_keywords: int = 24) -> list[str]:
    """Extract stable Unicode keywords without assuming a business topic."""
    tokens = re.findall(r"[a-z0-9]+", _plain(text).replace("_", " "))
    result: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if len(token) < 2 or token in _STOP_WORDS or token in seen:
            continue
        seen.add(token)
        result.append(token)
        if len(result) >= max_keywords:
            break
    return result


def profile_learning_entries(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert profile learning arrays into regular rankable memory entries."""
    learning = profile.get("learningData")
    if not isinstance(learning, dict):
        return []

    entries: list[dict[str, Any]] = []
    for index, value in enumerate(learning.get("commonFeedback") or []):
        if str(value).strip():
            entries.append(
                {
                    "layer": "preference",
                    "key": f"common_feedback_{index}",
                    "value": str(value).strip(),
                    "source": "profile.learningData",
                    "confidence": 0.9,
                    "is_locked": 0,
                }
            )
    for index, value in enumerate(learning.get("bestPerformingPrompts") or []):
        if str(value).strip():
            entries.append(
                {
                    "layer": "preference",
                    "key": f"best_prompt_{index}",
                    "value": str(value).strip(),
                    "source": "profile.learningData",
                    "confidence": 0.85,
                    "is_locked": 0,
                }
            )
    return entries


def _entry_score(entry: dict[str, Any], query_keywords: set[str]) -> float:
    layer = str(entry.get("layer") or "").lower()
    key = _plain(entry.get("key")).replace(" ", "_")
    value = _plain(entry.get("value"))
    entry_keywords = set(extract_keywords(f"{key} {value}", max_keywords=80))
    overlap = len(query_keywords & entry_keywords)

    try:
        confidence = min(max(float(entry.get("confidence", 1.0)), 0.0), 1.0)
    except (TypeError, ValueError):
        confidence = 0.5

    score = _LAYER_WEIGHT.get(layer, 0.5) + confidence * 2.0
    score += overlap * 4.0
    if query_keywords and query_keywords <= entry_keywords:
        score += 2.0
    if entry.get("is_locked"):
        score += 1.0
    if any(marker in key for marker in _CONSTRAINT_MARKERS):
        score += 2.0
    return score


def _entry_size(entry: dict[str, Any]) -> int:
    return (
        len(str(entry.get("layer") or ""))
        + len(str(entry.get("key") or ""))
        + len(str(entry.get("value") or ""))
        + 2
    )


def _fit_entry(entry: dict[str, Any], remaining: int) -> dict[str, Any] | None:
    fitted = dict(entry)
    overhead = (
        len(str(fitted.get("layer") or ""))
        + len(str(fitted.get("key") or ""))
        + 2
    )
    available = remaining - overhead
    if available < 12:
        return None
    value = str(fitted.get("value") or "").strip()
    if len(value) > available:
        value = value[: max(1, available - 1)].rstrip() + "…"
    fitted["value"] = value
    return fitted


def select_relevant_memory(
    entries: Iterable[dict[str, Any]],
    *,
    query: str = "",
    max_chars: int = 1200,
    max_entries: int = 12,
) -> list[dict[str, Any]]:
    """Select the highest-value memory that fits a strict character budget."""
    if max_chars <= 0 or max_entries <= 0:
        return []

    query_keywords = set(extract_keywords(query))
    ranked: list[tuple[float, int, dict[str, Any]]] = []
    seen: set[tuple[str, str]] = set()
    for index, raw in enumerate(entries):
        if not isinstance(raw, dict):
            continue
        layer = str(raw.get("layer") or "").strip().lower()
        key = str(raw.get("key") or "").strip()
        value = str(raw.get("value") or "").strip()
        if not layer or not key or not value:
            continue
        identity = (layer, _plain(value))
        if identity in seen:
            continue
        seen.add(identity)
        entry = dict(raw)
        entry.update({"layer": layer, "key": key, "value": value})
        entry_keywords = set(extract_keywords(f"{key} {value}", max_keywords=80))
        overlap = query_keywords & entry_keywords
        if (
            query_keywords
            and layer in {"project", "insight"}
            and not overlap
        ):
            continue
        normalized_key = _plain(key).replace(" ", "_")
        learned_example = any(
            marker in normalized_key
            for marker in ("feedback", "best_prompt", "good_prompt")
        )
        if query_keywords and layer == "preference" and learned_example and not overlap:
            continue
        ranked.append((_entry_score(entry, query_keywords), index, entry))

    ranked.sort(key=lambda item: (-item[0], item[1]))

    selected: list[dict[str, Any]] = []
    used = 0
    for _, _, entry in ranked:
        if len(selected) >= max_entries:
            break
        separator = 1 if selected else 0
        remaining = max_chars - used - separator
        if remaining <= 0:
            break
        fitted = _fit_entry(entry, remaining)
        if fitted is None:
            continue
        selected.append(fitted)
        used += separator + _entry_size(fitted)
    return selected


def load_relevant_memory(
    profile: dict[str, Any],
    *,
    query: str = "",
    max_chars: int = 1200,
    max_entries: int = 12,
    db: Any | None = None,
) -> list[dict[str, Any]]:
    """Load DB memory plus profile learning, then return a budgeted selection."""
    entries: list[dict[str, Any]] = []
    user_id = str(
        profile.get("telegramUserId")
        or profile.get("telegram_user_id")
        or ""
    ).split("|")[0].strip()
    if user_id:
        try:
            if db is None:
                from nanobot.db.customer_db import get_db

                db = get_db()
            candidate_loader = getattr(db, "get_memory_candidates", None)
            if callable(candidate_loader):
                entries.extend(candidate_loader(user_id, limit=200))
            else:
                for layer_entries in db.get_all_memory(user_id).values():
                    entries.extend(layer_entries)
        except Exception:
            pass

    entries.extend(profile_learning_entries(profile))
    return select_relevant_memory(
        entries,
        query=query,
        max_chars=max_chars,
        max_entries=max_entries,
    )
