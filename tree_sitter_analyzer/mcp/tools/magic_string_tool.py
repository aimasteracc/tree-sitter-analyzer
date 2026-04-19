"""Magic String Tool — MCP Tool.

Analyzes code for hardcoded string literals that should be
extracted to named constants. Complements magic_values.
"""
from __future__ import annotations

from typing import Any

from ...analysis.magic_string import (
    MagicStringAnalyzer,
    MagicStringResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class MagicStringTool(BaseMCPTool):
    """MCP tool for analyzing magic strings."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "magic_string",
            "description": (
                "Analyze code for hardcoded string literals that should be constants. "
                "\n\n"
                "Detects magic strings (hardcoded literals in functions) and "
                "repeated strings (same literal appearing 3+ times). "
                "Complements magic_values which detects magic numbers."
                "\n\n"
                "Supported Languages:\n"
                "- Python, JavaScript/TypeScript, Java, Go\n"
                "\n"
                "Issue Types:\n"
                "- magic_string: hardcoded string literal in function body\n"
                "- repeated_string: same string appears 3+ times\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find hardcoded strings that should be constants\n"
                "- To detect repeated strings that need extraction\n"
                "- As a complement to magic_values (numbers)\n"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to a specific file to analyze.",
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

        analyzer = MagicStringAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: MagicStringResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_functions": result.total_functions,
            "total_strings": result.total_strings,
            "issue_count": len(result.issues),
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: MagicStringResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Magic String Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Functions: {result.total_functions}, Strings: {result.total_strings}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {len(result.issues)} issue(s):")
            for i in result.issues:
                lines.append(
                    f"  L{i.line_number}: [{i.issue_type}] [{i.severity}] "
                    f'"{i.string_value[:40]}"'
                )
        else:
            lines.append("No magic string issues found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_functions": result.total_functions,
            "total_strings": result.total_strings,
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
