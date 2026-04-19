"""Assert-on-Tuple Tool — MCP Tool.

Detects `assert (condition, message)` patterns where the assertion always passes.
"""
from __future__ import annotations

from typing import Any

from ...analysis.assert_on_tuple import AssertOnTupleAnalyzer
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class AssertOnTupleTool(BaseMCPTool):
    """MCP tool for detecting assert-on-tuple patterns."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "assert_on_tuple",
            "description": (
                "Detect assert-on-tuple patterns where assert always passes. "
                "`assert (cond, msg)` evaluates the tuple (always truthy), "
                "not the condition."
                "\n\n"
                "Supported Languages:\n"
                "- Python only\n"
                "\n"
                "Issue Types:\n"
                "- assert_on_tuple: assert with tuple literal as condition\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find asserts that never actually check anything\n"
                "- To catch the classic `(cond, msg)` vs `cond, msg` mistake\n"
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

        analyzer = AssertOnTupleAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: Any) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_asserts": result.total_asserts,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: Any) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Assert-on-Tuple Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total assert statements: {result.total_asserts}")
        lines.append("")

        if result.issues:
            lines.append(
                f"Found {len(result.issues)} assert-on-tuple pattern(s):"
            )
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: [{issue.severity}] "
                    f"{issue.issue_type} — {issue.context}"
                )
        else:
            lines.append("No assert-on-tuple patterns found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
