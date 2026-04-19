"""Dict Merge in Loop Tool — MCP Tool.

Detects dict key assignment inside loops that should use dict.update()
or dict comprehension for better performance.
"""
from __future__ import annotations

from typing import Any

from ...analysis.dict_merge_loop import (
    DictMergeLoopAnalyzer,
    DictMergeLoopResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class DictMergeLoopTool(BaseMCPTool):
    """MCP tool for detecting dict key assignments in loops."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "dict_merge_loop",
            "description": (
                "Detect dict key assignment in loops that should use "
                "dict.update() for better performance."
                "\n\n"
                "Finds patterns like `for k,v in items: d[k] = v` "
                "which should be `d.update(items)`. Each subscript "
                "assignment is a Python-level operation, while "
                "dict.update() is a single C-level bulk operation."
                "\n\n"
                "Supported Languages:\n"
                "- Python: d[key] = value inside for/while loops\n"
                "\n"
                "Severity Levels:\n"
                "- medium: subscript assign in single loop\n"
                "- high: subscript assign in nested loop (2+ levels)\n"
                "\n"
                "WHEN TO USE:\n"
                "- During performance review to find inefficient dict building\n"
                "- To identify code that should use dict.update()\n"
                "- As a complement to string_concat_loop for loop perf\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For string concat in loops (use string_concat_loop)\n"
                "- For general loop complexity (use loop_complexity)"
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

        analyzer = DictMergeLoopAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: DictMergeLoopResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_hotspots": result.total_hotspots,
            "hotspots": [h.to_dict() for h in result.hotspots],
        }

    def _format_toon(self, result: DictMergeLoopResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Dict Merge in Loop Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append("")

        if result.hotspots:
            lines.append(
                f"Found {len(result.hotspots)} dict assign(s) in loops:"
            )
            for h in result.hotspots:
                lines.append(
                    f"  L{h.line_number}: {h.dict_variable}[key] = value "
                    f"in {h.loop_type} ({h.severity})"
                )
        else:
            lines.append("No dict key assignments found inside loops.")

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
