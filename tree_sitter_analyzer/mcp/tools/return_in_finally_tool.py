"""Return in Finally Tool — MCP Tool.

Detects return/raise statements inside finally blocks that silently
swallow exceptions.
"""
from __future__ import annotations

from typing import Any

from ...analysis.return_in_finally import ReturnInFinallyAnalyzer
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class ReturnInFinallyTool(BaseMCPTool):
    """MCP tool for detecting return/raise in finally blocks."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "return_in_finally",
            "description": (
                "Detect return/raise in finally blocks. These silently "
                "swallow exceptions from the try block."
                "\n\n"
                "Supported Languages:\n"
                "- Python, JavaScript, TypeScript, Java\n"
                "\n"
                "Issue Types:\n"
                "- return_in_finally: return inside finally\n"
                "- raise_in_finally: raise/throw inside finally\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find silent exception swallowing\n"
                "- To catch bugs where errors disappear without trace\n"
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

        analyzer = ReturnInFinallyAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: Any) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_finally_blocks": result.total_finally_blocks,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: Any) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Return-in-Finally Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total finally blocks: {result.total_finally_blocks}")
        lines.append("")

        if result.issues:
            lines.append(
                f"Found {len(result.issues)} return/raise in finally:"
            )
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: [{issue.severity}] "
                    f"{issue.issue_type} — {issue.context}"
                )
        else:
            lines.append("No return/raise in finally blocks found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
