"""Nested Class Tool — MCP Tool.

Detects classes defined inside other classes, which is often a
design smell suggesting missing composition or module-level classes.
"""
from __future__ import annotations

from typing import Any

from ...analysis.nested_class import (
    NestedClassAnalyzer,
    NestedClassResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class NestedClassTool(BaseMCPTool):
    """MCP tool for detecting nested class definitions."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "nested_class",
            "description": (
                "Detect classes defined inside other classes."
                "\n\n"
                "Finds inner/nested class definitions that often "
                "indicate design smells. While sometimes intentional "
                "(builders, helpers), frequent nesting suggests "
                "composition or module-level classes would be better."
                "\n\n"
                "Supported Languages:\n"
                "- Python: class inside class\n"
                "- Java: inner classes\n"
                "- C#: nested classes\n"
                "- C++: nested classes/structs\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find design smells in class hierarchies\n"
                "- To identify classes that should be composed instead\n"
                "- As an architectural quality check\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For god class detection (use god_class)\n"
                "- for lazy class detection (use lazy_class)"
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

        analyzer = NestedClassAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: NestedClassResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_issues": result.total_issues,
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: NestedClassResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Nested Class Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append("")

        if result.issues:
            lines.append(
                f"Found {len(result.issues)} nested class(es):"
            )
            for i in result.issues:
                lines.append(
                    f"  L{i.line_number}: {i.inner_class} inside "
                    f"{i.outer_class} (depth={i.nesting_depth}, "
                    f"{i.severity})"
                )
        else:
            lines.append("No nested classes found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_issues": result.total_issues,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")

        return True
