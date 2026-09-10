"""Frozen candidate revalidation helpers for project indexing."""

from __future__ import annotations

import logging
import sqlite3
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    pass

from ..indexing_snapshot import (
    IndexCandidateSnapshot,
    IndexFileFingerprint,
    IndexSnapshotEntry,
    changed_since_snapshot,
)
from .indexer import _invalidate_ladybug, _normalize_relative_path

logger = logging.getLogger(__name__)


def _snapshot_result_change_reason(
    result: dict[str, Any],
    entries: dict[str, IndexSnapshotEntry],
) -> tuple[str, str | None]:
    rel_path = _normalize_relative_path(str(result["rel_path"]))
    entry = entries[rel_path]
    if result.get("status") == "source_changed":
        return rel_path, "file changed after candidate snapshot"
    fingerprint = cast(IndexFileFingerprint, entry.fingerprint)
    worker_fingerprint = (
        int(result.get("mtime_ns", fingerprint.mtime_ns)),
        int(result.get("file_size", fingerprint.file_size)),
    )
    expected_fingerprint = (fingerprint.mtime_ns, fingerprint.file_size)
    return rel_path, (
        "file changed after candidate snapshot"
        if worker_fingerprint != expected_fingerprint
        else None
        if entry.frozen_path is not None
        else changed_since_snapshot(entry)
    )


def _record_snapshot_change(
    stats: dict[str, Any], rel_path: str, change_reason: str
) -> None:
    """Replace one processed result with a deterministic snapshot skip."""
    stats["skipped"] += 1
    stats["incomplete_skips"] = stats.get("incomplete_skips", 0) + 1
    stats["processed"] = max(0, int(stats["processed"]) - 1)
    stats["changed_during_run"] += 1
    stats["changed_during_run_files"].append(rel_path)
    stats["files"].append(
        {"file": rel_path, "status": "skipped", "reason": change_reason}
    )


def _discard_snapshot_generation(
    cache: Any,
    conn: sqlite3.Connection,
    rel_path: str,
    *,
    root_fd: int | None = None,
) -> None:
    """Remove canonical rows and invalidate their derived graph projection."""
    from . import write as _write

    _write.discard_file_rows(conn, rel_path, cache.fts5_available)
    try:
        _invalidate_ladybug(cache, root_fd)
    except Exception:
        logger.debug("could not invalidate Ladybug mirror", exc_info=True)


def _discard_with_root_lease(
    cache: Any,
    conn: sqlite3.Connection,
    rel_path: str,
    root_fd: int | None,
) -> None:
    """Preserve the legacy call seam when no pinned lease is active."""
    if root_fd is None:
        _discard_snapshot_generation(cache, conn, rel_path)
    else:
        _discard_snapshot_generation(cache, conn, rel_path, root_fd=root_fd)


def _snapshot_result_is_stable(
    result: dict[str, Any],
    entries: dict[str, IndexSnapshotEntry],
    stats: dict[str, Any],
    *,
    cache: Any,
    conn: sqlite3.Connection,
    root_fd: int | None = None,
) -> bool:
    """Validate one worker result immediately before its database write."""
    rel_path, change_reason = _snapshot_result_change_reason(result, entries)
    if change_reason is None:
        return True

    _discard_with_root_lease(cache, conn, rel_path, root_fd)
    _record_snapshot_change(stats, rel_path, change_reason)
    return False


def _revalidate_snapshot_batch(
    pending_results: list[dict[str, Any]],
    *,
    cache: Any,
    conn: sqlite3.Connection,
    entries: dict[str, IndexSnapshotEntry],
    stats: dict[str, Any],
    root_fd: int | None = None,
) -> None:
    """Discard pending generations that changed before their batch commit."""
    for result in pending_results:
        rel_path, change_reason = _snapshot_result_change_reason(result, entries)
        if change_reason is None:
            continue
        _discard_with_root_lease(cache, conn, rel_path, root_fd)
        if result["status"] in ("io_error", "parse_failed"):
            stats["errors"] -= 1
        else:
            stats["indexed"] -= 1
        for index in range(len(stats["files"]) - 1, -1, -1):
            if stats["files"][index]["file"] == rel_path:
                del stats["files"][index]
                break
        _record_snapshot_change(stats, rel_path, change_reason)


