"""String Format Consistency Tool — MCP Tool.

Detects mixed string formatting styles within the same Python file
(%-formatting, .format(), f-strings).
"""
from __future__ import annotations

from typing import Any

from ...analysis.string_format_consistency import (
    StringFormatConsistencyAnalyzer,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class StringFormatConsistencyTool(BaseMCPTool):
    """MCP tool for detecting mixed string formatting styles."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "string_format_consistency",
            "description": (
                "Detect mixed string formatting styles in Python: "
                "%-formatting, .format(), and f-strings used together."
                "\n\n"
                "Modern Python should standardize on f-strings."
                "\n\n"
                "Supported Languages:\n"
                "- Python only\n"
                "\n"
                "Issue Types:\n"
                "- mixed_format_styles: multiple styles in same file\n"
                "- legacy_percent_format: %-formatting only\n"
                "- legacy_dot_format: .format() only\n"
                "\n"
                "WHEN TO USE:\n"
                "- To enforce consistent formatting style\n"
                "- To modernize string formatting to f-strings\n"
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

        analyzer = StringFormatConsistencyAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: Any) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_strings": result.total_strings,
            "percent_format_count": result.percent_format_count,
            "dot_format_count": result.dot_format_count,
            "fstring_count": result.fstring_count,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: Any) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("String Format Consistency Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total formatted strings: {result.total_strings}")
        lines.append(f"  %-formatting: {result.percent_format_count}")
        lines.append(f"  .format(): {result.dot_format_count}")
        lines.append(f"  f-strings: {result.fstring_count}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} consistency issue(s):")
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: [{issue.severity}] "
                    f"{issue.issue_type} — {issue.context}"
                )
        else:
            lines.append("Formatting is consistent.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
