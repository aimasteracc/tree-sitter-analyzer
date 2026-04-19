"""Assignment in Conditional Tool — MCP Tool.

Detects assignments used as conditions in if/while statements.
"""
from __future__ import annotations

from typing import Any

from ...analysis.assignment_in_conditional import (
    AssignmentInConditionalAnalyzer,
    AssignmentInConditionalResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class AssignmentInConditionalTool(BaseMCPTool):
    """MCP tool for detecting assignments in conditions."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "assignment_in_conditional",
            "description": (
                "Detect assignments used as if/while conditions "
                "(likely = vs == typo)."
                "\n\n"
                "Catches `if (x = 5)` patterns that are valid syntax "
                "but almost always a typo for `if (x == 5)`."
                "\n\n"
                "Supported Languages:\n"
                "- JavaScript/TypeScript\n"
                "- Java\n"
                "- C/C++\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find = vs == typos in conditions\n"
                "- To detect accidental assignments in if/while\n"
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
            return {"error": "file_path must be provided", "format": output_format}

        analyzer = AssignmentInConditionalAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: AssignmentInConditionalResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_issues": result.total_issues,
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: AssignmentInConditionalResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Assignment in Conditional Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {result.total_issues} issue(s):")
            for i in result.issues:
                lines.append(f"  L{i.line}: {i.message}")
        else:
            lines.append("No assignments in conditions found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_issues": result.total_issues,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")
        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")
        return True
