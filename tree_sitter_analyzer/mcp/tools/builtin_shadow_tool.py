"""Builtin Shadow Tool — MCP Tool.

Detects variable, function, class, and parameter names that shadow
Python builtins (list, dict, set, id, type, input, etc.).
"""
from __future__ import annotations

from typing import Any

from ...analysis.builtin_shadow import (
    BuiltinShadowAnalyzer,
    BuiltinShadowResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class BuiltinShadowTool(BaseMCPTool):
    """MCP tool for detecting builtin shadowing."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "builtin_shadow",
            "description": (
                "Detect Python builtin shadowing: variable, function, class, "
                "or parameter names that override builtins like list, dict, "
                "set, id, type, input."
                "\n\n"
                "Shadowing builtins silently breaks all subsequent calls "
                "to the original builtin."
                "\n\n"
                "Supported Languages:\n"
                "- Python only\n"
                "\n"
                "Issue Types:\n"
                "- shadowed_builtin: assignment shadows builtin\n"
                "- shadowed_by_function: function def shadows builtin\n"
                "- shadowed_by_class: class def shadows builtin\n"
                "- shadowed_by_parameter: parameter shadows builtin\n"
                "- shadowed_by_import: import shadows builtin\n"
                "- shadowed_by_for_target: for-loop target shadows builtin\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find dangerous name collisions with Python builtins\n"
                "- To catch Pylint W0622 violations\n"
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

        analyzer = BuiltinShadowAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: BuiltinShadowResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_definitions": result.total_definitions,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: BuiltinShadowResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Builtin Shadow Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Definitions checked: {result.total_definitions}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} builtin shadow(s):")
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: [{issue.severity}] "
                    f"{issue.issue_type}: {issue.description}"
                )
        else:
            lines.append("No builtin shadowing found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
