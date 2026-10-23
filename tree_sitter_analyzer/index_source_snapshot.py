"""Bounded read-only owner for the current full-index source scope."""

from __future__ import annotations

import fnmatch
import hashlib
import os
import stat
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import Literal

from ._recorded_source_rows import read_recorded_source_rows
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
from .index_source_stream import hash_source_or_unsafe, opened_entry_matches
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
    """把缓存声明的源码清单读取为一个有界集合。"""
    effective_deadline = (
        deadline
        if deadline is not None
        else time.monotonic() + _SOURCE_DEADLINE_SECONDS
    )
    return read_recorded_source_rows(
        conn,
        effective_deadline=effective_deadline,
        monotonic=lambda: time.monotonic(),
        row_budget=_RECORDED_SOURCE_ROW_BUDGET,
        cell_byte_budget=_RECORDED_SOURCE_CELL_BYTE_BUDGET,
        total_byte_budget=_RECORDED_SOURCE_TOTAL_BYTE_BUDGET,
    )


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
    try:
        scan = _scan_source_scope(os.path.abspath(project_root), scope, deadline)
    except TimeoutError:
        return _unknown_snapshot("SOURCE_SCAN_DEADLINE")
    except OverflowError:
        return _unknown_snapshot("SOURCE_SCOPE_UNBOUNDED")
    except OSError:
        return _unknown_snapshot("SOURCE_SCOPE_UNREADABLE")

    rows = frozenset(
        (path, marker.split("|", 1)[1], language)
        for path, marker, language in scan.first
    )
    try:
        fingerprint = inventory_fingerprint(rows, deadline=deadline)
    except TimeoutError:
        return _unknown_snapshot("SOURCE_SCAN_DEADLINE")
    generation = "idxsrc-v3:" + fingerprint.removeprefix("sha256:")
    if not scan.exact():
        return CurrentSourceSnapshot(
            rows, fingerprint, generation, "unsafe", "SOURCE_SCOPE_UNSAFE"
        )
    return CurrentSourceSnapshot(rows, fingerprint, generation, "exact", None)


def _unknown_snapshot(reason: str) -> CurrentSourceSnapshot:
    """A snapshot whose source state could not be determined."""
    return CurrentSourceSnapshot(frozenset(), None, None, "unknown", reason)


@dataclass(frozen=True, slots=True)
class _SourceScan:
    """The two inventories of one capture and the checks made around them."""

    first: frozenset[tuple[str, str, str]]
    unsafe: bool
    second: frozenset[tuple[str, str, str]]
    unsafe_second: bool
    revalidated: bool
    root_current: bool

    def exact(self) -> bool:
        """Both walks are clean, agree with each other, and still match the tree."""
        return (
            not self.unsafe
            and not self.unsafe_second
            and self.root_current
            and _inventories_agree(self.first, self.second)
            and self.revalidated
        )


def _scan_source_scope(
    root: str, scope: SourceScopeDescriptor, deadline: float
) -> _SourceScan:
    """Walk the scope with content, walk it again by metadata, then revalidate."""
    root_before = os.stat(root, follow_symlinks=False)
    first, unsafe = _inventory(root, deadline, scope, with_content=True)
    second, unsafe_second = _inventory(root, deadline, scope, with_content=False)
    revalidated = _revalidate_source_rows(root, second, deadline)
    root_current = _reopened_root_matches(root, root_before)
    return _SourceScan(first, unsafe, second, unsafe_second, revalidated, root_current)


def _inventories_agree(
    first: frozenset[tuple[str, str, str]],
    second: frozenset[tuple[str, str, str]],
) -> bool:
    """The content walk's metadata matches the metadata walk, path for path."""
    metadata = {(path, language): marker for path, marker, language in second}
    stable = all(
        metadata.get((path, language)) == marker.split("|", 1)[0]
        for path, marker, language in first
    )
    first_scope = frozenset((r[0], r[2]) for r in first)
    second_scope = frozenset((r[0], r[2]) for r in second)
    unique_scope = len(first_scope) == len(first) and len(second_scope) == len(second)
    return stable and first_scope == second_scope and unique_scope


def _directory_open_flags() -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    return flags | getattr(os, "O_NOFOLLOW", 0)


def _leaf_open_flags() -> int:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    return flags | getattr(os, "O_NONBLOCK", 0)


