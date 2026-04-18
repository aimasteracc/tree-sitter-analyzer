"""String Concat in Loops Tool — MCP Tool.

Analyzes string concatenation inside loops. Detects O(n^2) patterns
where += is used on strings inside for/while loops.
"""
from __future__ import annotations

from typing import Any

from ...analysis.string_concat_loop import (
    StringConcatLoopAnalyzer,
    StringConcatLoopResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class StringConcatLoopTool(BaseMCPTool):
    """MCP tool for analyzing string concatenation inside loops."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "string_concat_loop",
            "description": (
                "Analyze string concatenation inside loops (O(n^2) risk). "
                "\n\n"
                "Detects string += operations inside for/while loops, "
                "which cause quadratic performance due to repeated "
                "string copying. Suggests join(), StringBuilder, or "
                "buffer alternatives."
                "\n\n"
                "Supported Languages:\n"
                "- Python: s += ... inside for/while\n"
                "- JavaScript/TypeScript: s += ... inside for/while/do-while\n"
                "- Java: s += ... inside for/while\n"
                "- Go: s += ... inside for\n"
                "\n"
                "Severity Levels:\n"
                "- medium: += in single loop\n"
                "- high: += in nested loop (2+ levels)\n"
                "\n"
                "WHEN TO USE:\n"
                "- During performance review to find O(n^2) string patterns\n"
                "- To identify code that should use join() or StringBuilder\n"
                "- As a performance-focused complement to loop_complexity\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For loop complexity estimation (use loop_complexity)\n"
                "- For nesting depth (use nesting_depth)\n"
                "- For general performance (use health_score)"
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

        analyzer = StringConcatLoopAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: StringConcatLoopResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_hotspots": result.total_hotspots,
            "hotspots": [h.to_dict() for h in result.hotspots],
        }

    def _format_toon(self, result: StringConcatLoopResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("String Concat in Loops Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append("")

        if result.hotspots:
            lines.append(f"Found {len(result.hotspots)} string concat(s) in loops:")
            for h in result.hotspots:
                lines.append(
                    f"  L{h.line_number}: {h.variable} {h.concat_operator} "
                    f"in {h.loop_type} ({h.severity})"
                )
        else:
            lines.append("No string concatenation found inside loops.")

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
