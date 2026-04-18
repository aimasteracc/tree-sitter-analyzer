"""Function Size Analyzer Tool — MCP Tool.

Detects oversized functions and methods by measuring lines of code,
parameter count, and body span. Supports Python, JavaScript/TypeScript,
Java, and Go.
"""
from __future__ import annotations

from typing import Any

from ...analysis.function_size import (
    RATING_CRITICAL,
    RATING_GOOD,
    RATING_WARNING,
    FunctionSizeAnalyzer,
    FunctionSizeResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class FunctionSizeTool(BaseMCPTool):
    """MCP tool for analyzing function size."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "function_size",
            "description": (
                "Analyze function/method size (lines of code, parameters). "
                "\n\n"
                "Detects oversized functions that are hard to read, review, "
                "and test. Reports LOC, parameter count, and a rating "
                "(good/warning/critical) for each function."
                "\n\n"
                "Thresholds:\n"
                "- Good: <= 20 LOC, <= 4 params\n"
                "- Warning: 21-50 LOC or 5-6 params\n"
                "- Critical: > 50 LOC or > 6 params\n"
                "\n"
                "Supported Languages:\n"
                "- Python: functions, methods, class methods, staticmethods\n"
                "- JavaScript/TypeScript: function declarations, arrow functions, "
                "class methods\n"
                "- Java: methods, constructors, static methods\n"
                "- Go: functions, methods\n"
                "\n"
                "WHEN TO USE:\n"
                "- During code review to flag oversized functions\n"
                "- To guide refactoring priorities\n"
                "- To track code size trends over time\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For complexity analysis (use cognitive_complexity)\n"
                "- For nesting depth (use nesting_depth)\n"
                "- For dead code detection (use dead_code)"
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
                    "project_root": {
                        "type": "string",
                        "description": (
                            "Project root directory for multi-file scan. "
                            "Ignored if file_path is provided."
                        ),
                    },
                    "loc_threshold": {
                        "type": "integer",
                        "description": (
                            "LOC threshold for oversized detection. "
                            "Default: 20."
                        ),
                        "default": 20,
                    },
                    "rating_filter": {
                        "type": "string",
                        "description": (
                            "Filter by rating: warning, critical, or all. "
                            "Default: all."
                        ),
                        "enum": ["warning", "critical", "all"],
                        "default": "all",
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
        project_root = arguments.get("project_root", "")
        loc_threshold = arguments.get("loc_threshold", 20)
        rating_filter = arguments.get("rating_filter", "all")
        output_format = arguments.get("format", "toon")

        analyzer = FunctionSizeAnalyzer()

        if file_path:
            result = analyzer.analyze_file(file_path)
            filtered = self._filter_result(result, rating_filter, loc_threshold)
            if output_format == "json":
                return self._format_json(filtered)
            return self._format_toon(filtered)

        root = project_root or self.project_root
        if root:
            results = analyzer.analyze_directory(root)
            if output_format == "json":
                return self._format_directory_json(results)
            return self._format_directory_toon(results)

        return {
            "error": "file_path or project_root must be provided",
            "format": output_format,
        }

    def _filter_result(
        self,
        result: FunctionSizeResult,
        rating_filter: str,
        loc_threshold: int,
    ) -> FunctionSizeResult:
        funcs = list(result.functions)
        if rating_filter == "warning":
            funcs = [
                f for f in funcs
                if f.rating in (RATING_WARNING, RATING_CRITICAL)
            ]
        elif rating_filter == "critical":
            funcs = [f for f in funcs if f.rating == RATING_CRITICAL]

        oversized = sum(1 for f in funcs if f.rating != RATING_GOOD)
        return FunctionSizeResult(
            functions=tuple(funcs),
            total_functions=len(funcs),
            oversized_functions=oversized,
            avg_loc=result.avg_loc,
            max_loc=result.max_loc,
            max_params=result.max_params,
            file_path=result.file_path,
        )

    def _format_json(self, result: FunctionSizeResult) -> dict[str, Any]:
        return result.to_dict()

    def _format_toon(self, result: FunctionSizeResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Function Size Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(
            f"Functions: {result.total_functions} "
            f"(oversized: {result.oversized_functions})"
        )
        lines.append(
            f"Avg LOC: {result.avg_loc} | "
            f"Max LOC: {result.max_loc} | "
            f"Max Params: {result.max_params}"
        )
        lines.append("")

        for fn in result.functions:
            if fn.rating != RATING_GOOD:
                lines.append(
                    f"  [{fn.rating.upper()}] {fn.name}: "
                    f"{fn.loc} LOC, {fn.param_count} params "
                    f"(L{fn.start_line}-L{fn.end_line})"
                )

        if result.oversized_functions == 0:
            lines.append("All functions within size limits.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_functions": result.total_functions,
            "oversized_functions": result.oversized_functions,
        }

    def _format_directory_json(
        self,
        results: list[tuple[str, FunctionSizeResult]],
    ) -> dict[str, Any]:
        files: list[dict[str, Any]] = []
        total_funcs = 0
        total_oversized = 0
        for _file_path, result in results:
            files.append(result.to_dict())
            total_funcs += result.total_functions
            total_oversized += result.oversized_functions
        return {
            "files": files,
            "total_files": len(results),
            "total_functions": total_funcs,
            "total_oversized": total_oversized,
        }

    def _format_directory_toon(
        self,
        results: list[tuple[str, FunctionSizeResult]],
    ) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Function Size Analysis - Project Summary")
        lines.append(f"Files analyzed: {len(results)}")

        total_funcs = 0
        total_oversized = 0
        for _path, result in results:
            total_funcs += result.total_functions
            total_oversized += result.oversized_functions

        lines.append(
            f"Functions: {total_funcs} total, "
            f"{total_oversized} oversized"
        )
        lines.append("")

        for _path, result in results:
            if result.oversized_functions > 0:
                lines.append(
                    f"  {result.file_path}: "
                    f"{result.oversized_functions} oversized"
                )
                for fn in result.functions:
                    if fn.rating != RATING_GOOD:
                        lines.append(
                            f"    [{fn.rating.upper()}] {fn.name}: "
                            f"{fn.loc} LOC, {fn.param_count} params"
                        )

        if total_oversized == 0:
            lines.append("All functions within size limits.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_files": len(results),
            "total_functions": total_funcs,
            "total_oversized": total_oversized,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        rating = arguments.get("rating_filter", "all")
        if rating not in ("warning", "critical", "all"):
            raise ValueError(
                "rating_filter must be 'warning', 'critical', or 'all'"
            )

        return True
