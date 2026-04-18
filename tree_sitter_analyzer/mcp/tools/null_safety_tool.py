"""
Null Safety Tool — MCP Tool.

Analyzes code for potential None/null dereference risks. Detects unchecked
access on nullable values, missing null checks, unsafe chained access,
and dict/map bracket access without key validation.

Supports Python, JavaScript/TypeScript, Java, Go.
"""
from __future__ import annotations

from typing import Any

from ...analysis.null_safety import (
    NullSafetyAnalyzer,
    NullSafetyResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class NullSafetyTool(BaseMCPTool):
    """MCP tool for analyzing null safety of code."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "null_safety",
            "description": (
                "Analyze code for potential None/null dereference risks. "
                "\n\n"
                "Detects places where a nullable value is accessed "
                "without a safety check: attribute access on potential "
                "None, dict bracket access without key check, missing "
                "Optional validation, and chained calls without null guards."
                "\n\n"
                "Supported Languages:\n"
                "- Python: None returns, Optional params, dict[key] without check\n"
                "- JavaScript/TypeScript: null/undefined, optional chaining\n"
                "- Java: null returns, Optional<T>, NPE risk\n"
                "- Go: nil pointer dereference, map access without comma-ok\n"
                "\n"
                "Issue Types:\n"
                "- unchecked_access: nullable value accessed without None check\n"
                "- missing_null_check: Optional/nullable param used directly\n"
                "- chained_access: chained calls without null guard\n"
                "- dict_unsafe_access: dict/map[key] instead of .get()/comma-ok\n"
                "\n"
                "WHEN TO USE:\n"
                "- During code review to catch null dereference bugs\n"
                "- To prevent NullPointerException / NoneType errors\n"
                "- As a complement to return_path and error_handling analyzers\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For return path analysis (use return_path)\n"
                "- For error handling patterns (use error_handling)\n"
                "- For exception quality (use exception_quality)"
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
                    "severity": {
                        "type": "string",
                        "description": (
                            "Minimum severity to report: "
                            "high, medium, or low. Default: medium."
                        ),
                        "enum": ["high", "medium", "low"],
                    },
                    "format": {
                        "type": "string",
                        "description": "Output format: toon (default), json, or text",
                        "enum": ["toon", "json", "text"],
                    },
                },
            },
        }

    @handle_mcp_errors(operation="execute")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path = arguments.get("file_path", "")
        min_severity = arguments.get("severity", "medium")
        output_format = arguments.get("format", "toon")

        if not file_path:
            return {
                "error": "file_path must be provided",
                "format": output_format,
            }

        analyzer = NullSafetyAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return self._format_json(result, min_severity)
        if output_format == "text":
            return self._format_text(result, min_severity)
        return self._format_toon(result, min_severity)

    def _filter_issues(
        self,
        result: NullSafetyResult,
        min_severity: str,
    ) -> list[dict[str, Any]]:
        severity_order = {"high": 0, "medium": 1, "low": 2}
        min_level = severity_order.get(min_severity, 1)
        return [
            {
                "line": i.line,
                "issue_type": i.issue_type,
                "severity": i.severity,
                "variable": i.variable,
                "description": i.description,
                "suggestion": i.suggestion,
            }
            for i in result.issues
            if severity_order.get(i.severity, 1) <= min_level
        ]

    def _format_json(
        self,
        result: NullSafetyResult,
        min_severity: str,
    ) -> dict[str, Any]:
        filtered = self._filter_issues(result, min_severity)
        return {
            "file": result.file_path,
            "language": result.language,
            "total_issues": result.total_issues,
            "high_severity": result.high_severity,
            "medium_severity": result.medium_severity,
            "low_severity": result.low_severity,
            "filtered_count": len(filtered),
            "issues": filtered,
        }

    def _format_text(
        self,
        result: NullSafetyResult,
        min_severity: str,
    ) -> dict[str, Any]:
        filtered = self._filter_issues(result, min_severity)
        lines: list[str] = []
        lines.append(f"Null Safety Analysis: {result.file_path}")
        lines.append(f"Language: {result.language}")
        lines.append(f"Issues: {len(filtered)} (of {result.total_issues})")
        lines.append("")

        if filtered:
            for issue in filtered:
                lines.append(
                    f"L{issue['line']}: [{issue['severity'].upper()}] "
                    f"{issue['issue_type']}"
                )
                lines.append(f"  {issue['description']}")
                lines.append(f"  Fix: {issue['suggestion']}")
                lines.append("")
        else:
            lines.append("No null safety issues found.")

        return {
            "content": "\n".join(lines),
            "total_issues": result.total_issues,
            "filtered_count": len(filtered),
        }

    def _format_toon(
        self,
        result: NullSafetyResult,
        min_severity: str,
    ) -> dict[str, Any]:
        filtered = self._filter_issues(result, min_severity)
        lines: list[str] = []
        lines.append("Null Safety Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Language: {result.language}")
        lines.append(
            f"Issues: {result.total_issues} "
            f"(H:{result.high_severity} M:{result.medium_severity} "
            f"L:{result.low_severity})"
        )
        lines.append("")

        if filtered:
            for issue in filtered:
                icon = {"high": "!!", "medium": "!", "low": "~"}.get(
                    issue["severity"], "?"
                )
                lines.append(
                    f"  [{icon}] L{issue['line']}: "
                    f"{issue['issue_type']} — {issue['variable']}"
                )
                lines.append(f"      {issue['description']}")
                lines.append(f"      Fix: {issue['suggestion']}")
        else:
            lines.append("No null safety issues found at this severity level.")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_issues": result.total_issues,
            "filtered_count": len(filtered),
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json", "text"):
            raise ValueError("format must be 'toon', 'json', or 'text'")

        severity = arguments.get("severity", "medium")
        if severity not in ("high", "medium", "low"):
            raise ValueError("severity must be 'high', 'medium', or 'low'")

        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")

        return True
