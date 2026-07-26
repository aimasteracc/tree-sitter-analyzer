"""Immutable project-file snapshots shared by full-index phases."""

from __future__ import annotations

import fnmatch
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .indexing_limits import normalize_index_max_files

SnapshotDecision = Literal["selected", "excluded", "skipped", "error"]


@dataclass(frozen=True, slots=True)
class IndexFileFingerprint:
    """Filesystem identity captured when an index operation starts."""

    mtime_ns: int
    ctime_ns: int
    file_size: int

    @classmethod
    def from_stat(cls, stat: os.stat_result) -> IndexFileFingerprint:
        return cls(
            mtime_ns=int(stat.st_mtime_ns),
            ctime_ns=int(stat.st_ctime_ns),
            file_size=int(stat.st_size),
        )


@dataclass(frozen=True, slots=True)
class IndexSnapshotEntry:
    """One file inside the max-files selection window."""

    abs_path: str
    rel_path: str
    language: str | None
    decision: SnapshotDecision
    reason: str | None = None
    fingerprint: IndexFileFingerprint | None = None


@dataclass(frozen=True, slots=True)
class IndexCandidateSnapshot:
    """A complete, immutable view of one full-index operation's file scope."""

    project_root: str
    max_files: int
    entries: tuple[IndexSnapshotEntry, ...]
    present_paths: frozenset[str]
    discovered: int
    selected: int
    excluded: int
    skipped: int
    errors: int
    limited: int

    @property
    def selected_entries(self) -> tuple[IndexSnapshotEntry, ...]:
        return tuple(entry for entry in self.entries if entry.decision == "selected")

    @property
    def truncated_by_max_files(self) -> bool:
        return self.limited > 0

    @property
    def discovery_reconciled(self) -> bool:
        return self.discovered == (
            self.selected + self.excluded + self.skipped + self.errors + self.limited
        )

    def metrics(self) -> dict[str, int | bool]:
        """Return the stable scope counters exposed by the full-index result."""
        return {
            "discovered": self.discovered,
            "selected": self.selected,
            "excluded": self.excluded,
            "skipped": self.skipped,
            "errors": self.errors,
            "limited_by_max_files": self.limited,
            "truncated_by_max_files": self.truncated_by_max_files,
            "discovery_reconciled": self.discovery_reconciled,
        }


def validate_index_candidate_snapshot(
    project_root: str,
    max_files: int,
    snapshot: IndexCandidateSnapshot,
) -> None:
    """Reject forged or incompatible snapshots before they drive cache writes."""
    logical_root = os.path.abspath(project_root)
    if logical_root != snapshot.project_root:
        raise ValueError("candidate snapshot belongs to a different project root")
    if max_files != snapshot.max_files:
        raise ValueError("candidate snapshot uses a different max_files limit")

    resolved_root = os.path.realpath(logical_root)
    for entry in snapshot.entries:
        logical_path = os.path.abspath(entry.abs_path)
        resolved_path = os.path.realpath(logical_path)
        if not Path(resolved_path).is_relative_to(resolved_root):
            raise ValueError(f"candidate path escapes project root: {entry.abs_path}")
        expected_rel_path = os.path.relpath(logical_path, logical_root).replace("\\", "/")
        if entry.rel_path != expected_rel_path:
            raise ValueError(f"candidate relative path mismatch: {entry.rel_path}")
        if entry.decision == "selected" and entry.fingerprint is None:
            raise ValueError(
                f"selected candidate lacks metadata; lacks fingerprint: {entry.rel_path}"
            )
        if entry.decision == "selected" and entry.language is None:
            raise ValueError(
                f"selected candidate lacks metadata; lacks language: {entry.rel_path}"
            )


def build_index_candidate_snapshot(
    project_root: str,
    *,
    max_files: int,
    exclude_patterns: frozenset[str],
    walk_fn: Callable[[str], Iterable[str]],
    language_fn: Callable[[str], str | None],
    language_filter: str | None = None,
) -> IndexCandidateSnapshot:
    """Walk once and freeze file ordering, scope decisions, and fingerprints.

    The max-files window is applied before exclusions to preserve the public
    indexing contract. Files beyond the window are still counted and retained
    in ``present_paths`` so deletion detection does not mistake an unselected
    live file for a deleted one.
    """
    normalized_max = normalize_index_max_files(max_files)
    logical_root = os.path.abspath(project_root)
    resolved_root = os.path.realpath(logical_root)
    entries: list[IndexSnapshotEntry] = []
    present_paths: set[str] = set()
    resolved_paths: set[str] = set()
    discovered = selected = excluded = skipped = errors = limited = 0

    for raw_path in walk_fn(logical_root):
        abs_path = os.path.abspath(raw_path)
        resolved_path = os.path.realpath(abs_path)
        if not Path(resolved_path).is_relative_to(resolved_root):
            raise ValueError(f"candidate path escapes project root: {raw_path}")
        if resolved_path in resolved_paths:
            continue
        resolved_paths.add(resolved_path)
        rel_path = os.path.relpath(abs_path, logical_root).replace("\\", "/")
        discovered += 1
        present_paths.add(rel_path)

        if discovered > normalized_max:
            limited += 1
            continue

        if any(fnmatch.fnmatch(rel_path, pattern) for pattern in exclude_patterns):
            excluded += 1
            entries.append(
                IndexSnapshotEntry(
                    abs_path=abs_path,
                    rel_path=rel_path,
                    language=None,
                    decision="excluded",
                    reason="excluded by pattern",
                )
            )
            continue

        language = language_fn(abs_path)
        if language is None:
            skipped += 1
            entries.append(
                IndexSnapshotEntry(
                    abs_path=abs_path,
                    rel_path=rel_path,
                    language=None,
                    decision="skipped",
                    reason="unsupported language",
                )
            )
            continue
        if language_filter is not None and language != language_filter:
            skipped += 1
            entries.append(
                IndexSnapshotEntry(
                    abs_path=abs_path,
                    rel_path=rel_path,
                    language=language,
                    decision="skipped",
                    reason=f"language does not match {language_filter}",
                )
            )
            continue

        try:
            fingerprint = IndexFileFingerprint.from_stat(os.stat(abs_path))
        except OSError as exc:
            errors += 1
            entries.append(
                IndexSnapshotEntry(
                    abs_path=abs_path,
                    rel_path=rel_path,
                    language=language,
                    decision="error",
                    reason=str(exc),
                )
            )
            continue

        selected += 1
        entries.append(
            IndexSnapshotEntry(
                abs_path=abs_path,
                rel_path=rel_path,
                language=language,
                decision="selected",
                fingerprint=fingerprint,
            )
        )

    return IndexCandidateSnapshot(
        project_root=logical_root,
        max_files=normalized_max,
        entries=tuple(entries),
        present_paths=frozenset(present_paths),
        discovered=discovered,
        selected=selected,
        excluded=excluded,
        skipped=skipped,
        errors=errors,
        limited=limited,
    )


def changed_since_snapshot(entry: IndexSnapshotEntry) -> str | None:
    """Return a stable skip reason when a selected file changed or disappeared."""
    fingerprint = entry.fingerprint
    if entry.decision != "selected" or fingerprint is None:
        return None
    try:
        current = IndexFileFingerprint.from_stat(os.stat(entry.abs_path))
    except OSError:
        return "file disappeared after candidate snapshot"
    if current != fingerprint:
        return "file changed after candidate snapshot"
    return None
