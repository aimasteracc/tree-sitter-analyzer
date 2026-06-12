#!/usr/bin/env python3
"""Pre-indexed AST Cache — SQLite-backed persistent parse result storage.

Stores serialized AST metadata (symbols, imports, structure) keyed by
content SHA-256 hash. Re-analysis of unchanged files is a simple DB lookup.
"""

import json
import logging
import os
import sqlite3
import threading
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

from ._ast_cache_graph import bfs_callees as _bfs_callees_impl
from ._ast_cache_graph import bfs_callers as _bfs_callers_impl
from ._ast_cache_query import (
    backfill_cross_file_edges as _backfill_cross_file_edges,
    fts_search as _fts_search,
    fts_search_ranked as _fts_search_ranked,
    get_cross_file_stats as _get_cross_file_stats,
    get_stats as _get_stats,
    invalidate as _invalidate,
    lookup as _lookup,
    query_callers_enhanced as _query_callers_enhanced,
    query_callees_enhanced as _query_callees_enhanced,
    search_symbols_linear as _search_symbols_linear,
)
from ._ast_cache_search import search_symbols_cascade as _search_symbols_cascade
from ._ast_cache_helpers import (
    _build_function_entry,
    _commit_index_results,
    _make_error_entry,
    _project_index_activation_enabled,
)
from ._ast_cache_schema import (
    EXPECTED_SCHEMA_VERSIONS as _EXPECTED_SCHEMA_VERSIONS,
    SQL_GET_SCHEMA_VERSION as _SQL_GET_SCHEMA_VERSION,
    apply_large_repo_indexes as _apply_large_repo_indexes,
    apply_migration_v3 as _apply_migration_v3,
    apply_migration_v4 as _apply_migration_v4,
    apply_migration_v5 as _apply_migration_v5,
    apply_migration_v6 as _apply_migration_v6,
    apply_migration_v7 as _apply_migration_v7,
    apply_migration_v8 as _apply_migration_v8,
    apply_migration_v9 as _apply_migration_v9,
    apply_migration_v10 as _apply_migration_v10,
    apply_migration_v11 as _apply_migration_v11,
    apply_migration_v12 as _apply_migration_v12,
    backfill_schema_version_row as _backfill_schema_version_row,
    check_schema_expectations as _check_schema_expectations,
    clear_activation_for_file as _clear_activation_for_file_fn,
    init_db as _schema_init_db,
)
from .core.parser import Parser
from .project_graph import _language_from_ext

logger = logging.getLogger(__name__)

# v3: #610 — Python module-level constants extracted as kind="constant".
# v4: #613 — Go package-level const/var specs extracted as kind="constant".
# v5: #613 — Rust const/static items extracted as kind="constant".
# v6: #614 — docstring/return_type/params serialized into symbols_json.
# v7: #624 — PHP const declarations extracted as kind="constant".
# v8: #626 — JS/TS function-local variables no longer over-captured.
_AST_CACHE_EXTRACTOR_VERSION = 8


class SchemaIntegrityError(RuntimeError):
    """Raised when _init_db cannot prove all expected schema versions are present."""


# Extraction helpers — re-exported for back-compat; logic lives in _ast_extraction.py.
from ._ast_extraction import (  # noqa: E402
    _EXCLUDE_DIRS,
    _content_hash,
    _extract_symbols,  # noqa: F401 - back-compat re-export used by tests
    _has_fts5,
    _node_text,  # noqa: F401 - public back-compat re-export
    _worker_index_file,
)

# Back-compat alias imported by file_watcher.py and incremental_sync.py.
from ._lang_extension_map import EXT_TO_LANG as _EXT_TO_LANG  # noqa: E402


