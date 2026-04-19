"""Len-Comparison Anti-pattern Tool — MCP Tool.

Detects explicit len() comparisons that should use truthiness.
"""
from __future__ import annotations

from typing import Any

from ...analysis.len_comparison import LenComparisonAnalyzer
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class LenComparisonTool(BaseMCPTool):
    """MCP tool for detecting len() comparison anti-patterns."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "len_comparison",
            "description": (
                "Detect len() comparison anti-patterns where truthiness is preferred. "
                "Flags `len(x) == 0` (use `not x`), `len(x) > 0` (use `x`), etc."
                "\n\n"
                "Supported Languages:\n"
                "- Python: len(x) == 0, > 0, != 0, >= 1, < 1\n"
                "- JavaScript/TypeScript: x.length == 0, > 0, etc.\n"
                "- Go: len(x) == 0, > 0, etc.\n"
                "\n"
                "Issue Types:\n"
                "- len_eq_zero: len(x) == 0 → use `not x`\n"
                "- len_ne_zero: len(x) != 0 → use `x`\n"
                "- len_gt_zero: len(x) > 0 → use `x`\n"
                "- len_ge_one: len(x) >= 1 → use `x`\n"
                "- len_lt_one: len(x) < 1 → use `not x`\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find unidiomatic empty/collection checks\n"
                "- To enforce PEP 8 style (Pylint C1801)\n"
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

        analyzer = LenComparisonAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: Any) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_comparisons": result.total_comparisons,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: Any) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Len-Comparison Anti-pattern Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total len comparisons: {result.total_comparisons}")
        lines.append("")

        if result.issues:
            lines.append(
                f"Found {len(result.issues)} len-comparison anti-pattern(s):"
            )
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: [{issue.severity}] "
                    f"{issue.issue_type} — {issue.suggestion}"
                )
        else:
            lines.append("No len-comparison anti-patterns found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
