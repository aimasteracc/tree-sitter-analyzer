"""Iterable Modification in Loop Tool — MCP Tool.

Detects modification of a collection while iterating over it,
which causes RuntimeError or silent element skipping.
"""
from __future__ import annotations

from typing import Any

from ...analysis.iterable_modification import (
    IterableModificationAnalyzer,
    IterableModificationResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class IterableModificationTool(BaseMCPTool):
    """MCP tool for detecting collection modification during iteration."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "iterable_modification",
            "description": (
                "Detect collection modification while iterating over it."
                "\n\n"
                "Finds patterns like `for x in items: items.remove(x)` "
                "which cause RuntimeError (dict changed size during "
                "iteration) or silently skip elements in lists."
                "\n\n"
                "Detected Methods:\n"
                "- list: append, extend, insert, remove, pop, clear\n"
                "- dict: pop, update, setdefault\n"
                "- set: add, discard, pop\n"
                "- del statement on subscript\n"
                "\n"
                "Supported Languages:\n"
                "- Python: for loops with collection modification\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find bugs that cause RuntimeError at runtime\n"
                "- To detect silent element skipping in list iteration\n"
                "- As a bug-finding complement to loop_complexity\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For loop performance (use loop_complexity)\n"
                "- For dict merge in loops (use dict_merge_loop)"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Path to a specific file to analyze. "
                            "If provided, analyzes only this file."
                        ),
                    },
                    "format": {
                        "type": "string",
                        "description": "Output format: toon (default) or json",
                        "enum": ["toon", "json"],
                    },
                },
            },
        }

    @handle_mcp_errors(operation="execute")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path = arguments.get("file_path", "")
        output_format = arguments.get("format", "toon")

        if not file_path:
            return {
                "error": "file_path must be provided",
                "format": output_format,
            }

        analyzer = IterableModificationAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: IterableModificationResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_hotspots": result.total_hotspots,
            "hotspots": [h.to_dict() for h in result.hotspots],
        }

    def _format_toon(self, result: IterableModificationResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Iterable Modification in Loop Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append("")

        if result.hotspots:
            lines.append(
                f"Found {len(result.hotspots)} modification(s) during iteration:"
            )
            for h in result.hotspots:
                lines.append(
                    f"  L{h.line_number}: {h.loop_variable}.{h.method_name}() "
                    f"in for loop ({h.severity})"
                )
        else:
            lines.append("No collection modifications found during iteration.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_hotspots": result.total_hotspots,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")

        return True
