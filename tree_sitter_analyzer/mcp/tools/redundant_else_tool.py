"""Redundant Else Tool — MCP Tool.

Analyzes code for redundant else/elif blocks where the if branch already
terminates with return/break/continue/raise/throw.
"""
from __future__ import annotations

from typing import Any

from ...analysis.redundant_else import (
    RedundantElseAnalyzer,
    RedundantElseResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class RedundantElseTool(BaseMCPTool):
    """MCP tool for analyzing redundant else blocks."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "redundant_else",
            "description": (
                "Analyze code for redundant else/elif blocks. "
                "\n\n"
                "Detects else blocks that are unnecessary because the "
                "corresponding if branch already terminates with "
                "return/break/continue/raise/throw."
                "\n\n"
                "Supported Languages:\n"
                "- Python, JavaScript/TypeScript, Java, Go\n"
                "\n"
                "Issue Types:\n"
                "- redundant_else: else block after a terminating if (low)\n"
                "\n"
                "WHEN TO USE:\n"
                "- To simplify control flow by removing unnecessary else\n"
                "- To improve code readability with guard clauses\n"
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

        analyzer = RedundantElseAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: RedundantElseResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_ifs": result.total_ifs,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: RedundantElseResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Redundant Else Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total if statements: {result.total_ifs}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} redundant else issue(s):")
            for i in result.issues:
                lines.append(
                    f"  L{i.line_number}: [{i.issue_type}] "
                    f"[{i.severity}]"
                )
        else:
            lines.append("No redundant else issues found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_ifs": result.total_ifs,
            "issue_count": len(result.issues),
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")

        return True
