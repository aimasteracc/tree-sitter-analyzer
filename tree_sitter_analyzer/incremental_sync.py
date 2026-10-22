"""Incrementally reconcile source files with the persistent AST cache."""

import fnmatch
import logging
import os
import sqlite3
import time
from typing import Any

from .ast_cache import _EXT_TO_LANG, _walk_source_files
from .cache.helpers import _project_index_activation_enabled
from .cache.publication_policy import FAILURE_KIND
from .incremental_sync_support import (
    SyncResult,
    file_changed,
    get_changes,
    stamp_certified_at,
)
from .index_source_scope import default_exclude_patterns
from .index_source_snapshot import (
    SourceScopeDescriptor,
    make_source_scope_descriptor,
    validate_full_index_source_scope,
)
from .indexing_limits import normalize_index_max_files
from .indexing_snapshot import (
    _PERMANENT_SOURCE_REJECTIONS,
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
        self._default_generation = False

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
            # #1697：省略排除策略即默认范围，与项目索引（``index_project``）同一
            # 来源；显式给出的集合就是生效集合（不再叠加默认模式）。
            source_scope = make_source_scope_descriptor(
                no_default_excludes=exclude_patterns is not None,
                exclude_patterns=tuple(sorted(exclude_patterns or ())),
                certification_max_files=max_files,
            )
        if exclude_patterns is None:
            exclude_patterns = source_scope.effective_excludes
        validate_full_index_source_scope(source_scope, exclude_patterns, max_files)
        if getattr(self._cache, "_generation_managed", False) or getattr(
            self, "_default_generation", False
        ):
            from .cache.generation_indexing import run_incremental_sync

            return run_incremental_sync(
                self._cache,
                max_files=max_files,
                callback=callback,
                exclude_patterns=exclude_patterns,
                candidate_snapshot=candidate_snapshot,
                source_scope=source_scope,
                certify_manifest=certify_manifest,
            )
        from .cache.writer_state import writer_operation

        # RFC-0032 slice 5：原地写入（自定义 db_path）是一次以修订号 CAS 绑定的操作；
        # 候选已绑定修订号时，期间任何其他写入都使本次同步在写入前被拒绝。
        with writer_operation(self._cache, candidate_snapshot):
            return self._sync_in_place(
                max_files,
                callback,
                exclude_patterns,
                candidate_snapshot,
                source_scope,
                certify_manifest,
            )

    def _sync_in_place(
        self,
        max_files: int,
        callback: Any | None,
        exclude_patterns: frozenset[str] | None,
        candidate_snapshot: IndexCandidateSnapshot | None,
        source_scope: SourceScopeDescriptor,
        certify_manifest: bool,
    ) -> SyncResult:
        """Reconcile in place: a custom ``db_path`` or a private generation build."""
        from .cache.stable_failures import clear_record

        result = SyncResult()
        conn = self._cache.get_conn()
        # #1696：武装回填范围记录；本轮写入的文件、符号名与被重置的边由此界定回填。
        from .cache import backfill_scope, certification_tracking

        # RFC-0039 slice 2：在本连接写入任何行之前武装增量认证（记录脏组）。
        certification_tracking.arm(conn)
        backfill_scope.begin(conn, backfill_scope.published_parent(self._cache))
        # #1671：先撤销继承的稳定失败记录；只有收敛的运行结束时重新签发。
        clear_record(conn)
        conn.commit()
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
        # #1697：同步是项目范围的刷新，activation 与项目索引同一策略
        # （``TSA_INDEX_ACTIVATION``，默认关闭）；单文件索引的默认不变。
        activation_enabled = _project_index_activation_enabled(None)
        previous_activation = getattr(self._cache, "_project_activation_enabled", None)
        self._cache._project_activation_enabled = activation_enabled
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
            self._cache._project_activation_enabled = previous_activation

        # Phase B-3: Set certified_at for successfully processed files.
        # New/updated files receive this run's Unix epoch; unchanged files keep
        # their value unless it is still NULL (#1718, RFC-0039 step 0). Error
        # files retain NULL (or get it reset in the clear paths below).
        if action_by_file:
            try:
                stamp_certified_at(conn, action_by_file, int(time.time()))
            except Exception:
                # PR #1350：认证写入失败必须进入既有失败闭合路径，不能仍发布 complete。
                result.errors += 1
                result.details.append(
                    {
                        "file": "",
                        "status": "error",
                        "reason": "FILE_CERTIFICATION_FAILED",
                    }
                )

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
                # 扫描与处理已为每个 late-change 路径登记 action；缺键是协议错误。
                action = action_by_file[rel_path]
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
                except sqlite3.DatabaseError:
                    conn.rollback()
                    raise
            from .cache.callgraph_state import clear_call_graph_built_strict

            clear_call_graph_built_strict(conn)
            conn.execute("DELETE FROM ast_index_snapshot_manifest")
        try:
            conn.commit()
        except Exception as exc:  # pragma: no cover - DB commit failure is rare
            logger.error("Final DB commit failed after partial sync: %s", exc)
            result.errors += 1

        from .cache.callgraph_state import writer_marker_is_current

        # #1684：写入方期限；负载下的超时不能被当作"标记未建成"而重跑全部回填。
        marker_current = writer_marker_is_current(conn)
        from .incremental_sync_callgraph import (
            pipeline_repair_required,
            run_call_graph_pipeline,
        )

        backfill_complete = marker_current
        if pipeline_repair_required(result, marker_current):
            backfill_complete, result.synapse_resolved = run_call_graph_pipeline(
                self._cache, result
            )

        if invalidate_snapshot_changes():
            # The pipeline ran against a generation that no longer exists.  A
            # later retry sees this explicit incomplete marker and repairs all
            # three stages; this run must never certify its pre-race results.
            from .cache.callgraph_state import clear_call_graph_built_strict

            backfill_complete = False
            clear_call_graph_built_strict(conn)
            # 仅撤销认证；partial_at 持久历史尚未实现，不写入随后必删的 manifest。
        if activation_enabled:
            # 与项目索引相同：开启时每次运行只处理一个有界批次的 pending 行。
            from .cache.write import _flush_pending_activations

            _flush_pending_activations(conn, self._cache.project_root)
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
                except sqlite3.DatabaseError:
                    conn.rollback()
                    raise
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
        stamped = False
        from .cache import certification_tracking

        if (
            result.scope_complete
            and candidate_snapshot is not None
            and indexed_paths == expected_paths
            and certify_manifest
        ):
            from .index_snapshot_schema import stamp_full_index_manifest

            try:
                stamp_full_index_manifest(conn, self._cache.project_root, source_scope)
                stamped = True
                # RFC-0039：这次盖章是增量还是完整重算，以及原因。
                result.certification = certification_tracking.last_decision(conn)
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
        if not stamped:
            # 不盖章：撤销本轮的增量认证武装（TEMP 触发器不留到之后的写入）。
            certification_tracking.disarm(conn)
        # 不盖清单的调用（``index action=full`` 的分阶段运行）只能签发带失败的
        # 记录：stamped 为假时 issue_after_run 拒绝无失败的记录。
        self._issue_stable_failure_record(
            conn,
            candidate_snapshot,
            source_scope,
            result,
            converged=bool(
                backfill_complete
                and result.backfill_errors == 0
                and result.changed_during_run == 0
                and not result.truncated_by_max_files
            ),
            stamped=stamped,
        )
        return result

    def _issue_stable_failure_record(
        self,
        conn: Any,
        candidate_snapshot: IndexCandidateSnapshot | None,
        source_scope: SourceScopeDescriptor,
        result: SyncResult,
        *,
        converged: bool,
        stamped: bool,
    ) -> None:
        """#1671：精确（或仅稳定失败）且调用图已收敛的同步签发零变化判定证据。"""
        from .cache.stable_failures import current_extractor_version, issue_after_run
        from .index_source_snapshot import canonical_source_scope_descriptor

        issue_after_run(
            conn,
            project_root=self._cache.project_root,
            candidate=candidate_snapshot,
            scope=canonical_source_scope_descriptor(source_scope),
            extractor_version=current_extractor_version(),
            details=result.details,
            errors=result.errors,
            converged=converged,
            stamped=stamped,
        )

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
            # #1405：只撤销有永久拒绝证据的源码；读取/时限故障保留缓存并降低完整性。
            changed_files: list[tuple[str, str]] = [
                (entry.rel_path, entry.reason or "candidate source rejected")
                for entry in candidate_snapshot.entries
                if entry.decision == "error"
                and entry.reason in _PERMANENT_SOURCE_REJECTIONS
            ]
            # #1673：路径平台的候选快照不带摘要；发布侧捕获时绑定的摘要随私有
            # 构建传入，比较直接使用它们，不为每个文件重读一遍（file_changed）。
            supplied = getattr(self._cache, "_bound_source_digests", None)
            bound = supplied if isinstance(supplied, dict) else {}
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
                    "content_hash": bound.get(entry.rel_path)
                    or fingerprint.content_hash,
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
            if exclude_patterns and any(
                fnmatch.fnmatch(rel, pattern) for pattern in exclude_patterns
            ):
                # #1697：被排除的文件不在范围内；旧库留下的行按删除处理。
                continue
            present_paths.add(rel)
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
        if getattr(self._cache, "_owns_project_mirror", True):
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
                # #1405：内容相同仍刷新捕获到的元数据，不需要重建语法树。
                if info["mtime_ns"] != indexed_info["mtime_ns"]:
                    conn.execute(
                        "UPDATE ast_index SET mtime_ns = ?, file_size = ? WHERE file_path = ?",
                        (info["mtime_ns"], info["file_size"], rel),
                    )
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
        if status == "error" and FAILURE_KIND in index_result:
            detail[FAILURE_KIND] = index_result[FAILURE_KIND]
            if "content_hash" in index_result:
                # #1671：稳定失败绑定被拒绝字节的摘要。
                detail["content_hash"] = index_result["content_hash"]
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
        if status == "error" and FAILURE_KIND in index_result:
            detail[FAILURE_KIND] = index_result[FAILURE_KIND]
            if "content_hash" in index_result:
                # #1671：稳定失败绑定被拒绝字节的摘要。
                detail["content_hash"] = index_result["content_hash"]
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

    def get_changes(
        self, *, exclude_patterns: frozenset[str] | None = None
    ) -> dict[str, list[str]]:
        """按调用方的排除策略返回 ``sync`` 将做的变更；省略策略即默认范围（#1697）。

        已入索引却落在范围外的文件（旧代码按全范围建的库）会被 ``sync`` 删除，
        因此报告为 ``deleted``，而不是从预览中消失。
        """
        if exclude_patterns is None:
            exclude_patterns = default_exclude_patterns()
        changes = get_changes(self._cache, self._file_changed, _walk_source_files)

        def excluded(path: str) -> bool:
            return any(fnmatch.fnmatch(path, pattern) for pattern in exclude_patterns)

        conn = self._cache.get_conn()
        out_of_scope = {
            str(row["file_path"])
            for row in conn.execute("SELECT file_path FROM ast_index").fetchall()
            if excluded(str(row["file_path"]))
        }
        return {
            "new": [path for path in changes["new"] if not excluded(path)],
            "deleted": sorted(set(changes["deleted"]) | out_of_scope),
            "modified": [path for path in changes["modified"] if not excluded(path)],
        }
