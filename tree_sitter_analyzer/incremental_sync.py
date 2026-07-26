"""Incrementally reconcile source files with the persistent AST cache."""

import fnmatch
import hashlib
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from .ast_cache import _EXT_TO_LANG, _walk_source_files
from .indexing_limits import normalize_index_max_files
from .indexing_snapshot import (
    IndexCandidateSnapshot,
    changed_since_snapshot,
    validate_index_candidate_snapshot,
)

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Result of an incremental sync operation."""

    scanned: int = 0
    new_files: int = 0
    updated_files: int = 0
    deleted_files: int = 0
    unchanged_files: int = 0
    errors: int = 0
    processed: int = 0
    changed_during_run: int = 0
    changed_during_run_files: list[str] = field(default_factory=list)
    truncated_by_max_files: bool = False
    synapse_resolved: int = 0
    details: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode_used": "incremental",
            "scanned": self.scanned,
            "new_files": self.new_files,
            "updated_files": self.updated_files,
            "deleted_files": self.deleted_files,
            "unchanged_files": self.unchanged_files,
            "errors": self.errors,
            "processed": self.processed,
            "changed_during_run": self.changed_during_run,
            "changed_during_run_files": self.changed_during_run_files,
            "truncated_by_max_files": self.truncated_by_max_files,
            "synapse_resolved": self.synapse_resolved,
            "details": self.details,
        }


def _file_content_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class IncrementalSync:
    """Reconcile new, modified, deleted, and unchanged source files."""

    def __init__(self, cache: Any) -> None:
        self._cache = cache

    def sync(
        self,
        max_files: int = 20_000,
        callback: Any | None = None,
        *,
        exclude_patterns: frozenset[str] | None = None,
        candidate_snapshot: IndexCandidateSnapshot | None = None,
    ) -> SyncResult:
        """Sync the on-disk source tree with the AST cache."""
        max_files = normalize_index_max_files(max_files)
        result = SyncResult()
        conn = self._cache.get_conn()
        indexed_rows = self._load_indexed_rows(conn)
        disk_files, present_paths, truncated, changed_files = self._scan_disk_files(
            max_files,
            exclude_patterns,
            candidate_snapshot,
        )
        result.scanned = len(disk_files)
        result.processed = len(disk_files)
        result.changed_during_run = len(changed_files)
        result.changed_during_run_files = sorted(path for path, _ in changed_files)
        result.truncated_by_max_files = truncated
        if candidate_snapshot is not None and candidate_snapshot.errors:
            from .cache.callgraph_state import clear_call_graph_built_strict

            clear_call_graph_built_strict(conn)
        for rel_path, reason in sorted(changed_files):
            self._cache.invalidate(os.path.join(self._cache.project_root, rel_path))
            detail = {
                "file": rel_path,
                "considered": "skipped",
                "action": "skipped",
                "status": "skipped",
                "reason": reason,
            }
            result.details.append(detail)
            if callback:
                callback(detail)

        # Never infer deletions from a capped prefix of the live source set.
        if not truncated or candidate_snapshot is not None:
            deleted_paths = set(indexed_rows) - present_paths
            self._invalidate_deleted_files(deleted_paths, result, callback)
        previous_defer = getattr(self._cache, "_defer_single_file_backfill", False)
        self._cache._defer_single_file_backfill = True
        try:
            action_by_file = self._index_or_reindex_files(
                disk_files,
                indexed_rows,
                conn,
                result,
                callback,
                preserve_order=candidate_snapshot is not None,
            )
        finally:
            self._cache._defer_single_file_backfill = previous_defer

        def invalidate_snapshot_changes() -> None:
            if candidate_snapshot is None:
                return
            known_changed = set(result.changed_during_run_files)
            late_changes = [
                (entry.rel_path, reason)
                for entry in candidate_snapshot.selected_entries
                if entry.rel_path not in known_changed
                and (reason := changed_since_snapshot(entry)) is not None
            ]
            for rel_path, reason in sorted(late_changes):
                self._cache.invalidate(os.path.join(self._cache.project_root, rel_path))
                for index in range(len(result.details) - 1, -1, -1):
                    prior = result.details[index]
                    if prior.get("file") != rel_path:
                        continue
                    if prior.get("status") == "error":
                        result.errors -= 1
                    del result.details[index]
                    break
                counter_name = {
                    "new": "new_files",
                    "updated": "updated_files",
                    "unchanged": "unchanged_files",
                }[action_by_file[rel_path]]
                setattr(result, counter_name, getattr(result, counter_name) - 1)
                detail = {
                    "file": rel_path,
                    "considered": "skipped",
                    "action": "skipped",
                    "status": "skipped",
                    "reason": reason,
                }
                result.details.append(detail)
                if callback:
                    callback(detail)
            result.changed_during_run_files = sorted(
                known_changed | {path for path, _reason in late_changes}
            )
            result.changed_during_run = len(result.changed_during_run_files)
            result.processed = max(
                0,
                candidate_snapshot.selected - result.changed_during_run,
            )

        invalidate_snapshot_changes()
        try:
            conn.commit()
        except Exception as exc:  # pragma: no cover - DB commit failure is rare
            logger.error("Final DB commit failed after partial sync: %s", exc)
            result.errors += 1

        backfill_complete = self._cache.call_graph_built()
        if result.new_files or result.updated_files or result.deleted_files:
            try:
                stats = self._cache._run_synapse_backfill()
                if stats is None:
                    backfill_complete = False
                else:
                    result.synapse_resolved = int(stats.get("resolved", 0))
                    backfill_complete = int(stats.get("errors", 0)) == 0
            except Exception:  # pragma: no cover - backfill is best-effort
                backfill_complete = False
            try:
                stats = self._cache._run_unresolved_refs_backfill()
                clean = stats is not None and not int(stats.get("errors", 0))
                backfill_complete = bool(backfill_complete and clean)
            except Exception:  # pragma: no cover - backfill is best-effort
                backfill_complete = False

        invalidate_snapshot_changes()
        indexed_paths = {
            str(row["file_path"])
            for row in conn.execute("SELECT file_path FROM ast_index").fetchall()
        }
        snapshot_scope_complete = bool(
            disk_files if candidate_snapshot is None else candidate_snapshot.selected
        ) and (candidate_snapshot is None or candidate_snapshot.errors == 0)
        if (
            not result.truncated_by_max_files
            and result.errors == 0
            and result.changed_during_run == 0
            and backfill_complete
            and snapshot_scope_complete
            and indexed_paths == present_paths
        ):
            from .cache.callgraph_state import mark_call_graph_built

            mark_call_graph_built(conn)

        return result

    @staticmethod
    def _load_indexed_rows(conn: Any) -> dict[str, dict[str, Any]]:
        """Snapshot the ``ast_index`` table as ``{path: {hash, mtime, size}}``."""
        return {
            row["file_path"]: {
                "content_hash": row["content_hash"],
                "mtime_ns": row["mtime_ns"],
                "file_size": row["file_size"],
            }
            for row in conn.execute(
                "SELECT file_path, content_hash, mtime_ns, file_size FROM ast_index"
            ).fetchall()
        }

    def _scan_disk_files(
        self,
        max_files: int,
        exclude_patterns: frozenset[str] | None = None,
        candidate_snapshot: IndexCandidateSnapshot | None = None,
    ) -> tuple[dict[str, dict[str, Any]], set[str], bool, list[tuple[str, str]]]:
        """Return eligible files, all present paths, and truncation state."""
        max_files = normalize_index_max_files(max_files)
        disk_files: dict[str, dict[str, Any]] = {}
        present_paths: set[str] = set()

        if candidate_snapshot is not None:
            validate_index_candidate_snapshot(
                self._cache.project_root, max_files, candidate_snapshot
            )
            changed_files: list[tuple[str, str]] = []
            for entry in candidate_snapshot.selected_entries:
                change_reason = changed_since_snapshot(entry)
                if change_reason is not None:
                    changed_files.append((entry.rel_path, change_reason))
                    continue
                fingerprint = entry.fingerprint
                assert fingerprint is not None
                disk_files[entry.rel_path] = {
                    "abs_path": entry.abs_path,
                    "mtime_ns": fingerprint.mtime_ns,
                    "file_size": fingerprint.file_size,
                }
            return (
                disk_files,
                set(candidate_snapshot.present_paths),
                candidate_snapshot.truncated_by_max_files,
                changed_files,
            )

        count = 0
        for abs_path in _walk_source_files(self._cache.project_root):
            if count >= max_files:
                return disk_files, present_paths, True, []
            count += 1
            rel = os.path.relpath(abs_path, self._cache.project_root).replace("\\", "/")
            present_paths.add(rel)
            if exclude_patterns and any(
                fnmatch.fnmatch(rel, pattern) for pattern in exclude_patterns
            ):
                continue
            try:
                stat = os.stat(abs_path)
                disk_files[rel] = {
                    "abs_path": abs_path,
                    "mtime_ns": int(stat.st_mtime_ns),
                    "file_size": stat.st_size,
                }
            except OSError:
                continue
        return disk_files, present_paths, False, []

    def _invalidate_deleted_files(
        self,
        deleted_paths: set[str],
        result: SyncResult,
        callback: Any | None,
    ) -> None:
        """Drop supported-language cache rows for files absent from disk."""
        for rel in deleted_paths:
            ext = os.path.splitext(rel)[1].lower()
            if ext not in _EXT_TO_LANG:
                continue
            abs_del = os.path.join(self._cache.project_root, rel)
            self._cache.invalidate(abs_del)
            result.deleted_files += 1
            detail = {"file": rel, "considered": "deleted", "action": "deleted"}
            result.details.append(detail)
            if callback:
                callback(detail)

    def _index_or_reindex_files(
        self,
        disk_files: dict[str, dict[str, Any]],
        indexed_rows: dict[str, dict[str, Any]],
        conn: Any,
        result: SyncResult,
        callback: Any | None,
        *,
        preserve_order: bool = False,
    ) -> dict[str, str]:
        """For each disk file: index if new, re-index if changed, skip otherwise."""
        action_by_file: dict[str, str] = {}
        items = disk_files.items() if preserve_order else sorted(disk_files.items())
        for rel, info in items:
            indexed_info = indexed_rows.get(rel)
            if indexed_info is None:
                detail = self._index_new_file(rel, info["abs_path"], conn)
                result.new_files += 1
                action_by_file[rel] = "new"
            elif self._file_changed(info, indexed_info, rel):
                detail = self._reindex_modified(rel, info["abs_path"], conn)
                result.updated_files += 1
                action_by_file[rel] = "updated"
            else:
                result.unchanged_files += 1
                action_by_file[rel] = "unchanged"
                continue
            if detail.get("status") == "error":
                result.errors += 1
            result.details.append(detail)
            if callback:
                callback(detail)
        return action_by_file

    def _file_changed(
        self,
        disk_info: dict[str, Any],
        indexed_info: dict[str, Any],
        rel_path: str,
    ) -> bool:
        if disk_info["file_size"] != indexed_info["file_size"]:
            return True
        if disk_info["mtime_ns"] != indexed_info["mtime_ns"]:
            try:
                current_hash = _file_content_hash(disk_info["abs_path"])
                return current_hash != indexed_info["content_hash"]
            except OSError:
                return True
        return False

    def _index_new_file(
        self,
        rel_path: str,
        abs_path: str,
        conn: sqlite3.Connection,
    ) -> dict[str, Any]:
        # Keep attempted action separate from the cache layer's actual status.
        try:
            index_result = self._cache.index_file(abs_path)
        except Exception as exc:
            # #886: if index_file wrote partial rows before raising, clean them
            # all up (ast_index + ast_symbol_rows + ast_symbols_fts) so the next
            # sync treats the file as new rather than silently "unchanged" with
            # missing symbols. Codex P2: wrap best-effort cleanup so a locked/
            # full DB doesn't abort the whole sync — we already have the error.
            try:
                conn.execute("DELETE FROM ast_index WHERE file_path = ?", (rel_path,))
                conn.execute(
                    "DELETE FROM ast_symbol_rows WHERE file_path = ?", (rel_path,)
                )
                conn.execute(
                    "DELETE FROM ast_symbols_fts WHERE file_path = ?", (rel_path,)
                )
            except Exception:
                logger.debug("Cleanup DELETE failed for %s — continuing", rel_path)
            # Issue #806/#805: catch all per-file errors so one pathological
            # file cannot abort the whole sync and discard accumulated results.
            logger.error(
                "Error indexing %s (%s): %s",
                rel_path,
                type(exc).__name__,
                exc,
            )
            return {
                "file": rel_path,
                "considered": "indexed",
                "action": "indexed",
                "status": "error",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
        status = index_result.get("status", "unknown")
        detail = {
            "file": rel_path,
            "considered": "indexed",
            "action": "indexed",
            "status": status,
        }
        if status == "error" and "reason" in index_result:
            detail["reason"] = index_result["reason"]
        return detail

    def _reindex_modified(
        self,
        rel_path: str,
        abs_path: str,
        conn: sqlite3.Connection,
    ) -> dict[str, Any]:
        self._cache.invalidate(abs_path)
        try:
            index_result = self._cache.index_file(abs_path)
        except Exception as exc:
            # #886: same three-table cleanup as _index_new_file (Codex P2 parity).
            try:
                conn.execute("DELETE FROM ast_index WHERE file_path = ?", (rel_path,))
                conn.execute(
                    "DELETE FROM ast_symbol_rows WHERE file_path = ?", (rel_path,)
                )
                conn.execute(
                    "DELETE FROM ast_symbols_fts WHERE file_path = ?", (rel_path,)
                )
            except Exception:
                logger.debug("Cleanup DELETE failed for %s — continuing", rel_path)
            # Issue #806/#805: same broad guard for re-index path.
            logger.error(
                "Error re-indexing %s (%s): %s",
                rel_path,
                type(exc).__name__,
                exc,
            )
            return {
                "file": rel_path,
                "considered": "updated",
                "action": "updated",
                "status": "error",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
        status = index_result.get("status", "unknown")
        detail = {
            "file": rel_path,
            "considered": "updated",
            "action": "updated",
            "status": status,
        }
        if status == "error" and "reason" in index_result:
            detail["reason"] = index_result["reason"]
        return detail

    def get_changes(self) -> dict[str, list[str]]:
        """
        Quick scan that returns lists of changed file paths without re-indexing.

        Returns dict with keys: 'new', 'modified', 'deleted' — each a list of
        relative file paths.
        """
        conn = self._cache.get_conn()
        indexed_rows = {
            row["file_path"]: {
                "content_hash": row["content_hash"],
                "mtime_ns": row["mtime_ns"],
                "file_size": row["file_size"],
            }
            for row in conn.execute(
                "SELECT file_path, content_hash, mtime_ns, file_size FROM ast_index"
            ).fetchall()
        }

        disk_files: dict[str, dict[str, Any]] = {}
        for abs_path in _walk_source_files(self._cache.project_root):
            rel = os.path.relpath(abs_path, self._cache.project_root).replace("\\", "/")
            try:
                stat = os.stat(abs_path)
                disk_files[rel] = {
                    "abs_path": abs_path,
                    "mtime_ns": int(stat.st_mtime_ns),
                    "file_size": stat.st_size,
                }
            except OSError:
                continue

        indexed_set = set(indexed_rows.keys())
        disk_set = set(disk_files.keys())

        changes: dict[str, list[str]] = {
            "new": sorted(disk_set - indexed_set),
            "deleted": sorted(indexed_set - disk_set),
            "modified": [],
        }

        for rel in sorted(indexed_set & disk_set):
            if self._file_changed(disk_files[rel], indexed_rows[rel], rel):
                changes["modified"].append(rel)

        return changes
