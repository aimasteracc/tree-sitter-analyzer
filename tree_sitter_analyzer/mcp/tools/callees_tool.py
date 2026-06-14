#!/usr/bin/env python3
"""
CodeGraph Callees MCP Tool

Dedicated tool for finding all functions called by a given function.
CodeGraph parity: equivalent to codegraph_callees.

Simpler and more discoverable than the monolithic codegraph_call_graph tool.
"""

import os
from typing import Any

from ...utils import setup_logger
from ._response_builder import build_response
from .base_tool import BaseMCPTool
from .codegraph_relation_tool import (
    _STALE_CACHE_WARNING,
    CodeGraphRelationToolMixin,
    _is_stale_resolution,
    classify_callee_resolution,
)

logger = setup_logger(__name__)


class CodeGraphCalleesTool(CodeGraphRelationToolMixin, BaseMCPTool):
    """MCP Tool for finding callees of a function (CodeGraph parity)."""

    def __init__(self, project_root: str | None = None) -> None:
        self._init_relation_state()
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._reset_relation_state()

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_callees",
            "description": (
                "PRIMARY for 'what does FUNCTION X call' — try this FIRST "
                "instead of reading X's body to enumerate its callees. "
                "Forward call lookup over the indexed call graph (CodeGraph parity). "
                "Returns callee function name, file, line, and language."
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
                "function_name": {
                    "type": "string",
                    "description": "Source function name to find callees for",
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional file path to disambiguate overloaded functions",
                },
                "limit": {
                    "type": "integer",
                    "description": (
                        "Maximum number of callees to list in the response "
                        "(default 50). Raise for more, or qualify with "
                        "ClassName.method to narrow high-fan-out symbols."
                    ),
                    "default": 50,
                    "minimum": 1,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format: 'toon' (default, token-efficient) or 'json'",
                    "default": "toon",
                },
                "include_activation": {
                    "type": "boolean",
                    "description": (
                        "When true, embed per-callee git modification "
                        "frequency under the 'activation' key. Off by "
                        "default to preserve token budget."
                    ),
                    "default": False,
                },
            },
            "required": ["function_name"],
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if "function_name" not in arguments:
            raise ValueError("function_name is required")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        func_name = arguments["function_name"]
        file_path = arguments.get("file_path")
        output_format = arguments.get("output_format", "toon")
        include_activation = bool(arguments.get("include_activation", False))
        listed_cap = int(arguments.get("limit", 50))

        cache = self._try_get_cache()
        call_graph_indexed = cache is not None and cache.has_call_edges()
        if call_graph_indexed:
            callees = self._sql_native_callees(
                cache, func_name, file_path, include_activation
            )
            data_source = "sql"
            has_any_call_edges = True  # SQL path only runs when edges exist
        else:
            graph = self._get_call_graph()
            callees = graph.callees_of(func_name, file_path)
            data_source = self._data_source
            if include_activation:
                self._enrich_graph_callees_with_activation(callees)
            self._enrich_callees_with_resolution(callees)
            # Suppress the --full-index hint when either:
            #   (a) the index was built (data_source=="cache") — even if it
            #       has zero call edges, the user already ran --full-index; or
            #   (b) the parse fallback itself found call edges — the project
            #       has calls, so the symbol just isn't there.
            # Only fire the hint when the index is absent AND the parse found
            # no edges at all (truly empty/unbuilt state).
            has_any_call_edges = (
                self._data_source == "cache" or len(graph.call_edges()) > 0
            )

        warnings_list: list[str] = []
        if _is_stale_resolution(callees):
            warnings_list.append(_STALE_CACHE_WARNING)

        # Honest-truncation cap: record total before slicing so agents know
        # what was omitted (same pattern as dead_code_tool / hyphae_select_tool).
        total_callees = len(callees)
        truncated = total_callees > listed_cap
        callees = callees[:listed_cap]

        # P2: inline each callee's verbatim source body (top-N capped) so the
        # agent answers from content, not coordinates — no Read per file:line.
        next_step = self._inline_callee_bodies(cache, callees)

        result = build_response(
            verdict="INFO" if callees or total_callees else "NOT_FOUND",
            warnings=warnings_list or None,
            data_source=data_source,
            function=func_name,
            callee_count=total_callees,
            callees_listed=len(callees),
            listed_cap=listed_cap,
            truncated=truncated,
            callees=callees,
        )
        if truncated:
            trunc_note = (
                f"showing {len(callees)} of {total_callees} callees — raise limit, "
                "or qualify with ClassName.method to narrow "
                "(dynamic-dispatch names like 'execute' have huge fan-out)"
            )
            # Combine truncation note with any body-inlining deterrent.
            next_step = f"{trunc_note}. {next_step}" if next_step else trunc_note
        # #548: when the call-graph has no edges at all (NOT_FOUND AND the graph
        # itself is empty), surface a --full-index hint so users know why
        # results are empty.  We deliberately skip the hint when the graph has
        # edges but the specific symbol was simply not found.
        if result.get("verdict") == "NOT_FOUND" and not has_any_call_edges:
            index_hint = (
                "Call-graph index is empty or has not been built yet. "
                "Run `tree-sitter-analyzer --full-index` first, then retry."
            )
            next_step = f"{index_hint} {next_step}" if next_step else index_hint
        if next_step:
            result["next_step"] = next_step

        # #546 seam 3 / #577 leftover: uniform agent_summary across all nav actions.
        verdict = result.get("verdict", "NOT_FOUND")
        if verdict == "NOT_FOUND":
            as_summary_line = f"callees: {func_name!r} calls 0 function(s)"
            as_next_step = result.get("next_step") or (
                f"No callees found for '{func_name}'. "
                "Check spelling or run --full-index to build the call graph."
            )
        else:
            as_summary_line = (
                f"callees: {func_name!r} calls {total_callees} function(s)"
            )
            as_next_step = result.get("next_step") or (
                "Review callees above, run tests for dependencies, "
                "or use nav action=callee_tree for the full call tree."
            )
        result["agent_summary"] = {
            "summary_line": as_summary_line,
            "verdict": verdict,
            "next_step": as_next_step,
        }

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)

    def _inline_callee_bodies(
        self,
        cache: Any,
        callees: list[dict[str, Any]],
    ) -> str | None:
        """P2: attach a body to the top-N callees (in place). Returns deterrent.

        Best-effort: any failure leaves the bare-coordinate list intact and
        returns ``None`` (no deterrent).
        """
        if not callees or not self.project_root:
            return None
        try:
            from . import symbol_body_inline as sbi

            # cache may be None (graph-parse path with no index yet); the
            # helper only needs it for the end_line fallback, and records on
            # the graph path already carry end_line, so it degrades cleanly.
            enriched = sbi.inline_neighbor_bodies(self.project_root, cache, callees)
            if not any("body" in c for c in enriched):
                return None
            callees[:] = enriched
            return sbi.NEIGHBORS_DETERRENT
        except Exception as exc:  # best-effort enrichment
            logger.debug(f"Callee body inlining failed: {exc}")
            return None

    def _sql_native_callees(
        self,
        cache: Any,
        func_name: str,
        file_path: str | None,
        include_activation: bool = False,
    ) -> list[dict[str, Any]]:
        """Use SQL-native callees query — O(k) instead of full graph build.

        When ``include_activation`` is True, each entry gets an
        ``activation`` sub-dict carrying ``mod_count_30d`` and
        ``last_modified_at`` read from ``ast_symbol_activation``. The
        lookup is keyed by ``(callee_file, callee_line)`` and falls back
        to zero counts when no row is found.
        """
        raw = cache.query_callees(func_name, caller_file=file_path)
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        activation_map: dict[tuple[str, int], dict[str, Any]] = {}
        if include_activation:
            activation_map = self._fetch_activation_map(cache)
        for edge in raw:
            key = f"{edge['callee_name']}:{edge.get('callee_file', '')}"
            if key in seen:
                continue
            seen.add(key)
            callee_resolved = edge.get("callee_resolved_file", "")
            callee_file_val = edge.get("callee_file", callee_resolved)
            caller_file_val = edge.get("caller_file", "")
            resolution, resolved_file = classify_callee_resolution(
                edge["callee_name"], callee_resolved, caller_file_val
            )
            entry: dict[str, Any] = {
                "name": edge["callee_name"],
                "file": resolved_file or callee_file_val,
                "line": edge["callee_line"],
                "language": "",
                "callee_resolution": resolution,
                "callee_resolved_file": resolved_file,
            }
            row_data = cache.lookup(
                os.path.join(cache.project_root, resolved_file or callee_file_val)
            )
            if row_data:
                entry["language"] = row_data.get("language", "")
            if include_activation:
                entry["activation"] = self._activation_for(
                    activation_map,
                    resolved_file or callee_file_val,
                    edge["callee_line"],
                )
            results.append(entry)
        if not raw:
            results = self._resolve_via_enhanced(
                cache,
                func_name,
                file_path,
                activation_map if include_activation else {},
            )
        return results

    def _enrich_callees_with_resolution(self, callees: list[dict[str, Any]]) -> None:
        """Add callee_resolution and callee_resolved_file to graph-fallback results."""
        for entry in callees:
            callee_file = entry.get("file", "")
            callee_name = entry.get("name", "")
            if "callee_resolution" not in entry or "callee_resolved_file" not in entry:
                resolution, resolved_file = classify_callee_resolution(
                    callee_name, callee_file, ""
                )
                entry.setdefault("callee_resolution", resolution)
                entry.setdefault("callee_resolved_file", resolved_file)

    def _resolve_via_enhanced(
        self,
        cache: Any,
        func_name: str,
        file_path: str | None,
        activation_map: dict[tuple[str, int], dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Fallback to query_callees_enhanced for cross-file resolution."""
        try:
            enhanced = cache.query_callees_enhanced(func_name, caller_file=file_path)
        except Exception:
            return []
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        for edge in enhanced:
            callee_resolved = edge.get("callee_resolved_file", "")
            key = f"{edge['callee_name']}:{callee_resolved}"
            if key in seen:
                continue
            seen.add(key)
            caller_file_val = edge.get("caller_file", "")
            resolution, resolved_file = classify_callee_resolution(
                edge["callee_name"], callee_resolved, caller_file_val
            )
            entry: dict[str, Any] = {
                "name": edge["callee_name"],
                "file": resolved_file or edge.get("callee_file", ""),
                "line": edge["callee_line"],
                "language": "",
                "callee_resolution": resolution,
                "callee_resolved_file": resolved_file,
            }
            if activation_map:
                entry["activation"] = self._activation_for(
                    activation_map,
                    resolved_file or edge.get("callee_file", ""),
                    edge["callee_line"],
                )
            results.append(entry)
        return results

    def _enrich_graph_callees_with_activation(
        self, callees: list[dict[str, Any]]
    ) -> None:
        """Decorate graph-walk results with activation when SQL path missed.

        Used when the cache is unavailable / has no call edges so the tool
        falls back to a fresh CallGraph parse. We still try to attach
        activation if the cache table happens to exist.
        """
        try:
            from ...ast_cache import ASTCache
        except Exception:
            return
        if not self.project_root:
            return
        try:
            cache = ASTCache(self.project_root)
        except Exception:
            return
        try:
            activation_map = self._fetch_activation_map(cache)
            for entry in callees:
                entry.setdefault(
                    "activation",
                    self._activation_for(
                        activation_map,
                        entry.get("file", ""),
                        int(entry.get("line", 0) or 0),
                    ),
                )
        finally:
            try:
                cache.close()
            except Exception:
                pass
