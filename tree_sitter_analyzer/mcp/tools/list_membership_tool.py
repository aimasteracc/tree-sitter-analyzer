"""List-in-Membership Performance Tool — MCP Tool.

Detects membership tests using list literals where set literals
would provide O(1) lookup instead of O(n).
"""
from __future__ import annotations

from typing import Any

from ...analysis.list_membership import (
    ListMembershipAnalyzer,
    ListMembershipResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class ListMembershipTool(BaseMCPTool):
    """MCP tool for detecting list-in-membership performance issues."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "list_membership",
            "description": (
                "Detect membership tests using list literals where set "
                "literals would provide O(1) lookup "
                "(e.g., `x in [1, 2, 3]` → `x in {1, 2, 3}`)."
                "\n\n"
                "List membership is O(n); set membership is O(1)."
                "\n\n"
                "Supported Languages:\n"
                "- Python, JavaScript/TypeScript\n"
                "\n"
                "Issue Types:\n"
                "- list_in_membership: `x in [...]` (use `{...}`)\n"
                "- list_not_in_membership: `x not in [...]` (use `{...}`)\n"
                "- array_includes_literal: `[...].includes(x)` (use Set)\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find O(n) membership tests that should be O(1)\n"
                "- To optimize performance of frequent lookups\n"
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

        analyzer = ListMembershipAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: ListMembershipResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_membership_tests": result.total_membership_tests,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: ListMembershipResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("List-in-Membership Performance Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total membership tests: {result.total_membership_tests}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} issue(s):")
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: [{issue.severity}] "
                    f"{issue.issue_type} — {issue.context}"
                )
        else:
            lines.append("No list-in-membership issues found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