def _revalidate_committed_snapshot(
    *,
    cache: Any,
    conn: sqlite3.Connection,
    entries: dict[str, IndexSnapshotEntry],
    stats: dict[str, Any],
    root_fd: int | None = None,
) -> None:
    """Invalidate any earlier committed generation changed before backfill."""
    known_changed = set(stats["changed_during_run_files"])
    for rel_path, entry in entries.items():
        change_reason = (
            None if rel_path in known_changed else changed_since_snapshot(entry)
        )
        if change_reason is None:
            continue
        _discard_with_root_lease(cache, conn, rel_path, root_fd)
        detail_files = [detail["file"] for detail in stats["files"]]
        detail_index = detail_files.index(rel_path)
        detail = stats["files"].pop(detail_index)
        counter = {
            "error": "errors",
            "indexed": "indexed",
            "cached": "cached",
        }[detail["status"]]
        stats[counter] -= 1
        _record_snapshot_change(stats, rel_path, change_reason)


def _record_frozen_replay_mismatches(
    entries: dict[str, IndexSnapshotEntry], stats: dict[str, Any]
) -> None:
    """Report live divergence without deleting the complete frozen epoch."""
    changed = [
        (rel_path, reason)
        for rel_path, entry in entries.items()
        if (reason := changed_since_snapshot(entry)) is not None
    ]
    if not changed:
        return
    known = set(stats.get("changed_during_run_files", []))
    known.update(rel_path for rel_path, _reason in changed)
    stats["changed_during_run_files"] = sorted(known)
    stats["changed_during_run"] = len(known)
    stats["live_source_replay_mismatch"] = True
    stats["manifest_warning"] = "INDEX_CANDIDATE_SNAPSHOT_CHANGED"
    for rel_path, reason in changed:
        stats["files"].append({"file": rel_path, "status": "warning", "reason": reason})


def _unsafe_force_snapshot_result(
    candidate_snapshot: IndexCandidateSnapshot | None,
    activation_enabled: bool,
    *,
    changed: list[tuple[IndexSnapshotEntry, str]] | None = None,
) -> dict[str, Any]:
    """Return a terminal force result before any persistent state is touched."""
    changed = changed or []
    discovery_details = (
        [
            {
                "file": entry.rel_path,
                "status": "error",
                "reason": entry.reason or "candidate discovery failed",
            }
            for entry in candidate_snapshot.entries
            if entry.decision == "error"
        ]
        if candidate_snapshot is not None
        else []
    )
    frozen_reason = (
        candidate_snapshot.frozen_error
        or (
            "INDEX_CANDIDATE_FROZEN_EVIDENCE_MISSING"
            if candidate_snapshot.frozen_root is None
            else None
        )
        if candidate_snapshot is not None
        else "INDEX_CANDIDATE_FROZEN_EVIDENCE_MISSING"
    )
    if frozen_reason and not changed:
        discovery_details.append(
            {"file": "", "status": "error", "reason": frozen_reason}
        )
    changed_details = [
        {"file": entry.rel_path, "status": "error", "reason": reason}
        for entry, reason in changed
    ]
    errors = max(
        1,
        (candidate_snapshot.errors if candidate_snapshot is not None else 0)
        + len(changed_details),
    )
    return {
        "mode_used": "full",
        "verdict": "WARN",
        "abort_remaining_phases": True,
        "indexed": 0,
        "cached": 0,
        "errors": errors,
        "skipped": candidate_snapshot.skipped if candidate_snapshot is not None else 0,
        "incomplete_skips": (
            candidate_snapshot.skipped if candidate_snapshot is not None else 0
        )
        + len(changed_details),
        "processed": 0,
        "changed_during_run": len(changed_details),
        "changed_during_run_files": [detail["file"] for detail in changed_details],
        "files": discovery_details + changed_details,
        "activation_enabled": activation_enabled,
        "truncated_by_max_files": bool(
            candidate_snapshot and candidate_snapshot.truncated_by_max_files
        ),
        "snapshot_metrics": candidate_snapshot.metrics() if candidate_snapshot else {},
        "manifest_warning": (
            "INDEX_CANDIDATE_SNAPSHOT_CHANGED"
            if changed_details
            else "INDEX_CANDIDATE_SNAPSHOT_INCOMPLETE"
        ),
    }
