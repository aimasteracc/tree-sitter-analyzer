"""Float Equality Comparison Tool — MCP Tool.

Detects exact equality comparisons with floating-point literals.
IEEE 754 rounding makes == and != unreliable for float values.
"""
from __future__ import annotations

from typing import Any

from ...analysis.float_equality import (
    FloatEqualityAnalyzer,
    FloatEqualityResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class FloatEqualityTool(BaseMCPTool):
    """MCP tool for detecting float equality comparisons."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "float_equality",
            "description": (
                "Detect exact equality comparisons (`==`/`!=`) involving "
                "floating-point literals, which can produce incorrect results "
                "due to IEEE 754 rounding (e.g., `x == 0.1`, `result != 3.14`)."
                "\n\n"
                "Floating-point values cannot represent most decimal fractions "
                "exactly, making direct equality comparison unreliable."
                "\n\n"
                "Supported Languages:\n"
                "- Python, JavaScript/TypeScript, Java, Go\n"
                "\n"
                "Issue Types:\n"
                "- float_equality: `x == 0.1` (use epsilon comparison)\n"
                "- float_inequality: `x != 3.14` (use epsilon comparison)\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find IEEE 754 precision bugs in numeric code\n"
                "- To catch unreliable float comparisons in financial/scientific code\n"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Path to a specific file to analyze."
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

        analyzer = FloatEqualityAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: FloatEqualityResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_float_comparisons": result.total_float_comparisons,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: FloatEqualityResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Float Equality Comparison Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total float comparisons: {result.total_float_comparisons}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} issue(s):")
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: [{issue.severity}] "
                    f"{issue.issue_type} — {issue.context}"
                )
        else:
            lines.append("No float equality issues found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
