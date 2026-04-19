"""Duplicate Dict Key Tool — MCP Tool.

Detects duplicate keys in dictionary/object literals.
"""
from __future__ import annotations

from typing import Any

from ...analysis.duplicate_dict_key import DuplicateDictKeyAnalyzer
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class DuplicateDictKeyTool(BaseMCPTool):
    """MCP tool for detecting duplicate dictionary keys."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "duplicate_dict_key",
            "description": (
                "Detect duplicate keys in dictionary/object literals. "
                "The last value silently overwrites earlier ones."
                "\n\n"
                "Supported Languages:\n"
                "- Python, JavaScript, TypeScript\n"
                "\n"
                "Issue Types:\n"
                "- duplicate_dict_key: repeated key in dict literal\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find silent value overwrites in dicts\n"
                "- To catch config/data errors from duplicate keys\n"
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

        analyzer = DuplicateDictKeyAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: Any) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_dicts": result.total_dicts,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: Any) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Duplicate Dict Key Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total dicts/objects: {result.total_dicts}")
        lines.append("")

        if result.issues:
            lines.append(
                f"Found {len(result.issues)} duplicate key(s):"
            )
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: [{issue.severity}] "
                    f"{issue.issue_type} key={issue.key}"
                )
        else:
            lines.append("No duplicate keys found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
