"""Empty Block Tool — MCP Tool.

Analyzes code for empty blocks that may hide bugs. Detects
empty function bodies, empty catch/except blocks, empty loops.
"""
from __future__ import annotations

from typing import Any

from ...analysis.empty_block import (
    EmptyBlockAnalyzer,
    EmptyBlockResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class EmptyBlockTool(BaseMCPTool):
    """MCP tool for analyzing empty blocks."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "empty_block",
            "description": (
                "Analyze code for empty blocks that may hide bugs. "
                "\n\n"
                "Detects empty function bodies, empty catch/except blocks, "
                "empty loops, and other empty blocks. Empty catch blocks "
                "silently swallow errors, which is a common bug source."
                "\n\n"
                "Supported Languages:\n"
                "- Python: function definitions, except clauses, loops\n"
                "- JavaScript/TypeScript: functions, catch clauses, loops\n"
                "- Java: methods, catch clauses, loops\n"
                "- Go: functions, loops\n"
                "\n"
                "Issue Types:\n"
                "- empty_catch: empty except/catch block (high severity)\n"
                "- empty_function: empty function/method body (medium)\n"
                "- empty_loop: empty for/while body (low)\n"
                "- empty_block: other empty blocks (low)\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find empty catch blocks hiding bugs\n"
                "- To detect stub functions that need implementation\n"
                "- To find dead loops or no-op code blocks\n"
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

        analyzer = EmptyBlockAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: EmptyBlockResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_blocks": result.total_blocks,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: EmptyBlockResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Empty Block Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total blocks: {result.total_blocks}")
        lines.append("")

        if result.issues:
            lines.append(
                f"Found {len(result.issues)} issue(s):"
            )
            for i in result.issues:
                lines.append(
                    f"  L{i.line_number}: [{i.issue_type}] [{i.severity}] "
                    f"{i.description}"
                )
        else:
            lines.append("No empty block issues found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_blocks": result.total_blocks,
            "issue_count": len(result.issues),
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")

        return True
