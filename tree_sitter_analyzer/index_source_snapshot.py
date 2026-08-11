"""Bounded read-only owner for the current full-index source scope."""

from __future__ import annotations

import fnmatch
import hashlib
import os
import sqlite3
import stat
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Literal

from .constants import EXCLUDE_DIRS
from .index_source_scope import (
    SOURCE_SCOPE_DESCRIPTOR_BYTE_BUDGET,
    SOURCE_SCOPE_ROOT_COUNT_BUDGET,
    SourceScopeDescriptor,
    canonical_source_scope_descriptor,
    make_source_scope_descriptor,
    parse_source_scope_descriptor,
    validate_full_index_source_scope,
)
from .index_source_stream import hash_source_at, opened_entry_matches
from .indexing_limits import KNOWLEDGE_INDEX_MAX_FILES
from .languages.lang_extension_map import EXT_TO_LANG

__all__ = [
    "SOURCE_SCOPE_DESCRIPTOR_BYTE_BUDGET",
    "SOURCE_SCOPE_ROOT_COUNT_BUDGET",
    "SourceScopeDescriptor",
    "canonical_source_scope_descriptor",
    "make_source_scope_descriptor",
    "parse_source_scope_descriptor",
    "validate_full_index_source_scope",
]

_SOURCE_DEADLINE_SECONDS = 5.0
_SOURCE_BYTE_BUDGET = 512 * 1024 * 1024
_SOURCE_PATH_BUDGET = KNOWLEDGE_INDEX_MAX_FILES
# Enumeration budgets cover every directory entry, including unsupported and
# excluded names; traversal and hashing never require a global ordering copy.
_SOURCE_ENTRY_BUDGET = 1_000_000
_SOURCE_ENTRY_PATH_BYTE_BUDGET = 128 * 1024 * 1024
_RECORDED_SOURCE_ROW_BUDGET = 100_000
_RECORDED_SOURCE_CELL_BYTE_BUDGET = 1024 * 1024
_RECORDED_SOURCE_TOTAL_BYTE_BUDGET = 64 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class CurrentSourceSnapshot:
    rows: frozenset[tuple[str, str, str]]
    fingerprint: str | None
    generation: str | None
    state: Literal["exact", "unsafe", "unknown"]
    reason: str | None


def inventory_fingerprint(
    rows: Iterable[tuple[str, str, str]], *, deadline: float | None = None
) -> str:
    """Hash unique rows without an ordering copy or attacker-controlled sorting."""
    total = 0
    count = 0
    paths: set[str] = set()
    modulus_mask = (1 << 256) - 1
    for row in rows:
        if deadline is not None and time.monotonic() > deadline:
            raise TimeoutError
        path = row[0]
        if path in paths:
            raise ValueError("SOURCE_INVENTORY_DUPLICATE_PATH")
        paths.add(path)
        row_digest = hashlib.sha256(b"tsa-index-source-row-v3\0")
        for value in row:
            if deadline is not None and time.monotonic() > deadline:
                raise TimeoutError
            raw = value.encode("utf-8", "surrogatepass")
            row_digest.update(len(raw).to_bytes(8, "big"))
            row_digest.update(raw)
        total = (total + int.from_bytes(row_digest.digest(), "big")) & modulus_mask
        count += 1
    digest = hashlib.sha256(b"tsa-index-source-set-v3\0")
    digest.update(count.to_bytes(8, "big"))
    digest.update(total.to_bytes(32, "big"))
    return "sha256:" + digest.hexdigest()