#: One admitted leaf: its path parts, its ancestors' metadata and its own metadata.
_AdmittedRow = tuple[tuple[str, ...], tuple[os.stat_result, ...], os.stat_result]


def _revalidate_source_rows(
    root: str,
    rows: Iterable[tuple[str, str, str]],
    deadline: float,
) -> bool:
    """Authenticate one epoch while retaining only O(path depth) descriptors.

    Admission walks each leaf from the pinned root, recording identity and
    mutation-sensitive metadata for every ancestor and the leaf, then closes
    that chain.  Once all leaves have been admitted, every chain is reopened
    from the same pinned root and compared with its admission record.  Thus an
    early leaf's stable interval reaches the recheck phase while a late leaf's
    interval starts in the admission phase, without retaining O(files) fds.
    """
    root_before = os.stat(root, follow_symlinks=False)
    root_fd = os.open(root, _directory_open_flags())
    root_opened = os.fstat(root_fd)
    try:
        if not stat.S_ISDIR(root_opened.st_mode) or not opened_entry_matches(
            root_before, root_opened
        ):
            return False
        admitted_rows = _admit_rows(root_fd, rows, deadline)
        if admitted_rows is None:
            return False

        # The pinned root itself must still name the caller-visible root before
        # chain replay; otherwise a stable but renamed tree could authenticate.
        if time.monotonic() > deadline:
            raise TimeoutError
        try:
            if not _reopened_root_matches(root, root_opened):
                return False
        except OSError:
            return False
        return _recheck_rows(root_fd, admitted_rows, deadline)
    finally:
        os.close(root_fd)


def _admit_rows(
    root_fd: int, rows: Iterable[tuple[str, str, str]], deadline: float
) -> list[_AdmittedRow] | None:
    """Admission: open each row's chain once and record it; None if any row fails.

    Each descriptor chain is short-lived, but its complete identity/ctime record
    survives until the common recheck boundary.
    """
    admitted_rows: list[_AdmittedRow] = []
    for relative, expected_marker, _language in rows:
        if time.monotonic() > deadline:
            raise TimeoutError
        parts = tuple(relative.split("/"))
        if not parts or any(part in ("", ".", "..") for part in parts):
            return None
        try:
            fds, ancestors, opened = _open_chain(
                root_fd, parts, deadline, check_deadline=False
            )
        except OSError:
            return None
        try:
            if _metadata_marker(opened) != expected_marker:
                return None
        finally:
            _close_descriptors(fds)
        admitted_rows.append((parts, ancestors, opened))
    return admitted_rows


def _recheck_rows(
    root_fd: int, admitted_rows: list[_AdmittedRow], deadline: float
) -> bool:
    """Recheck: reopen every admitted chain from the pinned root and compare
    both identity and ctime-bearing mutation metadata."""
    for parts, admitted_ancestors, admitted_leaf in admitted_rows:
        if time.monotonic() > deadline:
            raise TimeoutError
        try:
            fds, current_ancestors, current_leaf = _open_chain(
                root_fd, parts, deadline, check_deadline=True
            )
        except OSError:
            # Includes the chain's own deadline check (TimeoutError is an OSError).
            return False
        try:
            if not _same_chain(
                admitted_ancestors, admitted_leaf, current_ancestors, current_leaf
            ):
                return False
        finally:
            _close_descriptors(fds)
    return True


def _same_chain(
    admitted_ancestors: tuple[os.stat_result, ...],
    admitted_leaf: os.stat_result,
    current_ancestors: tuple[os.stat_result, ...],
    current_leaf: os.stat_result,
) -> bool:
    if not _same_file_metadata(admitted_leaf, current_leaf):
        return False
    return len(admitted_ancestors) == len(current_ancestors) and all(
        _same_file_metadata(admitted, current)
        for admitted, current in zip(admitted_ancestors, current_ancestors, strict=True)
    )


def _close_quietly(fd: int) -> None:
    """Close ``fd`` during cleanup, ignoring an error (the walk already failed)."""
    try:
        os.close(fd)
    except OSError:
        pass


def _close_descriptors(fds: list[int]) -> None:
    for fd in reversed(fds):
        os.close(fd)


