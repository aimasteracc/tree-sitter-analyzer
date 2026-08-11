"""Bounded qualitative index-lag signal for status compatibility.

This read-only mtime comparison is informational only. Authoritative snapshot
freshness and completeness never depend on it.
"""

from __future__ import annotations

import os
import stat
import time
from collections.abc import Iterator

_LAG_WALK_FILE_CAP = 5000
_LAG_ENTRY_CAP = 100_000
_LAG_PATH_BYTE_CAP = 16 * 1024 * 1024
_LAG_DEADLINE_SECONDS = 0.5
_LAG_SOURCE_EXTS = (".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs")
_LAG_SKIP_DIRS = frozenset(
    {
        ".ast-cache",
        "__pycache__",
        ".git",
        "node_modules",
        ".venv",
        "venv",
        ".tox",
        "dist",
        "build",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
)


def compute_qualitative_lag(project_root: str, cache_path: str) -> float | None:
    """Compare newest bounded source mtime with cache mtime, never as evidence."""
    if os.name != "posix" or not os.path.exists("/dev/fd"):
        return None
    try:
        db_mtime = os.path.getmtime(cache_path)
    except OSError:
        return None
    newest = _newest_source_mtime(project_root)
    return None if newest is None else max(0.0, newest - db_mtime)


def _newest_source_mtime(project_root: str) -> float | None:
    """Stream a descriptor-relative, no-follow source scan within hard bounds."""
    if os.name != "posix" or not os.path.exists("/dev/fd"):
        return None
    deadline = time.monotonic() + _LAG_DEADLINE_SECONDS
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    newest: float | None = None
    counters = {"entries": 0, "path_bytes": 0, "sources": 0}
    stack: list[tuple[int, str, Iterator[os.DirEntry[str]]]] = []

    def open_entries(
        name: str, directory_fd: int | None = None
    ) -> tuple[int, Iterator[os.DirEntry[str]]]:
        """Open a directory and transfer fd ownership only with a live iterator."""
        fd = (
            os.open(name, flags)
            if directory_fd is None
            else os.open(name, flags, dir_fd=directory_fd)
        )
        try:
            entries = iter(os.scandir(fd))
        except BaseException:
            os.close(fd)
            raise
        return fd, entries

    try:
        root_fd, root_entries = open_entries(os.path.abspath(project_root))
        stack.append((root_fd, "", root_entries))
        while stack:
            directory_fd, prefix, entries = stack[-1]
            if time.monotonic() > deadline:
                return None
            try:
                entry = next(entries)
            except StopIteration:
                close = getattr(entries, "close", None)
                if close is not None:
                    close()
                os.close(directory_fd)
                stack.pop()
                continue
            name = entry.name
            relative = f"{prefix}/{name}" if prefix else name
            counters["entries"] += 1
            counters["path_bytes"] += len(relative.encode("utf-8", "surrogatepass"))
            if (
                counters["entries"] > _LAG_ENTRY_CAP
                or counters["path_bytes"] > _LAG_PATH_BYTE_CAP
            ):
                return None
            info = entry.stat(follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                if name in _LAG_SKIP_DIRS:
                    continue
                child_fd, child_entries = open_entries(name, directory_fd)
                stack.append((child_fd, relative, child_entries))
                continue
            if not stat.S_ISREG(info.st_mode) or not name.endswith(_LAG_SOURCE_EXTS):
                continue
            counters["sources"] += 1
            if counters["sources"] > _LAG_WALK_FILE_CAP:
                return None
            modified = float(info.st_mtime)
            if newest is None or modified > newest:
                newest = modified
        return newest
    except OSError:
        return None
    finally:
        for directory_fd, _prefix, entries in stack:
            close = getattr(entries, "close", None)
            if close is not None:
                close()
            try:
                os.close(directory_fd)
            except OSError:
                pass
