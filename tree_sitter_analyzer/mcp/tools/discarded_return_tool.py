"""Discarded Return Value Tool — MCP Tool.

Analyzes code for function calls whose return values are silently discarded.
"""
from __future__ import annotations

from typing import Any

from ...analysis.discarded_return import (
    DiscardedReturnAnalyzer,
    DiscardedReturnResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class DiscardedReturnTool(BaseMCPTool):
    """MCP tool for detecting discarded return values."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "discarded_return",
            "description": (
                "Analyze code for function calls whose return values are "
                "silently discarded."
                "\n\n"
                "Detects three types of issues:\n"
                "- discarded_result: function call used as bare statement\n"
                "- discarded_await: async call without await (JS/TS)\n"
                "- discarded_error: error-returning call ignored (Go)\n"
                "\n"
                "Supported Languages:\n"
                "- Python, JavaScript/TypeScript, Java, Go\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find silently discarded return values\n"
                "- To detect missing await on async calls\n"
                "- To catch ignored error returns\n"
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

        analyzer = DiscardedReturnAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: DiscardedReturnResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_calls": result.total_calls,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: DiscardedReturnResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Discarded Return Value Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total function calls: {result.total_calls}")
        lines.append("")

        if result.issues:
            lines.append(
                f"Found {len(result.issues)} discarded return issue(s):"
            )
            for i in result.issues:
                lines.append(
                    f"  L{i.line}: [{i.issue_type}] [{i.severity}] "
                    f"{i.function_name}()"
                )
        else:
            lines.append("No discarded return issues found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_calls": result.total_calls,
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
