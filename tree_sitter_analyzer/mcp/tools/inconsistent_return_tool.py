"""Inconsistent Return Tool — MCP Tool.

Detects functions where some paths return a value and others don't.
"""
from __future__ import annotations

from typing import Any

from ...analysis.inconsistent_return import (
    InconsistentReturnAnalyzer,
    InconsistentReturnResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class InconsistentReturnTool(BaseMCPTool):
    """MCP tool for detecting inconsistent return behavior."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "inconsistent_return",
            "description": (
                "Detect functions where some code paths return a value "
                "and others don't (implicit None return)."
                "\n\n"
                "This is a common Python bug source — functions that "
                "sometimes return a value and sometimes fall through "
                "to return None implicitly."
                "\n\n"
                "Supported Languages:\n"
                "- Python, JavaScript/TypeScript, Java, Go\n"
                "\n"
                "Issue Types:\n"
                "- inconsistent_return: mixed value/bare returns\n"
                "\n"
                "WHEN TO USE:\n"
                "- To catch implicit None returns in Python\n"
                "- To verify return path consistency\n"
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

        analyzer = InconsistentReturnAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: InconsistentReturnResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_functions": result.total_functions,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: InconsistentReturnResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Inconsistent Return Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total functions: {result.total_functions}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} function(s) with inconsistent returns:")
            for issue in result.issues:
                parts = [f"L{issue.line}: {issue.function_name}()"]
                if issue.has_value_returns:
                    parts.append(f"{issue.has_value_returns} value returns")
                if issue.has_bare_returns:
                    parts.append(f"{issue.has_bare_returns} bare returns")
                if issue.has_implicit:
                    parts.append("implicit None return")
                lines.append(f"  {', '.join(parts)} [{issue.severity}]")
        else:
            lines.append("No inconsistent returns found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
