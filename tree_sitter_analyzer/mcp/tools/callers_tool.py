#!/usr/bin/env python3
"""
CodeGraph Callers MCP Tool

Dedicated tool for finding all functions that call a given function.
CodeGraph parity: equivalent to codegraph_callers.

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


class CodeGraphCallersTool(CodeGraphRelationToolMixin, BaseMCPTool):
    """MCP Tool for finding callers of a function (CodeGraph parity)."""

    def __init__(self, project_root: str | None = None) -> None:
        self._init_relation_state()
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._reset_relation_state()

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "codegraph_callers",
            "description": (
                "PRIMARY for 'who calls FUNCTION X' — try this FIRST instead "
                "of grepping for the function name. "
                "Reverse call lookup over the indexed call graph (CodeGraph parity). "
                "Returns caller function name, file, line, and language."
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
                    "description": "Target function name to find callers for",
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional file path to disambiguate overloaded functions",
                },
                "limit": {
                    "type": "integer",
                    "description": (
                        "Maximum number of callers to list in the response "
                        "(default 50). Raise for more, or qualify with "
                        "ClassName.method to narrow high-fan-in symbols."
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
                        "When true, embed per-caller git modification "
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

        # Detect "ClassName.method_name" qualified lookup.  The SQL fast-path
        # stores bare callee names and can't filter by receiver class, so we
        # fall through to the in-memory CallGraph which does handle qualified
        # names via the FunctionRef.receiver field.
        is_qualified = (
            "." in func_name
            and ":" not in func_name
            and "/" not in func_name
            and "\\" not in func_name
            and func_name.rpartition(".")[0]  # non-empty class part
        )

        unattributed_call_sites = 0
        cache = self._try_get_cache()
        call_graph_indexed = cache is not None and cache.has_call_edges()
        if call_graph_indexed and not is_qualified:
            callers, unattributed_call_sites = self._sql_native_callers(
                cache, func_name, file_path, include_activation
            )
            data_source = "sql"
            has_any_call_edges = True  # SQL path only runs when edges exist
        else:
            graph = self._get_call_graph()
            callers = graph.callers_of(func_name, file_path)
            data_source = self._data_source
            self._enrich_callers_with_resolution(callers)
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
        if _is_stale_resolution(callers):
            warnings_list.append(_STALE_CACHE_WARNING)

        # Honest-truncation cap: record total before slicing so agents know
        # what was omitted (same pattern as dead_code_tool / hyphae_select_tool).
        total_callers = len(callers)
        truncated = total_callers > listed_cap
        callers = callers[:listed_cap]

        # P2: inline each caller's verbatim source body (top-N capped) so the
        # agent answers from content, not coordinates — no Read per file:line.
        next_step = self._inline_caller_bodies(cache, callers)

        result = build_response(
            verdict="INFO" if callers or total_callers else "NOT_FOUND",
            warnings=warnings_list or None,
            data_source=data_source,
            function=func_name,
            caller_count=total_callers,
            callers_listed=len(callers),
            listed_cap=listed_cap,
            truncated=truncated,
            callers=callers,
        )
        if unattributed_call_sites:
            # #638: module-level call sites have no enclosing function — they
            # are counted here instead of being emitted as un-navigable ghost
            # rows ({name: '', line: 0}).
            result["unattributed_call_sites"] = unattributed_call_sites
        if truncated:
            trunc_note = (
                f"showing {len(callers)} of {total_callers} callers — raise limit, "
                "or qualify with ClassName.method to narrow "
                "(dynamic-dispatch names like 'execute' have huge fan-in)"
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
            as_summary_line = f"callers: {func_name!r} has 0 caller(s)"
            as_next_step = result.get("next_step") or (
                f"No callers found for '{func_name}'. "
                "Check spelling or run --full-index to build the call graph."
            )
        else:
            as_summary_line = f"callers: {func_name!r} has {total_callers} caller(s)"
            as_next_step = result.get("next_step") or (
                "Review callers above, run tests for affected paths, "
                "or use nav action=caller_tree for the full blast-radius."
            )
        result["agent_summary"] = {
            "summary_line": as_summary_line,
            "verdict": verdict,
            "next_step": as_next_step,
        }

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)

    def _inline_caller_bodies(
        self,
        cache: Any,
        callers: list[dict[str, Any]],
    ) -> str | None:
        """P2: attach a body to the top-N callers (in place). Returns deterrent.

        Best-effort: any failure leaves the bare-coordinate list intact and
        returns ``None`` (no deterrent).
        """
        if not callers or not self.project_root:
            return None
        try:
            from . import symbol_body_inline as sbi

            # cache may be None (graph-parse path with no index yet); the
            # helper only needs it for the end_line fallback, and records on
            # the graph path already carry end_line, so it degrades cleanly.
            enriched = sbi.inline_neighbor_bodies(self.project_root, cache, callers)
            if not any("body" in c for c in enriched):
                return None
            callers[:] = enriched
            return sbi.NEIGHBORS_DETERRENT
        except Exception as exc:  # best-effort enrichment
            logger.debug(f"Caller body inlining failed: {exc}")
            return None

    def _sql_native_callers(
        self,
        cache: Any,
        func_name: str,
        file_path: str | None,
        include_activation: bool = False,
    ) -> tuple[list[dict[str, Any]], int]:
        """Use SQL-native callers query — O(k) instead of full graph build.

        Returns ``(callers, unattributed_call_sites)``.  Edges without an
        enclosing function (module-level call sites store
        ``caller_name='' / caller_line=0``) are never emitted as result rows
        — they are counted instead (#638 ghost-caller fix).

        When ``include_activation`` is True, each entry gets an
        ``activation`` sub-dict carrying ``mod_count_30d`` and
        ``last_modified_at`` read from ``ast_symbol_activation``.
        """
        raw = cache.query_callers(func_name, callee_file=file_path)
        results: list[dict[str, Any]] = []
        unattributed = 0
        seen: set[str] = set()
        activation_map: dict[tuple[str, int], dict[str, Any]] = {}
        if include_activation:
            activation_map = self._fetch_activation_map(cache)
        for edge in raw:
            if not edge.get("caller_name"):
                unattributed += 1
                continue
            key = f"{edge['caller_file']}:{edge['caller_name']}:{edge['caller_line']}"
            if key in seen:
                continue
            seen.add(key)
            callee_resolved = edge.get("callee_resolved_file", "")
            caller_file_val = edge["caller_file"]
            resolution, resolved_file = classify_callee_resolution(
                func_name, callee_resolved, caller_file_val
            )
            entry: dict[str, Any] = {
                "name": edge["caller_name"],
                "file": edge["caller_file"],
                "line": edge["caller_line"],
                "language": "",
                "callee_resolution": resolution,
                "callee_resolved_file": resolved_file,
            }
            row_data = cache.lookup(
                os.path.join(cache.project_root, edge["caller_file"])
            )
            if row_data:
                entry["language"] = row_data.get("language", "")
            if include_activation:
                entry["activation"] = activation_map.get(
                    (edge["caller_file"], edge["caller_line"]),
                    {"mod_count_30d": 0, "last_modified_at": None},
                )
            results.append(entry)
        return results, unattributed

    @staticmethod
    def _enrich_callers_with_resolution(
        callers: list[dict[str, Any]],
    ) -> None:
        """Add callee_resolution and callee_resolved_file to graph-fallback results."""
        for entry in callers:
            if "callee_resolution" not in entry or "callee_resolved_file" not in entry:
                callee_file = entry.get("file", "")
                resolution, resolved_file = classify_callee_resolution(
                    "", callee_file, callee_file
                )
                entry.setdefault("callee_resolution", resolution)
                entry.setdefault("callee_resolved_file", resolved_file)
