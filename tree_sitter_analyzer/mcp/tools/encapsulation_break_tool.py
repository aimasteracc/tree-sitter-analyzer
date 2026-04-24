"""Encapsulation Break Tool — MCP Tool.

Detects methods that return direct references to internal mutable state,
breaking encapsulation and allowing callers to corrupt object invariants.
"""
from __future__ import annotations

from typing import Any

from ...analysis.encapsulation_break import (
    EncapsulationBreakAnalyzer,
    EncapsulationBreakResult,
)
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class EncapsulationBreakTool(BaseMCPTool):
    """MCP tool for detecting encapsulation breaks via mutable state exposure."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "encapsulation_break",
            "description": (
                "Detect methods that return direct references to internal "
                "mutable state (lists, dicts, sets), breaking encapsulation."
                "\n\n"
                "Finds patterns like `return self._items` where `_items` "
                "was initialized as a list/dict/set. Callers can then "
                "mutate the object's internal state without its knowledge."
                "\n\n"
                "Finding Types:\n"
                "- state_exposure (medium): public mutable field returned\n"
                "- private_state_exposure (low): private mutable field returned\n"
                "\n"
                "Supported Languages:\n"
                "- Python: self.X = [] / {} / set(), return self.X\n"
                "- JavaScript/TypeScript: this.X = [] / {}, return this.X\n"
                "- Java: ArrayList/HashMap fields, return this.X\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find encapsulation violations in class-based code\n"
                "- To detect potential corruption of object invariants\n"
                "- As a complement to side_effects (which detects parameter "
                "mutation, not return-value exposure)"
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
                "required": ["file_path"],
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

        analyzer = EncapsulationBreakAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: EncapsulationBreakResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_issues": result.total_issues,
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: EncapsulationBreakResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Encapsulation Break Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append("")

        if result.issues:
            lines.append(
                f"Found {len(result.issues)} mutable state exposure(s):"
            )
            for issue in result.issues:
                lines.append(
                    f"  L{issue.line}: {issue.method_name}() returns "
                    f"{issue.field_name} [{issue.issue_type}] "
                    f"({issue.severity})"
                )
                lines.append(f"    -> {issue.suggestion}")
        else:
            lines.append("No encapsulation breaks detected.")

        return {
            "format": "toon",
            "content": "\n".join(lines),
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
