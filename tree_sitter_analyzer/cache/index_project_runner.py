# mypy: disable-error-code="name-defined, no-any-return"
"""High-level project-index orchestration bound to the indexer facade globals."""
# ruff: noqa: F821

from __future__ import annotations

from typing import Any


def run_index_project(
    cache: Any,
    max_files: int = 20_000,
    force: bool = False,
    *,
    workers: int | None = None,
    resolve_only: bool = False,
    include_activation: bool | None = None,
    language_filter: str | None = None,
    exclude_patterns: frozenset[str] | None = None,
    candidate_snapshot: IndexCandidateSnapshot | None = None,
    source_scope: SourceScopeDescriptor | None = None,
    certify_manifest: bool = True,
) -> dict[str, Any]:
    """Orchestrate a full ASTCache project index run.

    ASTCache keeps the connection/backfill helpers; this module owns the
    high-level control flow so ``ast_cache.py`` stays thin.
    """
    max_files = normalize_index_max_files(max_files)
    activation_enabled = _project_index_activation_enabled(include_activation)
    if resolve_only:
        synapse = cache._run_synapse_backfill()
        edge_store_refresh = cache._refresh_graph_edges_from_cache()
        unresolved = cache._run_unresolved_refs_backfill()
        return {
            "mode_used": "resolve_only",
            "resolve_only": True,
            "indexed": 0,
            "cached": 0,
            "errors": 0,
            "skipped": 0,
            "incomplete_skips": 0,
            "files": [],
            "synapse_backfill": synapse,
            "edge_store_refresh": edge_store_refresh,
            "unresolved_refs_backfill": unresolved,
            "activation_enabled": activation_enabled,
        }
    effective_exclude = (
        exclude_patterns if exclude_patterns is not None else _DEFAULT_EXCLUDE_PATTERNS
    )
    owns_candidate_snapshot = False
    candidate_released = False
    cleanup_result: dict[str, Any] | None = None
    materialized = False
    if force and candidate_snapshot is None:
        candidate_snapshot = build_index_candidate_snapshot(
            cache.project_root,
            max_files=max_files,
            exclude_patterns=effective_exclude,
            walk_fn=lambda root: walk_index_candidate_entries(
                root, excluded_dir_names=frozenset(_EXCLUDE_DIRS)
            ),
            language_fn=_language_from_ext,
            language_filter=language_filter,
            materialize=True,
        )
        owns_candidate_snapshot = True
    if candidate_snapshot is not None:
        validate_index_candidate_snapshot(
            cache.project_root, max_files, candidate_snapshot
        )
    if source_scope is None:
        source_scope = make_source_scope_descriptor(
            no_default_excludes=exclude_patterns is not None,
            exclude_patterns=tuple(sorted(effective_exclude))
            if exclude_patterns is not None
            else (),
            certification_max_files=max_files,
        )
    else:
        source_scope = parse_source_scope_descriptor(
            canonical_source_scope_descriptor(source_scope)
        )
    validate_full_index_source_scope(source_scope, effective_exclude, max_files)
    from ..indexing_candidate_materialization import (
        index_candidate_snapshot_is_materialized,
        secure_candidate_materialization_supported,
    )

    if force:
        materialized = bool(
            candidate_snapshot is not None
            and index_candidate_snapshot_is_materialized(candidate_snapshot)
        )
        legacy_materialization = bool(
            candidate_snapshot is not None
            and candidate_snapshot.frozen_error == "SECURE_MATERIALIZATION_UNSUPPORTED"
            and not secure_candidate_materialization_supported()
        )
        snapshot_is_unsafe = bool(
            candidate_snapshot is None
            or candidate_snapshot.errors > 0
            or candidate_snapshot.discovery_error is not None
            or candidate_snapshot.truncated_by_max_files
            or not candidate_snapshot.discovery_reconciled
            or (not materialized and not legacy_materialization)
        )
        if snapshot_is_unsafe:
            # Destructive rebuilds consume only a fully materialized frozen epoch.
            changed = (
                [
                    (entry, reason)
                    for entry in candidate_snapshot.selected_entries
                    if (reason := changed_since_snapshot(entry)) is not None
                ]
                if candidate_snapshot is not None and not materialized
                else []
            )
            result = _unsafe_force_snapshot_result(
                candidate_snapshot, activation_enabled, changed=changed
            )
            if owns_candidate_snapshot and candidate_snapshot is not None:
                from ..indexing_candidate_materialization import (
                    release_index_candidate_snapshot,
                )

                release_index_candidate_snapshot(candidate_snapshot, result)
                candidate_released = True
            return result

    rebuild_signaled = False
    root_lease_fd: int | None = None
    try:
        if (
            candidate_snapshot is not None
            and secure_candidate_materialization_supported()
            and getattr(cache, "_uses_project_mirror", True)
        ):
            from ..indexing_candidate_materialization import (
                index_candidate_cache_hierarchy_is_current,
                open_index_candidate_snapshot_root,
            )

            root_lease_fd = open_index_candidate_snapshot_root(candidate_snapshot)
            if root_lease_fd is None or not index_candidate_cache_hierarchy_is_current(
                candidate_snapshot, cache, root_fd=root_lease_fd
            ):
                cleanup_result = _unsafe_force_snapshot_result(
                    candidate_snapshot, activation_enabled, changed=[]
                )
                cleanup_result["mode_used"] = "full" if force else "incremental"
                cleanup_result["files"] = [
                    {
                        "file": "",
                        "status": "error",
                        "reason": "INDEX_CACHE_HIERARCHY_CHANGED",
                    }
                ]
                return cleanup_result
        if force:
            # #578: a full rebuild empties ast_index up front (the DELETE
            # below commits), then re-populates in bounded batches over
            # ~70 s. Stamp a persisted marker across that window so
            # concurrent readers on other connections/processes warn
            # instead of trusting the half-built table. MARK + DELETE live
            # INSIDE the try so the finally clears the marker even if the
            # DELETE/commit itself raises (e.g. SQLITE_FULL) — otherwise a
            # failed rebuild would leave a stuck marker until TTL expiry.
            conn = cache._get_conn()
            # The only destructive authorization is the immutable materialized
            # epoch validated above; live path replay must never gate the clear.
            had_call_graph = cache.call_graph_built()
            _mark_build_in_progress(conn)
            rebuild_signaled = True
            _clear_call_graph_built(conn)
            try:
                _clear_full_rebuild_rows(cache, conn)
                conn.commit()
                try:
                    _invalidate_ladybug(cache, root_lease_fd)
                except Exception:
                    logger.debug("could not invalidate Ladybug mirror", exc_info=True)
            except Exception:
                conn.rollback()
                if had_call_graph:
                    _mark_call_graph_built(conn)
                raise
        conn = cache._get_conn()
        projection_repair = not symbol_projection_is_exact(
            conn, require_fts=cache.fts5_available
        )
        if projection_repair and not rebuild_signaled:
            # Repair rewrites ordinary rows in committed batches just like a full
            # rebuild. Publish incomplete evidence before the first batch so no
            # concurrent reader can trust the old manifest/call-graph epoch.
            _mark_build_in_progress(conn)
            rebuild_signaled = True
            _clear_call_graph_built_strict(conn)
            _delete_all_rows_if_present(conn, "ast_index_snapshot_manifest")
            conn.commit()
        stats, candidates, count = walk_and_partition(
            cache,
            conn,
            max_files,
            force or projection_repair,
            activation_enabled,
            _walk_source_files,
            _language_from_ext,
            _AST_CACHE_EXTRACTOR_VERSION,
            _make_error_entry,
            language_filter,
            effective_exclude,
            candidate_snapshot,
        )
        cleanup_result = stats
        candidate_fingerprints = (
            {
                entry.abs_path: cast(IndexFileFingerprint, entry.fingerprint)
                for entry in candidate_snapshot.selected_entries
            }
            if candidate_snapshot is not None
            else {}
        )
        candidate_frozen_paths = (
            {
                entry.abs_path: entry.frozen_path
                for entry in candidate_snapshot.selected_entries
                if entry.frozen_path is not None
            }
            if candidate_snapshot is not None
            else {}
        )
        candidate_frozen_identities = (
            {
                entry.abs_path: entry.frozen_identity
                for entry in candidate_snapshot.selected_entries
                if entry.frozen_identity is not None
            }
            if candidate_snapshot is not None
            else {}
        )
        # The snapshot-wide absolute deadline protects only freeze/pre-clear
        # validation.  Once the destructive clear is authorized, every immutable
        # worker gets its own bounded read window so a long parse/build cannot
        # expire later frozen inputs before their reads begin.
        frozen_read_deadline = None
        workers = cache._resolve_worker_count(workers, candidates)
        if workers and workers >= 2 and len(candidates) >= 2:
            results = index_parallel(
                cache,
                candidates,
                workers,
                candidate_fingerprints,
                candidate_frozen_paths,
                candidate_frozen_identities,
                frozen_read_deadline,
            )
        else:
            from .extraction import _worker_index_file

            results = [
                _worker_index_file(
                    (
                        path,
                        cache.project_root,
                        language,
                        candidate_fingerprints.get(path),
                        candidate_frozen_paths.get(path),
                        candidate_frozen_identities.get(path),
                        frozen_read_deadline,
                    )
                )
                for path, language in candidates
            ]
        indexed_at = datetime.now(timezone.utc).isoformat()
        from .. import ast_cache as _ast_cache_mod

        snapshot_entries = (
            {entry.rel_path: entry for entry in candidate_snapshot.selected_entries}
            if candidate_snapshot is not None
            else None
        )
        result_guard = (
            partial(
                _snapshot_result_is_stable,
                entries=snapshot_entries,
                stats=stats,
                cache=cache,
                conn=conn,
                root_fd=root_lease_fd,
            )
            if snapshot_entries is not None
            else None
        )
        batch_guard = (
            partial(
                _revalidate_snapshot_batch,
                cache=cache,
                conn=conn,
                entries=snapshot_entries,
                stats=stats,
                root_fd=root_lease_fd,
            )
            if snapshot_entries is not None
            else None
        )
        _ast_cache_mod._commit_index_results(
            conn,
            results,
            stats,
            partial(
                insert_index_row,
                cache,
                conn,
                extractor_version=_AST_CACHE_EXTRACTOR_VERSION,
            ),
            indexed_at,
            activation_enabled,
            result_guard=result_guard,
            batch_guard=batch_guard,
        )
        if snapshot_entries is not None:
            if all(
                entry.frozen_path is not None for entry in snapshot_entries.values()
            ):
                _record_frozen_replay_mismatches(snapshot_entries, stats)
                if stats.get("changed_during_run", 0) > 0:
                    # The frozen epoch remains internally coherent, but it no
                    # longer certifies the live workspace consumed by readers.
                    _clear_call_graph_built_strict(conn)
            else:
                _revalidate_committed_snapshot(
                    cache=cache,
                    conn=conn,
                    entries=snapshot_entries,
                    stats=stats,
                    root_fd=root_lease_fd,
                )
        if projection_repair and stats["errors"] == 0:
            # A partial projection cannot use the unchanged-file fast path. Every
            # canonical file has now been rewritten with ordinary/FTS/activation
            # rows in its writer transaction; remove only orphan derived paths.
            conn.execute(
                "DELETE FROM ast_symbol_rows WHERE file_path NOT IN "
                "(SELECT file_path FROM ast_index)"
            )
            if cache.fts5_available:
                # Contentless FTS5 cannot reliably predicate-delete stale rows.
                # Rebuild it from the now-exact ordinary projection instead.
                conn.execute(
                    "INSERT INTO ast_symbols_fts(ast_symbols_fts) VALUES('delete-all')"
                )
                conn.execute(
                    "INSERT INTO ast_symbols_fts"
                    "(rowid, name, kind, file_path, language) "
                    "SELECT id, name, kind, file_path, language "
                    "FROM ast_symbol_rows ORDER BY id"
                )
            for table in ("ast_symbol_projection_state", "ast_symbol_activation"):
                conn.execute(
                    f"DELETE FROM {table} WHERE file_path NOT IN "  # nosec B608
                    "(SELECT file_path FROM ast_index)"
                )
            conn.commit()
            # The operation-boundary validator detected the repair and forced
            # every canonical file through the writer path.  The bounded migration
            # certifier publishes the projection marker only after exact payload,
            # state, and FTS validation; an oversized repair remains incomplete.
            from ..index_snapshot_symbols import ensure_symbol_rows_backfilled

            if not ensure_symbol_rows_backfilled(
                conn,
                require_fts=cache.fts5_available,
                allow_incomplete=True,
            ):
                stats["backfill_errors"] = stats.get("backfill_errors", 0) + 1
                _clear_call_graph_built_strict(conn)
                conn.execute("DELETE FROM ast_index_snapshot_manifest")
            conn.commit()
        frozen_epoch = bool(
            candidate_snapshot is not None
            and all(
                entry.frozen_path is not None
                for entry in candidate_snapshot.selected_entries
            )
        )
        if stats["changed_during_run"] > 0 and not frozen_epoch:
            _clear_call_graph_built(conn)
        stats["total_files"] = count
        stats["workers"] = workers
        if (
            candidate_snapshot is not None
            and not candidate_snapshot.truncated_by_max_files
            and candidate_snapshot.errors == 0
            and (
                stats.get("changed_during_run", 0) == 0
                or all(
                    entry.frozen_path is not None
                    for entry in candidate_snapshot.selected_entries
                )
            )
        ):
            stats["pruned"] = _prune_to_selected_scope(
                cache, conn, candidate_snapshot, root_fd=root_lease_fd
            )
        run_incomplete = bool(
            stats.get("incomplete_skips", 0)
            or stats.get("truncated_by_max_files", False)
            or stats.get("errors", 0)
            or (
                candidate_snapshot is not None
                and (
                    candidate_snapshot.errors
                    or candidate_snapshot.discovery_error is not None
                    or candidate_snapshot.truncated_by_max_files
                    or not candidate_snapshot.discovery_reconciled
                )
            )
        )
        if run_incomplete:
            # Global certification is invalid regardless of whether this run
            # happened to rewrite or prune a row.
            _clear_call_graph_built_strict(conn)
            conn.execute("DELETE FROM ast_index_snapshot_manifest")
            conn.commit()
            stats["verdict"] = "WARN"
            stats["manifest_warning"] = "INDEX_RUN_INCOMPLETE"

        # A missing marker is persisted evidence that a previous backfill did
        # not converge. Fully cached retries must run the complete chain again.
        needs_backfill = bool(
            stats["indexed"] > 0
            or stats.get("pruned", 0) > 0
            or not _call_graph_marker_is_built(conn)
        )
        if needs_backfill:
            _clear_call_graph_built(conn)
            post_index_backfill(cache, stats, root_fd=root_lease_fd)
            if stats.get("backfill_errors", 0) == 0 and _candidate_paths_are_exact(
                cache,
                conn,
                candidate_snapshot,
                stats,
                max_files,
                language_filter,
                effective_exclude,
            ):
                try:
                    _mark_call_graph_built_strict(conn)
                except sqlite3.OperationalError:
                    logger.warning(
                        "call-graph marker certification failed", exc_info=True
                    )
                    stats["backfill_errors"] = stats.get("backfill_errors", 0) + 1
                    stats["manifest_warning"] = "CALL_GRAPH_MARKER_CERTIFICATION_FAILED"
                    _clear_call_graph_built_strict(conn)
            else:
                _clear_call_graph_built_strict(conn)
        if force:
            stats["db_maintenance"] = (
                _ast_cache_mod._reclaim_storage_after_full_rebuild(conn, cache.db_path)
            )
        if certify_manifest:
            _update_authoritative_manifest(
                cache, candidate_snapshot, stats, source_scope
            )
        return stats
    finally:
        try:
            if root_lease_fd is not None:
                try:
                    os.close(root_lease_fd)
                except OSError:
                    logger.warning("could not close project-root lease", exc_info=True)
        finally:
            try:
                if rebuild_signaled:
                    _clear_build_in_progress(cache._get_conn())
            finally:
                if (
                    owns_candidate_snapshot
                    and candidate_snapshot is not None
                    and not candidate_released
                ):
                    from ..indexing_candidate_materialization import (
                        release_index_candidate_snapshot,
                    )

                    release_index_candidate_snapshot(candidate_snapshot, cleanup_result)
                    candidate_released = True
