"""Duplicate Condition Tool — MCP Tool.

Analyzes duplicate if conditions. Detects identical conditions that
appear multiple times, indicating DRY violations.
"""
from __future__ import annotations

from typing import Any

from ...analysis.duplicate_condition import (
    DuplicateConditionAnalyzer,
    DuplicateConditionResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class DuplicateConditionTool(BaseMCPTool):
    """MCP tool for analyzing duplicate if conditions."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "duplicate_condition",
            "description": (
                "Analyze duplicate if conditions (DRY violations). "
                "\n\n"
                "Detects identical if conditions that appear multiple "
                "times in the same file. Repeated conditions should be "
                "extracted into shared variables or helper functions."
                "\n\n"
                "Supported Languages:\n"
                "- Python: if/elif conditions\n"
                "- JavaScript/TypeScript: if conditions\n"
                "- Java: if conditions\n"
                "- Go: if conditions\n"
                "\n"
                "WHEN TO USE:\n"
                "- During code review to spot DRY violations in conditions\n"
                "- To identify conditions that should be named variables\n"
                "- As a DRY-focused complement to code_clones\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For cloned code blocks (use code_clones)\n"
                "- For duplicated strings (use magic_values)\n"
                "- For general code quality (use code_smells)"
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

        analyzer = DuplicateConditionAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: DuplicateConditionResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_conditions": result.total_conditions,
            "unique_conditions": result.unique_conditions,
            "duplicate_count": len(result.duplicates),
            "duplicates": [d.to_dict() for d in result.duplicates],
        }

    def _format_toon(
        self, result: DuplicateConditionResult
    ) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Duplicate Condition Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(
            f"Total conditions: {result.total_conditions}, "
            f"unique: {result.unique_conditions}"
        )
        lines.append("")

        if result.duplicates:
            lines.append(f"Found {len(result.duplicates)} duplicate(s):")
            for d in result.duplicates:
                lines.append(
                    f"  \"{d.condition}\" appears {d.count}x "
                    f"at lines {', '.join(str(ln) for ln in d.occurrences)}"
                )
        else:
            lines.append("No duplicate conditions found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_conditions": result.total_conditions,
            "duplicate_count": len(result.duplicates),
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")

        return True
