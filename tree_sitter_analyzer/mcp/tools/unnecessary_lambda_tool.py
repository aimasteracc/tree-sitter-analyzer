"""Unnecessary Lambda Tool — MCP Tool.

Detects lambda expressions that can be simplified: trivial wrappers
(lambda x: f(x)) and identity functions (lambda x: x).
"""
from __future__ import annotations

from typing import Any

from ...analysis.unnecessary_lambda import (
    UnnecessaryLambdaAnalyzer,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class UnnecessaryLambdaTool(BaseMCPTool):
    """MCP tool for detecting unnecessary lambdas."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "unnecessary_lambda",
            "description": (
                "Detect unnecessary lambda expressions in Python: "
                "trivial wrappers and identity functions."
                "\n\n"
                "Replaces lambda x: f(x) with f, and lambda x: x "
                "with direct value usage."
                "\n\n"
                "Supported Languages:\n"
                "- Python only\n"
                "\n"
                "Issue Types:\n"
                "- trivial_lambda: lambda x: f(x) → use f\n"
                "- identity_lambda: lambda x: x → remove\n"
                "\n"
                "WHEN TO USE:\n"
                "- To simplify lambda-heavy code\n"
                "- To find overly verbose function references\n"
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

        analyzer = UnnecessaryLambdaAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: Any) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_lambdas": result.total_lambdas,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: Any) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Unnecessary Lambda Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total lambdas: {result.total_lambdas}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} unnecessary lambda(s):")
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: [{issue.severity}] "
                    f"{issue.issue_type} — {issue.context}"
                )
        else:
            lines.append("No unnecessary lambdas found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
