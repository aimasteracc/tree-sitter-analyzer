"""
Side Effect Tool — MCP Tool.

Detects functions with side effects: global state mutation and parameter mutation.
"""
from __future__ import annotations

from typing import Any

from ...analysis.side_effects import (
    SideEffectAnalyzer,
    SideEffectResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class SideEffectTool(BaseMCPTool):
    """MCP tool for analyzing side effects in functions."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "side_effects",
            "description": (
                "Analyze functions for side effects in source code. "
                "\n\n"
                "Detects functions that modify external state instead of "
                "returning new values, making code harder to test and reason about."
                "\n\n"
                "Supported Languages:\n"
                "- Python: global/nonlocal, parameter mutation\n"
                "- JavaScript/TypeScript: module var mutation, parameter mutation\n"
                "- Java: static field mutation, parameter setter calls\n"
                "- Go: package var mutation, append on parameter\n"
                "\n"
                "Detection Patterns:\n"
                "- global_state_mutation: function modifies global/module state (HIGH)\n"
                "- parameter_mutation: function mutates passed-in parameter (MEDIUM)\n"
                "\n"
                "WHEN TO USE:\n"
                "- During code review to identify impure functions\n"
                "- When improving testability of a codebase\n"
                "- Before refactoring to functional patterns\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For variable mutability analysis (use variable_mutability)\n"
                "- For coupling metrics (use coupling_metrics)\n"
                "- For design pattern detection (use design_patterns)"
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

        analyzer = SideEffectAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: SideEffectResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "language": result.language,
            "total_issues": result.total_issues,
            "high_severity": result.high_severity,
            "medium_severity": result.medium_severity,
            "issues": [
                {
                    "type": i.issue_type,
                    "line": i.line,
                    "severity": i.severity,
                    "function_name": i.function_name,
                    "variable": i.variable,
                    "description": i.description,
                    "suggestion": i.suggestion,
                }
                for i in result.issues
            ],
        }

    def _format_toon(self, result: SideEffectResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Side Effect Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Language: {result.language}")
        lines.append(f"Issues: {result.total_issues}")
        if result.high_severity > 0:
            lines.append(f"  HIGH: {result.high_severity}")
        if result.medium_severity > 0:
            lines.append(f"  MEDIUM: {result.medium_severity}")
        lines.append("")

        if result.issues:
            for i in result.issues:
                lines.append(
                    f"  [{i.severity.upper()}] {i.issue_type}: "
                    f"L{i.line} in {i.function_name}() - {i.description}"
                )
                lines.append(f"    Suggestion: {i.suggestion}")
        else:
            lines.append("No side effect issues detected.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_issues": result.total_issues,
            "high_severity": result.high_severity,
            "medium_severity": result.medium_severity,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")

        return True
