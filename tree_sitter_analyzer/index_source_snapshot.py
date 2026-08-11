"""Bounded read-only owner for the current full-index source scope."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import stat
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any, Literal

from .constants import EXCLUDE_DIRS
from .index_source_stream import hash_source_at
from .indexing_limits import DEFAULT_INDEX_MAX_FILES, KNOWLEDGE_INDEX_MAX_FILES
from .languages.lang_extension_map import EXT_TO_LANG

_SOURCE_DEADLINE_SECONDS = 5.0
_SOURCE_BYTE_BUDGET = 512 * 1024 * 1024
_DEFAULT_EXCLUDES = frozenset({"tests/golden/corpus_*"})
_SOURCE_DISCOVERY_POLICY = "tsa-full-index-walk"
_SOURCE_DISCOVERY_POLICY_VERSION = 2
_SOURCE_PATH_BUDGET = KNOWLEDGE_INDEX_MAX_FILES
# Enumeration budgets cover every directory entry, including unsupported and
# excluded names; traversal and hashing never require a global ordering copy.
_SOURCE_ENTRY_BUDGET = 1_000_000
_SOURCE_ENTRY_PATH_BYTE_BUDGET = 128 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class SourceScopeDescriptor:
    """Canonical, replayable source-selection policy certified by a build."""

    roots: tuple[str, ...]
    no_default_excludes: bool
    exclude_patterns: tuple[str, ...]
    certification_max_files: int
    discovery_policy: str = _SOURCE_DISCOVERY_POLICY
    discovery_policy_version: int = _SOURCE_DISCOVERY_POLICY_VERSION

    @property
    def effective_excludes(self) -> frozenset[str]:
        extras = frozenset(self.exclude_patterns)
        return extras if self.no_default_excludes else _DEFAULT_EXCLUDES | extras


def make_source_scope_descriptor(
    *,
    roots: tuple[str, ...] = (".",),
    no_default_excludes: bool = False,
    exclude_patterns: tuple[str, ...] = (),
    certification_max_files: int = DEFAULT_INDEX_MAX_FILES,
) -> SourceScopeDescriptor:
    """Build a normalized full-index scope descriptor."""
    descriptor = SourceScopeDescriptor(
        tuple(roots),
        no_default_excludes,
        tuple(sorted(set(exclude_patterns))),
        certification_max_files,
    )
    return parse_source_scope_descriptor(canonical_source_scope_descriptor(descriptor))


def canonical_source_scope_descriptor(scope: SourceScopeDescriptor) -> str:
    """Serialize a scope with stable keys, values, and separators."""
    return json.dumps(
        {
            "certification_max_files": scope.certification_max_files,
            "discovery_policy": scope.discovery_policy,
            "discovery_policy_version": scope.discovery_policy_version,
            "exclude_patterns": list(scope.exclude_patterns),
            "no_default_excludes": scope.no_default_excludes,
            "roots": list(scope.roots),
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def parse_source_scope_descriptor(raw: str) -> SourceScopeDescriptor:
    """Validate a persisted descriptor strictly enough for safe replay."""
    try:
        value: Any = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("SOURCE_SCOPE_DESCRIPTOR_INVALID") from exc
    expected = {
        "certification_max_files",
        "discovery_policy",
        "discovery_policy_version",
        "exclude_patterns",
        "no_default_excludes",
        "roots",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("SOURCE_SCOPE_DESCRIPTOR_INVALID")
    roots = value["roots"]
    patterns = value["exclude_patterns"]
    if (
        value["discovery_policy"] != _SOURCE_DISCOVERY_POLICY
        or not isinstance(value["certification_max_files"], int)
        or isinstance(value["certification_max_files"], bool)
        or value["certification_max_files"] <= 0
        or value["discovery_policy_version"] != _SOURCE_DISCOVERY_POLICY_VERSION
        or not isinstance(value["no_default_excludes"], bool)
        or not isinstance(roots, list)
        or not roots
        or not isinstance(patterns, list)
        or any(not isinstance(item, str) for item in roots + patterns)
    ):
        raise ValueError("SOURCE_SCOPE_DESCRIPTOR_INVALID")
    normalize = (
        (lambda item: item.replace("\\", "/"))
        if os.name == "nt"
        else (lambda item: item)
    )
    normalized_roots = tuple(dict.fromkeys(normalize(item) for item in roots))
    normalized_patterns = tuple(sorted({normalize(item) for item in patterns}))
    if any(
        not item
        or os.path.isabs(item)
        or item == ".."
        or item.startswith("../")
        or "/../" in item
        for item in normalized_roots
    ):
        raise ValueError("SOURCE_SCOPE_DESCRIPTOR_INVALID")
    descriptor = SourceScopeDescriptor(
        normalized_roots,
        value["no_default_excludes"],
        normalized_patterns,
        value["certification_max_files"],
    )
    if raw != canonical_source_scope_descriptor(descriptor):
        raise ValueError("SOURCE_SCOPE_DESCRIPTOR_INVALID")
    return descriptor


def validate_full_index_source_scope(
    scope: SourceScopeDescriptor,
    effective_excludes: frozenset[str],
    max_files: int | None = None,
) -> None:
    """Reject descriptors that do not describe the walk being executed."""
    normalized = frozenset(
        item.replace("\\", "/") if os.name == "nt" else item
        for item in effective_excludes
    )
    if (
        scope.roots != (".",)
        or scope.effective_excludes != normalized
        or (max_files is not None and scope.certification_max_files != max_files)
    ):
        raise ValueError("SOURCE_SCOPE_DESCRIPTOR_MISMATCH")


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
    values: set[tuple[str, str, str]] = set()
    paths: set[str] = set()
    for row in conn.execute(  # type: ignore[attr-defined]
        "SELECT file_path, content_hash, language FROM ast_index"
    ):
        if deadline is not None and time.monotonic() > deadline:
            raise TimeoutError
        raw_path = str(row[0])
        path = raw_path.replace("\\", "/") if os.name == "nt" else raw_path
        if path in paths:
            raise ValueError("SOURCE_INVENTORY_DUPLICATE_PATH")
        paths.add(path)
        values.add((path, str(row[1]), str(row[2])))
    return frozenset(values)


def capture_current_source_snapshot(
    project_root: str, source_scope: SourceScopeDescriptor | None = None
) -> CurrentSourceSnapshot:
    """Hash a stable, fully bounded view of the certified supported scope."""
    scope = source_scope or make_source_scope_descriptor()
    if os.name != "posix" or not os.path.exists("/dev/fd"):
        return CurrentSourceSnapshot(
            frozenset(), None, None, "unsafe", "SOURCE_SCOPE_UNSUPPORTED"
        )
    deadline = time.monotonic() + _SOURCE_DEADLINE_SECONDS
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
    root_fd = os.open(root, directory_flags)
    try:
        root_info = os.fstat(root_fd)
        if not stat.S_ISDIR(root_info.st_mode):
            raise OSError("source root is not a directory")
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
                    for part in parts:
                        child = os.open(part, directory_flags, dir_fd=current)
                        os.close(current)
                        current = child
                    scope_roots.append((current, "/".join(parts)))
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
                                if not stat.S_ISDIR(child_info.st_mode):
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
                        supported_count += 1
                        if supported_count > replay_limit:
                            raise OverflowError
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
