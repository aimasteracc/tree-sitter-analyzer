"""Production Assert Tool — MCP Tool.

Detects assert statements in non-test code that are stripped by python -O.
"""
from __future__ import annotations

from typing import Any

from ...analysis.production_assert import ProductionAssertAnalyzer
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class ProductionAssertTool(BaseMCPTool):
    """MCP tool for detecting asserts in non-test code."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "production_assert",
            "description": (
                "Detect assert statements in non-test code. "
                "Asserts are stripped by python -O, making them "
                "unreliable for production validation."
                "\n\n"
                "Supported Languages:\n"
                "- Python only\n"
                "\n"
                "Issue Types:\n"
                "- production_assert: assert in non-test code\n"
                "- assert_with_message: assert with side-effect message\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find asserts that disappear with -O flag\n"
                "- To catch data validation using assert instead of raise\n"
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

        analyzer = ProductionAssertAnalyzer()
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
        lines.append("Production Assert Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total assert statements: {result.total_asserts}")
        lines.append("")

        if result.issues:
            lines.append(
                f"Found {len(result.issues)} production assert(s):"
            )
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: [{issue.severity}] "
                    f"{issue.issue_type} — {issue.context}"
                )
        else:
            lines.append("No production asserts found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
