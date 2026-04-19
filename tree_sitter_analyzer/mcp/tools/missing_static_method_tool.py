"""Missing Static Method Tool — MCP Tool.

Detects instance methods that never reference self, indicating they
should be @staticmethod instead.
"""
from __future__ import annotations

from typing import Any

from ...analysis.missing_static_method import (
    MissingStaticMethodAnalyzer,
    MissingStaticMethodResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class MissingStaticMethodTool(BaseMCPTool):
    """MCP tool for detecting methods that should be static."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "missing_static_method",
            "description": (
                "Detect instance methods that never use self."
                "\n\n"
                "Finds methods that should be @staticmethod because "
                "they don't access any instance attributes or methods. "
                "This is a common code smell that misleads callers."
                "\n\n"
                "Supported Languages:\n"
                "- Python: methods with self parameter but no self usage\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find methods that should be @staticmethod\n"
                "- To identify misleading instance method declarations\n"
                "- As a design quality check for class interfaces\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For overall class design analysis (use solid_principles)\n"
                "- For feature envy detection (use feature_envy)"
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

        analyzer = MissingStaticMethodAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: MissingStaticMethodResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_issues": result.total_issues,
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: MissingStaticMethodResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Missing Static Method Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append("")

        if result.issues:
            lines.append(
                f"Found {len(result.issues)} method(s) that should be @staticmethod:"
            )
            for i in result.issues:
                lines.append(
                    f"  L{i.line_number}: {i.class_name}.{i.method_name}() "
                    f"({i.severity})"
                )
        else:
            lines.append("All methods properly use self or are already static.")

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
