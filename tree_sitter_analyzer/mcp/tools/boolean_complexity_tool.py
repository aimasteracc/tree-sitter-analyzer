"""Boolean Complexity Tool — MCP Tool.

Analyzes boolean expression complexity. Detects complex boolean chains
that are hard to reason about and suggests extracting named variables.
"""
from __future__ import annotations

from typing import Any

from ...analysis.boolean_complexity import (
    BooleanComplexityAnalyzer,
    BooleanComplexityResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class BooleanComplexityTool(BaseMCPTool):
    """MCP tool for analyzing boolean expression complexity."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "boolean_complexity",
            "description": (
                "Analyze boolean expression complexity. "
                "\n\n"
                "Detects complex boolean expressions (&&/||/and/or chains) "
                "that are hard to reason about. Counts conditions per "
                "expression and flags those with too many conditions, "
                "suggesting extraction into named variables."
                "\n\n"
                "Supported Languages:\n"
                "- Python: and, or\n"
                "- JavaScript/TypeScript: &&, ||\n"
                "- Java: &&, ||\n"
                "- Go: &&, ||\n"
                "\n"
                "Complexity Ratings:\n"
                "- Good (1-3): Acceptable\n"
                "- Warning (4): Consider extracting\n"
                "- Critical (5+): Should extract named variables\n"
                "\n"
                "WHEN TO USE:\n"
                "- During code review to spot complex conditions\n"
                "- To identify boolean expressions that need simplification\n"
                "- As a readability-focused complement to other metrics\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For loop complexity (use loop_complexity)\n"
                "- For nesting depth (use nesting_depth)\n"
                "- For cognitive complexity (use cognitive_complexity)"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Path to a specific file to analyze. "
                            "If provided, analyzes only this file."
                        ),
                    },
                    "threshold": {
                        "type": "integer",
                        "description": (
                            "Condition count threshold. Expressions at or "
                            "above this count are flagged. Default: 4."
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
        threshold = arguments.get("threshold", 4)
        output_format = arguments.get("format", "toon")

        if not file_path:
            return {
                "error": "file_path must be provided",
                "format": output_format,
            }

        analyzer = BooleanComplexityAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result, threshold)
        return self._format_toon(result, threshold)

    def _format_json(
        self,
        result: BooleanComplexityResult,
        threshold: int,
    ) -> dict[str, Any]:
        hotspots = [
            h for h in result.hotspots if h.condition_count >= threshold
        ]
        return {
            "file": result.file_path,
            "total_expressions": result.total_expressions,
            "max_conditions": result.max_conditions,
            "threshold": threshold,
            "hotspot_count": len(hotspots),
            "hotspots": [
                {
                    "line": h.line_number,
                    "conditions": h.condition_count,
                    "expression": h.expression,
                }
                for h in hotspots
            ],
        }

    def _format_toon(
        self,
        result: BooleanComplexityResult,
        threshold: int,
    ) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Boolean Complexity Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total expressions: {result.total_expressions}")
        lines.append(f"Max conditions: {result.max_conditions}")
        lines.append("")

        hotspots = [h for h in result.hotspots if h.condition_count >= threshold]
        if hotspots:
            lines.append(f"Complex expressions (>= {threshold} conditions):")
            for h in hotspots:
                lines.append(
                    f"  L{h.line_number}: {h.condition_count} conditions"
                )
                lines.append(f"    {h.expression}")
        else:
            lines.append(
                f"No expressions exceed condition threshold ({threshold})."
            )

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_expressions": result.total_expressions,
            "max_conditions": result.max_conditions,
            "hotspot_count": len(hotspots),
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")

        return True
