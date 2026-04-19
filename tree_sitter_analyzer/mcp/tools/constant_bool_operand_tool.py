"""Constant Boolean Operand Tool — MCP Tool.

Analyzes code for non-boolean constant operands in boolean expressions.
"""
from __future__ import annotations

from typing import Any

from ...analysis.constant_bool_operand import (
    ConstantBoolOperandAnalyzer,
    ConstantBoolOperandResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class ConstantBoolOperandTool(BaseMCPTool):
    """MCP tool for detecting constant boolean operands."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "constant_bool_operand",
            "description": (
                "Analyze code for non-boolean constant operands in boolean expressions. "
                "\n\n"
                "Detects strings, numbers, lists, dicts used as operands in "
                "and/or expressions. Classic Python pitfall: `if x == 'a' or 'b':` "
                "is always True because 'b' is truthy."
                "\n\n"
                "Supported Languages:\n"
                "- Python: and/or expressions\n"
                "\n"
                "Issue Types:\n"
                "- constant_bool_operand: non-boolean constant in boolean expression (medium)\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find misleading boolean conditions\n"
                "- To catch the `x == a or b` anti-pattern\n"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to a specific file to analyze.",
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

        analyzer = ConstantBoolOperandAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: ConstantBoolOperandResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_boolean_expressions": result.total_boolean_expressions,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: ConstantBoolOperandResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Constant Boolean Operand Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Boolean expressions: {result.total_boolean_expressions}")
        lines.append("")

        if result.issues:
            lines.append(
                f"Found {len(result.issues)} constant operand issue(s):"
            )
            for i in result.issues:
                lines.append(
                    f"  L{i.line_number}: [{i.issue_type}] "
                    f"[{i.severity}] {i.operand_snippet}"
                )
        else:
            lines.append("No constant boolean operand issues found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_boolean_expressions": result.total_boolean_expressions,
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
