"""Bounded read-only owner for the current full-index source scope."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .constants import EXCLUDE_DIRS
from .indexing_limits import DEFAULT_INDEX_MAX_FILES, KNOWLEDGE_INDEX_MAX_FILES
from .languages.lang_extension_map import EXT_TO_LANG

_SOURCE_DEADLINE_SECONDS = 5.0
_SOURCE_BYTE_BUDGET = 512 * 1024 * 1024
_DEFAULT_EXCLUDES = frozenset({"tests/golden/corpus_*"})
_SOURCE_DISCOVERY_POLICY = "tsa-full-index-walk"
_SOURCE_DISCOVERY_POLICY_VERSION = 2
_SOURCE_PATH_BUDGET = KNOWLEDGE_INDEX_MAX_FILES


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
        ensure_ascii=False,
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
    normalized_roots = tuple(dict.fromkeys(item.replace("\\", "/") for item in roots))
    normalized_patterns = tuple(sorted({item.replace("\\", "/") for item in patterns}))
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
    normalized = frozenset(item.replace("\\", "/") for item in effective_excludes)
    if (
        scope.roots != (".",)
        or scope.effective_excludes != normalized
        or (max_files is not None and scope.certification_max_files != max_files)
    ):
        raise ValueError("SOURCE_SCOPE_DESCRIPTOR_MISMATCH")


@dataclass(frozen=True, slots=True)
class CurrentSourceSnapshot:
    rows: tuple[tuple[str, str, str], ...]
    fingerprint: str | None
    generation: str | None
    state: Literal["exact", "unsafe", "unknown"]
    reason: str | None


def inventory_fingerprint(rows: tuple[tuple[str, str, str], ...]) -> str:
    """Return the shared owner token for path/content/language inventory."""
    digest = hashlib.sha256(b"tsa-index-source-v2\0")
    for row in sorted(rows):
        for value in row:
            raw = value.encode("utf-8", "surrogatepass")
            digest.update(len(raw).to_bytes(8, "big"))
            digest.update(raw)
    return "sha256:" + digest.hexdigest()


def recorded_source_rows(conn: object) -> tuple[tuple[str, str, str], ...]:
    """Read the cache's claimed source inventory without filesystem access."""
    return tuple(
        sorted(
            (str(row[0]).replace("\\", "/"), str(row[1]), str(row[2]))
            for row in conn.execute(  # type: ignore[attr-defined]
                "SELECT file_path, content_hash, language FROM ast_index"
            )
        )
    )


def capture_current_source_snapshot(
    project_root: str, source_scope: SourceScopeDescriptor | None = None
) -> CurrentSourceSnapshot:
    """Hash a stable, fully bounded view of the certified supported scope."""
    scope = source_scope or make_source_scope_descriptor()
    deadline = time.monotonic() + _SOURCE_DEADLINE_SECONDS
    root = os.path.realpath(os.path.abspath(project_root))
    try:
        first, unsafe = _inventory(root, deadline, scope, with_content=True)
        second, unsafe_second = _inventory(root, deadline, scope, with_content=False)
    except TimeoutError:
        return CurrentSourceSnapshot((), None, None, "unknown", "SOURCE_SCAN_DEADLINE")
    except OverflowError:
        return CurrentSourceSnapshot(
            (), None, None, "unknown", "SOURCE_SCOPE_UNBOUNDED"
        )
    except OSError:
        return CurrentSourceSnapshot(
            (), None, None, "unknown", "SOURCE_SCOPE_UNREADABLE"
        )

    metadata = {(path, language): marker for path, marker, language in second}
    stable = all(
        metadata.get((path, language)) == marker.split("|", 1)[0]
        for path, marker, language in first
    )
    first_scope = [(r[0], r[2]) for r in first]
    second_scope = [(r[0], r[2]) for r in second]
    unique_scope = len(first_scope) == len(set(first_scope)) and len(
        second_scope
    ) == len(set(second_scope))
    same_paths = set(first_scope) == set(second_scope)
    rows = tuple(
        (path, marker.split("|", 1)[1], language) for path, marker, language in first
    )
    fingerprint = inventory_fingerprint(rows)
    generation = "idxsrc-v2:" + fingerprint.removeprefix("sha256:")
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
) -> tuple[tuple[tuple[str, str, str], ...], bool]:
    scope = scope or make_source_scope_descriptor()
    rows: list[tuple[str, str, str]] = []
    unsafe = False
    byte_count = 0
    supported_count = 0
    stack: list[str] = []
    for relative_root in reversed(scope.roots):
        candidate = os.path.realpath(os.path.join(root, relative_root))
        if not Path(candidate).is_relative_to(root):
            raise OSError("source root escapes project")
        stack.append(candidate)
    while stack:
        if time.monotonic() > deadline:
            raise TimeoutError
        directory = stack.pop()
        entries = sorted(os.scandir(directory), key=lambda item: item.name)
        for entry in entries:
            if time.monotonic() > deadline:
                raise TimeoutError
            rel = os.path.relpath(entry.path, root).replace("\\", "/")
            info = entry.stat(follow_symlinks=False)
            mode = info.st_mode
            if stat.S_ISDIR(mode):
                if entry.name not in EXCLUDE_DIRS and not entry.name.startswith("."):
                    stack.append(entry.path)
                continue
            language = EXT_TO_LANG.get(Path(entry.name).suffix.lower())
            if language is None:
                continue
            supported_count += 1
            replay_limit = min(scope.certification_max_files, _SOURCE_PATH_BUDGET)
            if supported_count > replay_limit:
                raise OverflowError
            if any(fnmatch.fnmatch(rel, p) for p in scope.effective_excludes):
                continue
            if not stat.S_ISREG(mode):
                unsafe = True
                rows.append((rel, _metadata_marker(info) + "|<unsafe>", language))
                continue
            if not with_content:
                rows.append((rel, _metadata_marker(info), language))
                continue
            # Pre-stat is admission-only. Actual reads below own the budget so
            # a file that grows after stat cannot over-allocate the snapshot.
            if int(info.st_size) > _SOURCE_BYTE_BUDGET - byte_count:
                raise OverflowError
            try:
                fd = os.open(entry.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            except OSError:
                unsafe = True
                rows.append((rel, _metadata_marker(info) + "|<unsafe>", language))
                continue
            try:
                opened = os.fstat(fd)
                data = bytearray()
                while True:
                    chunk = os.read(fd, 65536)
                    if not chunk:
                        break
                    byte_count += len(chunk)
                    if byte_count > _SOURCE_BYTE_BUDGET:
                        raise OverflowError
                    data.extend(chunk)
                    if time.monotonic() > deadline:
                        raise TimeoutError
                after = os.fstat(fd)
            finally:
                os.close(fd)
            marker = _metadata_marker(after)
            if not _same_file_metadata(info, after) or not stat.S_ISREG(opened.st_mode):
                unsafe = True
            # Match ``open(..., encoding="utf-8", errors="replace")`` in the
            # indexer: TextIOWrapper performs universal-newline translation
            # before the UTF-8 text is hashed.
            content = bytes(data).decode("utf-8", "replace")
            normalized = content.replace("\r\n", "\n").replace("\r", "\n")
            rows.append(
                (
                    rel,
                    marker
                    + "|"
                    + hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
                    language,
                )
            )
    return tuple(sorted(rows)), unsafe


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
