"""Stub git-based memory versioning.

The full GitStore implementation was removed as part of the Vidtory
refactoring. This stub satisfies any remaining imports.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class GitCommit:
    sha: str = ""
    timestamp: str = ""
    message: str = ""


class GitStore:
    """No-op stub for git-based memory versioning."""

    def __init__(self, workspace: Path, tracked_files: list[str] | None = None) -> None:
        pass

    def init(self) -> None:
        pass

    def is_initialized(self) -> bool:
        return False

    def commit(self, message: str = "") -> str | None:
        return None

    def log(self, max_entries: int = 10) -> list[GitCommit]:
        return []

    def show_commit_diff(self, sha: str) -> tuple[GitCommit, str] | None:
        return None

    def revert(self, sha: str) -> str | None:
        return None
