"""Variable Shadowing Tool — MCP Tool.

Analyzes code for variable shadowing issues. Detects inner-scope
variables that shadow outer-scope variables of the same name.
"""
from __future__ import annotations

from typing import Any

from ...analysis.variable_shadowing import (
    ShadowResult,
    VariableShadowingAnalyzer,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class VariableShadowingTool(BaseMCPTool):
    """MCP tool for analyzing variable shadowing."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "variable_shadowing",
            "description": (
                "Analyze code for variable shadowing issues. "
                "\n\n"
                "Detects inner-scope variables that shadow outer-scope "
                "variables of the same name. Variable shadowing is a "
                "common source of silent bugs in Python, JS/TS, Java, Go."
                "\n\n"
                "Supported Languages:\n"
                "- Python: functions, lambdas, comprehensions, for loops\n"
                "- JavaScript/TypeScript: functions, arrow functions, blocks, loops\n"
                "- Java: methods, lambdas, classes, catch, loops\n"
                "- Go: functions, if/for blocks, func literals\n"
                "\n"
                "Issue Types:\n"
                "- param_shadows_outer: parameter shadows outer variable (medium)\n"
                "- local_shadows_param: local variable shadows parameter (medium)\n"
                "- local_shadows_outer: inner variable shadows outer variable (low)\n"
                "- comprehension_shadows: comprehension var shadows outer (high)\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find silent bugs from variable name reuse\n"
                "- To catch comprehension variables hiding outer names\n"
                "- To detect parameter names conflicting with outer scope\n"
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

        analyzer = VariableShadowingAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: ShadowResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_scopes": result.total_scopes,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: ShadowResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Variable Shadowing Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total scopes: {result.total_scopes}")
        lines.append("")

        if result.issues:
            lines.append(
                f"Found {len(result.issues)} shadowing issue(s):"
            )
            for i in result.issues:
                lines.append(
                    f"  L{i.line_number}: [{i.issue_type}] "
                    f"[{i.severity}] '{i.variable_name}' "
                    f"({i.outer_scope} -> {i.inner_scope})"
                )
        else:
            lines.append("No variable shadowing issues found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_scopes": result.total_scopes,
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
