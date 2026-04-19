"""Deep Unpacking Tool — MCP Tool.

Detects excessive tuple unpacking where too many variables are assigned
from a single iterable, reducing readability and risking silent failures.
"""
from __future__ import annotations

from typing import Any

from ...analysis.deep_unpacking import (
    DeepUnpackingAnalyzer,
    DeepUnpackingResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class DeepUnpackingTool(BaseMCPTool):
    """MCP tool for detecting excessive tuple unpacking."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "deep_unpacking",
            "description": (
                "Detect excessive tuple unpacking with too many variables."
                "\n\n"
                "Finds patterns like `a, b, c, d, e, f = iterable` where "
                "4+ variables are unpacked from a single iterable. "
                "This reduces readability and risks ValueError if element "
                "count doesn't match."
                "\n\n"
                "Supported Languages:\n"
                "- Python: tuple unpacking in assignments and for loops\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find code that's hard to read due to excessive unpacking\n"
                "- To identify fragile unpacking that breaks on length mismatch\n"
                "- As a readability check for assignment statements\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For general variable analysis (use variable_mutability)\n"
                "- For dead code detection (use dead_code)"
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

        analyzer = DeepUnpackingAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: DeepUnpackingResult) -> dict[str, Any]:
        return {
            "file": result.file_path,
            "total_hotspots": result.total_hotspots,
            "hotspots": [h.to_dict() for h in result.hotspots],
        }

    def _format_toon(self, result: DeepUnpackingResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Deep Unpacking Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append("")

        if result.hotspots:
            lines.append(
                f"Found {len(result.hotspots)} excessive tuple unpacking(s):"
            )
            for h in result.hotspots:
                lines.append(
                    f"  L{h.line_number}: {h.variable_count} variables "
                    f"unpacked ({h.severity})"
                )
        else:
            lines.append("No excessive tuple unpacking found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_hotspots": result.total_hotspots,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")

        return True
