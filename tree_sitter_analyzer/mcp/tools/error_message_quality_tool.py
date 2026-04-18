"""Error Message Quality Tool — MCP Tool.

Analyzes error message quality in raise/throw statements.
Detects generic, empty, or unhelpful error messages.
"""
from __future__ import annotations

from typing import Any

from ...analysis.error_message_quality import (
    ErrorMessageQualityAnalyzer,
    ErrorMessageResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class ErrorMessageQualityTool(BaseMCPTool):
    """MCP tool for analyzing error message quality."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "error_message_quality",
            "description": (
                "Analyze error message quality in raise/throw statements. "
                "\n\n"
                "Detects poor error messages: generic (e.g., 'error', 'failed'), "
                "empty (no message), or vague (too short). Good error messages "
                "include context about what went wrong."
                "\n\n"
                "Quality Ratings:\n"
                "- good: Includes context and is specific\n"
                "- generic: Uses vague words like 'error', 'failed'\n"
                "- empty: No message provided\n"
                "- vague: Too short to be helpful\n"
                "\n"
                "Supported Languages:\n"
                "- Python: raise ValueError(...)\n"
                "- JavaScript/TypeScript: throw new Error(...)\n"
                "- Java: throw new RuntimeException(...)\n"
                "- Go: errors.New(...) / fmt.Errorf(...)\n"
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

        analyzer = ErrorMessageQualityAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: ErrorMessageResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_raises": result.total_raises,
            "poor_messages": result.poor_messages,
            "messages": [
                {
                    "line": m.line_number,
                    "message": m.message,
                    "quality": m.quality,
                    "error_type": m.error_type,
                }
                for m in result.messages
            ],
        }

    def _format_toon(self, result: ErrorMessageResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Error Message Quality Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total raises: {result.total_raises}")
        lines.append(f"Poor messages: {result.poor_messages}")
        lines.append("")

        if result.messages:
            lines.append("Poor error messages:")
            for m in result.messages:
                msg_preview = m.message[:40] if m.message else "(empty)"
                lines.append(
                    f"  L{m.line_number}: [{m.quality}] {m.error_type}: {msg_preview}"
                )
        else:
            lines.append("All error messages look good.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_raises": result.total_raises,
            "poor_messages": result.poor_messages,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")
        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")
        return True