def recorded_source_rows(
    conn: object, *, deadline: float | None = None
) -> frozenset[tuple[str, str, str]]:
    """Read the cache's claimed inventory directly into one bounded set."""
    connection = conn  # Keep the boundary typed for lightweight test doubles.
    effective_deadline = (
        deadline
        if deadline is not None
        else time.monotonic() + _SOURCE_DEADLINE_SECONDS
    )

    def expired() -> int:
        return int(time.monotonic() > effective_deadline)

    def check_deadline() -> None:
        if time.monotonic() > effective_deadline:
            raise TimeoutError

    connection.set_progress_handler(expired, 1_000)  # type: ignore[attr-defined]
    try:
        check_deadline()
        preflight = connection.execute(  # type: ignore[attr-defined]
            "SELECT COUNT(*), "
            "MAX(length(CAST(file_path AS BLOB))), "
            "MAX(length(CAST(content_hash AS BLOB))), "
            "MAX(length(CAST(language AS BLOB))), "
            "SUM(COALESCE(length(CAST(file_path AS BLOB)), ?) + "
            "COALESCE(length(CAST(content_hash AS BLOB)), ?) + "
            "COALESCE(length(CAST(language AS BLOB)), ?)) FROM ast_index",
            (_RECORDED_SOURCE_TOTAL_BYTE_BUDGET + 1,) * 3,
        ).fetchone()
        check_deadline()
        if preflight is None or len(preflight) != 5:
            raise OverflowError("SOURCE_INVENTORY_BUDGET")
        count, max_path, max_hash, max_language, total_bytes = preflight
        if not isinstance(count, int):
            raise OverflowError("SOURCE_INVENTORY_BUDGET")
        if count < 0 or count > _RECORDED_SOURCE_ROW_BUDGET:
            raise OverflowError("SOURCE_INVENTORY_BUDGET")
        if count == 0:
            return frozenset()
        if (
            not isinstance(max_path, int)
            or not isinstance(max_hash, int)
            or not isinstance(max_language, int)
            or not isinstance(total_bytes, int)
            or max_path > _RECORDED_SOURCE_CELL_BYTE_BUDGET
            or max_hash > _RECORDED_SOURCE_CELL_BYTE_BUDGET
            or max_language > _RECORDED_SOURCE_CELL_BYTE_BUDGET
            or total_bytes > _RECORDED_SOURCE_TOTAL_BYTE_BUDGET
        ):
            raise OverflowError("SOURCE_INVENTORY_BUDGET")

        # Repeat the cell guards in the payload query so a value enlarged after
        # preflight is replaced with NULL inside SQLite instead of crossing the
        # SQLite/Python boundary. The Python loop still recharges every cell and
        # the total from the values it actually receives.
        cursor = connection.execute(  # type: ignore[attr-defined]
            "SELECT "
            "CASE WHEN typeof(file_path)='text' AND length(CAST(file_path AS BLOB)) <= ? THEN file_path END, "
            "CASE WHEN typeof(content_hash)='text' AND length(CAST(content_hash AS BLOB)) <= ? THEN content_hash END, "
            "CASE WHEN typeof(language)='text' AND length(CAST(language AS BLOB)) <= ? THEN language END "
            "FROM ast_index ORDER BY file_path",
            (_RECORDED_SOURCE_CELL_BYTE_BUDGET,) * 3,
        )

        def rows() -> Iterator[tuple[str, str, str]]:
            previous_path: str | None = None
            fetched = charged_bytes = 0
            while True:
                check_deadline()
                row = cursor.fetchone()
                check_deadline()
                if row is None:
                    break
                fetched += 1
                if fetched > count:
                    raise OverflowError("SOURCE_INVENTORY_BUDGET")
                raw_path, content_hash, language = row
                if not all(
                    isinstance(value, str)
                    for value in (raw_path, content_hash, language)
                ):
                    raise ValueError("CORRUPT_INDEX")
                cell_bytes = tuple(
                    len(value.encode("utf-8", "surrogatepass"))
                    for value in (raw_path, content_hash, language)
                )
                charged_bytes += sum(cell_bytes)
                if (
                    any(size > _RECORDED_SOURCE_CELL_BYTE_BUDGET for size in cell_bytes)
                    or charged_bytes > _RECORDED_SOURCE_TOTAL_BYTE_BUDGET
                ):
                    raise OverflowError("SOURCE_INVENTORY_BUDGET")
                path = raw_path.replace("\\", "/") if os.name == "nt" else raw_path
                if path == previous_path:
                    raise ValueError("SOURCE_INVENTORY_DUPLICATE_PATH")
                previous_path = path
                yield path, content_hash, language
            if fetched != count:
                raise ValueError("CORRUPT_INDEX")

        # The generator streams directly into the sole retained inventory object.
        return frozenset(rows())
    except sqlite3.OperationalError as exc:
        if time.monotonic() > effective_deadline or "interrupt" in str(exc).lower():
            raise TimeoutError from exc
        raise
    finally:
        connection.set_progress_handler(None, 0)  # type: ignore[attr-defined]


