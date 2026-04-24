"""Silent Error Suppression Tool — MCP Tool.

Detects catch/except blocks that silently suppress errors without
meaningful recovery, re-raise, or state cleanup.
"""
from __future__ import annotations

from typing import Any

from ...analysis.silent_suppression import (
    SilentSuppressionAnalyzer,
    SilentSuppressionResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class SilentSuppressionTool(BaseMCPTool):
    """MCP tool for detecting silent error suppression in catch/except blocks."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "silent_suppression",
            "description": (
                "Detect catch/except blocks that silently suppress errors "
                "(pass, continue, logging-only, return None)."
                "\n\n"
                "Finds error handlers that swallow exceptions without "
                "meaningful recovery, re-raise, or state cleanup."
                "\n\n"
                "Supported Languages:\n"
                "- Python, JavaScript/TypeScript, Java, Go\n"
                "\n"
                "Issue Types:\n"
                "- silent_suppression: handler body is empty/pass/continue/return None\n"
                "- logging_only_suppression: handler only logs without recovery\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find hidden bugs from silently swallowed exceptions\n"
                "- To audit error handling quality across the codebase\n"
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

        analyzer = SilentSuppressionAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: SilentSuppressionResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_issues": result.total_issues,
            "issue_count": len(result.issues),
            "issues": [
                {
                    "line": i.line,
                    "issue_type": i.issue_type,
                    "severity": i.severity,
                    "handler_type": i.handler_type,
                    "description": i.description,
                    "suggestion": i.suggestion,
                }
                for i in result.issues
            ],
        }

    def _format_toon(self, result: SilentSuppressionResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Silent Error Suppression Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} silent suppression(s):")
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: [{issue.severity}] "
                    f"{issue.handler_type} — {issue.description}"
                )
        else:
            lines.append("No silent error suppressions found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
