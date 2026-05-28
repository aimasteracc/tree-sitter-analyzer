"""Shared backend for CodeGraph symbol and relation queries."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .semantic_search import SemanticSymbolSearch

_DEFINITION_KINDS = frozenset({"function", "class", "method", "variable"})


class CodeGraphQueryBackend:
    """Thin facade over AST-cache-backed symbol and relation lookups."""

    def __init__(self, cache: Any) -> None:
        self.cache = cache

    def resolve_definitions(self, symbol: str) -> list[dict[str, Any]]:
        results = self._fts_definitions(symbol)
        if not results:
            results = self._symbol_row_definitions(symbol)
        if not results:
            results = self._symbols_json_definitions(symbol)
        return results

    def relation_entries(
        self,
        *,
        direction: str,
        name: str,
        file_path: str,
        depth: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        if direction == "callers":
            rows = (
                self.cache.query_callers(name, file_path or None, max_depth=depth) or []
            )
            entries = [
                _row_symbol(row, "caller_name", "caller_file", "caller_line")
                for row in rows
            ]
        elif direction == "callees":
            rows = (
                self.cache.query_callees(name, file_path or None, max_depth=depth) or []
            )
            entries = [
                _row_symbol(row, "callee_name", "callee_file", "callee_line")
                for row in rows
            ]
        else:
            raise ValueError(f"unsupported relation direction: {direction}")
        # The caller owns final ordering/filtering/limit policy. Returning the
        # full normalized row set preserves existing source-first and noise
        # filtering semantics in the query surface.
        return [entry for entry in entries if entry["name"]]

    def semantic_symbols(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        return SemanticSymbolSearch(self.cache).search(query, limit=limit)

    def _fts_definitions(self, symbol: str) -> list[dict[str, Any]]:
        if not getattr(self.cache, "fts5_available", False):
            return []
        return [
            _definition(
                file_path=row.get("file", ""),
                name=row.get("name", ""),
                kind=row.get("kind", ""),
                line=row.get("line", 0),
                end_line=row.get("end_line", 0),
                language=row.get("language", ""),
                confidence=1.0,
            )
            for row in self.cache.fts_search(symbol, limit=50)
            if row.get("name") == symbol and row.get("kind") in _DEFINITION_KINDS
        ]

    def _symbol_row_definitions(self, symbol: str) -> list[dict[str, Any]]:
        conn = self.cache.get_conn()
        try:
            rows = conn.execute(
                """SELECT name, kind, file_path, language, line, end_line
                   FROM ast_symbol_rows
                   WHERE name = ? AND kind IN ('function', 'class', 'method', 'variable')
                   ORDER BY file_path, line""",
                (symbol,),
            ).fetchall()
        except sqlite3.Error:
            return []
        return [
            _definition(
                file_path=row["file_path"],
                name=row["name"],
                kind=row["kind"],
                line=row["line"],
                end_line=row["end_line"],
                language=row["language"],
                confidence=1.0,
            )
            for row in rows
        ]

    def _symbols_json_definitions(self, symbol: str) -> list[dict[str, Any]]:
        conn = self.cache.get_conn()
        try:
            rows = conn.execute(
                "SELECT file_path, symbols_json, language FROM ast_index"
            ).fetchall()
        except sqlite3.Error:
            return []
        results: list[dict[str, Any]] = []
        for row in rows:
            symbols = json.loads(row["symbols_json"])
            for sym in symbols.get("symbols", []):
                if sym.get("name") == symbol and sym.get("kind") in _DEFINITION_KINDS:
                    results.append(
                        _definition(
                            file_path=row["file_path"],
                            name=symbol,
                            kind=sym["kind"],
                            line=sym.get("line", 0),
                            end_line=sym.get("end_line", 0),
                            language=row["language"],
                            confidence=0.9,
                        )
                    )
        return results


def _row_symbol(
    row: dict[str, Any],
    name_key: str,
    file_key: str,
    line_key: str,
) -> dict[str, Any]:
    return {
        "name": row.get(name_key, ""),
        "file": row.get(file_key, ""),
        "line": row.get(line_key, 0),
        "end_line": row.get("end_line", row.get(line_key, 0)),
        "kind": "function",
        "language": row.get("language", ""),
        "depth": row.get("depth"),
    }


def _definition(
    *,
    file_path: str,
    name: str,
    kind: str,
    line: int,
    end_line: int,
    language: str,
    confidence: float,
) -> dict[str, Any]:
    return {
        "file": file_path,
        "name": name,
        "kind": kind,
        "line": line,
        "end_line": end_line,
        "language": language,
        "confidence": confidence,
    }
