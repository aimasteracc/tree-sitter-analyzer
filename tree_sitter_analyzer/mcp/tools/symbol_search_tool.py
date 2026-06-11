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
import os
from typing import Any

from ..._ast_cache_query import _normalize_bm25 as _norm_bm25
from ...utils import setup_logger
from ...utils.test_detection import query_wants_tests, rank_tier
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)

# Default result cap. 50 source-rich hits made symbol search ~8 KB/call; 15 is
# plenty to judge relevance. Exported so the CLI (`--symbol-search-limit`) and
# the tool schema stay in sync — MCP/CLI parity (Codex P2 on #297).
DEFAULT_SYMBOL_SEARCH_LIMIT = 15


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
                "PRIMARY for 'where is X defined' or 'find symbol named X' — "
                "try this FIRST before reading files, grepping, or chaining "
                "navigate/resolve. Instant FTS5-powered symbol search across "
                "the pre-indexed project (CodeGraph parity). "
                "Finds classes, functions, methods, variables by name in microseconds. "
                "Supports exact, wildcard (*), and fuzzy (~) matching. "
                "Requires ast_cache index (run codegraph_autoindex mode=warm)."
            ),
            "inputSchema": self.get_tool_schema(),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
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
                    "description": "Max results (default: 15)",
                    "default": DEFAULT_SYMBOL_SEARCH_LIMIT,
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
        # Default 50 results, each carrying inline source context, made symbol
        # search ~8 KB/call — peers return location-only results. 15 source-rich
        # hits are plenty to judge relevance; callers raise ``limit`` for a
        # wider sweep.
        limit = arguments.get("limit", DEFAULT_SYMBOL_SEARCH_LIMIT)
        output_format = arguments.get("output_format", "toon")
        cache = self._get_cache()

        raw_results = self._search(cache, query, language, kind, limit)

        results = self._apply_kind_filter(raw_results, kind)
        # Issue #443: fold duplicate imports and rank definitions first
        results = self._fold_and_rank_results(results)
        self._add_source_context(results)
        # P2: inline a short verbatim body for the top matches so the agent
        # judges relevance from content, not coordinates — no Read per hit.
        search_deterrent = self._inline_match_bodies(cache, results)

        by_file: dict[str, int] = {}
        for r in results:
            # A folded import row represents ALL its importing files —
            # count each of them so file_count agrees with import_files
            # (Codex P2 on #492).
            for extra_fp in r.get("import_files", []):
                by_file[extra_fp] = by_file.get(extra_fp, 0) + 0
            fp = r.get("file", "")
            by_file[fp] = by_file.get(fp, 0) + 1

        # Pain #25 (dogfood pass 3): symbol_search emitted no verdict.
        # NOT_FOUND on zero matches so agents stop chasing; INFO otherwise.
        result: dict[str, Any] = {
            "success": True,
            "verdict": "INFO" if results else "NOT_FOUND",
            "query": query,
            "match_count": len(results),
            # Wave 1b (audit search-06): expose ``count`` too — it is the stable
            # canonical result-count key already emitted by search action=content,
            # so an agent can read ``count`` consistently across both search
            # actions. ``match_count`` stays for back-compat.
            "count": len(results),
            "file_count": len(by_file),
            "results": results,
            "data_source": "fts5" if cache.fts5_available else "linear_scan",
        }
        if results:
            if search_deterrent:
                result["next_step"] = search_deterrent
            else:
                result["next_step"] = (
                    f"Run structure action=explore symbols=[{query!r}] before "
                    "raw grep/read to bulk-fetch related symbols and concept matches."
                )
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
            raw = self._fuzzy_search(cache, query[1:], language, kind, limit)
        elif "*" in query:
            raw = self._wildcard_search(cache, query, language, kind, limit)
        else:
            raw = self._exact_search(cache, query, language, kind, limit)
        return self._demote_test_files(raw, query)

    def _exact_search(
        self,
        cache: Any,
        query: str,
        language: str | None,
        kind: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        if cache.fts5_available and hasattr(cache, "search_symbols_cascade"):
            cascade = cache.search_symbols_cascade(
                query, language=language, limit=limit * 3
            )
            if cascade:
                return self._fts_to_results(cascade, kind, limit)
        if cache.fts5_available:
            if len(query) >= 2:
                fts_results = cache.fts_search_ranked(
                    query, language=language, limit=limit * 3
                )
            else:
                fts_results = cache.fts_search(
                    query, language=language, limit=limit * 3
                )
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

        if cache.fts5_available:
            terms = substring.split()
            if terms:
                fts_query = " OR ".join(f'"{t}"' for t in terms)

                conn = cache.get_conn()
                # Weighted BM25 (name col 10x) — hardcoded constant, no injection risk.
                _SQL_FUZZY_LANG = (
                    "SELECT r.name, r.kind, r.file_path, r.language, r.line, r.end_line, "
                    "bm25(ast_symbols_fts, 10.0, 0.5, 0.5, 0.1) AS bm25_raw "
                    "FROM ast_symbols_fts f JOIN ast_symbol_rows r ON f.rowid = r.id "
                    "WHERE ast_symbols_fts MATCH ? AND r.language = ? "
                    "ORDER BY bm25_raw LIMIT ?"
                )
                _SQL_FUZZY_ANY = (
                    "SELECT r.name, r.kind, r.file_path, r.language, r.line, r.end_line, "
                    "bm25(ast_symbols_fts, 10.0, 0.5, 0.5, 0.1) AS bm25_raw "
                    "FROM ast_symbols_fts f JOIN ast_symbol_rows r ON f.rowid = r.id "
                    "WHERE ast_symbols_fts MATCH ? "
                    "ORDER BY bm25_raw LIMIT ?"
                )
                if language:
                    rows = conn.execute(
                        _SQL_FUZZY_LANG,
                        (fts_query, language, limit * 5),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        _SQL_FUZZY_ANY,
                        (fts_query, limit * 5),
                    ).fetchall()
                # Min-max normalize BM25 scores across this result set.
                raw_scores = [row["bm25_raw"] for row in rows if row["bm25_raw"] < 0]
                worst = max(raw_scores) if raw_scores else -1.0
                best = min(raw_scores) if raw_scores else worst
                for row in rows:
                    if sub_lower in row["name"].lower():
                        entry: dict[str, Any] = {
                            "name": row["name"],
                            "kind": row["kind"],
                            "file": row["file_path"],
                            "language": row["language"],
                            "line": row["line"],
                            "end_line": row["end_line"],
                        }
                        raw = row["bm25_raw"]
                        entry["relevance_score"] = round(
                            _norm_bm25(raw, worst, best), 3
                        )
                        all_results.append(entry)
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

        conn = cache.get_conn()
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
            entry: dict[str, Any] = {
                "name": r.get("name", ""),
                "kind": r.get("kind", ""),
                "file": r.get("file", ""),
                "language": r.get("language", ""),
                "line": r.get("line", 0),
                "end_line": r.get("end_line", 0),
            }
            if "relevance_score" in r:
                entry["relevance_score"] = r["relevance_score"]
            if "match_tier" in r:
                entry["match_tier"] = r["match_tier"]
            results.append(entry)
            if len(results) >= limit:
                break
        return self._apply_kind_filter(results, kind)

    def _apply_kind_filter(
        self, results: list[dict[str, Any]], kind: str
    ) -> list[dict[str, Any]]:
        if kind == "any":
            return results
        return [r for r in results if r.get("kind", "") == kind]

    def _demote_test_files(
        self,
        results: list[dict[str, Any]],
        query: str,
    ) -> list[dict[str, Any]]:
        """Apply test-file demotion as primary sort key.

        Consistent with fts_search_ranked and semantic_search.SemanticSymbolSearch.
        Covers cascade (exact-tier) and FTS5/fuzzy/wildcard paths.
        PRIMARY: rank_tier (0=prod, 1=test) unless query asks about tests.
        SECONDARY: relevance_score descending (existing ranking preserved).
        TERTIARY: file + line + name for a fully deterministic stable order.
        """
        if not results:
            return results
        wants_tests = query_wants_tests(query)
        return sorted(
            results,
            key=lambda r: (
                rank_tier(str(r.get("file", "")), wants_tests=wants_tests),
                -(r.get("relevance_score") or 0.0),
                str(r.get("file", "")),
                int(r.get("line") or 0),
                str(r.get("name", "")),
            ),
        )

    def _inline_match_bodies(
        self,
        cache: Any,
        results: list[dict[str, Any]],
    ) -> str | None:
        """P2: attach a short body summary to the top matches (in place).

        Returns the deterrent ``next_step`` when at least one body inlined,
        else ``None``.  Best-effort: any failure leaves results coordinate-only.
        """
        if not results or cache is None or not self.project_root:
            return None
        try:
            from . import symbol_body_inline as sbi

            enriched = sbi.inline_search_summaries(self.project_root, cache, results)
            if not any("body" in r for r in enriched):
                return None
            results[:] = enriched
            return sbi.SEARCH_DETERRENT
        except Exception as exc:  # best-effort enrichment
            logger.debug(f"Search body inlining failed: {exc}")
            return None

    def _add_source_context(self, results: list[dict[str, Any]]) -> None:
        for r in results:
            line = int(r.get("line", 0) or 0)
            if line < 1:
                continue
            text = self._read_line(str(r.get("file", "")), line)
            if text:
                r["code"] = text.strip()[:300]

    def _read_line(self, file_path: str, line: int) -> str:
        if not self.project_root or not file_path:
            return ""
        path = (
            file_path
            if os.path.isabs(file_path)
            else os.path.join(self.project_root, file_path)
        )
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                for idx, text in enumerate(fh, start=1):
                    if idx == line:
                        return text
        except OSError:
            return ""
        return ""

    def _fold_and_rank_results(
        self, results: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Issue #443: fold duplicate imports, rank definitions first.

        Returns a new list where:
        1. Non-import kinds (function, class, method, variable) come first
        2. Imports are folded: duplicate imports of the same symbol become a
           single entry with import_count and import_files list
        3. Within each group, original order/ranking is preserved
        """
        if not results:
            return results

        non_imports: list[dict[str, Any]] = []
        imports_by_name: dict[str, dict[str, Any]] = {}

        for result in results:
            if result.get("kind") == "import":
                # Fold imports by name
                name = result.get("name", "")
                if name not in imports_by_name:
                    # Create folded entry: copy the result but prepare for accumulation
                    imports_by_name[name] = {
                        "name": name,
                        "kind": "import",
                        "import_files": [result.get("file", "")],
                        "import_count": 1,
                        # Keep first file, code, line for reference
                        "file": result.get("file", ""),
                        "code": result.get("code", ""),
                        "line": result.get("line", 0),
                        "end_line": result.get("end_line", 0),
                        "language": result.get("language", ""),
                        "relevance_score": result.get("relevance_score", 0.0),
                    }
                else:
                    # Accumulate additional import file
                    file = result.get("file", "")
                    if file not in imports_by_name[name]["import_files"]:
                        imports_by_name[name]["import_files"].append(file)
                    imports_by_name[name]["import_count"] += 1
            else:
                non_imports.append(result)

        # Combine: definitions first, then folded imports
        folded_imports = list(imports_by_name.values())
        return non_imports + folded_imports
