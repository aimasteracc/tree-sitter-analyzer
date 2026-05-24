#!/usr/bin/env python3
"""
CodeGraph Callers MCP Tool

Dedicated tool for finding all functions that call a given function.
CodeGraph parity: equivalent to codegraph_callers.

Simpler and more discoverable than the monolithic codegraph_call_graph tool.
"""

import os
from typing import Any

from ...call_graph import CachedCallGraph, CallGraph
from ...utils import setup_logger
from ._response_builder import build_response
from .base_tool import BaseMCPTool
from .callees_tool import (
    _STALE_CACHE_WARNING,
    _is_stale_resolution,
    classify_callee_resolution,
)

logger = setup_logger(__name__)


class CodeGraphCallersTool(BaseMCPTool):
    """MCP Tool for finding callers of a function (CodeGraph parity)."""

    def __init__(self, project_root: str | None = None) -> None:
        self._call_graph: CallGraph | None = None
        self._data_source: str = "unknown"
        super().__init__(project_root)

    def _on_project_root_changed(self, project_root: str | None) -> None:
        self._call_graph = None
        self._data_source = "unknown"

    def _try_get_cache(self) -> Any:
        try:
            from ...ast_cache import ASTCache

            if self.project_root is None:
                return None
            cache = ASTCache(self.project_root)
            if cache.has_call_edges():
                return cache
            stats = cache.get_stats()
            if stats.get("total_files", 0) > 0:
                return cache
            cache.close()
        except Exception:  # nosec B110
            pass
        return None

    def _get_call_graph(self) -> CallGraph:
        if self._call_graph is None:
            if not self.project_root:
                raise ValueError("Project root not set. Call set_project_path first.")
            cache = self._try_get_cache()
            if cache is not None:
                self._call_graph = CachedCallGraph(self.project_root, cache=cache)
                self._data_source = "cache"
            else:
                self._call_graph = CallGraph(self.project_root)
                self._data_source = "parse"
        return self._call_graph

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

        cache = self._try_get_cache()
        if cache is not None and cache.has_call_edges():
            callers = self._sql_native_callers(
                cache, func_name, file_path, include_activation
            )
            data_source = "sql"
        else:
            graph = self._get_call_graph()
            callers = graph.callers_of(func_name, file_path)
            data_source = self._data_source
            self._enrich_callers_with_resolution(callers)

        warnings_list: list[str] = []
        if _is_stale_resolution(callers):
            warnings_list.append(_STALE_CACHE_WARNING)

        result = build_response(
            verdict="INFO" if callers else "NOT_FOUND",
            warnings=warnings_list or None,
            data_source=data_source,
            function=func_name,
            caller_count=len(callers),
            callers=callers,
        )

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)

    def _sql_native_callers(
        self,
        cache: Any,
        func_name: str,
        file_path: str | None,
        include_activation: bool = False,
    ) -> list[dict[str, Any]]:
        """Use SQL-native callers query — O(k) instead of full graph build.

        When ``include_activation`` is True, each entry gets an
        ``activation`` sub-dict carrying ``mod_count_30d`` and
        ``last_modified_at`` read from ``ast_symbol_activation``.
        """
        raw = cache.query_callers(func_name, callee_file=file_path)
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        activation_map: dict[tuple[str, int], dict[str, Any]] = {}
        if include_activation:
            activation_map = self._fetch_activation_map(cache)
        for edge in raw:
            key = f"{edge['caller_file']}:{edge['caller_name']}"
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
        return results

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

    @staticmethod
    def _fetch_activation_map(
        cache: Any,
    ) -> dict[tuple[str, int], dict[str, Any]]:
        """Build a (file_path, line) -> activation map.

        Returns an empty map when ``ast_symbol_activation`` doesn't exist
        on a legacy cache — callers default to zero-counts in that case.
        """
        try:
            conn = cache._get_conn()
            rows = conn.execute(
                "SELECT s.file_path, s.line, a.mod_count_30d, a.last_modified_at "
                "FROM ast_symbol_activation a "
                "JOIN ast_symbol_rows s ON s.id = a.symbol_id"
            ).fetchall()
        except Exception:
            return {}
        out: dict[tuple[str, int], dict[str, Any]] = {}
        for row in rows:
            file_path = row["file_path"] or ""
            line = int(row["line"] or 0)
            out[(file_path, line)] = {
                "mod_count_30d": int(row["mod_count_30d"] or 0),
                "last_modified_at": (
                    int(row["last_modified_at"])
                    if row["last_modified_at"] is not None
                    else None
                ),
            }
        return out
