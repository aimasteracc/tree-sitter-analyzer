"""Loose Equality Comparison Tool — MCP Tool.

Analyzes JavaScript/TypeScript code for loose equality operators
(==, !=) that should use strict comparison (===, !==).
"""
from __future__ import annotations

from typing import Any

from ...analysis.loose_equality import (
    LooseEqualityAnalyzer,
    LooseEqualityResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class LooseEqualityTool(BaseMCPTool):
    """MCP tool for detecting loose equality comparisons."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "loose_equality",
            "description": (
                "Detect loose equality (==, !=) in JavaScript/TypeScript. "
                "\n\n"
                "Finds comparisons that should use strict equality "
                "(===, !==) to avoid type coercion bugs."
                "\n\n"
                "Supported Languages:\n"
                "- JavaScript, TypeScript\n"
                "\n"
                "Issue Types:\n"
                "- loose_eq: x == y (use x === y)\n"
                "- loose_neq: x != y (use x !== y)\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find type-coercion-prone comparisons\n"
                "- To enforce strict equality in JS/TS codebases\n"
                "- To catch == that may cause silent bugs\n"
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

        analyzer = LooseEqualityAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: LooseEqualityResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_comparisons": result.total_comparisons,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: LooseEqualityResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Loose Equality Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total binary expressions: {result.total_comparisons}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} loose comparison(s):")
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: [{issue.severity}] "
                    f"{issue.issue_type} — {issue.context}"
                )
        else:
            lines.append("No loose equality comparisons found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