def capture_current_source_snapshot(
    project_root: str,
    source_scope: SourceScopeDescriptor | None = None,
    *,
    deadline: float | None = None,
) -> CurrentSourceSnapshot:
    """Hash a stable, fully bounded view of the certified supported scope."""
    scope = source_scope or make_source_scope_descriptor()
    if os.name != "posix" or not os.path.exists("/dev/fd"):
        return CurrentSourceSnapshot(
            frozenset(), None, None, "unsafe", "SOURCE_SCOPE_UNSUPPORTED"
        )
    deadline = (
        time.monotonic() + _SOURCE_DEADLINE_SECONDS if deadline is None else deadline
    )
    root = os.path.abspath(project_root)
    try:
        first, unsafe = _inventory(root, deadline, scope, with_content=True)
        second, unsafe_second = _inventory(root, deadline, scope, with_content=False)
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

    metadata = {(path, language): marker for path, marker, language in second}
    stable = all(
        metadata.get((path, language)) == marker.split("|", 1)[0]
        for path, marker, language in first
    )
    first_scope = frozenset((r[0], r[2]) for r in first)
    second_scope = frozenset((r[0], r[2]) for r in second)
    unique_scope = len(first_scope) == len(first) and len(second_scope) == len(second)
    same_paths = first_scope == second_scope
    rows = frozenset(
        (path, marker.split("|", 1)[1], language) for path, marker, language in first
    )
    try:
        fingerprint = inventory_fingerprint(rows, deadline=deadline)
    except TimeoutError:
        return CurrentSourceSnapshot(
            frozenset(), None, None, "unknown", "SOURCE_SCAN_DEADLINE"
        )
    generation = "idxsrc-v3:" + fingerprint.removeprefix("sha256:")
    if unsafe or unsafe_second or not stable or not same_paths or not unique_scope:
        return CurrentSourceSnapshot(
            rows, fingerprint, generation, "unsafe", "SOURCE_SCOPE_UNSAFE"
        )
    return CurrentSourceSnapshot(rows, fingerprint, generation, "exact", None)


