"""Bounded source-scope certification for pathname-only platforms."""

from __future__ import annotations

import fnmatch
import os
import stat
import time
from pathlib import Path

from .constants import EXCLUDE_DIRS
from .index_source_scope import SourceScopeDescriptor
from .index_source_snapshot import CurrentSourceSnapshot, inventory_fingerprint
from .index_source_stream import hash_source_at
from .indexing_limits import KNOWLEDGE_INDEX_MAX_FILES
from .languages.lang_extension_map import EXT_TO_LANG

_SOURCE_BYTE_BUDGET = 512 * 1024 * 1024
_SOURCE_ENTRY_BUDGET = 1_000_000
_SOURCE_PATH_BYTE_BUDGET = 128 * 1024 * 1024


def _identity(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_mode),
        int(info.st_size),
        int(info.st_mtime_ns),
        int(info.st_ctime_ns),
    )


def _marker(info: os.stat_result) -> str:
    return (
        f"{info.st_dev}:{info.st_ino}:{info.st_size}:"
        f"{info.st_mtime_ns}:{info.st_ctime_ns}"
    )


def _is_reparse(info: os.stat_result) -> bool:
    attributes = int(getattr(info, "st_file_attributes", 0))
    reparse = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    return stat.S_ISLNK(info.st_mode) or bool(reparse and attributes & reparse)


def _same(before: os.stat_result, after: os.stat_result) -> bool:
    return _identity(before) == _identity(after)


def _scope_root(project_root: Path, relative: str) -> Path:
    normalized = relative.replace("\\", "/")
    parts = tuple(part for part in normalized.split("/") if part not in ("", "."))
    if normalized.startswith("/") or any(part == ".." for part in parts):
        raise OSError("source root escapes project")
    return project_root.joinpath(*parts)


def _portable_inventory(
    project_root: str,
    scope: SourceScopeDescriptor,
    deadline: float,
) -> tuple[frozenset[tuple[str, str, str]], bool]:
    """Hash one bounded pathname inventory without following directory links."""
    project = Path(project_root)
    root_before = os.lstat(project)
    if not stat.S_ISDIR(root_before.st_mode) or _is_reparse(root_before):
        return frozenset(), True
    rows: set[tuple[str, str, str]] = set()
    counters = {"entries": 0, "path_bytes": 0, "input": 0, "output": 0}
    supported = 0
    unsafe = False
    for relative_root in scope.roots:
        base = _scope_root(project, relative_root)
        try:
            base_before = os.lstat(base)
        except OSError:
            return frozenset(), True
        if not stat.S_ISDIR(base_before.st_mode) or _is_reparse(base_before):
            return frozenset(), True
        stack = [base]
        while stack:
            directory = stack.pop()
            directory_before = os.lstat(directory)
            try:
                entries = os.scandir(directory)
                with entries:
                    for entry in entries:
                        if time.monotonic() > deadline:
                            raise TimeoutError
                        path = Path(entry.path)
                        relative = path.relative_to(project).as_posix()
                        counters["entries"] += 1
                        counters["path_bytes"] += len(
                            relative.encode("utf-8", "surrogatepass")
                        )
                        if (
                            counters["entries"] > _SOURCE_ENTRY_BUDGET
                            or counters["path_bytes"] > _SOURCE_PATH_BYTE_BUDGET
                        ):
                            raise OverflowError
                        before = os.lstat(path)
                        language = EXT_TO_LANG.get(path.suffix.lower())
                        if stat.S_ISDIR(before.st_mode):
                            if entry.name in EXCLUDE_DIRS or entry.name.startswith("."):
                                continue
                            if _is_reparse(before):
                                continue
                            stack.append(path)
                            continue
                        if _is_reparse(before):
                            if language is not None:
                                unsafe = True
                            continue
                        if language is None or any(
                            fnmatch.fnmatch(relative, pattern)
                            for pattern in scope.effective_excludes
                        ):
                            continue
                        if not stat.S_ISREG(before.st_mode):
                            unsafe = True
                            continue
                        supported += 1
                        if supported > min(
                            scope.certification_max_files, KNOWLEDGE_INDEX_MAX_FILES
                        ):
                            raise OverflowError
                        marker, digest, clean = hash_source_at(
                            None,
                            str(path),
                            before,
                            deadline,
                            counters,
                            _SOURCE_BYTE_BUDGET,
                            _marker,
                            _same,
                        )
                        if not clean:
                            unsafe = True
                        rows.add((relative, digest, language))
            except OSError:
                return frozenset(), True
            if _identity(os.lstat(directory)) != _identity(directory_before):
                unsafe = True
        if _identity(os.lstat(base)) != _identity(base_before):
            unsafe = True
    if _identity(os.lstat(project)) != _identity(root_before):
        unsafe = True
    return frozenset(rows), unsafe


def capture_portable_source_snapshot(
    project_root: str,
    source_scope: SourceScopeDescriptor,
    *,
    deadline: float,
) -> CurrentSourceSnapshot:
    """Capture two equal bounded inventories on Windows/pathname-only hosts."""
    root = os.path.abspath(project_root)
    try:
        first, unsafe_first = _portable_inventory(root, source_scope, deadline)
        second, unsafe_second = _portable_inventory(root, source_scope, deadline)
        fingerprint = inventory_fingerprint(first, deadline=deadline)
    except TimeoutError:
        return CurrentSourceSnapshot(
            frozenset(), None, None, "unknown", "SOURCE_SCAN_DEADLINE"
        )
    except OverflowError:
        return CurrentSourceSnapshot(
            frozenset(), None, None, "unknown", "SOURCE_SCOPE_UNBOUNDED"
        )
    except OSError:
        return CurrentSourceSnapshot(
            frozenset(), None, None, "unknown", "SOURCE_SCOPE_UNREADABLE"
        )
    generation = "idxsrc-v3:" + fingerprint.removeprefix("sha256:")
    if unsafe_first or unsafe_second or first != second:
        return CurrentSourceSnapshot(
            first, fingerprint, generation, "unsafe", "SOURCE_SCOPE_UNSAFE"
        )
    return CurrentSourceSnapshot(first, fingerprint, generation, "exact", None)
