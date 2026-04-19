"""Flag Argument Tool — MCP Tool.

Detects boolean parameters (flag arguments) that indicate SRP violations.
"""
from __future__ import annotations

from typing import Any

from ...analysis.flag_argument import (
    FlagArgumentAnalyzer,
    FlagArgumentResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class FlagArgumentTool(BaseMCPTool):
    """MCP tool for detecting flag arguments."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "flag_argument",
            "description": (
                "Detect boolean parameters (flag arguments) that violate SRP."
                "\n\n"
                "Flag arguments indicate a function does more than one thing. "
                "Instead of `process(data, True)`, split into "
                "`process_verbose(data)` and `process_silent(data)`."
                "\n\n"
                "Supported Languages:\n"
                "- Python: typed `bool`, default `True/False`\n"
                "- JavaScript: default `true/false`\n"
                "- TypeScript: typed `boolean`\n"
                "- Java: typed `boolean`\n"
                "- Go: typed `bool`\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find functions that do too many things\n"
                "- To detect SRP violations via boolean parameters\n"
                "- To identify refactoring candidates for cleaner APIs\n"
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
            return {"error": "file_path must be provided", "format": output_format}

        analyzer = FlagArgumentAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: FlagArgumentResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "functions_analyzed": result.functions_analyzed,
            "total_issues": result.total_issues,
            "issues": [i.to_dict() for i in result.issues],
        }

    def _format_toon(self, result: FlagArgumentResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Flag Argument Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Functions analyzed: {result.functions_analyzed}")
        lines.append("")

        if result.issues:
            lines.append(f"Found {result.total_issues} flag argument(s):")
            for i in result.issues:
                lines.append(
                    f"  L{i.line}: [{i.severity}] "
                    f"param '{i.param_name}' in '{i.message.split(chr(39))[1]}'"
                )
        else:
            lines.append("No flag arguments found.")

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
