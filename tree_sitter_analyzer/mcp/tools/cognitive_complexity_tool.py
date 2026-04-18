"""
Cognitive Complexity Tool — MCP Tool

Analyzes cognitive complexity of functions using SonarSource specification.
Supports Python, JavaScript/TypeScript, Java, and Go.
"""
from __future__ import annotations

from typing import Any

from ...analysis.cognitive_complexity import (
    CognitiveComplexityAnalyzer,
    CognitiveComplexityResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class CognitiveComplexityTool(BaseMCPTool):
    """MCP tool for analyzing cognitive complexity of functions."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "cognitive_complexity",
            "description": (
                "Analyze cognitive complexity of functions and methods. "
                "\n\n"
                "Measures how hard code is to understand using the SonarSource "
                "cognitive complexity specification. Unlike cyclomatic complexity, "
                "cognitive complexity accounts for nesting depth, control flow breaks, "
                "and logical operator sequences.\n"
                "\n"
                "Supported Languages:\n"
                "- Python: functions, methods, lambdas, comprehensions\n"
                "- JavaScript/TypeScript: functions, methods, arrow functions\n"
                "- Java: methods, constructors\n"
                "- Go: functions, methods\n"
                "\n"
                "Complexity Ratings:\n"
                "- Simple (1-5): Easy to understand\n"
                "- Moderate (6-10): Manageable complexity\n"
                "- Complex (11-20): Consider refactoring\n"
                "- Very Complex (21-50): Should refactor\n"
                "- Extreme (50+): Must refactor\n"
                "\n"
                "WHEN TO USE:\n"
                "- During code review to identify hard-to-read functions\n"
                "- To prioritize refactoring efforts\n"
                "- As part of CI/CD quality gates\n"
                "- When evaluating code maintainability\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For cyclomatic complexity (use complexity_heatmap)\n"
                "- For detecting code smells (use code_smell_detector)\n"
                "- For file-level metrics (use health_score)"
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
                            "Complexity threshold. Functions above this "
                            "value are flagged. Default: 15."
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
        threshold = arguments.get("threshold", 15)
        output_format = arguments.get("format", "toon")

        if not file_path:
            return {
                "error": "file_path must be provided",
                "format": output_format,
            }

        analyzer = CognitiveComplexityAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result, threshold)
        return self._format_toon(result, threshold)

    def _format_json(
        self,
        result: CognitiveComplexityResult,
        threshold: int,
    ) -> dict[str, Any]:
        complex_fns = result.get_complex_functions(threshold)
        return {
            "file": result.file_path,
            "total_functions": result.total_functions,
            "total_complexity": result.total_complexity,
            "avg_complexity": result.avg_complexity,
            "max_complexity": result.max_complexity,
            "threshold": threshold,
            "complex_function_count": len(complex_fns),
            "complex_functions": [
                {
                    "name": f.name,
                    "type": f.element_type,
                    "start_line": f.start_line,
                    "end_line": f.end_line,
                    "complexity": f.total_complexity,
                    "rating": f.rating,
                    "increments": [
                        {
                            "type": i.increment_type,
                            "line": i.line_number,
                            "value": i.value,
                            "description": i.description,
                        }
                        for i in f.increments
                    ],
                }
                for f in complex_fns
            ],
            "all_functions": [
                {
                    "name": f.name,
                    "type": f.element_type,
                    "start_line": f.start_line,
                    "complexity": f.total_complexity,
                    "rating": f.rating,
                }
                for f in result.functions
            ],
        }

    def _format_toon(
        self,
        result: CognitiveComplexityResult,
        threshold: int,
    ) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Cognitive Complexity Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Functions: {result.total_functions}")
        lines.append(f"Total complexity: {result.total_complexity}")
        lines.append(f"Average: {result.avg_complexity:.1f}")
        lines.append(f"Max: {result.max_complexity}")
        lines.append("")

        complex_fns = result.get_complex_functions(threshold)
        if complex_fns:
            lines.append(f"Complex functions (>{threshold}):")
            for f in complex_fns:
                lines.append(
                    f"  [{f.rating}] {f.name} "
                    f"(L{f.start_line}-L{f.end_line}): "
                    f"complexity={f.total_complexity}"
                )
                for inc in f.increments:
                    lines.append(f"    +{inc.value} {inc.description}")
        else:
            lines.append(f"No functions exceed threshold ({threshold}).")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_functions": result.total_functions,
            "total_complexity": result.total_complexity,
            "max_complexity": result.max_complexity,
            "complex_function_count": len(complex_fns),
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")

        return True
