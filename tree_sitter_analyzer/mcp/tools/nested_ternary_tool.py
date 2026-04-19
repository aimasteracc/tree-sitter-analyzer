"""Nested Ternary Tool — MCP Tool.

Detects deeply nested ternary/conditional expressions that hurt readability.
"""
from __future__ import annotations

from typing import Any

from ...analysis.nested_ternary import (
    NestedTernaryAnalyzer,
    NestedTernaryResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class NestedTernaryTool(BaseMCPTool):
    """MCP tool for detecting deeply nested ternary expressions."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "nested_ternary",
            "description": (
                "Detect deeply nested ternary/conditional expressions."
                "\n\n"
                "Nested ternaries are hard to read and error-prone. "
                "Flagged at nesting depth >= 2."
                "\n\n"
                "Supported Languages:\n"
                "- Python: conditional_expression (x if a else y)\n"
                "- JavaScript/TypeScript: ternary_expression (a ? x : y)\n"
                "- Java: ternary_expression (a ? x : y)\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find unreadable nested ternary chains\n"
                "- To identify refactoring candidates for if/elif/else\n"
                "- To catch accidental nesting from copy-paste errors\n"
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
            return {"error": "file_path must be provided", "format": output_format}

        analyzer = NestedTernaryAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: NestedTernaryResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_ternaries": result.total_ternaries,
            "total_issues": result.total_issues,
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: NestedTernaryResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Nested Ternary Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total ternaries: {result.total_ternaries}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {result.total_issues} nested ternary issue(s):")
            for i in result.issues:
                lines.append(
                    f"  L{i.line}: [depth={i.depth}] [{i.severity}] "
                    f"{i.message}"
                )
        else:
            lines.append("No deeply nested ternaries found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_issues": result.total_issues,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")
        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")
        return True
