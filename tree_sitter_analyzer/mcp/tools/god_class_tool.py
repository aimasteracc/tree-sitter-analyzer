"""God Class Tool — MCP Tool.

Analyzes classes for excessive size and responsibility. Detects
classes with too many methods and fields (god classes).
"""
from __future__ import annotations

from typing import Any

from ...analysis.god_class import (
    GodClassAnalyzer,
    GodClassResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class GodClassTool(BaseMCPTool):
    """MCP tool for analyzing god classes."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "god_class",
            "description": (
                "Analyze classes for excessive size and responsibility (god classes). "
                "\n\n"
                "Detects classes with too many methods and fields, indicating "
                "too many responsibilities. The opposite of lazy_class."
                "\n\n"
                "Supported Languages:\n"
                "- Python: class definitions\n"
                "- JavaScript/TypeScript: class declarations\n"
                "- Java: class declarations\n"
                "- Go: struct type declarations\n"
                "\n"
                "Issue Types:\n"
                "- god_class: 10+ methods AND 8+ fields (high severity)\n"
                "- large_class: 7-9 methods AND 5+ fields (medium severity)\n"
                "- low_cohesion: many methods but few shared fields (low severity)\n"
                "\n"
                "WHEN TO USE:\n"
                "- During code review to spot overgrown classes\n"
                "- To identify candidates for the Single Responsibility Principle\n"
                "- As a complement to lazy_class and coupling_metrics\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For lazy class detection (use lazy_class)\n"
                "- For SOLID violations (use solid_principles)\n"
                "- For coupling between classes (use coupling_metrics)"
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

        analyzer = GodClassAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: GodClassResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_classes": result.total_classes,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
            "class_stats": [s.to_dict() for s in result.class_stats],
        }

    def _format_toon(self, result: GodClassResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("God Class Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total classes: {result.total_classes}")
        lines.append("")

        if result.issues:
            lines.append(
                f"Found {len(result.issues)} issue(s):"
            )
            for i in result.issues:
                lines.append(
                    f"  L{i.line_number}: {i.class_name} "
                    f"({i.method_count} methods, {i.field_count} fields) "
                    f"[{i.issue_type}] [{i.severity}]"
                )
        else:
            lines.append("No god class issues found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_classes": result.total_classes,
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
