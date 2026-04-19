"""
Nesting Complexity Tool -- MCP Tool.

Combines nesting depth analysis and loop complexity analysis into a single tool.
Routes to the appropriate analyzer based on the `check` parameter.

- "depth": Nesting pyramid depth (how deeply control flow is nested)
- "loops": Loop nesting and Big-O estimation (performance hotspots)
- "all":  Runs both analyses
"""
from __future__ import annotations

from typing import Any

from ...analysis.loop_complexity import (
    LoopComplexityAnalyzer,
    LoopComplexityResult,
)
from ...analysis.nesting_depth import (
    NestingDepthAnalyzer,
    NestingDepthResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)

_VALID_CHECKS = ("depth", "loops", "all")


class NestingComplexityTool(BaseMCPTool):
    """MCP tool for analyzing nesting depth and loop complexity."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "nesting_complexity",
            "description": (
                "Analyze nesting depth and/or loop complexity of functions. "
                "\n\n"
                "Routes to the appropriate analyzer based on the `check` "
                "parameter: nesting pyramid depth, loop nesting with Big-O "
                "estimation, or both combined."
                "\n\n"
                "Supported Languages:\n"
                "- Python: if/for/while/try/with/match, list/set/dict comprehensions\n"
                "- JavaScript/TypeScript: if/for/while/try/switch\n"
                "- Java: if/for/while/try/switch/synchronized\n"
                "- Go: if/for/switch/select\n"
                "\n"
                "Nesting Depth Ratings (check='depth' or 'all'):\n"
                "- Good (1-3): Acceptable nesting\n"
                "- Warning (4): Consider flattening\n"
                "- Critical (5+): Should flatten\n"
                "\n"
                "Loop Complexity Estimates (check='loops' or 'all'):\n"
                "- O(1): No loops\n"
                "- O(n): Single loop level\n"
                "- O(n^2): Two nested loops\n"
                "- O(n^k): k nested loops\n"
                "\n"
                "WHEN TO USE:\n"
                "- During code review to spot deep nesting and performance hotspots\n"
                "- To prioritize refactoring of pyramid code\n"
                "- To detect O(n^2) and higher patterns hidden in nested loops\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For cognitive complexity (use cognitive_complexity)\n"
                "- For cyclomatic complexity (use complexity_heatmap)\n"
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
                    "check": {
                        "type": "string",
                        "description": (
                            "Which analysis to run: "
                            "'depth' for nesting pyramid depth, "
                            "'loops' for loop nesting and Big-O estimation, "
                            "'all' for both. Default: all."
                        ),
                        "enum": ["depth", "loops", "all"],
                    },
                    "threshold": {
                        "type": "integer",
                        "description": (
                            "Threshold for flagging issues. "
                            "For depth: functions at or above this depth "
                            "are flagged (default: 4). "
                            "For loops: loops at or above this depth "
                            "are flagged (default: 2)."
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
        check = arguments.get("check", "all")
        output_format = arguments.get("format", "toon")

        if not file_path:
            return {
                "error": "file_path must be provided",
                "format": output_format,
            }

        resolved_path = self.resolve_and_validate_file_path(file_path)

        if check == "depth":
            return self._run_depth(resolved_path, arguments, output_format)
        if check == "loops":
            return self._run_loops(resolved_path, arguments, output_format)
        return self._run_all(resolved_path, arguments, output_format)

    # ------------------------------------------------------------------
    # Depth analysis
    # ------------------------------------------------------------------

    def _run_depth(
        self,
        file_path: str,
        arguments: dict[str, Any],
        output_format: str,
    ) -> dict[str, Any]:
        threshold = arguments.get("threshold", 4)
        analyzer = NestingDepthAnalyzer()
        result = analyzer.analyze_file(file_path)
        if output_format == "json":
            return self._format_depth_json(result, threshold)
        return self._format_depth_toon(result, threshold)

    def _format_depth_json(
        self,
        result: NestingDepthResult,
        threshold: int,
    ) -> dict[str, Any]:
        deep_fns = result.get_deep_functions(threshold)
        return {
            "check": "depth",
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

    def _format_depth_toon(
        self,
        result: NestingDepthResult,
        threshold: int,
    ) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Nesting Complexity -- Depth Analysis")
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
            "check": "depth",
            "content": toon.encode("\n".join(lines)),
            "total_functions": result.total_functions,
            "max_depth": result.max_depth,
            "deep_function_count": len(deep_fns),
        }

    # ------------------------------------------------------------------
    # Loop complexity analysis
    # ------------------------------------------------------------------

    def _run_loops(
        self,
        file_path: str,
        arguments: dict[str, Any],
        output_format: str,
    ) -> dict[str, Any]:
        threshold = arguments.get("threshold", 2)
        analyzer = LoopComplexityAnalyzer()
        result = analyzer.analyze_file(file_path)
        if output_format == "json":
            return self._format_loops_json(result, threshold)
        return self._format_loops_toon(result, threshold)

    def _format_loops_json(
        self,
        result: LoopComplexityResult,
        threshold: int,
    ) -> dict[str, Any]:
        hotspots = [h for h in result.hotspots if h.depth >= threshold]
        return {
            "check": "loops",
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

    def _format_loops_toon(
        self,
        result: LoopComplexityResult,
        threshold: int,
    ) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Nesting Complexity -- Loop Analysis")
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
            "check": "loops",
            "content": toon.encode("\n".join(lines)),
            "total_loops": result.total_loops,
            "max_loop_depth": result.max_loop_depth,
            "estimated_complexity": result.estimated_complexity,
            "hotspot_count": len(hotspots),
        }

    # ------------------------------------------------------------------
    # Combined analysis ("all")
    # ------------------------------------------------------------------

    def _run_all(
        self,
        file_path: str,
        arguments: dict[str, Any],
        output_format: str,
    ) -> dict[str, Any]:
        depth_threshold = arguments.get("threshold", 4)
        loop_threshold = arguments.get("threshold", 2)

        depth_analyzer = NestingDepthAnalyzer()
        loop_analyzer = LoopComplexityAnalyzer()

        depth_result = depth_analyzer.analyze_file(file_path)
        loop_result = loop_analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_combined_json(
                depth_result, loop_result, depth_threshold, loop_threshold,
            )
        return self._format_combined_toon(
            depth_result, loop_result, depth_threshold, loop_threshold,
        )

    def _format_combined_json(
        self,
        depth_result: NestingDepthResult,
        loop_result: LoopComplexityResult,
        depth_threshold: int,
        loop_threshold: int,
    ) -> dict[str, Any]:
        deep_fns = depth_result.get_deep_functions(depth_threshold)
        loop_hotspots = [
            h for h in loop_result.hotspots if h.depth >= loop_threshold
        ]
        return {
            "check": "all",
            "file": depth_result.file_path,
            "depth": {
                "total_functions": depth_result.total_functions,
                "max_depth": depth_result.max_depth,
                "avg_depth": depth_result.avg_depth,
                "deep_function_total": depth_result.deep_functions,
                "threshold": depth_threshold,
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
            },
            "loops": {
                "total_loops": loop_result.total_loops,
                "max_loop_depth": loop_result.max_loop_depth,
                "estimated_complexity": loop_result.estimated_complexity,
                "threshold": loop_threshold,
                "hotspot_count": len(loop_hotspots),
                "hotspots": [
                    {
                        "line": h.line_number,
                        "depth": h.depth,
                        "complexity": h.complexity,
                        "loop_type": h.loop_type,
                    }
                    for h in loop_hotspots
                ],
            },
        }

    def _format_combined_toon(
        self,
        depth_result: NestingDepthResult,
        loop_result: LoopComplexityResult,
        depth_threshold: int,
        loop_threshold: int,
    ) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Nesting Complexity -- Combined Analysis")
        lines.append(f"File: {depth_result.file_path}")
        lines.append("")

        # -- Depth section --
        lines.append("--- Depth ---")
        lines.append(f"Functions: {depth_result.total_functions}")
        lines.append(f"Max depth: {depth_result.max_depth}")
        lines.append(f"Average: {depth_result.avg_depth:.1f}")
        lines.append(
            f"Deep functions (>={depth_threshold}): "
            f"{depth_result.deep_functions}"
        )

        deep_fns = depth_result.get_deep_functions(depth_threshold)
        if deep_fns:
            lines.append("")
            lines.append(f"Deep nesting (depth >= {depth_threshold}):")
            for f in deep_fns:
                lines.append(
                    f"  [{f.rating}] {f.name} "
                    f"(L{f.start_line}-L{f.end_line}): "
                    f"max_depth={f.max_depth}"
                )
                for h in f.hotspots:
                    if h.depth >= depth_threshold:
                        indent = "    " + "  " * min(h.depth - 1, 5)
                        lines.append(
                            f"{indent}L{h.line_number}: "
                            f"{h.node_type} (depth {h.depth})"
                        )
        else:
            lines.append(
                f"No functions exceed depth threshold ({depth_threshold})."
            )

        # -- Loop section --
        lines.append("")
        lines.append("--- Loops ---")
        lines.append(f"Total loops: {loop_result.total_loops}")
        lines.append(f"Max depth: {loop_result.max_loop_depth}")
        lines.append(f"Estimated: {loop_result.estimated_complexity}")

        loop_hotspots = [
            lh for lh in loop_result.hotspots if lh.depth >= loop_threshold
        ]
        if loop_hotspots:
            lines.append(
                f"Performance hotspots (depth >= {loop_threshold}):"
            )
            for lh in loop_hotspots:
                indent = "  " + "  " * min(lh.depth - 1, 5)
                lines.append(
                    f"{indent}L{lh.line_number}: "
                    f"{lh.loop_type} -> {lh.complexity}"
                )
        else:
            lines.append(
                f"No loops exceed depth threshold ({loop_threshold})."
            )

        toon = ToonEncoder()
        return {
            "check": "all",
            "content": toon.encode("\n".join(lines)),
            "depth_max": depth_result.max_depth,
            "deep_function_count": len(deep_fns),
            "loop_max_depth": loop_result.max_loop_depth,
            "estimated_complexity": loop_result.estimated_complexity,
            "hotspot_count": len(loop_hotspots),
        }

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        check = arguments.get("check", "all")
        if check not in _VALID_CHECKS:
            raise ValueError(
                f"check must be one of {_VALID_CHECKS}, got '{check}'"
            )

        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")

        return True
