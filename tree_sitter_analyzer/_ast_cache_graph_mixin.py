"""Call-edge readers and graph traversal for :class:`ASTCache`."""

from __future__ import annotations

import sqlite3
from typing import Any

from ._ast_cache_database_mixin import ASTCacheSurface
from .cache.callgraph_state import call_graph_built as _call_graph_built
from .cache.graph import bfs_callees as _bfs_callees_impl
from .cache.graph import bfs_callers as _bfs_callers_impl
from .cache.query import (
    backfill_cross_file_edges as _backfill_cross_file_edges,
)
from .cache.query import (
    get_cross_file_stats as _get_cross_file_stats,
)
from .cache.query import (
    query_callees_enhanced as _query_callees_enhanced,
)
from .cache.query import (
    query_callers_enhanced as _query_callers_enhanced,
)


def _edge_query(
    kind: str,
    caller_name: str | None,
    callee_name: str | None,
    limit: int,
) -> tuple[str, list[Any]]:
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
    return sql, params


def _edge_store_traversal(
    conn: sqlite3.Connection,
    direction: str,
    symbol_name: str,
    file_path: str | None,
    max_depth: int,
) -> list[dict[str, Any]] | None:
    try:
        from .graph.edge_store import EdgeKind, EdgeStore

        store = EdgeStore(conn, ensure_schema=False)
        if not store.has_edges(EdgeKind.CALLS):
            return None
        query = store.query_callers if direction == "callers" else store.query_callees
        return query(symbol_name, file_path, max_depth)
    except sqlite3.OperationalError:
        return None


