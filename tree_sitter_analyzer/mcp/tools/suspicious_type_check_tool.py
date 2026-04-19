"""Suspicious Type Check Tool — MCP Tool.

Detects type(x) == Y comparisons that should use isinstance(x, Y)
to properly handle subclasses.
"""
from __future__ import annotations

from typing import Any

from ...analysis.suspicious_type_check import (
    SuspiciousTypeCheckAnalyzer,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class SuspiciousTypeCheckTool(BaseMCPTool):
    """MCP tool for detecting suspicious type checks."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "suspicious_type_check",
            "description": (
                "Detect type(x) == Y comparisons that should use "
                "isinstance(x, Y) to support subclasses."
                "\n\n"
                "Supported Languages:\n"
                "- Python only\n"
                "\n"
                "Issue Types:\n"
                "- eq_type_check: type(x) == Y\n"
                "- ne_type_check: type(x) != Y\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find non-Pythonic type checks\n"
                "- To catch subclass-ignoring comparisons\n"
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

        analyzer = SuspiciousTypeCheckAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: Any) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_comparisons": result.total_comparisons,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: Any) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Suspicious Type Check Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total comparisons: {result.total_comparisons}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} suspicious type check(s):")
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: [{issue.severity}] "
                    f"{issue.issue_type} — {issue.context}"
                )
        else:
            lines.append("No suspicious type checks found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
