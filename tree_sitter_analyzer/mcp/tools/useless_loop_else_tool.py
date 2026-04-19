"""Useless Loop Else Tool — MCP Tool.

Detects for...else and while...else without break in loop body.
"""
from __future__ import annotations

from typing import Any

from ...analysis.useless_loop_else import UselessLoopElseAnalyzer
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class UselessLoopElseTool(BaseMCPTool):
    """MCP tool for detecting useless loop else clauses."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "useless_loop_else",
            "description": (
                "Detect for...else and while...else without break. "
                "Without break, the else clause always runs, making it misleading."
                "\n\n"
                "Supported Languages:\n"
                "- Python only\n"
                "\n"
                "Issue Types:\n"
                "- useless_for_else: for...else without break in loop body\n"
                "- useless_while_else: while...else without break in loop body\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find misleading for/while...else patterns\n"
                "- To catch misunderstood Python loop-else semantics\n"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to a specific file to analyze.",
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

        analyzer = UselessLoopElseAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: Any) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_loop_else": result.total_loop_else,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: Any) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Useless Loop Else Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total loop-else patterns: {result.total_loop_else}")
        lines.append("")

        if result.issues:
            lines.append(
                f"Found {len(result.issues)} useless loop-else pattern(s):"
            )
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: [{issue.severity}] "
                    f"{issue.issue_type} — {issue.suggestion}"
                )
        else:
            lines.append("No useless loop-else patterns found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
