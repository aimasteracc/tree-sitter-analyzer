"""Simplified Conditional Expression Tool — MCP Tool.

Detects ternary/conditional expressions that can be simplified
for better readability.
"""
from __future__ import annotations

from typing import Any

from ...analysis.simplified_conditional import (
    SimplifiedConditionalAnalyzer,
    SimplifiedConditionalResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class SimplifiedConditionalTool(BaseMCPTool):
    """MCP tool for detecting simplifiable conditional expressions."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "simplified_conditional",
            "description": (
                "Detect ternary/conditional expressions that can be simplified. "
                "\n\n"
                "Finds patterns like `cond ? true : false` (use `cond`), "
                "`cond ? false : true` (use `!cond`), "
                "and `cond ? x : x` (identical branches)."
                "\n\n"
                "Supported Languages:\n"
                "- Python, JavaScript/TypeScript, Java\n"
                "\n"
                "Issue Types:\n"
                "- redundant_true_branch: cond ? true : false\n"
                "- redundant_false_branch: cond ? false : true\n"
                "- identical_branches: cond ? x : x\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find unnecessary ternary complexity\n"
                "- To simplify code for readability\n"
                "- To catch identical branch bugs\n"
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

        analyzer = SimplifiedConditionalAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: SimplifiedConditionalResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_ternaries": result.total_ternaries,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: SimplifiedConditionalResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Simplified Conditional Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total ternary expressions: {result.total_ternaries}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} simplifiable expression(s):")
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: [{issue.severity}] "
                    f"{issue.issue_type} — {issue.context}"
                )
        else:
            lines.append("No simplifiable conditional expressions found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
