"""Unreachable Code Tool — MCP Tool.

Detects code that appears after unconditional termination statements
(return/break/continue/raise/throw) which can never execute.
"""
from __future__ import annotations

from typing import Any

from ...analysis.unreachable_code import (
    UnreachableCodeAnalyzer,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class UnreachableCodeTool(BaseMCPTool):
    """MCP tool for detecting unreachable code."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "unreachable_code",
            "description": (
                "Detect unreachable code after terminal statements: "
                "return, break, continue, raise, throw."
                "\n\n"
                "Code after an unconditional termination statement can "
                "never execute and is dead code that should be removed."
                "\n\n"
                "Supported Languages:\n"
                "- Python, JavaScript/TypeScript, Java, Go\n"
                "\n"
                "Issue Types:\n"
                "- unreachable_after_return: code after return\n"
                "- unreachable_after_break: code after break\n"
                "- unreachable_after_continue: code after continue\n"
                "- unreachable_after_raise: code after raise (Python)\n"
                "- unreachable_after_throw: code after throw (Java/JS/TS)\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find dead code that cannot be reached\n"
                "- To clean up after refactoring or debugging\n"
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

        analyzer = UnreachableCodeAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: Any) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_blocks": result.total_blocks,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: Any) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Unreachable Code Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total blocks scanned: {result.total_blocks}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} unreachable code issue(s):")
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: [{issue.severity}] "
                    f"{issue.issue_type} — {issue.context}"
                )
        else:
            lines.append("No unreachable code found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
