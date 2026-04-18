"""
Inheritance Quality Tool — MCP Tool.

Detects inheritance anti-patterns: deep hierarchies, missing super() calls,
diamond inheritance, and empty overrides.
"""
from __future__ import annotations

from typing import Any

from ...analysis.inheritance_quality import (
    InheritanceQualityAnalyzer,
    InheritanceQualityResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class InheritanceQualityTool(BaseMCPTool):
    """MCP tool for analyzing inheritance quality patterns."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "inheritance_quality",
            "description": (
                "Analyze inheritance quality patterns in source code. "
                "\n\n"
                "Detects inheritance anti-patterns that make code hard to "
                "understand and maintain: deep hierarchies, missing super() "
                "calls, diamond inheritance, and empty overrides."
                "\n\n"
                "Supported Languages:\n"
                "- Python: class inheritance, __init__, super()\n"
                "- JavaScript/TypeScript: extends, constructor, super()\n"
                "- Java: extends/implements, constructor, super()\n"
                "- Go: struct embedding (limited support)\n"
                "\n"
                "Detection Patterns:\n"
                "- deep_inheritance: depth > 3 levels (HIGH)\n"
                "- missing_super_call: __init__ without super() (MEDIUM)\n"
                "- diamond_inheritance: multiple inheritance (INFO)\n"
                "- empty_override: method only calls super() (INFO)\n"
                "\n"
                "WHEN TO USE:\n"
                "- During code review to catch inheritance issues\n"
                "- Before refactoring a class hierarchy\n"
                "- To evaluate OOP design quality\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For SOLID principle violations (use solid_principles)\n"
                "- For design pattern detection (use design_patterns)\n"
                "- For coupling metrics (use coupling_metrics)"
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
                    "depth_threshold": {
                        "type": "integer",
                        "description": (
                            "Maximum allowed inheritance depth. "
                            "Classes exceeding this are flagged. Default: 3."
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
        depth_threshold = arguments.get("depth_threshold", 3)
        output_format = arguments.get("format", "toon")

        if not file_path:
            return {
                "error": "file_path must be provided",
                "format": output_format,
            }

        analyzer = InheritanceQualityAnalyzer(
            depth_threshold=depth_threshold,
        )
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: InheritanceQualityResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_classes": result.total_classes,
            "total_issues": result.total_issues,
            "high_severity_count": result.high_severity_count,
            "issues": [
                {
                    "type": i.issue_type,
                    "line": i.line,
                    "message": i.message,
                    "severity": i.severity,
                    "class_name": i.class_name,
                    "detail": i.detail,
                }
                for i in result.issues
            ],
            "classes": [
                {
                    "name": c.name,
                    "start_line": c.start_line,
                    "end_line": c.end_line,
                    "parent_names": list(c.parent_names),
                    "depth": c.depth,
                    "has_init": c.has_init,
                    "has_super_call": c.has_super_call,
                    "method_count": len(c.methods),
                }
                for c in result.classes
            ],
        }

    def _format_toon(self, result: InheritanceQualityResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Inheritance Quality Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Classes: {result.total_classes}")
        lines.append(f"Issues: {result.total_issues}")
        if result.high_severity_count > 0:
            lines.append(f"  HIGH: {result.high_severity_count}")
        lines.append("")

        if result.issues:
            for i in result.issues:
                lines.append(
                    f"  [{i.severity.upper()}] {i.issue_type}: "
                    f"{i.message}"
                )
                if i.detail:
                    lines.append(f"    {i.detail}")
        else:
            lines.append("No inheritance issues detected.")

        if result.classes:
            lines.append("")
            lines.append("Class hierarchy:")
            for c in result.classes:
                parents = ", ".join(c.parent_names) if c.parent_names else "none"
                lines.append(
                    f"  {c.name} (L{c.start_line}) extends: {parents}"
                )

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_classes": result.total_classes,
            "total_issues": result.total_issues,
            "high_severity_count": result.high_severity_count,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")

        return True