class ASTCacheGraphMixin(ASTCacheSurface):
    """Stable call-edge and graph-query API."""

    def get_call_edges(self) -> list[dict[str, Any]]:
        """Return legacy-compatible CALLS rows from unified EdgeStore."""
        try:
            rows = (
                self._get_conn()
                .execute(
                    "SELECT caller_name, file_path AS caller_file, caller_line, "
                    "callee_name, callee_full, callee_line, file_path, language "
                    "FROM edges WHERE kind = 'calls'"
                )
                .fetchall()
            )
        except sqlite3.OperationalError:
            return []
        return [dict(row) for row in rows]

    def get_resolved_call_edges(self) -> list[dict[str, Any]]:
        """Return caller files paired with persisted resolved callee files."""
        try:
            rows = (
                self._get_conn()
                .execute(
                    "SELECT file_path AS caller_file, callee_resolved_file "
                    "FROM edges WHERE kind = 'calls'"
                )
                .fetchall()
            )
        except sqlite3.OperationalError:
            return []
        return [dict(row) for row in rows]

    def query_edges(
        self,
        kind: str,
        caller_name: str | None = None,
        callee_name: str | None = None,
        limit: int = 10000,
    ) -> list[dict[str, Any]]:
        """Query unified edges by kind and optional endpoint names."""
        sql, params = _edge_query(kind, caller_name, callee_name, limit)
        try:
            rows = self._get_conn().execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            return []
        return [dict(row) for row in rows]

    def query_callers(
        self,
        callee_name: str,
        callee_file: str | None = None,
        max_depth: int = 1,
    ) -> list[dict[str, Any]]:
        """Look up callers through EdgeStore with legacy BFS fallback."""
        normalized_file = callee_file.replace("\\", "/") if callee_file else None
        rows = _edge_store_traversal(
            self._get_conn(),
            "callers",
            callee_name,
            normalized_file,
            max_depth,
        )
        if rows is not None:
            return rows
        try:
            return _bfs_callers_impl(
                self._get_conn(),
                callee_name,
                normalized_file,
                max_depth,
            )
        except sqlite3.OperationalError:
            return []

    def query_callees(
        self,
        caller_name: str,
        caller_file: str | None = None,
        max_depth: int = 1,
    ) -> list[dict[str, Any]]:
        """Look up callees through EdgeStore with legacy BFS fallback."""
        normalized_file = caller_file.replace("\\", "/") if caller_file else None
        rows = _edge_store_traversal(
            self._get_conn(),
            "callees",
            caller_name,
            normalized_file,
            max_depth,
        )
        if rows is not None:
            return rows
        try:
            return _bfs_callees_impl(
                self._get_conn(),
                caller_name,
                normalized_file,
                max_depth,
            )
        except sqlite3.OperationalError:
            return []

    def has_call_edges(self) -> bool:
        """Return whether unified EdgeStore has CALLS rows."""
        try:
            from .graph.edge_store import EdgeKind, EdgeStore

            return EdgeStore(self._get_conn(), ensure_schema=False).has_edges(
                EdgeKind.CALLS
            )
        except sqlite3.OperationalError:
            return False

    def count_unresolved_callers(
        self,
        callee_name: str,
        callee_file: str | None = None,
    ) -> int | None:
        """Count in-scope CALLS edges into ``callee_name`` not known resolved.

        Returns ``None`` when the count cannot be read.  ``None`` is not ``0``:
        a failed read must not become a confident "every edge is resolved", so
        callers treat it as unknown rather than complete.
        """
        try:
            from .graph.edge_store import EdgeStore

            return EdgeStore(
                self._get_conn(), ensure_schema=False
            ).count_unresolved_callers(callee_name, callee_file)
        except sqlite3.OperationalError:
            return None

    def count_unresolved_calls_in_file(self, file_path: str) -> int | None:
        """Count unresolved CALLS edges originating in ``file_path``.

        Returns ``None`` when the count cannot be read, for the same reason
        :meth:`count_unresolved_callers` does: a failed read must not read as
        "no unresolved call here".
        """
        try:
            from .graph.edge_store import EdgeStore

            return EdgeStore(
                self._get_conn(), ensure_schema=False
            ).count_unresolved_calls_in_file(file_path)
        except sqlite3.OperationalError:
            return None

    def symbol_declaring_files(self, name: str) -> tuple[str, ...] | None:
        """Return the files declaring ``name``, or ``None`` when unreadable.

        Empty is the honest answer for a name this project does not define — a
        stdlib or framework symbol such as ``SystemExit``.  ``None`` is a failed
        read, and the two must not collapse: a caller reading a failure as an
        empty scope turns "I could not check" into "nothing unresolved here".
        """
        try:
            rows = self._get_conn().execute(
                "SELECT DISTINCT file_path FROM ast_symbol_rows WHERE name = ?",
                (name,),
            ).fetchall()
        except sqlite3.OperationalError:
            return None
        return tuple(str(row[0]) for row in rows if row[0])

    def call_graph_built(self) -> bool:
        """Return whether a completed call-graph build is recorded."""
        return _call_graph_built(self._get_conn())

    def get_cross_file_resolver(self) -> Any:
        """Return the lazily built import-aware resolver."""
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
        """Run import-aware caller lookup."""
        return _query_callers_enhanced(self, callee_name, callee_file, max_depth)

    def query_callees_enhanced(
        self,
        caller_name: str,
        caller_file: str | None = None,
        max_depth: int = 1,
    ) -> list[dict[str, Any]]:
        """Run import-aware callee lookup."""
        return _query_callees_enhanced(self, caller_name, caller_file, max_depth)

    def backfill_cross_file_edges(self) -> dict[str, Any]:
        """Resolve and persist cross-file call targets."""
        if getattr(self, "_generation_managed", False):
            from .cache.generation_indexing import mutate_published_cache

            return mutate_published_cache(
                self, lambda writable: writable.backfill_cross_file_edges()
            )
        return _backfill_cross_file_edges(self, self._get_conn())

    def get_cross_file_stats(self) -> dict[str, Any]:
        """Return cross-file resolution statistics."""
        return _get_cross_file_stats(self._get_conn())