def _open_chain(
    root_fd: int, parts: tuple[str, ...], deadline: float, *, check_deadline: bool
) -> tuple[list[int], tuple[os.stat_result, ...], os.stat_result]:
    """Open every ancestor and the leaf of ``parts`` from the pinned root.

    Returns the open descriptors (the caller closes them), the opened ancestors'
    metadata and the opened leaf's metadata. On any failure the descriptors
    opened so far are closed before the error propagates.
    """
    current = os.dup(root_fd)
    opened_fds = [current]
    ancestors: list[os.stat_result] = []
    try:
        for component in parts[:-1]:
            if check_deadline and time.monotonic() > deadline:
                raise TimeoutError
            current, opened = _open_verified_child(
                current,
                component,
                _directory_open_flags(),
                opened_fds,
                stat.S_ISDIR,
                "source ancestor changed",
            )
            ancestors.append(opened)
        if check_deadline and time.monotonic() > deadline:
            raise TimeoutError
        _leaf, opened = _open_verified_child(
            current,
            parts[-1],
            _leaf_open_flags(),
            opened_fds,
            stat.S_ISREG,
            "source leaf changed",
        )
        return opened_fds, tuple(ancestors), opened
    except Exception:
        _close_descriptors(opened_fds)
        raise


def _open_verified_child(
    parent_fd: int,
    name: str,
    flags: int,
    opened_fds: list[int],
    is_kind: Callable[[int], bool],
    changed: str,
) -> tuple[int, os.stat_result]:
    """Open ``name`` under ``parent_fd``: it must be of the expected kind and be
    the entry that was stat'ed, else ``OSError(changed)``.

    The new descriptor is appended to ``opened_fds`` as soon as it exists, so the
    caller's cleanup closes it on every failure path.
    """
    before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    child = os.open(name, flags, dir_fd=parent_fd)
    opened_fds.append(child)
    opened = os.fstat(child)
    if not is_kind(opened.st_mode) or not opened_entry_matches(before, opened):
        raise OSError(changed)
    return child, opened


