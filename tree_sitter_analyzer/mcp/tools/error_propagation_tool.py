"""Error Propagation Tool — MCP Tool.

Analyzes error/exception propagation paths in code, detecting
unhandled raises/throws, swallowed exceptions, and missing catch blocks.
"""
from __future__ import annotations

from typing import Any

from ...analysis.error_propagation import (
    ErrorPropagationAnalyzer,
    ErrorPropagationResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class ErrorPropagationTool(BaseMCPTool):
    """MCP tool for analyzing error propagation paths."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "error_propagation",
            "description": (
                "Analyze error/exception propagation paths in code. "
                "\n\n"
                "Traces how errors flow through call chains, detecting: "
                "unhandled raises/throws not wrapped in try, "
                "exceptions caught but never re-raised (swallowed), "
                "try-finally blocks without catch/except."
                "\n\n"
                "Supported Languages:\n"
                "- Python: raise, try/except/finally\n"
                "- JavaScript/TypeScript: throw, try/catch/finally\n"
                "- Java: throw, try/catch/finally\n"
                "\n"
                "Gap Types:\n"
                "- unhandled_raise: raise not in try block (high)\n"
                "- unhandled_throw: throw not in try block (high)\n"
                "- swallowed_no_propagation: catch without re-raise (medium)\n"
                "- finally_no_catch: try-finally without except/catch (low)\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find errors silently swallowed by catch blocks\n"
                "- To audit error handling completeness\n"
                "- To find try-finally blocks that let errors escape\n"
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

        analyzer = ErrorPropagationAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def _format_json(self, result: ErrorPropagationResult) -> dict[str, Any]:
        return result.to_dict()

    def _format_toon(self, result: ErrorPropagationResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Error Propagation Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total gaps: {result.total_gaps}")
        lines.append("")

        if result.gaps:
            for g in result.gaps:
                exc = ", ".join(g.exception_types) if g.exception_types else "unknown"
                lines.append(
                    f"  L{g.line_number}: [{g.gap_type}] [{g.risk_level}] "
                    f"{g.message} ({exc})"
                )
        else:
            lines.append("No error propagation gaps found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_gaps": result.total_gaps,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")

        return True
