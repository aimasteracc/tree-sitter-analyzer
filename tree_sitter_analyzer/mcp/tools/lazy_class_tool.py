"""Lazy Class Tool — MCP Tool.

Analyzes classes for insufficient complexity. Detects classes with
too few methods that may not justify their existence.
"""
from __future__ import annotations

from typing import Any

from ...analysis.lazy_class import (
    LazyClassAnalyzer,
    LazyClassResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class LazyClassTool(BaseMCPTool):
    """MCP tool for analyzing lazy classes."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "lazy_class",
            "description": (
                "Analyze classes for insufficient complexity (lazy classes). "
                "\n\n"
                "Detects classes with 0-1 methods and 0-2 fields that may "
                "not justify their existence. These are candidates for "
                "simplification into plain functions or data structures."
                "\n\n"
                "Supported Languages:\n"
                "- Python: class definitions\n"
                "- JavaScript/TypeScript: class declarations\n"
                "- Java: class declarations\n"
                "- Go: struct type declarations\n"
                "\n"
                "Severity Levels:\n"
                "- lazy: 1 method, few fields\n"
                "- removal_candidate: 0 methods\n"
                "\n"
                "WHEN TO USE:\n"
                "- During code review to spot unnecessary classes\n"
                "- To identify over-engineered abstractions\n"
                "- As a simplicity-focused complement to design_patterns\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For design pattern detection (use design_patterns)\n"
                "- for SOLID violations (use solid_principles)\n"
                "- For dead code (use dead_code)"
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

        analyzer = LazyClassAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: LazyClassResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_classes": result.total_classes,
            "lazy_count": len(result.lazy_classes),
            "lazy_classes": [c.to_dict() for c in result.lazy_classes],
        }

    def _format_toon(self, result: LazyClassResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Lazy Class Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total classes: {result.total_classes}")
        lines.append("")

        if result.lazy_classes:
            lines.append(
                f"Found {len(result.lazy_classes)} lazy class(es):"
            )
            for c in result.lazy_classes:
                lines.append(
                    f"  L{c.line_number}: {c.class_name} "
                    f"({c.method_count} methods, {c.field_count} fields) "
                    f"[{c.severity}]"
                )
        else:
            lines.append("No lazy classes found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_classes": result.total_classes,
            "lazy_count": len(result.lazy_classes),
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")

        return True