def _inventory(
    root: str,
    deadline: float,
    scope: SourceScopeDescriptor | None = None,
    *,
    with_content: bool,
) -> tuple[frozenset[tuple[str, str, str]], bool]:
    """Walk supported sources through pinned directory descriptors on POSIX."""
    scope = scope or make_source_scope_descriptor()
    if len(scope.roots) > SOURCE_SCOPE_ROOT_COUNT_BUDGET:
        raise OverflowError
    if time.monotonic() > deadline:
        raise TimeoutError
    if os.name != "posix" or not os.path.exists("/dev/fd"):
        # Portable pathname traversal cannot close descendant-reparse and path-swap
        # TOCTOU windows, so certification is deliberately unavailable.
        return frozenset(), True
    rows: set[tuple[str, str, str]] = set()
    unsafe = False
    counters = {"entries": 0, "path_bytes": 0, "input": 0, "output": 0}
    replay_limit = min(scope.certification_max_files, _SOURCE_PATH_BUDGET)
    supported_count = 0
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_flags |= getattr(os, "O_NOFOLLOW", 0)
    root_before = os.stat(root, follow_symlinks=False)
    root_fd = os.open(root, directory_flags)
    try:
        root_info = os.fstat(root_fd)
        if not stat.S_ISDIR(root_info.st_mode):
            raise OSError("source root is not a directory")
        if not opened_entry_matches(root_before, root_info):
            return frozenset(), True
        scope_roots: list[tuple[int, str]] = []
        try:
            for relative_root in scope.roots:
                normalized = (
                    relative_root.replace("\\", "/")
                    if os.name == "nt"
                    else relative_root
                )
                parts = [
                    part for part in normalized.split("/") if part not in ("", ".")
                ]
                if any(part == ".." for part in parts) or normalized.startswith("/"):
                    raise OSError("source root escapes project")
                current = os.dup(root_fd)
                try:
                    scope_root_safe = True
                    for part in parts:
                        before = os.stat(part, dir_fd=current, follow_symlinks=False)
                        child = os.open(part, directory_flags, dir_fd=current)
                        child_info = os.fstat(child)
                        if not opened_entry_matches(before, child_info):
                            os.close(child)
                            unsafe = True
                            scope_root_safe = False
                            break
                        os.close(current)
                        current = child
                    if scope_root_safe:
                        scope_roots.append((current, "/".join(parts)))
                    else:
                        os.close(current)
                except Exception:
                    os.close(current)
                    raise

            while scope_roots:
                scope_fd, prefix = scope_roots.pop(0)
                stack: list[tuple[int, str, Iterator[tuple[str, os.stat_result]]]] = []
                try:
                    stack.append(
                        (
                            scope_fd,
                            prefix,
                            _enumerate_directory(scope_fd, prefix, deadline, counters),
                        )
                    )
                    while stack:
                        directory_fd, relative_dir, entries = stack[-1]
                        try:
                            name, info = next(entries)
                        except StopIteration:
                            os.close(directory_fd)
                            stack.pop()
                            continue
                        rel = f"{relative_dir}/{name}" if relative_dir else name
                        mode = info.st_mode
                        if stat.S_ISDIR(mode):
                            if name in EXCLUDE_DIRS or name.startswith("."):
                                continue
                            try:
                                child_fd = os.open(
                                    name, directory_flags, dir_fd=directory_fd
                                )
                            except OSError:
                                unsafe = True
                                continue
                            try:
                                child_info = os.fstat(child_fd)
                                if not stat.S_ISDIR(
                                    child_info.st_mode
                                ) or not opened_entry_matches(info, child_info):
                                    unsafe = True
                                    os.close(child_fd)
                                    continue
                                child_entries = _enumerate_directory(
                                    child_fd, rel, deadline, counters
                                )
                            except Exception:
                                os.close(child_fd)
                                raise
                            stack.append((child_fd, rel, child_entries))
                            continue

                        language = EXT_TO_LANG.get(os.path.splitext(name)[1].lower())
                        if language is None:
                            continue
                        if os.name == "posix" and "\\" in rel:
                            unsafe = True
                        if any(
                            fnmatch.fnmatch(rel, pattern)
                            for pattern in scope.effective_excludes
                        ):
                            continue
                        if not stat.S_ISREG(mode):
                            unsafe = True
                            rows.add(
                                (rel, _metadata_marker(info) + "|<unsafe>", language)
                            )
                            continue
                        # Match candidate discovery: max_files is consumed only by
                        # selected, supported regular files. Persisted exclusions
                        # and unsafe special files never consume that budget.
                        supported_count += 1
                        if supported_count > replay_limit:
                            raise OverflowError
                        if not with_content:
                            rows.add((rel, _metadata_marker(info), language))
                            continue
                        marker, content_hash, clean = hash_source_at(
                            directory_fd,
                            name,
                            info,
                            deadline,
                            counters,
                            _SOURCE_BYTE_BUDGET,
                            _metadata_marker,
                            _same_file_metadata,
                        )
                        if not clean:
                            unsafe = True
                        rows.add((rel, marker + "|" + content_hash, language))
                finally:
                    for directory_fd, _relative_dir, _entries in stack:
                        try:
                            os.close(directory_fd)
                        except OSError:
                            pass
        finally:
            for scope_fd, _prefix in scope_roots:
                try:
                    os.close(scope_fd)
                except OSError:
                    pass
    finally:
        os.close(root_fd)
    return frozenset(rows), unsafe


def _enumerate_directory(
    directory_fd: int,
    prefix: str,
    deadline: float,
    counters: dict[str, int],
) -> Iterator[tuple[str, os.stat_result]]:
    """Enumerate fully under absolute entry, path-byte, and time budgets."""
    with os.scandir(directory_fd) as entries:
        for entry in entries:
            if time.monotonic() > deadline:
                raise TimeoutError
            name = entry.name
            rel = f"{prefix}/{name}" if prefix else name
            counters["entries"] += 1
            counters["path_bytes"] += len(rel.encode("utf-8", "surrogatepass"))
            if (
                counters["entries"] > _SOURCE_ENTRY_BUDGET
                or counters["path_bytes"] > _SOURCE_ENTRY_PATH_BYTE_BUDGET
            ):
                raise OverflowError
            info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            yield name, info


def _metadata_marker(info: os.stat_result) -> str:
    return f"{info.st_dev}:{info.st_ino}:{info.st_size}:{info.st_mtime_ns}:{info.st_ctime_ns}"


def _same_file_metadata(before: os.stat_result, after: os.stat_result) -> bool:
    """Compare path/fd metadata without relying on platform-specific ctime."""
    identity_matches = not (before.st_ino and after.st_ino) or (
        before.st_dev,
        before.st_ino,
    ) == (after.st_dev, after.st_ino)
    return identity_matches and (before.st_size, before.st_mtime_ns) == (
        after.st_size,
        after.st_mtime_ns,
    )
