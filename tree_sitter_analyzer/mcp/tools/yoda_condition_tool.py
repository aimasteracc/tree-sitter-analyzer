"""Yoda Condition Tool — MCP Tool.

Detects Yoda conditions where a literal appears on the left
side of a comparison, hurting readability.
"""
from __future__ import annotations

from typing import Any

from ...analysis.yoda_condition import (
    YodaConditionAnalyzer,
    YodaConditionResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class YodaConditionTool(BaseMCPTool):
    """MCP tool for detecting Yoda conditions."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "yoda_condition",
            "description": (
                "Detect Yoda conditions: comparisons where a literal "
                "appears on the left side (e.g., '\"expected\" == actual')."
                "\n\n"
                "Modern languages don't need this C-era habit. "
                "Put the variable on the left for readability."
                "\n\n"
                "Supported Languages:\n"
                "- Python, JavaScript/TypeScript, Java, Go\n"
                "\n"
                "Issue Types:\n"
                "- yoda_eq: literal == variable\n"
                "- yoda_neq: literal != variable\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find readability anti-patterns in comparisons\n"
                "- To enforce consistent comparison style\n"
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

        analyzer = YodaConditionAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: YodaConditionResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_comparisons": result.total_comparisons,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: YodaConditionResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Yoda Condition Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total comparisons: {result.total_comparisons}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} Yoda condition(s):")
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: [{issue.severity}] "
                    f"{issue.issue_type} — {issue.context}"
                )
        else:
            lines.append("No Yoda conditions found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
