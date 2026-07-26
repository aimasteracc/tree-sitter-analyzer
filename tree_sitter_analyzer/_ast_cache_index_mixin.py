"""File and project indexing coordination for :class:`ASTCache`."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from typing import Any

from ._ast_cache_database_mixin import ASTCacheSurface
from .cache import indexer as _indexer
from .cache.callgraph_state import (
    clear_call_graph_built as _clear_call_graph_built,
)
from .cache.callgraph_state import (
    mark_call_graph_built as _mark_call_graph_built,
)
from .cache.extraction import _content_hash
from .cache.schema import clear_activation_for_file as _clear_activation_for_file_fn
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
        _write.write_graph_edges_for_file(
            conn,
            row["file_path"],
            row["language"],
            symbols,
            imports,
            [],
            preserve_calls=True,
        )
    except (json.JSONDecodeError, sqlite3.OperationalError):
        return False
    return True


class ASTCacheIndexMixin(ASTCacheSurface):
    """Stable indexing methods delegated to focused cache modules."""

    def index_file(self, file_path: str, language: str | None = None) -> dict[str, Any]:
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
        try:
            stat = os.stat(abs_path)
        except OSError as exc:
            return {"file": rel_path, "status": "error", "reason": str(exc)}
        conn = self._get_conn()
        had_built_marker = self.call_graph_built()
        cached_or_source = self._check_cache_or_read(conn, rel_path, abs_path, stat)
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
            stat,
            source_code,
            content_hash,
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
        if result.get("status") == "indexed":
            try:
                backfill = self._run_synapse_backfill()
            except Exception:
                logger.debug("single-file Synapse backfill failed", exc_info=True)
                return
            if backfill is None or int(backfill.get("errors", 0)) > 0:
                return
        _mark_call_graph_built(self._get_conn())

    def _check_cache_or_read(
        self,
        conn: sqlite3.Connection,
        rel_path: str,
        abs_path: str,
        stat: os.stat_result,
    ) -> dict[str, Any] | tuple[str, str]:
        """Return a cached response or source plus its content hash."""
        return _indexer.check_cache_or_read(
            conn,
            rel_path,
            abs_path,
            stat,
            _content_hash,
            self._extractor_version,
        )

    def _parse_and_write(
        self,
        conn: sqlite3.Connection,
        abs_path: str,
        rel_path: str,
        language: str,
        stat: os.stat_result,
        source_code: str,
        content_hash: str,
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
    ) -> dict[str, Any]:
        """Index every source file below the project root."""
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
        )

    def _post_index_backfill(self, stats: dict[str, Any]) -> None:
        """Run graph backfills after project indexing."""
        _indexer.post_index_backfill(self, stats)

    @staticmethod
    def _completed_full_index_sweep(stats: dict[str, Any]) -> bool:
        """Return whether a run processed the complete source set."""
        return (
            not stats.get("truncated_by_max_files", False)
            and stats.get("errors", 0) == 0
            and stats.get("skipped", 0) == 0
        )

    def _indexed_source_files_are_complete(self) -> bool:
        """Return whether ast_index exactly covers the current source set."""
        source_files = {
            os.path.relpath(path, self.project_root).replace("\\", "/")
            for path in _indexer._walk_source_files(self.project_root)
        }
        if not source_files:
            return False
        rows = self._get_conn().execute("SELECT file_path FROM ast_index").fetchall()
        indexed_files = {str(row["file_path"]).replace("\\", "/") for row in rows}
        return indexed_files == source_files

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
