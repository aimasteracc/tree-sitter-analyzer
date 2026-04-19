"""Range-Len Anti-pattern Tool — MCP Tool.

Detects `for i in range(len(x))` patterns that should use enumerate or direct iteration.
"""
from __future__ import annotations

from typing import Any

from ...analysis.range_len import RangeLenAnalyzer
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class RangeLenTool(BaseMCPTool):
    """MCP tool for detecting range(len(x)) anti-pattern."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "range_len",
            "description": (
                "Detect range(len(x)) anti-pattern in for loops. "
                "Suggests using direct iteration `for item in x` "
                "or `for i, item in enumerate(x)`."
                "\n\n"
                "Supported Languages:\n"
                "- Python only (range/len are Python builtins)\n"
                "\n"
                "Issue Types:\n"
                "- range_len_for: for i in range(len(x)) → use enumerate or direct iteration\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find unidiomatic indexed iteration patterns\n"
                "- To enforce PEP 8 style (Pylint C0200)\n"
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

        analyzer = RangeLenAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: Any) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_for_loops": result.total_for_loops,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: Any) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Range-Len Anti-pattern Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total for loops: {result.total_for_loops}")
        lines.append("")

        if result.issues:
            lines.append(
                f"Found {len(result.issues)} range(len(x)) anti-pattern(s):"
            )
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: [{issue.severity}] "
                    f"{issue.suggestion}"
                )
        else:
            lines.append("No range(len(x)) anti-patterns found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
