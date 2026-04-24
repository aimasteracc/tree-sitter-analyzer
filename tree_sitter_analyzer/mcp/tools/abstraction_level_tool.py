"""Abstraction Level Tool — MCP Tool.

Detects functions mixing high-level and low-level abstractions.
"""
from __future__ import annotations

from typing import Any

from ...analysis.abstraction_level import (
    AbstractionLevelAnalyzer,
    AbstractionResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class AbstractionLevelTool(BaseMCPTool):
    """MCP tool for detecting mixed abstraction levels in functions."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "abstraction_level",
            "description": (
                "Detect functions that mix high-level abstractions with "
                "low-level implementation details."
                "\n\n"
                "A function that calls business logic methods (validate, "
                "transform, persist) alongside raw string ops (split, trim), "
                "arithmetic, and indexing forces readers to context-switch "
                "between 'what it does' and 'how it does it'."
                "\n\n"
                "Supported Languages:\n"
                "- Python\n"
                "- JavaScript/TypeScript\n"
                "- Java\n"
                "- Go\n"
                "\n"
                "Issue Types:\n"
                "- mixed_abstraction: function mixes 3+ high-level and 3+ "
                "low-level statements (medium)\n"
                "- leaky_abstraction: function with abstraction level "
                "transitions (low)\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find functions that are hard to read due to abstraction "
                "mixing\n"
                "- To identify extract-method candidates for Clean Code "
                "refactoring\n"
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

        analyzer = AbstractionLevelAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: AbstractionResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_functions": result.total_functions,
            "issue_count": len(result.issues),
            "issues": [
                {
                    "line": i.line_number,
                    "function": i.function_name,
                    "type": i.issue_type,
                    "severity": i.severity,
                    "high_level": i.high_level_count,
                    "low_level": i.low_level_count,
                    "transitions": i.transitions,
                }
                for i in result.issues
            ],
        }

    def _format_toon(self, result: AbstractionResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Abstraction Level Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Functions: {result.total_functions}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} mixed-abstraction function(s):")
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line_number}: {issue.function_name} "
                    f"({issue.issue_type}, "
                    f"high={issue.high_level_count} low={issue.low_level_count} "
                    f"switches={issue.transitions})"
                )
        else:
            lines.append("All functions operate at consistent abstraction levels.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
