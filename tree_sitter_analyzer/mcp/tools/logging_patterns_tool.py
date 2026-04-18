"""Logging Pattern Analyzer Tool — MCP Tool.

Detects logging anti-patterns: silent catch blocks, print statements
used for logging, sensitive data in log calls, and bare raises without
logging. Supports Python, JavaScript/TypeScript, Java, and Go.
"""
from __future__ import annotations

from typing import Any

from ...analysis.logging_patterns import (
    LoggingPatternAnalyzer,
    LoggingPatternResult,
)
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class LoggingPatternsTool(BaseMCPTool):
    """MCP tool for detecting logging anti-patterns."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "logging_patterns",
            "description": (
                "Detect logging anti-patterns that make production debugging harder."
                "\n\n"
                "Catches the gap between 'errors are handled' and 'errors are "
                "debuggable'. A catch block that silently swallows errors is worse "
                "than no error handling at all."
                "\n\n"
                "Smells Detected:\n"
                "- silent_catch: catch/except block with no logging (HIGH severity)\n"
                "- print_logging: using print() instead of a logger (LOW)\n"
                "- sensitive_in_log: potential secrets in log arguments (HIGH)\n"
                "- bare_raise: re-raise without logging the original error (MEDIUM)\n"
                "\n"
                "Supported Languages:\n"
                "- Python: logging.*, logger.*, print()\n"
                "- JavaScript/TypeScript: console.*, logger.*\n"
                "- Java: log.*, logger.*, System.out\n"
                "- Go: log.*, slog.*, fmt.*\n"
                "\n"
                "WHEN TO USE:\n"
                "- After error_handling to verify errors are actually logged\n"
                "- During code review to find silent error swallowing\n"
                "- To audit for sensitive data leaking into logs\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For error handling patterns (use error_handling)\n"
                "- For security vulnerability scanning (use security_scan)\n"
                "- For code smell detection (use code_smell_detector)"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Path to a source file to analyze for logging patterns."
                        ),
                    },
                    "format": {
                        "type": "string",
                        "enum": ["json", "toon"],
                        "description": "Output format. Default: json.",
                        "default": "json",
                    },
                },
                "required": ["file_path"],
            },
        }

    @handle_mcp_errors(operation="execute")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path = arguments.get("file_path", "")
        fmt = arguments.get("format", "json")

        if not file_path:
            return {"error": "file_path must be provided", "format": fmt}

        analyzer = LoggingPatternAnalyzer()
        result = analyzer.analyze_file(file_path)

        if fmt == "toon":
            return self._format_toon(result)
        return self._format_json(result)

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "json")
        if fmt not in ("json", "toon"):
            raise ValueError("format must be 'json' or 'toon'")
        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path is required")
        return True

    def _format_json(self, result: LoggingPatternResult) -> dict[str, Any]:
        return result.to_dict()

    def _format_toon(self, result: LoggingPatternResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append(f"LOGGING PATTERNS | {result.file_path}")
        lines.append(f"catch_blocks: {result.total_catch_blocks} | smells: {result.total_smells}")

        if result.smell_counts:
            parts = [f"{k}: {v}" for k, v in sorted(result.smell_counts.items())]
            lines.append("smell_counts: " + ", ".join(parts))

        for block in result.catch_blocks:
            lines.append(f"  catch[{block.handler_type}] L{block.start_line}-{block.end_line}")
            if not block.has_logging:
                lines.append("    no_logging: true")
            for smell in block.smells:
                lines.append(f"    {smell.severity} | {smell.smell_type} | {smell.detail}")

        for call in result.print_logging_calls:
            lines.append(f"  L{call.line_number} | {call.severity} | {call.smell_type} | {call.detail}")

        toon_text = "\n".join(lines)
        return {"content": [{"type": "text", "text": toon_text}]}
