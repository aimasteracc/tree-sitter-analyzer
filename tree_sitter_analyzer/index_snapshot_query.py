"""绑定到单一认证索引 owner 的只读 AST 查询界面。"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, cast

from .cache.callgraph_state import call_graph_built as _call_graph_built
from .cache.graph import bfs_callees, bfs_callers
from .cache.helpers import _build_function_entry
from .cache.query import (
    fts_search,
    fts_search_ranked,
    search_symbols_linear,
)
from .cache.query import (
    lookup as cache_lookup,
)
from .cache.search import search_symbols_cascade
from .graph.edge_store import EdgeKind, EdgeStore


class CertifiedSnapshotCache:
    """所有操作均使用 owner 连接的窄只读适配器。"""

    strict_sql_errors = True

    def __init__(self, owner: Any) -> None:
        self._owner = owner
        self.project_root = str(owner.snapshot.canonical_root)
        self._fts5_available = bool(
            self.get_conn()
            .execute("SELECT 1 FROM sqlite_master WHERE name='ast_symbols_fts'")
            .fetchone()
        )

    def get_conn(self) -> sqlite3.Connection:
        self._owner.require_active()
        return cast(sqlite3.Connection, self._owner.connection)

    @property
    def fts5_available(self) -> bool:
        self._owner.require_active()
        return self._fts5_available

    def close(self) -> None:
        """连接由 owner 管理；此适配器没有独立关闭权。"""
        self._owner.require_active()

    def get_stats(self) -> dict[str, int]:
        row = self.get_conn().execute("SELECT COUNT(*) FROM ast_index").fetchone()
        return {"total_files": int(row[0])}

    def lookup(self, file_path: str) -> dict[str, Any] | None:
        return cache_lookup(self.get_conn(), file_path, self.project_root)

    def search_symbols_cascade(
        self, query: str, language: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        return search_symbols_cascade(
            self.get_conn(),
            query,
            language,
            limit,
            self.fts5_available,
            suppress_sql_errors=False,
        )

    def fts_search(
        self, query: str, language: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        if not self.fts5_available:
            return self._search_symbols_linear(query, language)[:limit]
        return fts_search(self.get_conn(), query, language, limit)

    def fts_search_ranked(
        self, query: str, language: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        if not self.fts5_available or len(query) < 2:
            return self._search_symbols_linear(query, language)[:limit]
        return fts_search_ranked(
            self.get_conn(),
            query,
            language,
            limit,
            suppress_sql_errors=False,
        )

    def _search_symbols_linear(
        self, query: str, language: str | None = None
    ) -> list[dict[str, Any]]:
        return search_symbols_linear(self.get_conn(), query, language)

    def get_functions(self) -> list[dict[str, Any]]:
        rows = self.get_conn().execute(
            "SELECT file_path, symbols_json, language FROM ast_index"
        )
        return [
            _build_function_entry(symbol, row["file_path"], row["language"])
            for row in rows
            for symbol in json.loads(row["symbols_json"]).get("symbols", [])
            if symbol.get("kind") in ("function", "method")
        ]

    def get_symbols_by_kind(
        self, kind: str, limit: int = 50000
    ) -> list[dict[str, Any]]:
        rows = self.get_conn().execute(
            "SELECT name, file_path, line, end_line, language "
            "FROM ast_symbol_rows WHERE kind=? LIMIT ?",
            (kind, limit),
        )
        return [
            {
                "name": row["name"],
                "file": row["file_path"],
                "line": row["line"],
                "end_line": row["end_line"],
                "language": row["language"],
                "kind": kind,
            }
            for row in rows
        ]

    def get_imports(self) -> dict[str, list[str]]:
        rows = self.get_conn().execute("SELECT file_path, imports_json FROM ast_index")
        result: dict[str, list[str]] = {}
        for row in rows:
            values = json.loads(row["imports_json"])
            result[row["file_path"]] = [
                value.get("text", "") if isinstance(value, dict) else value
                for value in values
            ]
        return result

    def get_call_edges(self) -> list[dict[str, Any]]:
        rows = self.get_conn().execute(
            "SELECT caller_name, file_path AS caller_file, caller_line, "
            "callee_name, callee_full, callee_line, file_path, language "
            "FROM edges WHERE kind='calls'"
        )
        return [dict(row) for row in rows]

    def query_edges(
        self,
        kind: str,
        caller_name: str | None = None,
        callee_name: str | None = None,
        limit: int = 10000,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM edges WHERE kind=?"
        params: list[Any] = [kind]
        if caller_name is not None:
            sql += " AND caller_name=?"
            params.append(caller_name)
        if callee_name is not None:
            sql += " AND callee_name=?"
            params.append(callee_name)
        sql += " LIMIT ?"
        params.append(limit)
        return [dict(row) for row in self.get_conn().execute(sql, params)]

    def has_call_edges(self) -> bool:
        return bool(
            EdgeStore(self.get_conn(), ensure_schema=False).has_edges(EdgeKind.CALLS)
        )

    def query_callers(
        self, callee_name: str, callee_file: str | None = None, max_depth: int = 1
    ) -> list[dict[str, Any]]:
        normalized = callee_file.replace("\\", "/") if callee_file else None
        store = EdgeStore(self.get_conn(), ensure_schema=False)
        if store.has_edges(EdgeKind.CALLS):
            return store.query_callers(callee_name, normalized, max_depth)
        return bfs_callers(self.get_conn(), callee_name, normalized, max_depth)

    def query_callees(
        self, caller_name: str, caller_file: str | None = None, max_depth: int = 1
    ) -> list[dict[str, Any]]:
        normalized = caller_file.replace("\\", "/") if caller_file else None
        store = EdgeStore(self.get_conn(), ensure_schema=False)
        if store.has_edges(EdgeKind.CALLS):
            return store.query_callees(caller_name, normalized, max_depth)
        return bfs_callees(self.get_conn(), caller_name, normalized, max_depth)

    def call_graph_built(self) -> bool:
        # PR #1491：外层 owner 已安装共同 deadline，内层探针不得清空它。
        return bool(
            _call_graph_built(
                self.get_conn(),
                deadline=self._owner.deadline,
                install_progress_handler=False,
            )
        )

    def _store(self) -> EdgeStore:
        return EdgeStore(self.get_conn(), ensure_schema=False)

    def count_unresolved_callers(
        self, name: str, file: str | None = None
    ) -> int | None:
        return cast(int | None, self._store().count_unresolved_callers(name, file))

    def unresolved_call_sites_in_file(
        self, file: str
    ) -> list[dict[str, object]] | None:
        return cast(
            list[dict[str, object]] | None,
            self._store().unresolved_call_sites_in_file(file),
        )

    def excluded_call_sites_in_file(self, file: str) -> list[dict[str, object]] | None:
        return cast(
            list[dict[str, object]] | None,
            self._store().excluded_call_sites_in_file(file),
        )

    def symbol_declaring_files(self, name: str) -> tuple[str, ...]:
        rows = self.get_conn().execute(
            "SELECT DISTINCT file_path FROM ast_symbol_rows WHERE name=?", (name,)
        )
        return tuple(str(row[0]) for row in rows if row[0])
