"""Data Clump Tool — MCP Tool.

Analyzes code for parameter groups that appear together across multiple
functions, indicating they should be extracted into a class or data structure.
"""
from __future__ import annotations

from typing import Any

from ...analysis.data_clump import (
    DEFAULT_MIN_OCCURRENCES,
    DEFAULT_MIN_PARAMS,
    DataClumpAnalyzer,
    DataClumpResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class DataClumpTool(BaseMCPTool):
    """MCP tool for detecting data clumps."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "data_clump",
            "description": (
                "Detect parameter groups (3+) that appear together across "
                "multiple functions, indicating they should be extracted "
                "into a class or data structure."
                "\n\n"
                "Supported Languages:\n"
                "- Python: functions, methods\n"
                "- JavaScript/TypeScript: functions, methods, arrows\n"
                "- Java: methods, constructors\n"
                "- Go: functions, methods\n"
                "\n"
                "Issue Types:\n"
                "- data_clump: parameter group in 2+ functions (medium)\n"
                "\n"
                "WHEN TO USE:\n"
                "- During code review to find repeated parameter patterns\n"
                "- To identify opportunities for introducing value objects\n"
                "- To reduce function signatures and improve readability\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For parameter count analysis (use function_size)\n"
                "- For coupling analysis (use coupling_metrics)\n"
                "- For naming issues (use naming_convention)"
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
                    "min_params": {
                        "type": "integer",
                        "description": (
                            "Minimum parameters to form a clump (default: 3)"
                        ),
                    },
                    "min_occurrences": {
                        "type": "integer",
                        "description": (
                            "Minimum function occurrences (default: 2)"
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
        min_params = arguments.get("min_params", DEFAULT_MIN_PARAMS)
        min_occurrences = arguments.get("min_occurrences", DEFAULT_MIN_OCCURRENCES)

        if not file_path:
            return {
                "error": "file_path must be provided",
                "format": output_format,
            }

        analyzer = DataClumpAnalyzer(
            min_params=int(min_params),
            min_occurrences=int(min_occurrences),
        )
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: DataClumpResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "functions_analyzed": result.functions_analyzed,
            "issue_count": result.total_issues,
            "high_severity_count": result.high_severity_count,
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: DataClumpResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Data Clump Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Functions analyzed: {result.functions_analyzed}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} clump(s):")
            for i in result.issues:
                params_str = ", ".join(i.params)
                lines.append(
                    f"  L{i.line}: [{i.issue_type}] [{i.severity}] "
                    f"({i.occurrences}x)"
                )
                lines.append(f"    Params: {params_str}")
                lines.append(f"    Locations: {'; '.join(i.locations)}")
        else:
            lines.append("No data clumps found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "functions_analyzed": result.functions_analyzed,
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
