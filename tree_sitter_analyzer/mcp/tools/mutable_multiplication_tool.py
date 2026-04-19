"""Mutable Multiplication Tool — MCP Tool.

Detects `[[]] * n` patterns that create shared references.
"""
from __future__ import annotations

from typing import Any

from ...analysis.mutable_multiplication import (
    MutableMultiplicationAnalyzer,
    MutableMultiplicationResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class MutableMultiplicationTool(BaseMCPTool):
    """MCP tool for detecting mutable multiplication aliases."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "mutable_multiplication",
            "description": (
                "Detect list/tuple multiplication with mutable elements "
                "(e.g., `[[]] * n`, `[{}] * 3`) that creates shared references."
                "\n\n"
                "Modifying one element affects all copies — "
                "a classic Python gotcha."
                "\n\n"
                "Supported Languages:\n"
                "- Python only\n"
                "\n"
                "Issue Types:\n"
                "- mutable_list_mult: `[[]] * n` (shared inner lists)\n"
                "- mutable_tuple_mult: `([[]],) * n` (shared inner lists)\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find silent bugs from list multiplication\n"
                "- To catch shared reference issues in initialization\n"
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

        analyzer = MutableMultiplicationAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: MutableMultiplicationResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_multiplications": result.total_multiplications,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: MutableMultiplicationResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Mutable Multiplication Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total multiplications: {result.total_multiplications}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} issue(s):")
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: [{issue.severity}] "
                    f"{issue.issue_type} — {issue.context}"
                )
        else:
            lines.append("No mutable multiplication issues found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
