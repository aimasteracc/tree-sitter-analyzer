"""Implicit String Concatenation Tool — MCP Tool.

Detects Python's implicit string literal concatenation where adjacent
string literals are silently joined without an explicit operator.
"""
from __future__ import annotations

from typing import Any

from ...analysis.implicit_string_concat import (
    ImplicitStringConcatAnalyzer,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class ImplicitStringConcatTool(BaseMCPTool):
    """MCP tool for detecting implicit string concatenation."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "implicit_string_concat",
            "description": (
                "Detect implicit string concatenation in Python: "
                "adjacent string literals silently joined without +."
                "\n\n"
                "This catches common bugs like ['a' 'b'] which is "
                "a one-element list, not two elements."
                "\n\n"
                "Supported Languages:\n"
                "- Python only (language-specific quirk)\n"
                "\n"
                "Issue Types:\n"
                "- implicit_string_concat: adjacent literals concatenated\n"
                "- implicit_concat_missing_comma: in collection, likely missing comma\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find accidental implicit concatenation\n"
                "- To catch missing commas in collection literals\n"
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

        analyzer = ImplicitStringConcatAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: Any) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_checked": result.total_checked,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: Any) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Implicit String Concatenation Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Locations checked: {result.total_checked}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} implicit concatenation(s):")
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: [{issue.severity}] "
                    f"{issue.issue_type} — {issue.context}"
                )
        else:
            lines.append("No implicit string concatenation found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