def _reopened_root_matches(root: str, expected: os.stat_result) -> bool:
    """Reopen the root after final inventory and authenticate its identity."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    current_path = os.stat(root, follow_symlinks=False)
    root_fd = os.open(root, flags)
    try:
        current_open = os.fstat(root_fd)
        return (
            opened_entry_matches(expected, current_path)
            and opened_entry_matches(current_path, current_open)
            and _same_file_metadata(expected, current_open)
        )
    finally:
        os.close(root_fd)


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
    walk = _InventoryWalk(deadline, scope, with_content)
    root_before = os.stat(root, follow_symlinks=False)
    root_fd = os.open(root, _directory_open_flags())
    try:
        root_info = os.fstat(root_fd)
        if not stat.S_ISDIR(root_info.st_mode):
            raise OSError("source root is not a directory")
        if not opened_entry_matches(root_before, root_info):
            return frozenset(), True
        walk.walk_scope_roots(root_fd)
    finally:
        os.close(root_fd)
    return frozenset(walk.rows), walk.unsafe


#: One directory being enumerated: its descriptor, relative path and entries.
_OpenDirectory = tuple[int, str, Iterator[tuple[str, os.stat_result]]]


class _InventoryWalk:
    """One inventory walk: the rows found, whether any entry was unsafe, and the
    entry, byte and file budgets it has consumed."""

    def __init__(
        self, deadline: float, scope: SourceScopeDescriptor, with_content: bool
    ) -> None:
        self.deadline = deadline
        self.scope = scope
        self.with_content = with_content
        self.rows: set[tuple[str, str, str]] = set()
        self.unsafe = False
        self.counters = {"entries": 0, "path_bytes": 0, "input": 0, "output": 0}
        self.replay_limit = min(scope.certification_max_files, _SOURCE_PATH_BUDGET)
        self.supported_count = 0

    def walk_scope_roots(self, root_fd: int) -> None:
        """Pin every scope root under ``root_fd``, then walk each one in turn."""
        scope_roots: list[tuple[int, str]] = []
        try:
            for relative_root in self.scope.roots:
                pinned = self._open_scope_root(root_fd, relative_root)
                if pinned is not None:
                    scope_roots.append(pinned)
            while scope_roots:
                scope_fd, prefix = scope_roots.pop(0)
                self._walk_tree(scope_fd, prefix)
        finally:
            for scope_fd, _prefix in scope_roots:
                try:
                    os.close(scope_fd)
                except OSError:
                    pass

    def _open_scope_root(
        self, root_fd: int, relative_root: str
    ) -> tuple[int, str] | None:
        """Open one scope root component by component; None (unsafe) if one moved."""
        normalized = (
            relative_root.replace("\\", "/") if os.name == "nt" else relative_root
        )
        parts = [part for part in normalized.split("/") if part not in ("", ".")]
        if any(part == ".." for part in parts) or normalized.startswith("/"):
            raise OSError("source root escapes project")
        current = os.dup(root_fd)
        try:
            for part in parts:
                before = os.stat(part, dir_fd=current, follow_symlinks=False)
                child = os.open(part, _directory_open_flags(), dir_fd=current)
                child_info = os.fstat(child)
                if not opened_entry_matches(before, child_info):
                    os.close(child)
                    self.unsafe = True
                    os.close(current)
                    return None
                os.close(current)
                current = child
        except Exception:
            os.close(current)
            raise
        return current, "/".join(parts)

    def _walk_tree(self, scope_fd: int, prefix: str) -> None:
        """Depth-first walk below one pinned scope root (it owns ``scope_fd``)."""
        # Creating the generator runs none of its body; enumeration starts at next().
        entries = _enumerate_directory(scope_fd, prefix, self.deadline, self.counters)
        stack: list[_OpenDirectory] = [(scope_fd, prefix, entries)]
        try:
            while stack:
                directory_fd, relative_dir, entries = stack[-1]
                try:
                    name, info = next(entries)
                except StopIteration:
                    os.close(directory_fd)
                    stack.pop()
                    continue
                rel = f"{relative_dir}/{name}" if relative_dir else name
                if stat.S_ISDIR(info.st_mode):
                    child = self._open_subdirectory(directory_fd, name, rel, info)
                    if child is not None:
                        stack.append(child)
                    continue
                self._visit_file(directory_fd, name, rel, info)
        finally:
            for directory_fd, _relative_dir, _entries in stack:
                try:
                    os.close(directory_fd)
                except OSError:
                    pass

    def _open_subdirectory(
        self, directory_fd: int, name: str, rel: str, info: os.stat_result
    ) -> _OpenDirectory | None:
        """Pin a subdirectory to descend into; None if it is skipped or unsafe."""
        if name in EXCLUDE_DIRS or name.startswith("."):
            return None
        try:
            child_fd = os.open(name, _directory_open_flags(), dir_fd=directory_fd)
        except OSError:
            self.unsafe = True
            return None
        try:
            child_info = os.fstat(child_fd)
            if not stat.S_ISDIR(child_info.st_mode) or not opened_entry_matches(
                info, child_info
            ):
                self.unsafe = True
                os.close(child_fd)
                return None
            child_entries = _enumerate_directory(
                child_fd, rel, self.deadline, self.counters
            )
        except Exception:
            os.close(child_fd)
            raise
        return child_fd, rel, child_entries

    def _visit_file(
        self, directory_fd: int, name: str, rel: str, info: os.stat_result
    ) -> None:
        """Record one non-directory entry if it is a supported, selected source."""
        language = EXT_TO_LANG.get(os.path.splitext(name)[1].lower())
        if language is None:
            return
        if os.name == "posix" and "\\" in rel:
            self.unsafe = True
        if any(
            fnmatch.fnmatch(rel, pattern) for pattern in self.scope.effective_excludes
        ):
            return
        if not stat.S_ISREG(info.st_mode):
            self.unsafe = True
            self.rows.add((rel, _metadata_marker(info) + "|<unsafe>", language))
            return
        # Match candidate discovery: max_files is consumed only by
        # selected, supported regular files. Persisted exclusions
        # and unsafe special files never consume that budget.
        self.supported_count += 1
        if self.supported_count > self.replay_limit:
            raise OverflowError
        if not self.with_content:
            self.rows.add((rel, _metadata_marker(info), language))
            return
        marker, content_hash, clean = hash_source_or_unsafe(
            directory_fd,
            name,
            info,
            self.deadline,
            self.counters,
            _SOURCE_BYTE_BUDGET,
            _metadata_marker,
            _same_file_metadata,
        )
        if not clean:
            self.unsafe = True
        self.rows.add((rel, marker + "|" + content_hash, language))


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
    """Compare identity and mutation-sensitive metadata around one content read."""
    identity_matches = not (before.st_ino and after.st_ino) or (
        before.st_dev,
        before.st_ino,
    ) == (after.st_dev, after.st_ino)
    return identity_matches and (
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    ) == (
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
