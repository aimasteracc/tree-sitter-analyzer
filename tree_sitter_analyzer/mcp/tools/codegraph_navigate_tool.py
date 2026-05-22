#!/usr/bin/env python3
"""
CodeGraph Navigate MCP Tool — Unified symbol navigation hub.

Single entry point for "understand this function/class" queries.
Combines go-to-definition, find-references, callers, callees,
and call hierarchy into one call — what takes 3-4 separate tool
invocations today.

Modes:
  - definition:  Where is this symbol defined? (go-to-def)
  - references:  Where is this symbol used? (find-all-refs)
  - hierarchy:   Callers + callees for a function (call hierarchy)
  - full:        All of the above in one response

CodeGraph parity: equivalent to CodeGraph's unified "navigate symbol" view.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from ...call_graph import CachedCallGraph, CallGraph
from ...utils import setup_logger
from ..utils.format_helper import apply_toon_format_to_response
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)

_MAX_TRANSITIVE = 50


class CodeGraphNavigateTool(BaseMCPTool):
    """MCP Tool for unified symbol navigation (CodeGraph parity)."""

    def __init__(self, project_root: str | None = None) -> None:
        self._call_graph: CallGraph | None = None
        self._cache: Any = None
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._call_graph = None
        self._cache = None

    def _try_get_cache(self) -> Any:
        try:
            from ...ast_cache import ASTCache

            if self.project_root is None:
                return None
            cache = ASTCache(self.project_root)
            stats = cache.get_stats()
            if stats.get("total_files", 0) > 0:
                return cache
            cache.close()
        except Exception:
            pass
        return None

    def _get_cache(self) -> Any:
        if self._cache is None:
            self._cache = self._try_get_cache()
        return self._cache

    def _get_call_graph(self) -> CallGraph:
        if self._call_graph is None:
            if not self.project_root:
                raise ValueError("Project root not set. Call set_project_path first.")
            cache = self._get_cache()
            if cache is not None:
                self._call_graph = CachedCallGraph(self.project_root, cache=cache)
            else:
                self._call_graph = CallGraph(self.project_root)
        return self._call_graph

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_navigate",
            "description": (
                "Unified symbol navigation hub (CodeGraph parity). "
                "Combines go-to-definition, find-references, call hierarchy "
                "(callers + callees) in a single call. Modes: "
                "definition, references, hierarchy, full. "
                "Replaces 3-4 separate tool calls for 'understand this symbol'. "
                "Requires ast_cache index (run ast_cache mode=index)."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": (
                        "Symbol name to navigate. "
                        "Simple names ('parse_tree') or qualified ('ast_cache.ASTCache.index_file')."
                    ),
                },
                "mode": {
                    "type": "string",
                    "enum": ["definition", "references", "hierarchy", "full"],
                    "default": "full",
                    "description": (
                        "definition=go-to-def, references=find-all-refs, "
                        "hierarchy=callers+callees, full=all combined"
                    ),
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional file path to disambiguate overloaded symbols",
                },
                "depth": {
                    "type": "integer",
                    "default": 2,
                    "description": "Max transitive depth for hierarchy mode (1=direct, 2=2 hops)",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "default": "toon",
                    "description": "Output format",
                },
            },
            "required": ["symbol"],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if not arguments.get("symbol"):
            raise ValueError("symbol is required")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        symbol = arguments["symbol"]
        mode = arguments.get("mode", "full")
        file_path = arguments.get("file_path")
        depth = min(arguments.get("depth", 2), 5)
        output_format = arguments.get("output_format", "toon")

        result: dict[str, Any] = {
            "success": True,
            "symbol": symbol,
            "mode": mode,
        }

        if mode in ("definition", "full"):
            result["definition"] = self._resolve_definition(symbol)

        if mode in ("references", "full"):
            result["references"] = self._find_references(symbol)

        if mode in ("hierarchy", "full"):
            result["hierarchy"] = self._call_hierarchy(symbol, file_path, depth)

        if not result.get("definition") and not result.get("references"):
            hi = result.get("hierarchy", {})
            if not hi.get("callers") and not hi.get("callees"):
                result["hint"] = (
                    f"No results for '{symbol}'. Check spelling or build AST cache "
                    "(ast_cache mode=index)."
                )

        return apply_toon_format_to_response(result, output_format)

    def _resolve_definition(self, symbol: str) -> dict[str, Any]:
        cache = self._get_cache()
        if cache is None:
            return {"found": False, "reason": "AST cache not available"}
        try:
            from ...symbol_resolver import SymbolResolver

            resolver = SymbolResolver(cache)
            resolve_result = resolver.resolve(symbol)
            definitions = [d.to_dict() for d in resolve_result.definitions]
            return {
                "found": len(definitions) > 0,
                "count": len(definitions),
                "definitions": definitions,
                "resolved_via": resolve_result.resolved_via,
            }
        except Exception as exc:
            logger.debug(f"Definition lookup failed: {exc}")
            return {"found": False, "reason": str(exc)}

    def _find_references(self, symbol: str) -> dict[str, Any]:
        cache = self._get_cache()
        if cache is None:
            return {"found": False, "reason": "AST cache not available"}
        try:
            from ...symbol_resolver import SymbolResolver

            resolver = SymbolResolver(cache)
            ref_result = resolver.find_references(symbol)
            return {
                "found": len(ref_result.references) > 0,
                "definition_count": len(ref_result.definitions),
                "reference_count": len(ref_result.references),
                "references": [r.to_dict() for r in ref_result.references],
            }
        except Exception as exc:
            logger.debug(f"Reference lookup failed: {exc}")
            return {"found": False, "reason": str(exc)}

    def _call_hierarchy(
        self,
        symbol: str,
        file_path: str | None,
        max_depth: int,
    ) -> dict[str, Any]:
        graph = self._get_call_graph()
        try:
            graph.build()
        except Exception as exc:
            logger.debug(f"Call graph build failed: {exc}")
            return {"callers": [], "callees": []}

        direct_callers = graph.callers_of(symbol, file_path)
        direct_callees = graph.callees_of(symbol, file_path)

        callers = [
            {
                "name": c["name"],
                "file": c["file"],
                "line": c["line"],
                "language": c.get("language", ""),
            }
            for c in direct_callers
        ]

        callees = [
            {
                "name": c["name"],
                "file": c["file"],
                "line": c["line"],
                "language": c.get("language", ""),
            }
            for c in direct_callees
        ]

        result: dict[str, Any] = {
            "caller_count": len(callers),
            "callees_count": len(callees),
            "callers": callers,
            "callees": callees,
        }

        if max_depth > 1:
            result["transitive_callers"] = _transitive_callers(
                graph, symbol, file_path, max_depth
            )
            result["transitive_callees"] = _transitive_callees(
                graph, symbol, file_path, max_depth
            )

        return result


def _transitive_callers(
    graph: CallGraph,
    symbol: str,
    file_path: str | None,
    max_depth: int,
) -> list[dict[str, Any]]:
    visited: set[str] = set()
    queue: deque[tuple[str, str | None, int]] = deque([(symbol, file_path, 0)])
    results: list[dict[str, Any]] = []

    while queue and len(results) < _MAX_TRANSITIVE:
        name, fpath, depth = queue.popleft()
        if depth >= max_depth:
            continue
        callers = graph.callers_of(name, fpath)
        for c in callers:
            key = f"{c['file']}:{c['name']}:{c['line']}"
            if key in visited:
                continue
            visited.add(key)
            results.append(
                {
                    "name": c["name"],
                    "file": c["file"],
                    "line": c["line"],
                    "depth": depth + 1,
                }
            )
            queue.append((c["name"], c["file"], depth + 1))

    return results


def _transitive_callees(
    graph: CallGraph,
    symbol: str,
    file_path: str | None,
    max_depth: int,
) -> list[dict[str, Any]]:
    visited: set[str] = set()
    queue: deque[tuple[str, str | None, int]] = deque([(symbol, file_path, 0)])
    results: list[dict[str, Any]] = []

    while queue and len(results) < _MAX_TRANSITIVE:
        name, fpath, depth = queue.popleft()
        if depth >= max_depth:
            continue
        callees = graph.callees_of(name, fpath)
        for c in callees:
            key = f"{c['file']}:{c['name']}:{c['line']}"
            if key in visited:
                continue
            visited.add(key)
            results.append(
                {
                    "name": c["name"],
                    "file": c["file"],
                    "line": c["line"],
                    "depth": depth + 1,
                }
            )
            queue.append((c["name"], c["file"], depth + 1))

    return results
