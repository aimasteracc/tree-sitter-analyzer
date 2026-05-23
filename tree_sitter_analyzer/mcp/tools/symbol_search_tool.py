#!/usr/bin/env python3
"""
CodeGraph Symbol Search MCP Tool — FTS5-powered instant symbol lookup.

Leverages the pre-indexed AST cache (SQLite + FTS5) for sub-millisecond
symbol search across an entire project. Replaces grep-based symbol search
with structured, indexed queries — CodeGraph parity.

Falls back to a linear scan when FTS5 is unavailable or the cache is empty.
"""

from __future__ import annotations

import fnmatch
from typing import Any

from ...utils import setup_logger
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class CodeGraphSymbolSearchTool(BaseMCPTool):
    """MCP Tool for FTS5-powered instant symbol search (CodeGraph parity)."""

    def __init__(self, project_root: str | None = None) -> None:
        self._cache: Any = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._cache = None

    def _get_cache(self) -> Any:
        if self._cache is None:
            if not self.project_root:
                raise ValueError("Project root not set. Call set_project_path first.")
            from ...ast_cache import ASTCache

            self._cache = ASTCache(self.project_root)
        return self._cache

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_symbol_search",
            "description": (
                "Instant FTS5-powered symbol search across pre-indexed project (CodeGraph parity). "
                "Finds classes, functions, methods, variables by name in microseconds. "
                "Supports exact, wildcard (*), and fuzzy (~) matching. "
                "Requires ast_cache index to be built first (run ast_cache mode=index). "
                "No other tool provides indexed cross-file symbol lookup."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Symbol search query. Plain name for exact match, "
                        "* wildcards for pattern match (e.g. 'handle_*'), "
                        "~ prefix for fuzzy substring (e.g. '~analyz')"
                    ),
                },
                "language": {
                    "type": "string",
                    "description": "Filter by language (e.g. 'python', 'javascript')",
                },
                "kind": {
                    "type": "string",
                    "enum": ["function", "class", "variable", "import", "any"],
                    "description": "Filter by symbol kind (default: any)",
                    "default": "any",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default: 50)",
                    "default": 50,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format: 'toon' (default, token-efficient) or 'json'",
                    "default": "toon",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if not arguments.get("query"):
            raise ValueError("query is required")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        query = arguments["query"]
        language = arguments.get("language")
        kind = arguments.get("kind", "any")
        limit = arguments.get("limit", 50)
        output_format = arguments.get("output_format", "toon")
        cache = self._get_cache()

        raw_results = self._search(cache, query, language, kind, limit)

        results = self._apply_kind_filter(raw_results, kind)

        by_file: dict[str, int] = {}
        for r in results:
            fp = r.get("file", "")
            by_file[fp] = by_file.get(fp, 0) + 1

        # Pain #25 (dogfood pass 3): symbol_search emitted no verdict.
        # NOT_FOUND on zero matches so agents stop chasing; INFO otherwise.
        result: dict[str, Any] = {
            "success": True,
            "verdict": "INFO" if results else "NOT_FOUND",
            "query": query,
            "match_count": len(results),
            "file_count": len(by_file),
            "results": results,
            "data_source": "fts5" if cache._fts5_available else "linear_scan",
        }
        if language:
            result["language_filter"] = language
        if kind != "any":
            result["kind_filter"] = kind

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)

    def _search(
        self,
        cache: Any,
        query: str,
        language: str | None,
        kind: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        if query.startswith("~"):
            return self._fuzzy_search(cache, query[1:], language, kind, limit)
        if "*" in query:
            return self._wildcard_search(cache, query, language, kind, limit)
        return self._exact_search(cache, query, language, kind, limit)

    def _exact_search(
        self,
        cache: Any,
        query: str,
        language: str | None,
        kind: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        if cache._fts5_available:
            fts_results = cache.fts_search(query, language=language, limit=limit * 3)
            if fts_results:
                return self._fts_to_results(fts_results, kind, limit)
        return self._linear_search(cache, query, language, kind, limit)

    def _fuzzy_search(
        self,
        cache: Any,
        substring: str,
        language: str | None,
        kind: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        sub_lower = substring.lower()
        all_results: list[dict[str, Any]] = []

        if cache._fts5_available:
            terms = substring.split()
            if terms:
                fts_query = " OR ".join(f'"{t}"' for t in terms)

                conn = cache._get_conn()
                if language:
                    rows = conn.execute(
                        """SELECT r.name, r.kind, r.file_path, r.language, r.line, r.end_line
                           FROM ast_symbols_fts f
                           JOIN ast_symbol_rows r ON f.rowid = r.id
                           WHERE ast_symbols_fts MATCH ? AND r.language = ?
                           ORDER BY rank LIMIT ?""",
                        (fts_query, language, limit * 5),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """SELECT r.name, r.kind, r.file_path, r.language, r.line, r.end_line
                           FROM ast_symbols_fts f
                           JOIN ast_symbol_rows r ON f.rowid = r.id
                           WHERE ast_symbols_fts MATCH ?
                           ORDER BY rank LIMIT ?""",
                        (fts_query, limit * 5),
                    ).fetchall()
                for row in rows:
                    if sub_lower in row["name"].lower():
                        all_results.append(
                            {
                                "name": row["name"],
                                "kind": row["kind"],
                                "file": row["file_path"],
                                "language": row["language"],
                                "line": row["line"],
                                "end_line": row["end_line"],
                            }
                        )
                    if len(all_results) >= limit:
                        return all_results
                if all_results:
                    return all_results

        return self._linear_search(cache, substring, language, kind, limit)

    def _wildcard_search(
        self,
        cache: Any,
        pattern: str,
        language: str | None,
        kind: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        import json

        conn = cache._get_conn()
        pattern_lower = pattern.lower()

        if language:
            rows = conn.execute(
                "SELECT file_path, symbols_json, language FROM ast_index WHERE language = ?",
                (language,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT file_path, symbols_json, language FROM ast_index"
            ).fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            symbols = json.loads(row["symbols_json"])
            for sym in symbols.get("symbols", []):
                name = sym.get("name", sym.get("text", ""))
                if fnmatch.fnmatch(name.lower(), pattern_lower):
                    results.append(
                        {
                            "name": name,
                            "kind": sym.get("kind", "unknown"),
                            "file": row["file_path"],
                            "language": row["language"],
                            "line": sym.get("line", 0),
                            "end_line": sym.get("end_line", 0),
                        }
                    )
                    if len(results) >= limit:
                        return results
        return results

    def _linear_search(
        self,
        cache: Any,
        query: str,
        language: str | None,
        kind: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        results = cache.search_symbols(query, language=language)
        filtered = self._apply_kind_filter(results, kind)
        return filtered[:limit]

    def _fts_to_results(
        self,
        fts_results: list[dict[str, Any]],
        kind: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for r in fts_results:
            results.append(
                {
                    "name": r.get("name", ""),
                    "kind": r.get("kind", ""),
                    "file": r.get("file", ""),
                    "language": r.get("language", ""),
                    "line": r.get("line", 0),
                    "end_line": r.get("end_line", 0),
                }
            )
            if len(results) >= limit:
                break
        return self._apply_kind_filter(results, kind)

    def _apply_kind_filter(
        self, results: list[dict[str, Any]], kind: str
    ) -> list[dict[str, Any]]:
        if kind == "any":
            return results
        return [r for r in results if r.get("kind", "") == kind]
