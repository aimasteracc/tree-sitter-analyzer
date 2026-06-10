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
# Wave 1b (audit nav-08b, sibling of nav-08): cap the EMITTED caller/callee
# lists. Counts stay accurate; a hub otherwise serialises a large payload that
# overflows the tool-result token budget. _MAX_TRANSITIVE caps the walk;
# _MAX_LISTED caps what is serialised back.
_MAX_LISTED = 50


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

    def get_call_graph(self) -> CallGraph:
        """Public alias for _get_call_graph() — use this instead of accessing _call_graph."""
        return self._get_call_graph()

    def get_cache(self) -> Any:
        """Public alias for _get_cache() — use this instead of replacing _get_cache."""
        return self._get_cache()

    @property
    def call_graph_initialized(self) -> bool:
        """True if the call graph has been lazily initialized (i.e. cached)."""
        return self._call_graph is not None

    @property
    def cache_initialized(self) -> bool:
        """True if the AST cache has been lazily initialized (i.e. cached)."""
        return self._cache is not None

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_navigate",
            "description": (
                "PRIMARY ENTRY POINT for 'understand this symbol' questions — "
                "try this FIRST before chaining codegraph_symbol_search / "
                "codegraph_resolve / codegraph_callers / codegraph_callees. "
                "Unified symbol navigation hub (CodeGraph parity): combines "
                "go-to-definition, find-references, and call hierarchy "
                "(callers + callees) in one call. "
                "Modes: definition, references, hierarchy, full. "
                "Replaces 3-4 separate tool invocations. "
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

        # P2: inline verbatim definition bodies so the agent answers from
        # content, not coordinates — no follow-up Read per file:line.
        self._inline_definition_bodies(result)

        # Pain #16 (dogfood pass 3): codegraph_navigate emitted no verdict.
        # NOT_FOUND when nothing matched (definition/references/hierarchy
        # all empty), INFO otherwise. Agents that branch on verdict
        # were silently treating "no symbol anywhere" as "INFO -> proceed
        # to edit" — the same anti-pattern symbol_lineage had in pass 1.
        def_found = bool((result.get("definition") or {}).get("found"))
        ref_found = bool((result.get("references") or {}).get("found"))
        hi = result.get("hierarchy", {}) or {}
        hi_found = bool(hi.get("callers")) or bool(hi.get("callees"))
        result["verdict"] = (
            "INFO" if (def_found or ref_found or hi_found) else "NOT_FOUND"
        )

        if not result.get("definition") and not result.get("references"):
            if not hi_found:
                result["hint"] = (
                    f"No results for '{symbol}'. Check spelling or build AST cache "
                    "(ast_cache mode=index)."
                )

        return apply_toon_format_to_response(result, output_format)

    def _inline_definition_bodies(self, result: dict[str, Any]) -> None:
        """P2: attach a verbatim source body to each definition record.

        Best-effort: any failure leaves the bare-coordinate response intact.
        Adds a deterrent ``next_step`` only when at least one body inlined.
        """
        definition = result.get("definition")
        if not isinstance(definition, dict) or not definition.get("found"):
            return
        defs = definition.get("definitions")
        if not isinstance(defs, list) or not defs:
            return
        try:
            from . import symbol_body_inline as sbi

            cache = self.get_cache()
            if cache is None or not self.project_root:
                return
            inlined = False
            new_defs: list[dict[str, Any]] = []
            for d in defs:
                if not isinstance(d, dict):
                    new_defs.append(d)
                    continue
                body = sbi.inline_symbol_body(self.project_root, cache, d)
                if body is not None:
                    d = {**d, "body": body}
                    inlined = True
                new_defs.append(d)
            if inlined:
                definition["definitions"] = new_defs
                result.setdefault("next_step", sbi.NAVIGATE_DETERRENT)
        except Exception as exc:  # best-effort enrichment
            logger.debug(f"Definition body inlining failed: {exc}")

    def _resolve_definition(self, symbol: str) -> dict[str, Any]:
        cache = self.get_cache()
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
        cache = self.get_cache()
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
        graph = self.get_call_graph()
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

        # Wave 1b (audit nav-08b): emit a capped head of each list; the counts
        # stay accurate so the agent sees the true call hierarchy size.
        truncated = len(callers) > _MAX_LISTED or len(callees) > _MAX_LISTED
        result: dict[str, Any] = {
            "caller_count": len(callers),
            "callees_count": len(callees),
            "callers": callers[:_MAX_LISTED],
            "callees": callees[:_MAX_LISTED],
        }

        if max_depth > 1:
            transitive_callers = _transitive_callers(
                graph, symbol, file_path, max_depth
            )
            transitive_callees = _transitive_callees(
                graph, symbol, file_path, max_depth
            )
            truncated = (
                truncated
                or len(transitive_callers) > _MAX_LISTED
                or len(transitive_callees) > _MAX_LISTED
            )
            result["transitive_caller_count"] = len(transitive_callers)
            result["transitive_callee_count"] = len(transitive_callees)
            result["transitive_callers"] = transitive_callers[:_MAX_LISTED]
            result["transitive_callees"] = transitive_callees[:_MAX_LISTED]

        result["lists_truncated"] = truncated
        result["listed_cap"] = _MAX_LISTED
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
