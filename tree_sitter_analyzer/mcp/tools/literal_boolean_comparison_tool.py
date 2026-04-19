"""Literal Boolean Comparison Tool — MCP Tool.

Analyzes code for improper comparisons with boolean/None/null literals.
"""
from __future__ import annotations

from typing import Any

from ...analysis.literal_boolean_comparison import (
    LiteralBooleanComparisonAnalyzer,
    LiteralBooleanComparisonResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class LiteralBooleanComparisonTool(BaseMCPTool):
    """MCP tool for detecting literal boolean comparison issues."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "literal_boolean_comparison",
            "description": (
                "Analyze code for improper comparisons with "
                "boolean/None/null literals."
                "\n\n"
                "Detects:\n"
                "- eq_true: x == True (use just x)\n"
                "- eq_false: x == False (use not x)\n"
                "- eq_none: x == None (use 'is None', Python)\n"
                "- ne_none: x != None (use 'is not None', Python)\n"
                "- eq_null_loose: x == null (use ===, JS/TS)\n"
                "- ne_null_loose: x != null (use !==, JS/TS)\n"
                "\n"
                "Supported Languages:\n"
                "- Python, JavaScript/TypeScript, Java, Go\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find non-idiomatic boolean comparisons\n"
                "- To detect loose null checks in JS/TS\n"
                "- To enforce proper None checks in Python\n"
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

        analyzer = LiteralBooleanComparisonAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(
        self, result: LiteralBooleanComparisonResult,
    ) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_comparisons": result.total_comparisons,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(
        self, result: LiteralBooleanComparisonResult,
    ) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Literal Boolean Comparison Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total comparisons: {result.total_comparisons}")
        lines.append("")

        if result.issues:
            lines.append(
                f"Found {len(result.issues)} issue(s):"
            )
            for i in result.issues:
                lines.append(
                    f"  L{i.line}: [{i.issue_type}] [{i.severity}] "
                    f"{i.description}"
                )
        else:
            lines.append("No literal boolean comparison issues found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_comparisons": result.total_comparisons,
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
