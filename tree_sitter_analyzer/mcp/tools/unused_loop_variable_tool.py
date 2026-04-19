"""Unused Loop Variable Tool — MCP Tool.

Detects named loop variables that are never referenced in the loop body.
"""
from __future__ import annotations

from typing import Any

from ...analysis.unused_loop_variable import (
    UnusedLoopVariableAnalyzer,
    UnusedLoopVariableResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class UnusedLoopVariableTool(BaseMCPTool):
    """MCP tool for detecting unused loop variables."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "unused_loop_variable",
            "description": (
                "Detect named loop variables that are never used in the loop body "
                "(e.g., `for x in items: process()` where x is never referenced)."
                "\n\n"
                "Unused loop variables often indicate missing logic or should be "
                "renamed to `_` to signal intentional non-use."
                "\n\n"
                "Supported Languages:\n"
                "- Python, JavaScript/TypeScript\n"
                "\n"
                "Issue Types:\n"
                "- unused_for_variable: Python for-loop variable never used\n"
                "- unused_for_of_variable: JS/TS for-of variable never used\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find potentially incomplete loop logic\n"
                "- To clean up code by renaming unused variables to `_`\n"
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

        analyzer = UnusedLoopVariableAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: UnusedLoopVariableResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_loops": result.total_loops,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: UnusedLoopVariableResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Unused Loop Variable Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total loops: {result.total_loops}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} issue(s):")
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: [{issue.severity}] "
                    f"{issue.issue_type} — variable '{issue.variable_name}' "
                    f"in {issue.context}"
                )
        else:
            lines.append("No unused loop variables found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
