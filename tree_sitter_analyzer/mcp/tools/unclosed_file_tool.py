"""Unclosed File Tool — MCP Tool.

Detects open() calls not wrapped in a with statement,
which can cause file handle leaks.
"""
from __future__ import annotations

from typing import Any

from ...analysis.unclosed_file import (
    UnclosedFileAnalyzer,
    UnclosedFileResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class UnclosedFileTool(BaseMCPTool):
    """MCP tool for detecting unclosed file handles."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "unclosed_file",
            "description": (
                "Detect open() calls not wrapped in a with statement."
                "\n\n"
                "Finds patterns like `f = open('file.txt')` without "
                "a corresponding `with` context manager, which can "
                "cause file handle leaks in long-running processes."
                "\n\n"
                "Supported Languages:\n"
                "- Python: open() without with\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find resource leaks in file handling code\n"
                "- To identify code that should use context managers\n"
                "- As a reliability check for file I/O operations\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For resource lifecycle analysis (use resource_lifecycle)\n"
                "- For error handling in file ops (use error_handling)"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Path to a specific file to analyze. "
                            "If provided, analyzes only this file."
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

        analyzer = UnclosedFileAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: UnclosedFileResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_hotspots": result.total_hotspots,
            "hotspots": [h.to_dict() for h in result.hotspots],
        }

    def _format_toon(self, result: UnclosedFileResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Unclosed File Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append("")

        if result.hotspots:
            lines.append(
                f"Found {len(result.hotspots)} open() without with:"
            )
            for h in result.hotspots:
                lines.append(
                    f"  L{h.line_number}: {h.variable} = open(...) "
                    f"({h.severity})"
                )
        else:
            lines.append("No unclosed file handles found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_hotspots": result.total_hotspots,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")

        return True
