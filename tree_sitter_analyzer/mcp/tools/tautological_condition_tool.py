"""Tautological Condition Tool — MCP Tool.

Detects conditions that always evaluate to the same value:
contradictory, subsumed, and self-comparison conditions.
"""
from __future__ import annotations

from typing import Any

from ...analysis.tautological_condition import (
    TautologicalConditionAnalyzer,
    TautologicalResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class TautologicalConditionTool(BaseMCPTool):
    """MCP tool for detecting tautological conditions."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "tautological_condition",
            "description": (
                "Detect conditions that always evaluate to the same value."
                "\n\n"
                "Finds contradictory, subsumed, and tautological comparisons "
                "in boolean expressions. These are common sources of bugs "
                "where the developer likely intended different logic."
                "\n\n"
                "Supported Languages:\n"
                "- Python: comparison_operator, boolean_operator\n"
                "- JavaScript/TypeScript: binary_expression\n"
                "- Java: binary_expression, method_invocation (.equals)\n"
                "- Go: binary_expression\n"
                "\n"
                "Issue Types:\n"
                "- contradictory_condition: x==5 && x==10 (always false)\n"
                "- subsumed_condition: x>3 && x>5 (first clause redundant)\n"
                "- tautological_comparison: x==x, if True/False\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find conditions that are always true or false\n"
                "- To detect redundant comparisons in compound conditions\n"
                "- To catch copy-paste errors in boolean expressions\n"
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

        analyzer = TautologicalConditionAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: TautologicalResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "functions_analyzed": result.functions_analyzed,
            "total_issues": result.total_issues,
            "high_severity_count": result.high_severity_count,
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: TautologicalResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Tautological Condition Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Functions analyzed: {result.functions_analyzed}")
        lines.append("")

        if result.issues:
            lines.append(
                f"Found {result.total_issues} issue(s) "
                f"({result.high_severity_count} high):"
            )
            for i in result.issues:
                lines.append(
                    f"  L{i.line}: [{i.issue_type}] [{i.severity}] "
                    f"{i.message}"
                )
        else:
            lines.append("No tautological condition issues found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_issues": result.total_issues,
            "high_severity_count": result.high_severity_count,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")

        return True
