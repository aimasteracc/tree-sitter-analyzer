"""Missing Break Tool — MCP Tool.

Analyzes code for missing break/return/throw statements in switch/case,
causing unintentional fall-through.
"""
from __future__ import annotations

from typing import Any

from ...analysis.missing_break import (
    MissingBreakAnalyzer,
    MissingBreakResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class MissingBreakTool(BaseMCPTool):
    """MCP tool for detecting missing break statements in switch/case."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "missing_break",
            "description": (
                "Analyze code for missing break statements in switch/case. "
                "\n\n"
                "Detects unintentional fall-through where a case statement "
                "does not end with break, return, throw, or continue."
                "\n\n"
                "Supported Languages:\n"
                "- JavaScript/TypeScript: switch statements\n"
                "- Java: switch statements\n"
                "\n"
                "Note: Python (match) and Go (switch) do not have fall-through by default.\n"
                "\n"
                "Issue Types:\n"
                "- missing_break: case without terminating statement (medium)\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find unintentional fall-through bugs\n"
                "- To audit switch statements for completeness\n"
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

        analyzer = MissingBreakAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: MissingBreakResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_switches": result.total_switches,
            "total_cases": result.total_cases,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: MissingBreakResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Missing Break Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Switch statements: {result.total_switches}")
        lines.append(f"Total cases: {result.total_cases}")
        lines.append("")

        if result.issues:
            lines.append(
                f"Found {len(result.issues)} missing break issue(s):"
            )
            for i in result.issues:
                lines.append(
                    f"  L{i.line_number}: [{i.issue_type}] "
                    f"[{i.severity}]"
                )
        else:
            lines.append("No missing break issues found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_switches": result.total_switches,
            "total_cases": result.total_cases,
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
