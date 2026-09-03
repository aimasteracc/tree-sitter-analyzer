"""File and project indexing coordination for :class:`ASTCache`."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from types import SimpleNamespace
from typing import Any

from ._ast_cache_database_mixin import ASTCacheSurface
from .cache import indexer as _indexer
from .cache.callgraph_state import (
    clear_call_graph_built as _clear_call_graph_built,
)
from .cache.callgraph_state import (
    mark_call_graph_built_strict as _mark_call_graph_built_strict,
)
from .cache.extraction import _content_hash
from .cache.schema import clear_activation_for_file as _clear_activation_for_file_fn
from .index_source_snapshot import SourceScopeDescriptor
from .indexing_snapshot import IndexCandidateSnapshot
from .project_graph import _language_from_ext

logger = logging.getLogger(__name__)


def _cached_graph_rows(
    conn: sqlite3.Connection,
    file_paths: list[str] | None,
) -> list[sqlite3.Row]:
    if file_paths is None:
        return conn.execute(
            "SELECT file_path, language, symbols_json, imports_json FROM ast_index"
        ).fetchall()
    rows: list[sqlite3.Row] = []
    for rel_path in file_paths:
        row = conn.execute(
            "SELECT file_path, language, symbols_json, imports_json "
            "FROM ast_index WHERE file_path = ?",
            (rel_path,),
        ).fetchone()
        if row is not None:
            rows.append(row)
    return rows


def _refresh_cached_graph_row(conn: sqlite3.Connection, row: sqlite3.Row) -> bool:
    """Write one cached file into EdgeStore, returning success."""
    from .cache import write as _write

    try:
        symbols = json.loads(row["symbols_json"] or "{}")
        imports = json.loads(row["imports_json"] or "[]")
        if not _write.write_graph_edges_for_file(
            conn,
            row["file_path"],
            row["language"],
            symbols,
            imports,
            [],
            preserve_calls=True,
        ):
            return False
    except (json.JSONDecodeError, sqlite3.OperationalError):
        return False
    return True


class ASTCacheIndexMixin(ASTCacheSurface):
    """Stable indexing methods delegated to focused cache modules."""

    def index_file(
        self,
        file_path: str,
        language: str | None = None,
        *,
        _source_path: str | None = None,
        _source_fingerprint: Any | None = None,
        _frozen_identity: tuple[int, int, int] | None = None,
        _frozen_deadline: float | None = None,
    ) -> dict[str, Any]:
        """Index one logical path; private frozen inputs are engine-only evidence."""
        abs_path = os.path.abspath(file_path)
        rel_path = os.path.relpath(abs_path, self.project_root).replace("\\", "/")
        if language is None:
            language = _language_from_ext(abs_path)
        if language is None:
            return {
                "file": rel_path,
                "status": "skipped",
                "reason": "unsupported language",
            }
        frozen_source: str | None = None
        stat_value: Any
        if _source_path is not None:
            if _source_fingerprint is None or _frozen_identity is None:
                return {
                    "file": rel_path,
                    "status": "error",
                    "reason": "INDEX_CANDIDATE_FROZEN_EVIDENCE_MISSING",
                }
            from .indexing_candidate_materialization import read_frozen_candidate

            try:
                frozen_source = read_frozen_candidate(
                    _source_path,
                    expected=_source_fingerprint,
                    frozen_identity=_frozen_identity,
                    deadline=_frozen_deadline,
                )
            except OSError as exc:
                return {"file": rel_path, "status": "error", "reason": str(exc)}
            stat_value = SimpleNamespace(
                st_mtime_ns=_source_fingerprint.mtime_ns,
                st_size=_source_fingerprint.file_size,
            )
        else:
            try:
                stat_value = os.stat(abs_path)
            except OSError as exc:
                return {"file": rel_path, "status": "error", "reason": str(exc)}
        conn = self._get_conn()
        had_built_marker = self.call_graph_built()
        cached_or_source = self._check_cache_or_read(
            conn, rel_path, abs_path, stat_value, source_code=frozen_source
        )
        if isinstance(cached_or_source, dict):
            self._mark_single_file_index_complete_if_needed(
                had_built_marker,
                cached_or_source,
            )
            return cached_or_source
        source_code, content_hash = cached_or_source
        if had_built_marker:
            _clear_call_graph_built(conn)
        result = self._parse_and_write(
            conn,
            abs_path,
            rel_path,
            language,
            stat_value,
            source_code,
            content_hash,
            source_is_frozen=_source_path is not None,
        )
        self._mark_single_file_index_complete_if_needed(had_built_marker, result)
        return result

    def _mark_single_file_index_complete_if_needed(
        self,
        had_built_marker: bool,
        result: dict[str, Any],
    ) -> None:
        """Refresh the built marker after a successful single-file reindex."""
        if result.get("status") not in {"indexed", "cached"}:
            return
        if getattr(self, "_defer_single_file_backfill", False):
            return
        if not had_built_marker and not self._indexed_source_files_are_complete():
            return
        if result.get("status") == "indexed" or not had_built_marker:
            from .incremental_sync_callgraph import run_call_graph_pipeline

            complete, _resolved = run_call_graph_pipeline(self)
            if not complete:
                return
        try:
            _mark_call_graph_built_strict(self._get_conn())
        except sqlite3.OperationalError:
            logger.debug("single-file call-graph certification failed", exc_info=True)

    def _check_cache_or_read(
        self,
        conn: sqlite3.Connection,
        rel_path: str,
        abs_path: str,
        stat: Any,
        *,
        source_code: str | None = None,
    ) -> dict[str, Any] | tuple[str, str]:
        """Return a cached response or source plus its content hash."""
        return _indexer.check_cache_or_read(
            conn,
            rel_path,
            abs_path,
            stat,
            _content_hash,
            self._extractor_version,
            source_code=source_code,
        )

    def _parse_and_write(
        self,
        conn: sqlite3.Connection,
        abs_path: str,
        rel_path: str,
        language: str,
        stat: Any,
        source_code: str,
        content_hash: str,
        *,
        source_is_frozen: bool = False,
    ) -> dict[str, Any]:
        """Parse a file and write all cache rows."""
        return _indexer.parse_and_write(
            self,
            conn,
            abs_path,
            rel_path,
            language,
            stat,
            source_code,
            content_hash,
            self._extractor_version,
            source_is_frozen=source_is_frozen,
        )

    def _write_activation_for_file(
        self,
        conn: sqlite3.Connection,
        rel_path: str,
        inserted_symbol_rows: list[dict[str, Any]],
    ) -> None:
        """Refresh activation rows for a single file."""
        from .cache import write as _write

        _write.write_activation_for_file(
            conn,
            rel_path,
            inserted_symbol_rows,
            self.project_root,
        )

    @staticmethod
    def _write_imports_for_file(
        conn: sqlite3.Connection,
        rel_path: str,
        language: str,
        imports: list[str] | list[dict[str, Any]],
    ) -> None:
        """Refresh import rows for one file."""
        from .cache import write as _write

        _write.write_imports_for_file(conn, rel_path, language, imports)

    def _resolve_call_edges_for_file(
        self,
        conn: sqlite3.Connection,
        rel_path: str,
    ) -> None:
        """Resolve one file's call edges through Synapse."""
        from .cache import synapse as _synapse

        _synapse.resolve_call_edges_for_file(self, conn, rel_path)

    @staticmethod
    def _clear_activation_for_file(
        conn: sqlite3.Connection,
        rel_path: str,
    ) -> None:
        """Drop stale activation rows during fast project indexing."""
        _clear_activation_for_file_fn(conn, rel_path)

    def _run_synapse_backfill(self) -> dict[str, int] | None:
        """Re-resolve unresolved call edges."""
        from .cache import synapse as _synapse

        return _synapse.run_synapse_backfill(self, self._get_conn())

    def index_project(
        self,
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
        """Index every source file below the project root."""
        # One cache owner serializes validation, destructive clear, and writes.
        # SQLite still arbitrates across processes; this lock closes the in-owner
        # thread window between the final source authorization and the clear.
        #
        # Phase B-4 (TBD-3) analysis: _index_lock is a writer-side serializer.
        # WAL read-only snapshot connections (Phase B-1) operate on the reader
        # side and are NOT affected by _index_lock.  Concurrent MCP readers can
        # acquire WAL snapshots without waiting for a write to finish, giving the
        # Phase B-2 parallelism improvement without relaxing this lock.
        # cache/indexer.py parallel workers run INSIDE _index_lock's critical
        # section (called via run_index_project), so WAL parallelism does not
        # conflict with them.
        with self._index_lock:
            return _indexer.run_index_project(
                self,
                max_files,
                force,
                workers=workers,
                resolve_only=resolve_only,
                include_activation=include_activation,
                language_filter=language_filter,
                exclude_patterns=exclude_patterns,
                candidate_snapshot=candidate_snapshot,
                source_scope=source_scope,
                certify_manifest=certify_manifest,
            )

    def _post_index_backfill(self, stats: dict[str, Any]) -> None:
        """Run graph backfills after project indexing."""
        _indexer.post_index_backfill(self, stats)
        # REQ-C-306: flush pending activation rows produced by write_activation_for_file.
        # Called synchronously here; ThreadPoolExecutor-based async scheduling is
        # deferred to a future scheduler-integration phase.
        try:
            from .cache.write import _flush_pending_activations

            _result = _flush_pending_activations(
                self._get_conn(), self.project_root
            )
            logger.debug("_flush_pending_activations result: %s", _result)
        except Exception as exc:  # pragma: no cover
            logger.debug("_flush_pending_activations raised: %s", exc)

    @staticmethod
    def _completed_full_index_sweep(stats: dict[str, Any]) -> bool:
        """Return whether a run processed the complete source set."""
        return (
            not stats.get("truncated_by_max_files", False)
            and stats.get("errors", 0) == 0
            and stats.get("skipped", 0) == 0
        )

    def _indexed_source_files_are_complete(self) -> bool:
        """Return whether ast_index is fully certified (O(1) via COUNT queries).

        REQ-E-401: Replaces the O(n) os.walk + full-table fetch with two
        COUNT(*) queries against the certified_at column added by
        apply_migration_v14.  Falls back to False when the column is absent
        (pre-v14 DB) rather than degrading to the expensive legacy path.
        """
        try:
            conn = self._get_conn()
            (uncertified,) = conn.execute(
                "SELECT COUNT(*) FROM ast_index WHERE certified_at IS NULL"
            ).fetchone()
            if uncertified > 0:
                return False
            row = conn.execute("SELECT COUNT(*) FROM ast_index").fetchone()
            return int(row[0]) > 0
        except sqlite3.OperationalError:
            # certified_at column absent (apply_migration_v14 not yet applied) — safe fallback
            return False

    @staticmethod
    def _resolve_worker_count(workers: int | None, candidates: list[Any]) -> int:
        """Pick worker count from environment, argument, or auto-detection."""
        env_workers = os.environ.get("TSA_INDEX_WORKERS")
        if env_workers is not None:
            try:
                workers = int(env_workers)
            except ValueError:
                pass
        if workers is None:
            cpu_count = os.cpu_count() or 4
            workers = 0 if len(candidates) < 64 else max(2, cpu_count - 1)
        return workers

    def _refresh_graph_edges_from_cache(
        self,
        file_paths: list[str] | None = None,
    ) -> dict[str, int]:
        """Refresh EdgeStore rows from persisted AST cache rows."""
        conn = self._get_conn()
        outcomes = [
            _refresh_cached_graph_row(conn, row)
            for row in _cached_graph_rows(conn, file_paths)
        ]
        conn.commit()
        refreshed = outcomes.count(True)
        return {"files": refreshed, "errors": len(outcomes) - refreshed}

    def _run_unresolved_refs_backfill(self) -> dict[str, int] | None:
        """Resolve persisted unresolved refs into EdgeStore edges."""
        from .cache import unresolved as _unresolved

        return _unresolved.resolve_unresolved_refs(self._get_conn())
