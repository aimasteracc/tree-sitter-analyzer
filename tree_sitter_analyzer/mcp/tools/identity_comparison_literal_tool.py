"""Identity Comparison with Literals Tool — MCP Tool.

Detects `is`/`is not` used with non-singleton literals.
Python 3.8+ SyntaxWarning, 3.12+ DeprecationWarning, future SyntaxError.
"""
from __future__ import annotations

from typing import Any

from ...analysis.identity_comparison_literal import (
    IdentityComparisonLiteralAnalyzer,
    IdentityComparisonLiteralResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class IdentityComparisonLiteralTool(BaseMCPTool):
    """MCP tool for detecting identity comparisons with literals."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "identity_comparison_literal",
            "description": (
                "Detect identity comparisons (`is`/`is not`) with non-singleton "
                "literals (e.g., `x is 5`, `y is not \"hello\"`)."
                "\n\n"
                "Python 3.8+ emits SyntaxWarning. Python 3.12+ emits "
                "DeprecationWarning. Future versions will raise SyntaxError."
                "\n\n"
                "Supported Languages:\n"
                "- Python only\n"
                "\n"
                "Issue Types:\n"
                "- is_literal: `x is 5` (use `x == 5`)\n"
                "- is_not_literal: `x is not \"hello\"` (use `x != \"hello\"`)\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find forward-compatibility issues in Python code\n"
                "- To catch incorrect identity vs value comparisons\n"
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

        analyzer = IdentityComparisonLiteralAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: IdentityComparisonLiteralResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_identity_comparisons": result.total_identity_comparisons,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: IdentityComparisonLiteralResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Identity Comparison with Literals Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total identity comparisons: {result.total_identity_comparisons}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} issue(s):")
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: [{issue.severity}] "
                    f"{issue.issue_type} — {issue.context}"
                )
        else:
            lines.append("No identity comparison issues found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
