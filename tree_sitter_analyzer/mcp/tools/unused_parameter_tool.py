"""Unused Parameter Tool — MCP Tool.

Analyzes code for unused function parameters. Detects parameters
that are declared but never referenced in the function body.
"""
from __future__ import annotations

from typing import Any

from ...analysis.unused_parameter import (
    UnusedParameterAnalyzer,
    UnusedParameterResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class UnusedParameterTool(BaseMCPTool):
    """MCP tool for analyzing unused parameters."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "unused_parameter",
            "description": (
                "Analyze code for unused function parameters. "
                "\n\n"
                "Detects parameters that are declared but never "
                "referenced in the function body, indicating dead code, "
                "incomplete refactoring, or misleading APIs."
                "\n\n"
                "Supported Languages:\n"
                "- Python: functions\n"
                "- JavaScript/TypeScript: functions, arrow functions, methods\n"
                "- Java: methods, constructors, lambdas\n"
                "- Go: functions, methods, func literals\n"
                "\n"
                "Issue Types:\n"
                "- unused_parameter: param declared but never used (medium)\n"
                "- unused_callback_param: _ prefix param unused (low)\n"
                "- unused_self_param: self/cls/this never used (low)\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find dead parameters from incomplete refactoring\n"
                "- To detect misleading function signatures\n"
                "- To find candidates for static methods\n"
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

        analyzer = UnusedParameterAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: UnusedParameterResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_functions": result.total_functions,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: UnusedParameterResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Unused Parameter Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total functions: {result.total_functions}")
        lines.append("")

        if result.issues:
            lines.append(
                f"Found {len(result.issues)} unused parameter issue(s):"
            )
            for i in result.issues:
                lines.append(
                    f"  L{i.line_number}: [{i.issue_type}] "
                    f"[{i.severity}] '{i.parameter_name}'"
                )
        else:
            lines.append("No unused parameter issues found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_functions": result.total_functions,
            "issue_count": len(result.issues),
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")

        return True
