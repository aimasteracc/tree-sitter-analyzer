#!/usr/bin/env python3
"""trace_symbol MCP tool for Code Intelligence Graph."""

from __future__ import annotations

from typing import Any

from ...intelligence.formatters import format_trace_result
from ...intelligence.project_indexer import ProjectIndexer
from ...utils import setup_logger
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)

VALID_TRACE_TYPES = ("definition", "usages", "call_chain", "inheritance", "full")
VALID_OUTPUT_FORMATS = ("summary", "tree", "json")


class TraceSymbolTool(BaseMCPTool):
    """MCP tool to trace a symbol across a project."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)
        self._indexer: ProjectIndexer | None = None
        self._owns_indexer: bool = True  # True if we created the indexer ourselves

    def set_indexer(self, indexer: ProjectIndexer) -> None:
        """Set a shared indexer (owned externally, e.g. by the server)."""
        self._indexer = indexer
        self._owns_indexer = False

    def _ensure_indexed(self) -> ProjectIndexer:
        """Lazily create and populate the project indexer."""
        if self._indexer is None:
            self._indexer = ProjectIndexer(self.project_root or "")
            self._owns_indexer = True
        self._indexer.ensure_indexed()
        return self._indexer

    def set_project_path(self, project_path: str) -> None:
        """Override to reset indexer when project path changes."""
        super().set_project_path(project_path)
        if self._owns_indexer:
            self._indexer = None

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "trace_symbol",
            "description": "Trace a symbol (function/class/variable) across the project: find definitions, usages, call chains, and inheritance hierarchy.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Symbol name to trace"},
                    "file_path": {
                        "type": "string",
                        "description": "Optional file path hint for disambiguation",
                    },
                    "trace_type": {
                        "type": "string",
                        "enum": list(VALID_TRACE_TYPES),
                        "description": "Type of trace to perform",
                        "default": "full",
                    },
                    "depth": {
                        "type": "integer",
                        "description": "Max depth for call chain tracing",
                        "default": 2,
                    },
                    "output_format": {
                        "type": "string",
                        "enum": list(VALID_OUTPUT_FORMATS),
                        "description": "Output format",
                        "default": "summary",
                    },
                },
                "required": ["symbol"],
                "additionalProperties": False,
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if "symbol" not in arguments or not arguments["symbol"]:
            raise ValueError("'symbol' is required")
        trace_type = arguments.get("trace_type", "full")
        if trace_type not in VALID_TRACE_TYPES:
            raise ValueError(
                f"Invalid trace_type '{trace_type}'. Must be one of {VALID_TRACE_TYPES}"
            )
        output_format = arguments.get("output_format", "summary")
        if output_format not in VALID_OUTPUT_FORMATS:
            raise ValueError(
                f"Invalid output_format '{output_format}'. Must be one of {VALID_OUTPUT_FORMATS}"
            )
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        symbol = arguments["symbol"]
        file_path = arguments.get("file_path")
        trace_type = arguments.get("trace_type", "full")
        depth = arguments.get("depth", 2)
        output_format = arguments.get("output_format", "summary")

        # Ensure project is indexed before querying
        indexer = self._ensure_indexed()
        symbol_index = indexer.symbol_index
        call_graph = indexer.call_graph

        result_data: dict[str, Any] = {
            "symbol": symbol,
            "definitions": [],
            "usages": [],
            "call_chain": {"callers": [], "callees": []},
            "inheritance": [],
        }

        try:
            # Definitions
            if trace_type in ("definition", "full"):
                defs = symbol_index.lookup_definition(symbol, file_hint=file_path)
                result_data["definitions"] = [d.to_dict() for d in defs]

            # Usages
            if trace_type in ("usages", "full"):
                refs = symbol_index.lookup_references(symbol)
                result_data["usages"] = [r.to_dict() for r in refs]

            # Call chain
            if trace_type in ("call_chain", "full"):
                callers = call_graph.find_callers(symbol, depth=depth)
                callees = call_graph.find_callees(symbol, depth=depth)
                result_data["call_chain"] = {
                    "callers": [c.to_dict() for c in callers],
                    "callees": [c.to_dict() for c in callees],
                }

            # Inheritance - formatter expects list for ' -> '.join()
            if trace_type in ("inheritance", "full"):
                chain = symbol_index.get_inheritance_chain(symbol)
                subclasses = symbol_index.get_subclasses(symbol)
                inh_list = list(reversed(chain)) + [symbol] + subclasses
                result_data["inheritance"] = inh_list

        except Exception as e:
            logger.error(f"Error tracing symbol '{symbol}': {e}")
            result_data["error"] = str(e)

        # Format output
        formatted = format_trace_result(result_data, output_format)
        return {
            "result": formatted,
            "data": result_data,
            "definitions": result_data.get("definitions", []),
        }
