"""Primitive Obsession Tool — MCP Tool.

Analyzes code for primitive obsession patterns where primitive types are
overused instead of proper value objects.
"""
from __future__ import annotations

from typing import Any

from ...analysis.primitive_obsession import (
    DEFAULT_MIN_ANEMIC_FIELDS,
    DEFAULT_MIN_PRIMITIVE_LOCALS,
    DEFAULT_MIN_PRIMITIVE_PARAMS,
    PrimitiveObsessionAnalyzer,
    PrimitiveObsessionResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class PrimitiveObsessionTool(BaseMCPTool):
    """MCP tool for detecting primitive obsession patterns."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "primitive_obsession",
            "description": (
                "Detect overuse of primitive types (str, int, float, bool) "
                "where value objects would be more appropriate."
                "\n\n"
                "Supported Languages:\n"
                "- Python: type hints and variable name heuristics\n"
                "- JavaScript/TypeScript: JSDoc/TS types and heuristics\n"
                "- Java: type declarations in method signatures\n"
                "- Go: type declarations in function signatures\n"
                "\n"
                "Issue Types:\n"
                "- primitive_heavy_params: 4+ params all of primitive types "
                "(medium)\n"
                "- primitive_soup: 8+ primitive local variables (medium)\n"
                "- anemic_value_object: data class with only primitive "
                "fields (low)\n"
                "- type_hint_code_smell: string/int used as type encoding "
                "(high)\n"
                "\n"
                "WHEN TO USE:\n"
                "- During code review to find value object candidates\n"
                "- To improve type safety in codebases\n"
                "- To identify Fowler's Primitive Obsession smell\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For coupling analysis (use coupling_metrics)\n"
                "- For naming issues (use naming_conventions)\n"
                "- For data clumps (use data_clump)"
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
                    "min_primitive_params": {
                        "type": "number",
                        "description": (
                            "Min primitive params to flag (default: 4)"
                        ),
                    },
                    "min_primitive_locals": {
                        "type": "number",
                        "description": (
                            "Min primitive locals to flag (default: 8)"
                        ),
                    },
                    "min_anemic_fields": {
                        "type": "number",
                        "description": (
                            "Min fields for anemic class flag (default: 3)"
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
        min_params = arguments.get(
            "min_primitive_params", DEFAULT_MIN_PRIMITIVE_PARAMS
        )
        min_locals = arguments.get(
            "min_primitive_locals", DEFAULT_MIN_PRIMITIVE_LOCALS
        )
        min_fields = arguments.get(
            "min_anemic_fields", DEFAULT_MIN_ANEMIC_FIELDS
        )

        if not file_path:
            return {
                "error": "file_path must be provided",
                "format": output_format,
            }

        analyzer = PrimitiveObsessionAnalyzer(
            min_primitive_params=int(min_params),
            min_primitive_locals=int(min_locals),
            min_anemic_fields=int(min_fields),
        )
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: PrimitiveObsessionResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "functions_analyzed": result.functions_analyzed,
            "classes_analyzed": result.classes_analyzed,
            "issue_count": result.total_issues,
            "high_severity_count": result.high_severity_count,
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: PrimitiveObsessionResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Primitive Obsession Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(
            f"Functions analyzed: {result.functions_analyzed}"
        )
        lines.append(f"Classes analyzed: {result.classes_analyzed}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} issue(s):")
            for i in result.issues:
                lines.append(
                    f"  L{i.line}: [{i.issue_type}] [{i.severity}]"
                )
                lines.append(f"    {i.message}")
                if i.suggestion:
                    lines.append(f"    Fix: {i.suggestion}")
        else:
            lines.append("No primitive obsession issues found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "functions_analyzed": result.functions_analyzed,
            "classes_analyzed": result.classes_analyzed,
            "issue_count": result.total_issues,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")

        return True
