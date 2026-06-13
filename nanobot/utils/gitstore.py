"""Git-backed version control for Dream-managed memory files."""

from __future__ import annotations

import io
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger


@dataclass
class CommitInfo:
    sha: str
    message: str
    timestamp: str

    def format(self, diff: str = "") -> str:
        header = f"## {self.message.splitlines()[0]}\n`{self.sha}` - {self.timestamp}\n"
        if diff:
            return f"{header}\n```diff\n{diff}\n```"
        return f"{header}\n(no file changes)"


GitCommit = CommitInfo


@dataclass
class LineAge:
    age_days: int


def _compute_line_ages(annotated) -> list[LineAge]:
    now = datetime.now(tz=timezone.utc).date()
    ages: list[LineAge] = []
    for (commit, _tree_entry), _line_bytes in annotated:
        changed = datetime.fromtimestamp(commit.commit_time, tz=timezone.utc).date()
        ages.append(LineAge(age_days=(now - changed).days))
    return ages


class GitStore:
    """A small isolated repository that tracks only memory-owned files."""

    def __init__(self, workspace: Path, tracked_files: list[str] | None = None) -> None:
        self._workspace = Path(workspace)
        self._tracked_files = list(tracked_files or [])

    def is_initialized(self) -> bool:
        return (self._workspace / ".git").is_dir()

    def init(self) -> bool:
        if self.is_initialized():
            return False
        if self._is_inside_git_repo():
            logger.warning(
                "Workspace {} is already inside a git repo; skipping nested repo",
                self._workspace,
            )
            return False

        try:
            from dulwich import porcelain

            self._workspace.mkdir(parents=True, exist_ok=True)
            porcelain.init(str(self._workspace))
            gitignore = self._workspace / ".gitignore"
            managed = self._build_gitignore()
            if gitignore.exists():
                existing = gitignore.read_text(encoding="utf-8")
                existing_lines = set(existing.splitlines())
                additions = [
                    line for line in managed.splitlines() if line not in existing_lines
                ]
                if additions:
                    gitignore.write_text(
                        existing.rstrip("\n") + "\n" + "\n".join(additions) + "\n",
                        encoding="utf-8",
                    )
            else:
                gitignore.write_text(managed, encoding="utf-8")

            for relative in self._tracked_files:
                path = self._workspace / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                if not path.exists():
                    path.write_text("", encoding="utf-8")

            porcelain.add(
                str(self._workspace),
                paths=[".gitignore", *self._tracked_files],
            )
            porcelain.commit(
                str(self._workspace),
                message=b"init: nanobot memory store",
                author=b"nanobot <nanobot@dream>",
                committer=b"nanobot <nanobot@dream>",
            )
            return True
        except Exception:
            logger.exception("Git store init failed for {}", self._workspace)
            return False

    def auto_commit(self, message: str) -> str | None:
        if not self.is_initialized():
            return None
        try:
            from dulwich import porcelain

            status = porcelain.status(str(self._workspace))
            if not status.unstaged and not any(status.staged.values()):
                return None
            porcelain.add(str(self._workspace), paths=self._tracked_files)
            sha = porcelain.commit(
                str(self._workspace),
                message=message.encode("utf-8"),
                author=b"nanobot <nanobot@dream>",
                committer=b"nanobot <nanobot@dream>",
            )
            return sha.hex()[:8] if sha is not None else None
        except Exception:
            logger.exception("Git auto-commit failed: {}", message)
            return None

    def commit(self, message: str = "") -> str | None:
        return self.auto_commit(message)

    def log(self, max_entries: int = 20) -> list[CommitInfo]:
        if not self.is_initialized():
            return []
        try:
            from dulwich.repo import Repo

            entries: list[CommitInfo] = []
            with Repo(str(self._workspace)) as repo:
                try:
                    sha = repo.refs[b"HEAD"]
                except KeyError:
                    return []
                while sha and len(entries) < max_entries:
                    commit = repo[sha]
                    if commit.type_name != b"commit":
                        break
                    entries.append(CommitInfo(
                        sha=sha.hex()[:8],
                        message=commit.message.decode("utf-8", errors="replace").strip(),
                        timestamp=time.strftime(
                            "%Y-%m-%d %H:%M",
                            time.localtime(commit.commit_time),
                        ),
                    ))
                    sha = commit.parents[0] if commit.parents else None
            return entries
        except Exception:
            logger.exception("Git log failed")
            return []

    def line_ages(self, file_path: str) -> list[LineAge]:
        if not self.is_initialized():
            return []
        target = self._workspace / file_path
        if not target.exists() or target.stat().st_size == 0:
            return []
        try:
            from dulwich import porcelain

            annotated = porcelain.annotate(str(self._workspace), file_path)
            return _compute_line_ages(annotated) if annotated else []
        except Exception:
            logger.exception("Git line_ages failed for {}", file_path)
            return []

    def diff_commits(self, sha1: str, sha2: str) -> str:
        if not self.is_initialized():
            return ""
        try:
            from dulwich import porcelain

            full1 = self._resolve_sha(sha1)
            full2 = self._resolve_sha(sha2)
            if not full1 or not full2:
                return ""
            output = io.BytesIO()
            porcelain.diff(
                str(self._workspace),
                commit=full1,
                commit2=full2,
                outstream=output,
            )
            return output.getvalue().decode("utf-8", errors="replace")
        except Exception:
            logger.exception("Git diff failed")
            return ""

    def find_commit(self, short_sha: str, max_entries: int = 20) -> CommitInfo | None:
        return next(
            (entry for entry in self.log(max_entries) if entry.sha.startswith(short_sha)),
            None,
        )

    def show_commit_diff(
        self,
        short_sha: str,
        max_entries: int = 20,
    ) -> tuple[CommitInfo, str] | None:
        commits = self.log(max_entries)
        for index, commit in enumerate(commits):
            if commit.sha.startswith(short_sha):
                diff = (
                    self.diff_commits(commits[index + 1].sha, commit.sha)
                    if index + 1 < len(commits)
                    else ""
                )
                return commit, diff
        return None

    def revert(self, commit: str) -> str | None:
        if not self.is_initialized():
            return None
        try:
            from dulwich.repo import Repo

            full_sha = self._resolve_sha(commit)
            if not full_sha:
                return None
            with Repo(str(self._workspace)) as repo:
                commit_obj = repo[full_sha]
                if commit_obj.type_name != b"commit" or not commit_obj.parents:
                    return None
                parent = repo[commit_obj.parents[0]]
                tree = repo[parent.tree]
                restored = False
                for relative in self._tracked_files:
                    content = self._read_blob_from_tree(repo, tree, relative)
                    if content is None:
                        continue
                    destination = self._workspace / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_text(content, encoding="utf-8")
                    restored = True
            return self.auto_commit(f"revert: undo {commit}") if restored else None
        except Exception:
            logger.exception("Git revert failed for {}", commit)
            return None

    def _resolve_sha(self, short_sha: str) -> bytes | None:
        try:
            from dulwich.repo import Repo

            with Repo(str(self._workspace)) as repo:
                try:
                    sha = repo.refs[b"HEAD"]
                except KeyError:
                    return None
                while sha:
                    if sha.hex().startswith(short_sha):
                        return sha
                    commit = repo[sha]
                    if commit.type_name != b"commit":
                        break
                    sha = commit.parents[0] if commit.parents else None
            return None
        except Exception:
            return None

    def _is_inside_git_repo(self) -> bool:
        current = self._workspace.resolve()
        while current != current.parent:
            if (current / ".git").exists():
                return True
            current = current.parent
        return False

    def _build_gitignore(self) -> str:
        directories = {
            str(Path(relative).parent)
            for relative in self._tracked_files
            if Path(relative).parent != Path(".")
        }
        lines = ["/*"]
        lines.extend(f"!{directory}/" for directory in sorted(directories))
        lines.extend(f"!{relative}" for relative in self._tracked_files)
        lines.append("!.gitignore")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _read_blob_from_tree(repo, tree, file_path: str) -> str | None:
        current = tree
        for part in Path(file_path).parts:
            try:
                entry = current[part.encode()]
            except KeyError:
                return None
            obj = repo[entry[1]]
            if obj.type_name == b"blob":
                return obj.data.decode("utf-8", errors="replace")
            if obj.type_name != b"tree":
                return None
            current = obj
        return None