class ASTCache:
    """SQLite-backed persistent AST cache. Re-analysis of unchanged files is a simple DB lookup."""

    def __init__(self, project_root: str, db_path: str | None = None) -> None:
        self.project_root = os.path.abspath(project_root)
        if db_path is None:
            db_path = os.path.join(self.project_root, ".ast-cache", "index.db")
        self.db_path = db_path
        self._local = threading.local()
        self._parser = Parser()
        self._index_lock = threading.Lock()
        self._fts5_available: bool | None = None
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def get_conn(self) -> sqlite3.Connection:
        """Return the thread-local SQLite connection for this cache.

        Public accessor for the database connection.  Each thread gets its
        own ``sqlite3.Connection`` (created lazily on first access) configured
        with WAL journal mode and ``Row`` row factory.

        Prefer this over the private ``_get_conn()`` — external modules that
        need raw SQL access should call ``cache.get_conn()``.
        """
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    def _get_conn(self) -> sqlite3.Connection:
        """Private alias kept for backward compatibility — delegates to get_conn()."""
        return self.get_conn()

    @property
    def fts5_available(self) -> bool:
        """Return True if the SQLite FTS5 extension is available for this cache.

        Lazily initialised on the first call to ``_init_db()``.  Safe to read
        before ``_init_db()`` completes — returns ``False`` in that case.
        """
        return bool(self._fts5_available)

    @property
    def parser(self) -> "Parser":
        """Public accessor for the tree-sitter Parser instance."""
        return self._parser

    def _init_db(self) -> None:
        conn = self._get_conn()
        migrations = [
            (3, _apply_migration_v3),
            (4, _apply_migration_v4),
            (5, _apply_migration_v5),
            (6, _apply_migration_v6),
            (7, _apply_migration_v7),
            (8, _apply_migration_v8),
            (9, _apply_migration_v9),
            (10, _apply_migration_v10),
            (11, _apply_migration_v11),
            (12, _apply_migration_v12),
        ]
        self._fts5_available = _schema_init_db(
            conn, self._fts5_available, _has_fts5, migrations
        )
        self._verify_schema_integrity(conn)

    @staticmethod
    def _ensure_large_repo_indexes(conn: sqlite3.Connection) -> None:
        """Create non-shape-changing indexes for large-repo query hot paths."""
        _apply_large_repo_indexes(conn)

    def _verify_schema_integrity(self, conn: sqlite3.Connection) -> None:
        missing: list[str] = []
        for version, description, expectations in _EXPECTED_SCHEMA_VERSIONS:
            payload_ok = _check_schema_expectations(conn, expectations, missing)
            try:
                _cur = conn.execute(_SQL_GET_SCHEMA_VERSION, (version,))
                row = _cur.fetchone()
            except sqlite3.OperationalError:
                row = None
            if row is None and payload_ok:
                _backfill_schema_version_row(conn, version, description, missing)
        if missing:
            remediation = (
                f"Remove the cache DB at {self.db_path!r} and re-index "
                "(e.g. ``rm -rf .ast-cache && uv run python -m tree_sitter_analyzer --index``)."
            )
            _missing_str = "; ".join(missing)
            raise SchemaIntegrityError(
                f"AST cache schema is incomplete. Missing: {_missing_str}. {remediation}"
            )

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
        except OSError as e:
            return {"file": rel_path, "status": "error", "reason": str(e)}
        conn = self._get_conn()
        cached_or_source = self._check_cache_or_read(conn, rel_path, abs_path, stat)
        if isinstance(cached_or_source, dict):
            return cached_or_source
        source_code, content_hash = cached_or_source
        return self._parse_and_write(
            conn, abs_path, rel_path, language, stat, source_code, content_hash
        )

    def _check_cache_or_read(
        self,
        conn: sqlite3.Connection,
        rel_path: str,
        abs_path: str,
        stat: os.stat_result,
    ) -> dict[str, Any] | tuple[str, str]:
        """Return cached-response dict, or (source_code, content_hash) if stale."""
        from . import _ast_cache_indexer as _indexer

        return _indexer.check_cache_or_read(
            conn, rel_path, abs_path, stat, _content_hash, _AST_CACHE_EXTRACTOR_VERSION
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
        from . import _ast_cache_indexer as _indexer

        return _indexer.parse_and_write(
            self,
            conn,
            abs_path,
            rel_path,
            language,
            stat,
            source_code,
            content_hash,
            _AST_CACHE_EXTRACTOR_VERSION,
        )

    def _write_activation_for_file(
        self,
        conn: sqlite3.Connection,
        rel_path: str,
        inserted_symbol_rows: list[dict[str, Any]],
    ) -> None:
        """Refresh ``ast_symbol_activation`` rows for a single file."""
        from . import _ast_cache_write as _write

        _write.write_activation_for_file(
            conn, rel_path, inserted_symbol_rows, self.project_root
        )

    def _write_imports_for_file(
        self,
        conn: sqlite3.Connection,
        rel_path: str,
        language: str,
        imports: list[str] | list[dict[str, Any]],
    ) -> None:
        """Refresh ``ast_imports`` rows for ``rel_path``."""
        from . import _ast_cache_write as _write

        _write.write_imports_for_file(conn, rel_path, language, imports)

    def _resolve_call_edges_for_file(
        self, conn: sqlite3.Connection, rel_path: str
    ) -> None:
        """Resolve call edges for ``rel_path`` via Synapse."""
        from . import _ast_cache_synapse as _synapse

        _synapse.resolve_call_edges_for_file(self, conn, rel_path)

    def _run_synapse_backfill(self) -> dict[str, int] | None:
        """Re-resolve every unresolved call edge. Returns stats dict or None."""
        from . import _ast_cache_synapse as _synapse

        return _synapse.run_synapse_backfill(self, self._get_conn())

    def index_project(
        self,
        max_files: int = 20_000,
        force: bool = False,
        *,
        workers: int | None = None,
        resolve_only: bool = False,
        include_activation: bool | None = None,
    ) -> dict[str, Any]:
        """Index every source file under ``self.project_root``."""
        activation_enabled = _project_index_activation_enabled(include_activation)
        if resolve_only:
            synapse = self._run_synapse_backfill()
            edge_store_refresh = self._refresh_graph_edges_from_cache()
            unresolved = self._run_unresolved_refs_backfill()
            return {
                "mode_used": "resolve_only",
                "resolve_only": True,
                "indexed": 0,
                "cached": 0,
                "errors": 0,
                "skipped": 0,
                "files": [],
                "synapse_backfill": synapse,
                "edge_store_refresh": edge_store_refresh,
                "unresolved_refs_backfill": unresolved,
                "activation_enabled": activation_enabled,
            }
        if force:
            conn = self._get_conn()
            conn.execute("DELETE FROM ast_index")
            conn.commit()
        stats, candidates, count = self._walk_and_partition(
            max_files, force, activation_enabled
        )
        workers = self._resolve_worker_count(workers, candidates)
        if workers and workers >= 2 and len(candidates) >= 2:
            results = self._index_parallel(candidates, workers)
        else:
            results = [
                _worker_index_file((p, self.project_root, lang))
                for p, lang in candidates
            ]
        conn = self._get_conn()
        indexed_at = datetime.now(timezone.utc).isoformat()
        _commit_index_results(
            conn, results, stats, self._insert_index_row, indexed_at, activation_enabled
        )
        stats["total_files"] = count
        stats["workers"] = workers
        if stats["indexed"] > 0:
            self._post_index_backfill(stats)
        return stats

    def _walk_and_partition(
        self, max_files: int, force: bool, activation_enabled: bool
    ) -> tuple[dict[str, Any], list[tuple[str, str]], int]:
        """Walk source files and partition into (stats, candidates, count)."""
        from . import _ast_cache_indexer as _indexer

        return _indexer.walk_and_partition(
            self,
            self._get_conn(),
            max_files,
            force,
            activation_enabled,
            _walk_source_files,
            _language_from_ext,
            _AST_CACHE_EXTRACTOR_VERSION,
            _make_error_entry,
        )

    @staticmethod
    def _resolve_worker_count(workers: int | None, candidates: list[Any]) -> int:
        """Pick worker count from env/arg/auto-detection."""
        env_workers = os.environ.get("TSA_INDEX_WORKERS")
        if env_workers is not None:
            try:
                workers = int(env_workers)
            except ValueError:
                pass
        if workers is None:
            _cpu = os.cpu_count() or 4
            workers = 0 if len(candidates) < 64 else max(2, _cpu - 1)
        return workers

    def _post_index_backfill(self, stats: dict[str, Any]) -> None:
        """Run cross-file and Synapse backfills after indexing."""
        try:
            stats["cross_file_backfill"] = self.backfill_cross_file_edges()
        except Exception:
            logger.debug("cross-file backfill failed", exc_info=True)
        try:
            synapse = self._run_synapse_backfill()
            if synapse is not None:
                stats["synapse_backfill"] = synapse
        except Exception:
            logger.debug("synapse backfill failed", exc_info=True)
        indexed_files = [
            str(entry["file"])
            for entry in stats.get("files", [])
            if entry.get("status") == "indexed"
        ]
        # ``insert_index_row`` already writes every file's graph edges during
        # commit when FTS5 is available (the common path) — re-deriving them
        # here is pure duplicate work: ~85 s on django (47 % of total index
        # time) for an IDENTICAL edge set (244,590 rows either way, verified).
        # Only refresh when insert could NOT have written them (no FTS5), where
        # this pass is the sole edge writer.
        self._maybe_refresh_edge_store(stats, indexed_files)
        try:
            unresolved = self._run_unresolved_refs_backfill()
            if unresolved is not None:
                stats["unresolved_refs_backfill"] = unresolved
        except Exception:
            logger.debug("unresolved refs backfill failed", exc_info=True)
        # Record that resolution has converged for this index state so a later
        # cold ensure_indexed() can skip a redundant resolve-only pass (~40 s
        # no-op) instead of blocking the first retrieval.
        try:
            from ._ast_cache_unresolved import mark_resolution_converged

            mark_resolution_converged(self._get_conn())
        except Exception:
            logger.debug("could not mark resolution converged", exc_info=True)

    def _maybe_refresh_edge_store(
        self, stats: dict[str, Any], indexed_files: list[str]
    ) -> None:
        if self.fts5_available:
            return
        try:
            stats["edge_store_refresh"] = self._refresh_graph_edges_from_cache(
                indexed_files
            )
        except Exception:
            logger.debug("edge store refresh failed", exc_info=True)

    def _refresh_graph_edges_from_cache(
        self, file_paths: list[str] | None = None
    ) -> dict[str, int]:
        """Refresh unified EdgeStore rows from persisted AST cache rows."""
        from . import _ast_cache_write as _write

        conn = self._get_conn()
        if file_paths is None:
            rows = conn.execute(
                "SELECT file_path, language, symbols_json, imports_json FROM ast_index"
            ).fetchall()
        else:
            rows = []
            for rel_path in file_paths:
                row = conn.execute(
                    "SELECT file_path, language, symbols_json, imports_json "
                    "FROM ast_index WHERE file_path = ?",
                    (rel_path,),
                ).fetchone()
                if row is not None:
                    rows.append(row)
        refreshed = errors = 0
        for row in rows:
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
                refreshed += 1
            except (json.JSONDecodeError, sqlite3.OperationalError):
                errors += 1
        conn.commit()
        return {"files": refreshed, "errors": errors}

    def _run_unresolved_refs_backfill(self) -> dict[str, int] | None:
        """Resolve persisted unresolved_refs rows into EdgeStore edges."""
        from . import _ast_cache_unresolved as _unresolved

        return _unresolved.resolve_unresolved_refs(self._get_conn())

    def _index_parallel(
        self, candidates: list[tuple[str, str]], workers: int
    ) -> list[dict[str, Any]]:
        """Dispatch parse+extract to a spawn process pool (safe on macOS/Linux)."""
        from multiprocessing import get_context

        from ._ast_extraction import _init_worker_parser

        ctx = get_context("spawn")
        args_iter = [(p, self.project_root, lang) for p, lang in candidates]
        with ctx.Pool(processes=workers, initializer=_init_worker_parser) as pool:
            return list(pool.imap_unordered(_worker_index_file, args_iter, chunksize=8))

    def _insert_index_row(
        self,
        r: dict[str, Any],
        indexed_at: str,
        *,
        include_activation: bool = True,
    ) -> None:
        """Write one worker result to SQLite (main table + optional FTS5)."""
        from . import _ast_cache_indexer as _indexer

        _indexer.insert_index_row(
            self,
            self._get_conn(),
            r,
            indexed_at,
            _AST_CACHE_EXTRACTOR_VERSION,
            include_activation,
        )

    @staticmethod
    def _clear_activation_for_file(conn: sqlite3.Connection, rel_path: str) -> None:
        """Drop stale activation rows when project indexing runs in fast mode."""
        _clear_activation_for_file_fn(conn, rel_path)

    def lookup(self, file_path: str) -> dict[str, Any] | None:
        return _lookup(self._get_conn(), file_path, self.project_root)

    def search_symbols(
        self, query: str, language: str | None = None
    ) -> list[dict[str, Any]]:
        # G4: use ranked search for queries >= 2 chars (BM25 ordering).
        if self._fts5_available:
            return self.fts_search_ranked(query, language=language)
        return self._search_symbols_linear(query, language)

    def search_symbols_cascade(
        self,
        query: str,
        language: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Three-tier cascading search: exact → FTS5 BM25 → LIKE.

        Returns deduplicated results ordered by relevance with a
        ``match_tier`` field indicating which tier found each result.
        """
        return _search_symbols_cascade(
            self._get_conn(),
            query,
            language,
            limit,
            bool(self._fts5_available),
        )

    def fts_search(
        self,
        query: str,
        language: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if not self._fts5_available:
            return self._search_symbols_linear(query, language)
        return _fts_search(self._get_conn(), query, language, limit)

    def fts_search_ranked(
        self,
        query: str,
        language: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """BM25-ranked FTS5 symbol search.

        Falls back to linear search when FTS5 is unavailable or query is too short.
        Results include a ``relevance_score`` field in [0.0, 1.0].
        """
        if not self._fts5_available or len(query) < 2:
            return self._search_symbols_linear(query, language)
        return _fts_search_ranked(self._get_conn(), query, language, limit)

    def _search_symbols_linear(
        self, query: str, language: str | None = None
    ) -> list[dict[str, Any]]:
        return _search_symbols_linear(self._get_conn(), query, language)

    def get_stats(self) -> dict[str, Any]:
        return _get_stats(self._get_conn(), self._fts5_available, self.db_path)

    def invalidate(self, file_path: str) -> bool:
        return _invalidate(
            self._get_conn(), file_path, self.project_root, self._fts5_available
        )

    def get_call_edges(self) -> list[dict[str, Any]]:
        """Return all stored call edges from the cache.

        CALLS rows now live in the unified ``edges`` table. Every legacy scalar
        is a real promoted column (B1.3): ``caller_name``/``callee_name``/
        ``file_path``/``caller_line``/``callee_full``/``callee_line``/
        ``language``. ``file_path`` is the caller's file (== legacy
        ``caller_file``). Aliases reproduce the exact dict keys the legacy SELECT
        yielded, so the three consumers (cross_file_resolver / call_graph /
        dependency_matrix) see identical rows.
        """
        try:
            _conn = self._get_conn()
            _cur = _conn.execute(
                "SELECT caller_name, "
                "file_path AS caller_file, "
                "caller_line, "
                "callee_name, "
                "callee_full, "
                "callee_line, "
                "file_path, "
                "language "
                "FROM edges WHERE kind = 'calls'"
            )
            rows = _cur.fetchall()
        except sqlite3.OperationalError:
            return []
        return [dict(row) for row in rows]

    def get_resolved_call_edges(self) -> list[dict[str, Any]]:
        """Return CALLS edges paired with their cross-file-resolved target file.

        ``get_call_edges()`` deliberately freezes its key set to the legacy
        ``ast_call_edges`` SELECT (B1.2b byte-for-byte parity) and therefore
        omits the resolved-target column. This reader instead surfaces the
        persisted ``callee_resolved_file`` (populated by the synapse /
        cross-file backfill on full index) so callers can attribute a call to
        the file that actually defines the callee. Each row is
        ``{"caller_file": <caller's file>, "callee_resolved_file": <target>}``;
        ``callee_resolved_file`` is ``""`` for calls the backfill could not
        resolve cross-file. Like the other unified-edges readers this is an
        O(1) index-backed read — no re-resolution.
        """
        try:
            _conn = self._get_conn()
            _cur = _conn.execute(
                "SELECT file_path AS caller_file, callee_resolved_file "
                "FROM edges WHERE kind = 'calls'"
            )
            rows = _cur.fetchall()
        except sqlite3.OperationalError:
            return []
        return [dict(row) for row in rows]

    def get_functions(self) -> list[dict[str, Any]]:
        """Return all indexed function definitions."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT file_path, symbols_json, language FROM ast_index"
        ).fetchall()
        return [
            _build_function_entry(sym, row["file_path"], row["language"])
            for row in rows
            for sym in json.loads(row["symbols_json"]).get("symbols", [])
            if sym.get("kind") in ("function", "method")
        ]

    def get_functions_by_file(self, file_path: str) -> list[dict[str, Any]]:
        """Return indexed function definitions for a specific file."""
        row = (
            self._get_conn()
            .execute(
                "SELECT symbols_json, language FROM ast_index WHERE file_path = ?",
                (file_path,),
            )
            .fetchone()
        )
        if row is None:
            return []
        return [
            _build_function_entry(sym, file_path, row["language"])
            for sym in json.loads(row["symbols_json"]).get("symbols", [])
            if sym.get("kind") in ("function", "method")
        ]

    def get_imports(self) -> dict[str, Any]:
        """Return per-file import lists from the cache."""
        conn = self._get_conn()
        rows = conn.execute("SELECT file_path, imports_json FROM ast_index").fetchall()
        return {row["file_path"]: json.loads(row["imports_json"]) for row in rows}

    def get_symbols_by_kind(
        self, kind: str, limit: int = 50000
    ) -> list[dict[str, Any]]:
        """Return all indexed symbols of a given kind (e.g. 'class', 'variable').

        Reads the flat ``ast_symbol_rows`` table directly. Used by the Hyphae
        evaluator to enumerate non-function symbols (.class/.struct/.interface)
        that ``get_functions`` does not cover. Returns ``[]`` if the table is
        absent (older schema).
        """
        import sqlite3 as _sqlite3

        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT name, file_path, line, end_line, language "
                "FROM ast_symbol_rows WHERE kind = ? LIMIT ?",
                (kind, limit),
            ).fetchall()
        except _sqlite3.OperationalError:
            return []
        return [
            {
                "name": r["name"],
                "file": r["file_path"],
                "line": r["line"],
                "end_line": r["end_line"],
                "language": r["language"],
                "kind": kind,
            }
            for r in rows
        ]

    def query_edges(
        self,
        kind: str,
        caller_name: str | None = None,
        callee_name: str | None = None,
        limit: int = 10000,
    ) -> list[dict[str, Any]]:
        """Query the unified ``edges`` table by edge kind and endpoint name.

        ``kind`` is one of ``calls`` / ``contains`` / ``extends`` / ``imports``.
        Filtering by ``caller_name`` (source) or ``callee_name`` (target) lets
        the Hyphae evaluator drive edge pseudo-classes reverse-style. Returns
        ``[]`` if the table is absent (older schema).
        """
        import sqlite3 as _sqlite3

        sql = (
            "SELECT caller_name, callee_name, file_path, caller_line, "
            "callee_line, callee_resolved_file FROM edges WHERE kind = ?"
        )
        params: list[Any] = [kind]
        if caller_name is not None:
            sql += " AND caller_name = ?"
            params.append(caller_name)
        if callee_name is not None:
            sql += " AND callee_name = ?"
            params.append(callee_name)
        sql += " LIMIT ?"
        params.append(limit)
        try:
            rows = self._get_conn().execute(sql, params).fetchall()
        except _sqlite3.OperationalError:
            return []
        return [dict(r) for r in rows]

    def query_callers(
        self,
        callee_name: str,
        callee_file: str | None = None,
        max_depth: int = 1,
    ) -> list[dict[str, Any]]:
        """SQL-native callers lookup via BFS on unified edges, with legacy fallback."""
        if callee_file:
            callee_file = callee_file.replace("\\", "/")
        try:
            from .graph.edge_store import EdgeKind, EdgeStore

            store = EdgeStore(self._get_conn(), ensure_schema=False)
            if store.has_edges(EdgeKind.CALLS):
                return store.query_callers(callee_name, callee_file, max_depth)
        except sqlite3.OperationalError:
            pass
        try:
            return _bfs_callers_impl(
                self._get_conn(), callee_name, callee_file, max_depth
            )
        except sqlite3.OperationalError:
            return []

    def query_callees(
        self,
        caller_name: str,
        caller_file: str | None = None,
        max_depth: int = 1,
    ) -> list[dict[str, Any]]:
        """SQL-native callees lookup via BFS on unified edges, with legacy fallback."""
        if caller_file:
            caller_file = caller_file.replace("\\", "/")
        try:
            from .graph.edge_store import EdgeKind, EdgeStore

            store = EdgeStore(self._get_conn(), ensure_schema=False)
            if store.has_edges(EdgeKind.CALLS):
                return store.query_callees(caller_name, caller_file, max_depth)
        except sqlite3.OperationalError:
            pass
        try:
            return _bfs_callees_impl(
                self._get_conn(), caller_name, caller_file, max_depth
            )
        except sqlite3.OperationalError:
            return []

    def has_call_edges(self) -> bool:
        """Check whether the cache contains any call edge data.

        CALLS rows live in the unified ``edges`` table (B1.3 — no
        ast_call_edges), so this is a single index-backed kind probe.
        """
        try:
            from .graph.edge_store import EdgeKind, EdgeStore

            return EdgeStore(self._get_conn(), ensure_schema=False).has_edges(
                EdgeKind.CALLS
            )
        except sqlite3.OperationalError:
            return False

    def get_cross_file_resolver(self) -> Any:
        """Get (or build) the CrossFileResolver for import-aware resolution."""
        resolver = getattr(self, "_cross_file_resolver", None)
        if resolver is None:
            from .cross_file_resolver import CrossFileResolver

            resolver = CrossFileResolver(self)
            self._cross_file_resolver = resolver
        return resolver

    def query_callers_enhanced(
        self,
        callee_name: str,
        callee_file: str | None = None,
        max_depth: int = 1,
    ) -> list[dict[str, Any]]:
        """Enhanced callers lookup with cross-file import resolution."""
        return _query_callers_enhanced(self, callee_name, callee_file, max_depth)

    def query_callees_enhanced(
        self,
        caller_name: str,
        caller_file: str | None = None,
        max_depth: int = 1,
    ) -> list[dict[str, Any]]:
        """Enhanced callees lookup with cross-file import resolution."""
        return _query_callees_enhanced(self, caller_name, caller_file, max_depth)

    def backfill_cross_file_edges(self) -> dict[str, Any]:
        """Resolve cross-file call edges and persist callee_resolved_file."""
        return _backfill_cross_file_edges(self, self._get_conn())

    def get_cross_file_stats(self) -> dict[str, Any]:
        """Return cross-file edge resolution statistics."""
        return _get_cross_file_stats(self._get_conn())

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None


def _walk_source_files(project_root: str) -> Iterator[str]:
    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = [
            d for d in dirnames if d not in _EXCLUDE_DIRS and not d.startswith(".")
        ]
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext in _EXT_TO_LANG:
                yield os.path.join(dirpath, fname)
