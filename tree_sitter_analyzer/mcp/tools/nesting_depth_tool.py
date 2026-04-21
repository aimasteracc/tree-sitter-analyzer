"""
Nesting Depth Tool — MCP Tool.

Analyzes nesting depth of functions. Detects deeply nested code pyramids
and suggests flattening. Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

from typing import Any

from ...analysis.nesting_depth import (
    NestingDepthAnalyzer,
    NestingDepthResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class NestingDepthTool(BaseMCPTool):
    """MCP tool for analyzing nesting depth of functions."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "nesting_depth",
            "description": (
                "Analyze nesting depth of functions and methods. "
                "\n\n"
                "Measures how deeply nested control flow structures are "
                "within each function. Unlike cognitive complexity (SonarSource) "
                "or cyclomatic complexity (path counting), nesting depth is a "
                "simple, immediately actionable metric: 'flatten this pyramid.'"
                "\n\n"
                "Supported Languages:\n"
                "- Python: if/for/while/try/with/match\n"
                "- JavaScript/TypeScript: if/for/while/try/switch\n"
                "- Java: if/for/while/try/switch/synchronized\n"
                "- Go: if/for/switch/select\n"
                "\n"
                "Depth Ratings:\n"
                "- Good (1-3): Acceptable nesting\n"
                "- Warning (4): Consider flattening\n"
                "- Critical (5+): Should flatten\n"
                "\n"
                "WHEN TO USE:\n"
                "- During code review to spot deep nesting\n"
                "- To prioritize refactoring of 'pyramid' code\n"
                "- As a simpler complement to cognitive/cyclomatic complexity\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For cognitive complexity (use cognitive_complexity)\n"
                "- For nesting complexity metrics (use nesting_complexity)\n"
                "- For code smell detection (use code_smell_detector)"
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
                            "Depth threshold. Functions at or above this "
                            "depth are flagged. Default: 4."
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

        analyzer = NestingDepthAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result, threshold)
        return self._format_toon(result, threshold)

    def _format_json(
        self,
        result: NestingDepthResult,
        threshold: int,
    ) -> dict[str, Any]:
        deep_fns = result.get_deep_functions(threshold)
        return {
            "file": result.file_path,
            "total_functions": result.total_functions,
            "max_depth": result.max_depth,
            "avg_depth": result.avg_depth,
            "deep_function_total": result.deep_functions,
            "threshold": threshold,
            "deep_function_count": len(deep_fns),
            "deep_functions": [
                {
                    "name": f.name,
                    "type": f.element_type,
                    "start_line": f.start_line,
                    "end_line": f.end_line,
                    "max_depth": f.max_depth,
                    "avg_depth": f.avg_depth,
                    "rating": f.rating,
                    "hotspots": [
                        {
                            "line": h.line_number,
                            "depth": h.depth,
                            "node_type": h.node_type,
                        }
                        for h in f.hotspots
                    ],
                }
                for f in deep_fns
            ],
            "all_functions": [
                {
                    "name": f.name,
                    "type": f.element_type,
                    "start_line": f.start_line,
                    "max_depth": f.max_depth,
                    "rating": f.rating,
                }
                for f in result.functions
            ],
        }

    def _format_toon(
        self,
        result: NestingDepthResult,
        threshold: int,
    ) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Nesting Depth Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Functions: {result.total_functions}")
        lines.append(f"Max depth: {result.max_depth}")
        lines.append(f"Average: {result.avg_depth:.1f}")
        lines.append(f"Deep functions (>={threshold}): {result.deep_functions}")
        lines.append("")

        deep_fns = result.get_deep_functions(threshold)
        if deep_fns:
            lines.append(f"Deep nesting (depth >= {threshold}):")
            for f in deep_fns:
                lines.append(
                    f"  [{f.rating}] {f.name} "
                    f"(L{f.start_line}-L{f.end_line}): "
                    f"max_depth={f.max_depth}"
                )
                for h in f.hotspots:
                    if h.depth >= threshold:
                        indent = "    " + "  " * min(h.depth - 1, 5)
                        lines.append(
                            f"{indent}L{h.line_number}: "
                            f"{h.node_type} (depth {h.depth})"
                        )
        else:
            lines.append(f"No functions exceed depth threshold ({threshold}).")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_functions": result.total_functions,
            "max_depth": result.max_depth,
            "deep_function_count": len(deep_fns),
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")

        return True
