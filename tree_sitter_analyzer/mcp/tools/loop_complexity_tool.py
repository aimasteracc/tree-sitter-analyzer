"""Loop Complexity Tool — MCP Tool.

Analyzes loop nesting and estimates algorithmic complexity.
Detects O(n²) and higher hidden in nested loops.
"""
from __future__ import annotations

from typing import Any

from ...analysis.loop_complexity import (
    LoopComplexityAnalyzer,
    LoopComplexityResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class LoopComplexityTool(BaseMCPTool):
    """MCP tool for analyzing loop complexity."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "loop_complexity",
            "description": (
                "Analyze loop nesting and estimate algorithmic complexity. "
                "\n\n"
                "Detects nested for/while loops and estimates Big-O complexity "
                "(O(n), O(n²), O(n³), etc.). Unlike cognitive complexity "
                "(reading difficulty) or nesting depth (control flow), this "
                "focuses on performance implications of loop nesting."
                "\n\n"
                "Supported Languages:\n"
                "- Python: for, while, list/set/dict comprehensions\n"
                "- JavaScript/TypeScript: for, for-in, for-of, while, do-while\n"
                "- Java: for, enhanced-for, while, do-while\n"
                "- Go: for (includes range)\n"
                "\n"
                "Complexity Estimates:\n"
                "- O(1): No loops\n"
                "- O(n): Single loop level\n"
                "- O(n²): Two nested loops\n"
                "- O(n³): Three nested loops\n"
                "- O(n^k): k nested loops\n"
                "\n"
                "WHEN TO USE:\n"
                "- During code review to spot performance hotspots\n"
                "- To identify O(n²) and higher patterns\n"
                "- As a performance-focused complement to complexity metrics\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For nesting depth (use nesting_depth)\n"
                "- For cognitive complexity (use cognitive_complexity)\n"
                "- For general code smells (use code_smell_detector)"
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
                            "Loop depth threshold. Loops at or above this "
                            "depth are flagged. Default: 2."
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
        threshold = arguments.get("threshold", 2)
        output_format = arguments.get("format", "toon")

        if not file_path:
            return {
                "error": "file_path must be provided",
                "format": output_format,
            }

        analyzer = LoopComplexityAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result, threshold)
        return self._format_toon(result, threshold)

    def _format_json(
        self,
        result: LoopComplexityResult,
        threshold: int,
    ) -> dict[str, Any]:
        hotspots = [
            h for h in result.hotspots if h.depth >= threshold
        ]
        return {
            "file": result.file_path,
            "total_loops": result.total_loops,
            "max_loop_depth": result.max_loop_depth,
            "estimated_complexity": result.estimated_complexity,
            "threshold": threshold,
            "hotspot_count": len(hotspots),
            "hotspots": [
                {
                    "line": h.line_number,
                    "depth": h.depth,
                    "complexity": h.complexity,
                    "loop_type": h.loop_type,
                }
                for h in hotspots
            ],
        }

    def _format_toon(
        self,
        result: LoopComplexityResult,
        threshold: int,
    ) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Loop Complexity Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total loops: {result.total_loops}")
        lines.append(f"Max depth: {result.max_loop_depth}")
        lines.append(f"Estimated: {result.estimated_complexity}")
        lines.append("")

        hotspots = [h for h in result.hotspots if h.depth >= threshold]
        if hotspots:
            lines.append(f"Performance hotspots (depth >= {threshold}):")
            for h in hotspots:
                indent = "  " + "  " * min(h.depth - 1, 5)
                lines.append(
                    f"{indent}L{h.line_number}: "
                    f"{h.loop_type} -> {h.complexity}"
                )
        else:
            lines.append(
                f"No loops exceed depth threshold ({threshold})."
            )

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_loops": result.total_loops,
            "max_loop_depth": result.max_loop_depth,
            "estimated_complexity": result.estimated_complexity,
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
