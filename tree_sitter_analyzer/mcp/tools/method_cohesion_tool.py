"""Method Cohesion Tool — MCP Tool.

Detects classes with low method cohesion using the LCOM4 metric.
"""
from __future__ import annotations

from typing import Any

from ...analysis.method_cohesion import (
    CohesionResult,
    MethodCohesionAnalyzer,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class MethodCohesionTool(BaseMCPTool):
    """MCP tool for detecting low-cohesion classes (LCOM4 > 1)."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "method_cohesion",
            "description": (
                "Detect classes with low method cohesion (LCOM4 > 1)."
                "\n\n"
                "LCOM4 measures whether methods in a class access the same "
                "instance fields. LCOM4 > 1 means the class contains "
                "disjoint method groups that should be split into separate classes."
                "\n\n"
                "Supported Languages:\n"
                "- Python: self.field access in methods\n"
                "- JavaScript/TypeScript: this.field access in methods\n"
                "- Java: this.field access in methods\n"
                "- Go: receiver.field access in methods\n"
                "\n"
                "Issue Types:\n"
                "- low_cohesion: class has LCOM4 > 1 (medium)\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find classes that do too many unrelated things\n"
                "- To identify split-candidate classes for SRP refactoring\n"
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

        analyzer = MethodCohesionAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)

        return self._format_toon(result)

    def _format_json(self, result: CohesionResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_classes": result.total_classes,
            "cohesive_classes": result.cohesive_classes,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: CohesionResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Method Cohesion Analysis (LCOM4)")
        lines.append(f"File: {result.file_path}")
        lines.append(
            f"Classes: {result.total_classes} total, "
            f"{result.cohesive_classes} cohesive"
        )
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} low-cohesion class(es):")
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: {issue.class_name} "
                    f"(LCOM4={issue.lcom4}, "
                    f"{issue.method_count} methods, "
                    f"{issue.component_count} components)"
                )
        else:
            lines.append("All classes have good cohesion (LCOM4=1).")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "issue_count": len(result.issues),
        }
