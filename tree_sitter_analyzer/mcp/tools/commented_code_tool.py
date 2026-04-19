"""Commented-Out Code Tool — MCP Tool.

Analyzes code for commented-out code blocks that should be removed
and tracked via version control instead.
"""
from __future__ import annotations

from typing import Any

from ...analysis.commented_code import (
    CommentedCodeDetector,
    CommentedCodeResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class CommentedCodeTool(BaseMCPTool):
    """MCP tool for detecting commented-out code."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "commented_code",
            "description": (
                "Analyze code for commented-out code blocks. "
                "\n\n"
                "Detects code that has been commented out instead of "
                "being removed: assignments, function calls, imports, "
                "and declarations hiding in comments."
                "\n\n"
                "Supported Languages:\n"
                "- Python, JavaScript/TypeScript, Java, Go\n"
                "\n"
                "Issue Types:\n"
                "- commented_assignment: assignment statements in comments\n"
                "- commented_call: function/method calls in comments\n"
                "- commented_import: import statements in comments\n"
                "- commented_declaration: function/class declarations in comments\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find commented-out code before code review\n"
                "- To audit codebase cleanliness\n"
                "- To identify dead code that should be in version control\n"
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

        analyzer = CommentedCodeDetector()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: CommentedCodeResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_count": result.total_count,
            "by_type": result.by_type,
            "items": [i.to_dict() for i in result.items],
        }

    def _format_toon(self, result: CommentedCodeResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Commented-Out Code Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Commented-out blocks: {result.total_count}")
        lines.append("")

        if result.items:
            lines.append(f"Found {result.total_count} commented-out code block(s):")
            for item in result.items:
                lines.append(
                    f"  L{item.line}: [{item.severity}] "
                    f"{item.issue_type} — {item.content[:60]}"
                )
        else:
            lines.append("No commented-out code found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_count": result.total_count,
        }
