"""Error Propagation Tool — MCP Tool.

Analyzes error/exception propagation paths in code, detecting
unhandled raises/throws, swallowed exceptions, missing catch blocks,
and silent error suppression.
"""
from __future__ import annotations

from typing import Any

from ...analysis.error_propagation import (
    ErrorPropagationAnalyzer,
    ErrorPropagationResult,
)
from ...analysis.silent_suppression import (
    SilentSuppressionAnalyzer,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class ErrorPropagationTool(BaseMCPTool):
    """MCP tool for analyzing error propagation paths and silent suppression."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "error_propagation",
            "description": (
                "Analyze error/exception propagation paths and silent suppression in code. "
                "\n\n"
                "Traces how errors flow through call chains, detecting: "
                "unhandled raises/throws not wrapped in try, "
                "exceptions caught but never re-raised (swallowed), "
                "try-finally blocks without catch/except, "
                "and silent suppression (empty handlers, logging-only)."
                "\n\n"
                "Supported Languages:\n"
                "- Python: raise, try/except/finally\n"
                "- JavaScript/TypeScript: throw, try/catch/finally\n"
                "- Java: throw, try/catch/finally\n"
                "- Go: error checks (silent suppression only)\n"
                "\n"
                "Gap Types:\n"
                "- unhandled_raise: raise not in try block (high)\n"
                "- unhandled_throw: throw not in try block (high)\n"
                "- swallowed_no_propagation: catch without re-raise (medium)\n"
                "- finally_no_catch: try-finally without except/catch (low)\n"
                "- silent_suppression: handler is empty/pass/continue/return None (high)\n"
                "- logging_only_suppression: handler only logs without recovery (medium)\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find errors silently swallowed by catch blocks\n"
                "- To audit error handling completeness\n"
                "- To find try-finally blocks that let errors escape\n"
                "- To find empty or logging-only error handlers"
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

        prop_result = ErrorPropagationAnalyzer().analyze_file(file_path)
        ss_result = SilentSuppressionAnalyzer().analyze_file(file_path)

        if output_format == "json":
            return self._format_json(prop_result, ss_result)
        return self._format_toon(prop_result, ss_result)

    def _format_json(
        self,
        prop_result: ErrorPropagationResult,
        ss_result: Any,
    ) -> dict[str, Any]:
        data = prop_result.to_dict()
        if ss_result.total_issues > 0:
            data["silent_suppressions"] = [
                {
                    "line": i.line,
                    "issue_type": i.issue_type,
                    "severity": i.severity,
                    "handler_type": i.handler_type,
                    "description": i.description,
                    "suggestion": i.suggestion,
                }
                for i in ss_result.issues
            ]
            data["total_gaps"] = data.get("total_gaps", 0) + ss_result.total_issues
        return data

    def _format_toon(
        self,
        prop_result: ErrorPropagationResult,
        ss_result: Any,
    ) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Error Propagation Analysis")
        lines.append(f"File: {prop_result.file_path}")

        total = prop_result.total_gaps + ss_result.total_issues
        lines.append(f"Total issues: {total}")
        lines.append("")

        if prop_result.gaps:
            lines.append("Propagation gaps:")
            for g in prop_result.gaps:
                exc = ", ".join(g.exception_types) if g.exception_types else "unknown"
                lines.append(
                    f"  L{g.line_number}: [{g.gap_type}] [{g.risk_level}] "
                    f"{g.message} ({exc})"
                )

        if ss_result.issues:
            lines.append("Silent suppressions:")
            for i in ss_result.issues:
                lines.append(
                    f"  L{i.line}: [{i.issue_type}] [{i.severity}] "
                    f"{i.handler_type} — {i.description}"
                )

        if not prop_result.gaps and not ss_result.issues:
            lines.append("No error propagation issues found.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_gaps": total,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")

        return True
