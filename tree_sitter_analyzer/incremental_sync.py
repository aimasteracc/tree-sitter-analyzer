"""Incrementally reconcile source files with the persistent AST cache."""

import fnmatch
import logging
import os
import sqlite3
import time
from typing import Any

from .ast_cache import _EXT_TO_LANG, _walk_source_files
from .incremental_sync_support import SyncResult, file_changed, get_changes
from .index_source_snapshot import (
    SourceScopeDescriptor,
    make_source_scope_descriptor,
    validate_full_index_source_scope,
)
from .indexing_limits import normalize_index_max_files
from .indexing_snapshot import (
    IndexCandidateSnapshot,
    changed_since_snapshot,
    validate_index_candidate_snapshot,
)

logger = logging.getLogger(__name__)
_DISAPPEARED_REASON = "file disappeared after candidate snapshot"


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
        source_scope: SourceScopeDescriptor | None = None,
        certify_manifest: bool = True,
    ) -> SyncResult:
        """Sync the on-disk source tree with the AST cache."""
        max_files = normalize_index_max_files(max_files)
        if source_scope is None:
            source_scope = make_source_scope_descriptor(
                no_default_excludes=True,
                exclude_patterns=tuple(sorted(exclude_patterns or ())),
                certification_max_files=max_files,
            )
        validate_full_index_source_scope(
            source_scope, exclude_patterns or frozenset(), max_files
        )
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
        disappeared_paths = {
            path for path, reason in changed_files if reason == _DISAPPEARED_REASON
        }
        for rel_path, reason in sorted(changed_files):
            self._cache.invalidate(os.path.join(self._cache.project_root, rel_path))
            if reason == _DISAPPEARED_REASON:
                continue
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

        # Never infer deletions from a capped prefix. For an exact candidate,
        # excluded/unsupported paths are intentionally outside the selected DB
        # scope and must be pruned before any certification can proceed.
        if (
            candidate_snapshot is not None
            and not truncated
            and not candidate_snapshot.errors
        ):
            selected_paths = {
                entry.rel_path for entry in candidate_snapshot.selected_entries
            }
            # ``indexed_rows`` is the pre-invalidation DB snapshot. Unioning
            # disappeared selected paths preserves deletion accounting even
            # though invalidate() above may already have removed their rows.
            deleted_paths = (set(indexed_rows) - selected_paths) | disappeared_paths
            self._invalidate_deleted_files(deleted_paths, result, callback)
        elif candidate_snapshot is None and not truncated:
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

        # Phase B-3: Set certified_at for successfully processed files.
        # Files that were indexed (new/updated/unchanged) receive a Unix epoch
        # timestamp.  Error files retain NULL (or get it reset in the clear paths
        # below).  This enables per-file partial certification tracking.
        _certified_at_epoch = int(time.time())
        _certified_paths = [
            p
            for p, a in action_by_file.items()
            if a in ("new", "updated", "unchanged")
        ]
        if _certified_paths:
            _placeholders = ",".join("?" * len(_certified_paths))
            try:
                conn.execute(
                    f"UPDATE ast_index SET certified_at = ?"
                    f" WHERE file_path IN ({_placeholders})",
                    [_certified_at_epoch, *_certified_paths],
                )
            except Exception:
                # certified_at column may not exist yet (pre-v14 DB).
                # Ignore silently; the column is added by apply_migration_v14.
                pass

        frozen_epoch = bool(
            candidate_snapshot is not None
            and all(
                entry.frozen_path is not None
                for entry in candidate_snapshot.selected_entries
            )
        )

        def invalidate_snapshot_changes() -> set[str]:
            if candidate_snapshot is None:
                return set()
            known_changed = set(result.changed_during_run_files)
            late_changes = [
                (entry.rel_path, reason)
                for entry in candidate_snapshot.selected_entries
                if entry.rel_path not in known_changed
                and (reason := changed_since_snapshot(entry)) is not None
            ]
            if frozen_epoch:
                known_changed.update(path for path, _reason in late_changes)
                result.changed_during_run_files = sorted(known_changed)
                result.changed_during_run = len(result.changed_during_run_files)
                result.processed = max(0, candidate_snapshot.selected)
                for rel_path, reason in sorted(late_changes):
                    result.details.append(
                        {"file": rel_path, "status": "warning", "reason": reason}
                    )
                return set()
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
                action = action_by_file.get(rel_path)
                if action is None:
                    # rel_path は action_by_file に存在しない (例: changed_files で
                    # スキップ済みのパス)。カウンタ操作なしで次へ進む。
                    continue
                counter_name = {
                    "new": "new_files",
                    "updated": "updated_files",
                    "unchanged": "unchanged_files",
                }[action]
                setattr(result, counter_name, getattr(result, counter_name) - 1)
                if reason == _DISAPPEARED_REASON:
                    disappeared_paths.add(rel_path)
                    self._invalidate_deleted_files({rel_path}, result, callback)
                else:
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
            return {path for path, _reason in late_changes}

        if not frozen_epoch:
            invalidate_snapshot_changes()
        result.scope_complete = bool(
            not result.truncated_by_max_files
            and result.changed_during_run == 0
            and (candidate_snapshot is None or candidate_snapshot.errors == 0)
        )
        if not result.scope_complete:
            # Incomplete enumeration invalidates global certification even when
            # the selected prefix is unchanged.  Clear it before consulting the
            # call-graph marker so a certified SQL fast path cannot survive.
            # Phase B-3 (Path 1): Reset certified_at for error files only.
            # PASS files retain their certified_at (partial certification model).
            _error_paths_1 = [
                d["file"]
                for d in result.details
                if d.get("status") == "error" and d.get("file")
            ]
            if _error_paths_1:
                _ph1 = ",".join("?" * len(_error_paths_1))
                try:
                    conn.execute(
                        f"UPDATE ast_index SET certified_at = NULL"
                        f" WHERE file_path IN ({_ph1})",
                        _error_paths_1,
                    )
                except Exception:
                    pass  # pre-v14 DB: column not yet added
            from .cache.callgraph_state import clear_call_graph_built_strict

            clear_call_graph_built_strict(conn)
            conn.execute("DELETE FROM ast_index_snapshot_manifest")
        try:
            conn.commit()
        except Exception as exc:  # pragma: no cover - DB commit failure is rare
            logger.error("Final DB commit failed after partial sync: %s", exc)
            result.errors += 1

        marker_current = self._cache.call_graph_built()
        from .incremental_sync_callgraph import (
            pipeline_repair_required,
            run_call_graph_pipeline,
        )

        backfill_complete = marker_current
        if pipeline_repair_required(result, marker_current):
            backfill_complete, result.synapse_resolved = run_call_graph_pipeline(
                self._cache, result
            )

        if changed_paths := invalidate_snapshot_changes():
            # The pipeline ran against a generation that no longer exists.  A
            # later retry sees this explicit incomplete marker and repairs all
            # three stages; this run must never certify its pre-race results.
            from .cache.callgraph_state import clear_call_graph_built_strict

            backfill_complete = False
            clear_call_graph_built_strict(conn)
            # REQ-E-202: record partial_at in the manifest without deleting it.
            # The manifest singleton row retains its other columns (canonical_root
            # etc.) for the next reader; only partial_at is updated to indicate
            # that this pipeline generation was overtaken by source changes.
            # REQ-E-201: full-manifest DELETE is intentionally avoided.
            # TD-001: reset certified_at for changed paths so they are re-certified.
            for rel_path in changed_paths:
                try:
                    conn.execute(
                        "UPDATE ast_index SET certified_at = NULL WHERE file_path = ?",
                        (rel_path,),
                    )
                except Exception:
                    pass  # pre-v14 DB: certified_at column not yet added
            try:
                _manifest_cols = {
                    r[1]
                    for r in conn.execute(
                        "PRAGMA table_info(ast_index_snapshot_manifest)"
                    ).fetchall()
                }
                if "partial_at" not in _manifest_cols:
                    conn.execute(
                        "ALTER TABLE ast_index_snapshot_manifest"
                        " ADD COLUMN partial_at INTEGER"
                    )
                # TD-002: UPSERT prevents silent no-op when manifest row is absent.
                # Inserts a sentinel row if missing; updates partial_at only otherwise.
                conn.execute(
                    "INSERT INTO ast_index_snapshot_manifest "
                    "(singleton, canonical_root, source_fingerprint, index_fingerprint, "
                    "file_count, source_scope_descriptor, manifest_version, partial_at) "
                    "VALUES (1, '', '', '', 0, '', 0, ?) "
                    "ON CONFLICT(singleton) DO UPDATE SET partial_at = excluded.partial_at",
                    (int(time.time()),),
                )
            except sqlite3.OperationalError:
                pass
        indexed_paths = {
            str(row["file_path"])
            for row in conn.execute("SELECT file_path FROM ast_index").fetchall()
        }
        certified_paths = (
            set(disk_files) if candidate_snapshot is not None else present_paths
        )
        candidate_scope_exact = bool(
            candidate_snapshot is None
            or (
                candidate_snapshot.errors == 0
                and candidate_snapshot.discovery_error is None
                and not candidate_snapshot.truncated_by_max_files
                and candidate_snapshot.discovery_reconciled
            )
        )
        operational_complete = bool(
            result.errors == 0
            and result.backfill_errors == 0
            and not result.truncated_by_max_files
            and result.changed_during_run == 0
            and backfill_complete
            and candidate_scope_exact
            and (candidate_snapshot is not None or bool(certified_paths))
            and indexed_paths == certified_paths
        )
        if not operational_complete:
            # Phase B-3 (Path 3): PASS files keep their certified_at.
            # Only reset certified_at for files that had errors.
            # Manifest (Layer 2) is fully purged; per-file Layer 1 state is preserved.
            _error_paths_3 = [
                d["file"]
                for d in result.details
                if d.get("status") == "error" and d.get("file")
            ]
            if _error_paths_3:
                _ph3 = ",".join("?" * len(_error_paths_3))
                try:
                    conn.execute(
                        f"UPDATE ast_index SET certified_at = NULL"
                        f" WHERE file_path IN ({_ph3})",
                        _error_paths_3,
                    )
                except Exception:
                    pass  # pre-v14 DB: column not yet added
            from .cache.callgraph_state import clear_call_graph_built_strict

            clear_call_graph_built_strict(conn)
            conn.execute("DELETE FROM ast_index_snapshot_manifest")
            conn.commit()
        if operational_complete:
            from .cache.callgraph_state import (
                clear_call_graph_built_strict,
                mark_call_graph_built_strict,
            )

            try:
                mark_call_graph_built_strict(conn)
            except Exception:
                logger.warning(
                    "incremental call-graph marker certification failed",
                    exc_info=True,
                )
                backfill_complete = False
                operational_complete = False
                result.backfill_errors += 1
                result.details.append(
                    {
                        "file": "",
                        "status": "warning",
                        "reason": "CALL_GRAPH_MARKER_CERTIFICATION_FAILED",
                    }
                )
                clear_call_graph_built_strict(conn)
                conn.execute("DELETE FROM ast_index_snapshot_manifest")
                conn.commit()
        # A live legacy walk remains operationally useful, but it is not frozen
        # candidate evidence and therefore cannot certify authoritative scope.
        result.scope_complete = bool(
            operational_complete and candidate_snapshot is not None
        )
        expected_paths = set(disk_files)
        if (
            result.scope_complete
            and candidate_snapshot is not None
            and indexed_paths == expected_paths
            and certify_manifest
        ):
            from .index_snapshot_schema import stamp_full_index_manifest

            try:
                stamp_full_index_manifest(conn, self._cache.project_root, source_scope)
            except Exception:
                logger.warning(
                    "incremental snapshot manifest certification failed",
                    exc_info=True,
                )
                result.scope_complete = False
                result.manifest_certification_failed = True
                result.errors += 1
                result.details.append(
                    {
                        "file": "",
                        "status": "warning",
                        "reason": "INDEX_MANIFEST_CERTIFICATION_FAILED",
                    }
                )
                # The call-graph marker was published only as a prerequisite
                # for this manifest epoch. Revoke it when final certification
                # fails so no SQL reader can trust the rejected epoch.
                from .cache.callgraph_state import clear_call_graph_built_strict

                clear_call_graph_built_strict(conn)
                conn.commit()

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
            if any(
                entry.frozen_path is not None
                for entry in candidate_snapshot.selected_entries
            ):
                from .indexing_candidate_materialization import (
                    _FROZEN_READ_SECONDS,
                    index_candidate_cache_hierarchy_is_current,
                    index_candidate_snapshot_is_materialized,
                )

                if not index_candidate_snapshot_is_materialized(
                    candidate_snapshot,
                    deadline=time.monotonic() + _FROZEN_READ_SECONDS,
                ):
                    raise ValueError("INDEX_CANDIDATE_FROZEN_EVIDENCE_INVALID")
                if not index_candidate_cache_hierarchy_is_current(
                    candidate_snapshot, self._cache
                ):
                    raise ValueError("INDEX_CACHE_HIERARCHY_CHANGED")
            changed_files: list[tuple[str, str]] = []
            for entry in candidate_snapshot.selected_entries:
                change_reason = (
                    None
                    if entry.frozen_path is not None
                    else changed_since_snapshot(entry)
                )
                if change_reason is not None:
                    changed_files.append((entry.rel_path, change_reason))
                    continue
                fingerprint = entry.fingerprint
                assert fingerprint is not None
                disk_files[entry.rel_path] = {
                    "abs_path": entry.abs_path,
                    "source_path": entry.frozen_path or entry.abs_path,
                    "language": entry.language,
                    "fingerprint": fingerprint,
                    "frozen_identity": entry.frozen_identity,
                    "mtime_ns": fingerprint.mtime_ns,
                    "file_size": fingerprint.file_size,
                    "content_hash": fingerprint.content_hash,
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
            rel = os.path.relpath(abs_path, self._cache.project_root)
            if os.name == "nt":
                rel = rel.replace("\\", "/")
            present_paths.add(rel)
            if exclude_patterns and any(
                fnmatch.fnmatch(rel, pattern) for pattern in exclude_patterns
            ):
                continue
            try:
                stat = os.stat(abs_path)
                disk_files[rel] = {
                    "abs_path": abs_path,
                    "source_path": abs_path,
                    "language": None,
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
        """Transactionally drop primary and graph rows outside the exact scope."""
        supported = sorted(
            rel
            for rel in deleted_paths
            if os.path.splitext(rel)[1].lower() in _EXT_TO_LANG
        )
        if not supported:
            return
        from .cache import write as cache_write
        from .cache.callgraph_state import clear_call_graph_built_strict

        conn = self._cache.get_conn()
        try:
            for rel in supported:
                cache_write.discard_file_rows(conn, rel, self._cache.fts5_available)
            clear_call_graph_built_strict(conn)
        except Exception:
            conn.rollback()
            raise
        if getattr(self._cache, "_uses_project_mirror", True):
            try:
                from .cache.indexer import _invalidate_ladybug

                _invalidate_ladybug(
                    self._cache, getattr(self._cache, "_cache_dir_fd", None)
                )
            except Exception as exc:
                # Codex review 3764611251: the derived mirror may still expose
                # deleted nodes, so this epoch cannot be certified as complete.
                logger.error(
                    "failed to invalidate Ladybug mirror after deletion", exc_info=True
                )
                result.errors += 1
                result.scope_complete = False
                detail = {
                    "file": "",
                    "status": "error",
                    "reason": "LADYBUG_MIRROR_INVALIDATION_FAILED",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }
                result.details.append(detail)
        for rel in supported:
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
                detail = self._index_new_file(rel, info, conn)
                result.new_files += 1
                action_by_file[rel] = "new"
            elif self._file_changed(info, indexed_info, rel):
                detail = self._reindex_modified(rel, info, conn)
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
        del rel_path
        return file_changed(disk_info, indexed_info)

    def _index_new_file(
        self,
        rel_path: str,
        info: dict[str, Any] | str,
        conn: sqlite3.Connection,
    ) -> dict[str, Any]:
        # Keep attempted action separate from the cache layer's actual status.
        if isinstance(info, str):
            info = {"abs_path": info, "source_path": info}
        try:
            index_result = self._index_logical_file(info)
        except Exception as exc:
            # #886: if index_file wrote partial rows before raising, clean the
            # complete generation through the shared ordered external-FTS helper.
            # Codex P2: cleanup remains best effort for locked/full databases.
            try:
                from .cache import write as cache_write

                cache_write.discard_file_rows(
                    conn, rel_path, self._cache.fts5_available
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
        info: dict[str, Any] | str,
        conn: sqlite3.Connection,
    ) -> dict[str, Any]:
        if isinstance(info, str):
            info = {"abs_path": info, "source_path": info}
        self._cache.invalidate(info["abs_path"])
        try:
            index_result = self._index_logical_file(info)
        except Exception as exc:
            # #886: same shared ordered cleanup as _index_new_file.
            try:
                from .cache import write as cache_write

                cache_write.discard_file_rows(
                    conn, rel_path, self._cache.fts5_available
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

    def _index_logical_file(self, info: dict[str, Any]) -> dict[str, Any]:
        """Index certified bytes under their original logical cache key."""
        logical_path = str(info["abs_path"])
        source_path = str(info.get("source_path", logical_path))
        if source_path == logical_path:
            return self._cache.index_file(logical_path)
        from .indexing_candidate_materialization import _FROZEN_READ_SECONDS

        return self._cache.index_file(
            logical_path,
            info.get("language"),
            _source_path=source_path,
            _source_fingerprint=info.get("fingerprint"),
            _frozen_identity=info.get("frozen_identity"),
            _frozen_deadline=time.monotonic() + _FROZEN_READ_SECONDS,
        )

    def get_changes(self) -> dict[str, list[str]]:
        """Return live new, modified, and deleted paths without re-indexing."""
        return get_changes(self._cache, self._file_changed, _walk_source_files)
