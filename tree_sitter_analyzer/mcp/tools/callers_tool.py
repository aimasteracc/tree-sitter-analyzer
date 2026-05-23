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
from .base_tool import BaseMCPTool

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
                "Find all functions that call the given function (CodeGraph parity). "
                "Returns caller function name, file, line, and language. "
                "No other built-in tool provides reverse call lookup."
            ),
            "inputSchema": self.get_tool_schema(),
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

        cache = self._try_get_cache()
        if cache is not None and cache.has_call_edges():
            callers = self._sql_native_callers(cache, func_name, file_path)
            data_source = "sql"
        else:
            graph = self._get_call_graph()
            callers = graph.callers_of(func_name, file_path)
            data_source = self._data_source

        result: dict[str, Any] = {
            "success": True,
            "verdict": "INFO" if callers else "NOT_FOUND",
            "data_source": data_source,
            "function": func_name,
            "caller_count": len(callers),
            "callers": callers,
        }

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)

    def _sql_native_callers(
        self, cache: Any, func_name: str, file_path: str | None
    ) -> list[dict[str, Any]]:
        """Use SQL-native callers query — O(k) instead of full graph build."""
        raw = cache.query_callers(func_name, callee_file=file_path)
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        for edge in raw:
            key = f"{edge['caller_file']}:{edge['caller_name']}"
            if key in seen:
                continue
            seen.add(key)
            entry: dict[str, Any] = {
                "name": edge["caller_name"],
                "file": edge["caller_file"],
                "line": edge["caller_line"],
                "language": "",
            }
            row_data = cache.lookup(
                os.path.join(cache.project_root, edge["caller_file"])
            )
            if row_data:
                entry["language"] = row_data.get("language", "")
            results.append(entry)
        return results
