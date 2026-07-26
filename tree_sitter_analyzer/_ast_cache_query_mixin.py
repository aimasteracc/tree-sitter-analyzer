"""Lookup and symbol search methods for :class:`ASTCache`."""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

from ._ast_cache_database_mixin import ASTCacheSurface
from .cache.helpers import _build_function_entry
from .cache.query import fts_search as _fts_search
from .cache.query import fts_search_ranked as _fts_search_ranked
from .cache.query import get_stats as _get_stats
from .cache.query import invalidate as _invalidate
from .cache.query import lookup as _lookup
from .cache.query import search_symbols_linear as _search_symbols_linear
from .cache.search import search_symbols_cascade as _search_symbols_cascade

logger = logging.getLogger(__name__)


class ASTCacheQueryMixin(ASTCacheSurface):
    """Stable lookup and symbol-search API."""

    def lookup(self, file_path: str) -> dict[str, Any] | None:
        return _lookup(self._get_conn(), file_path, self.project_root)

    def search_symbols(
        self,
        query: str,
        language: str | None = None,
    ) -> list[dict[str, Any]]:
        if self._fts5_available:
            return self.fts_search_ranked(query, language=language)
        return self._search_symbols_linear(query, language)

    def search_symbols_cascade(
        self,
        query: str,
        language: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Search exact, FTS5 BM25, then LIKE with stable deduplication."""
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
            return self._search_symbols_linear(query, language)[:limit]
        return _fts_search(self._get_conn(), query, language, limit)

    def fts_search_ranked(
        self,
        query: str,
        language: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return BM25-ranked results with a linear fallback."""
        if not self._fts5_available or len(query) < 2:
            return self._search_symbols_linear(query, language)[:limit]
        return _fts_search_ranked(self._get_conn(), query, language, limit)

    def _search_symbols_linear(
        self,
        query: str,
        language: str | None = None,
    ) -> list[dict[str, Any]]:
        return _search_symbols_linear(self._get_conn(), query, language)

    def get_stats(self) -> dict[str, Any]:
        return _get_stats(self._get_conn(), self._fts5_available, self.db_path)

    def invalidate(self, file_path: str) -> bool:
        removed = _invalidate(
            self._get_conn(),
            file_path,
            self.project_root,
            self._fts5_available,
        )
        if removed:
            try:
                from .knowledge_graph.stores import LadybugKnowledgeGraphStore

                LadybugKnowledgeGraphStore(self.project_root).remove_if_exists()
            except Exception:
                logger.debug("could not invalidate Ladybug mirror", exc_info=True)
        return removed

    def get_functions(self) -> list[dict[str, Any]]:
        """Return every indexed function and method definition."""
        rows = (
            self._get_conn()
            .execute("SELECT file_path, symbols_json, language FROM ast_index")
            .fetchall()
        )
        return [
            _build_function_entry(symbol, row["file_path"], row["language"])
            for row in rows
            for symbol in json.loads(row["symbols_json"]).get("symbols", [])
            if symbol.get("kind") in ("function", "method")
        ]

    def get_functions_by_file(self, file_path: str) -> list[dict[str, Any]]:
        """Return indexed function definitions for one file."""
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
            _build_function_entry(symbol, file_path, row["language"])
            for symbol in json.loads(row["symbols_json"]).get("symbols", [])
            if symbol.get("kind") in ("function", "method")
        ]

    def get_imports(self) -> dict[str, Any]:
        """Return per-file import lists."""
        rows = (
            self._get_conn()
            .execute("SELECT file_path, imports_json FROM ast_index")
            .fetchall()
        )
        return {row["file_path"]: json.loads(row["imports_json"]) for row in rows}

    def get_symbols_by_kind(
        self,
        kind: str,
        limit: int = 50000,
    ) -> list[dict[str, Any]]:
        """Return flat symbol rows for one kind."""
        try:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT name, file_path, line, end_line, language "
                "FROM ast_symbol_rows WHERE kind = ? LIMIT ?",
                (kind, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
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
