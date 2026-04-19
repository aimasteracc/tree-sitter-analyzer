"""Redundant Type Cast Tool — MCP Tool.

Detects redundant type conversions where the same type constructor
wraps an expression already of that type (e.g., str(str(x))).
"""
from __future__ import annotations

from typing import Any

from ...analysis.redundant_type_cast import (
    RedundantCastResult,
    RedundantTypeCastAnalyzer,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class RedundantTypeCastTool(BaseMCPTool):
    """MCP tool for detecting redundant type casts."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "redundant_type_cast",
            "description": (
                "Detect redundant type casts: wrapping a value in the "
                "same type constructor twice (e.g., str(str(x)), int(int(x)))."
                "\n\n"
                "Redundant casts are dead code suggesting programmer "
                "confusion or leftover refactoring artifacts."
                "\n\n"
                "Supported Languages:\n"
                "- Python, JavaScript/TypeScript, Java\n"
                "\n"
                "Issue Types:\n"
                "- redundant_str: str(str(x))\n"
                "- redundant_int: int(int(x))\n"
                "- redundant_float: float(float(x))\n"
                "- redundant_list/tuple/set/bool/bytes: same pattern\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find dead code in type conversions\n"
                "- To catch copy-paste or refactoring leftovers\n"
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

        analyzer = RedundantTypeCastAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: RedundantCastResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_calls": result.total_calls,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: RedundantCastResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Redundant Type Cast Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total calls: {result.total_calls}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} redundant cast(s):")
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: [{issue.severity}] "
                    f"{issue.issue_type} — {issue.context}"
                )
        else:
            lines.append("No redundant type casts found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
