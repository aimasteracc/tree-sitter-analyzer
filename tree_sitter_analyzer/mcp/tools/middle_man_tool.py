"""Middle Man Tool — MCP Tool.

Analyzes code for middle man classes that primarily delegate to another
object without adding value.
"""
from __future__ import annotations

from typing import Any

from ...analysis.middle_man import (
    DEFAULT_DELEGATION_THRESHOLD,
    MiddleManAnalyzer,
    MiddleManResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class MiddleManTool(BaseMCPTool):
    """MCP tool for detecting middle man classes."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "middle_man",
            "description": (
                "Detect classes that primarily delegate to another "
                "class without adding value (Middle Man smell)."
                "\n\n"
                "Supported Languages:\n"
                "- Python: classes with self.X.method() delegation\n"
                "- JavaScript/TypeScript: classes with this.X.method()\n"
                "- Java: classes with this.X.method()\n"
                "- Go: structs with receiver delegation\n"
                "\n"
                "Issue Types:\n"
                "- middle_man_class: class with ≥70% delegation (medium)\n"
                "\n"
                "WHEN TO USE:\n"
                "- During code review to find unnecessary delegation layers\n"
                "- To simplify overly indirect codebases\n"
                "- To identify classes that should be removed or merged\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For lazy class detection (use lazy_class)\n"
                "- for god class detection (use god_class)\n"
                "- For coupling analysis (use coupling_metrics)"
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
                    "delegation_threshold": {
                        "type": "number",
                        "description": (
                            "Min delegation ratio to flag (default: 0.7)"
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
        threshold = arguments.get(
            "delegation_threshold", DEFAULT_DELEGATION_THRESHOLD
        )

        if not file_path:
            return {
                "error": "file_path must be provided",
                "format": output_format,
            }

        analyzer = MiddleManAnalyzer(
            delegation_threshold=float(threshold)
        )
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: MiddleManResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "classes_analyzed": result.classes_analyzed,
            "issue_count": result.total_issues,
            "high_severity_count": result.high_severity_count,
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: MiddleManResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Middle Man Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Classes analyzed: {result.classes_analyzed}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} middle man class(es):")
            for i in result.issues:
                lines.append(
                    f"  L{i.line}: {i.class_name} "
                    f"[{i.issue_type}] [{i.severity}]"
                )
                lines.append(f"    {i.message}")
        else:
            lines.append("No middle man classes found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "classes_analyzed": result.classes_analyzed,
            "issue_count": result.total_issues,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")

        return True
