"""Error Quality Tool — MCP Tool.

Unified error quality analysis combining:
- Error handling anti-pattern detection (bare except, swallowed, broad, unchecked)
- Missing exception context detection (raise without chaining)
- Generic error message detection (unhelpful raise/throw strings)

Supports: Python, JavaScript/TypeScript, Java, Go
"""
from __future__ import annotations

from typing import Any

from ...analysis.error_handling import (
    ErrorHandlingAnalyzer,
    ErrorHandlingResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)

_CHECK_MODES = frozenset({"patterns", "context", "messages", "all"})

_SEVERITY_ORDER: dict[str, int] = {"error": 0, "warning": 1, "info": 2}


def _filter_results(
    results: list[ErrorHandlingResult],
    min_severity: str,
    pattern_filter: str,
) -> list[ErrorHandlingResult]:
    """Filter error-handling results by severity and pattern type."""
    min_level = _SEVERITY_ORDER.get(min_severity, 2)
    filtered: list[ErrorHandlingResult] = []
    for r in results:
        matching = [
            issue
            for issue in r.issues
            if _SEVERITY_ORDER.get(issue.severity, 2) <= min_level
            and (not pattern_filter or issue.pattern_type == pattern_filter)
        ]
        if matching:
            new_result = ErrorHandlingResult(file_path=r.file_path)
            for issue in matching:
                new_result.add_issue(issue)
            filtered.append(new_result)
    return filtered


def _format_json(results: list[ErrorHandlingResult]) -> dict[str, Any]:
    """Format results as JSON."""
    total_issues = sum(r.total_issues for r in results)
    files_with_issues = len(results)

    by_severity: dict[str, int] = {}
    by_pattern: dict[str, int] = {}
    all_issues: list[dict[str, Any]] = []

    for r in results:
        for sev, count in r.by_severity.items():
            by_severity[sev] = by_severity.get(sev, 0) + count
        for pat, count in r.by_pattern.items():
            by_pattern[pat] = by_pattern.get(pat, 0) + count
        for issue in r.issues:
            all_issues.append({
                "pattern_type": issue.pattern_type,
                "severity": issue.severity,
                "message": issue.message,
                "file_path": issue.file_path,
                "line": issue.line_number,
                "end_line": issue.end_line,
                "snippet": issue.code_snippet,
                "suggestion": issue.suggestion,
                "language": issue.language,
            })

    return {
        "total_issues": total_issues,
        "files_with_issues": files_with_issues,
        "by_severity": by_severity,
        "by_pattern": by_pattern,
        "issues": all_issues,
    }


def _format_toon(results: list[ErrorHandlingResult]) -> dict[str, Any]:
    """Format results as TOON text."""
    total_issues = sum(r.total_issues for r in results)
    lines: list[str] = [
        "Error Quality Analysis",
        f"Files: {len(results)} with issues",
        f"Total issues: {total_issues}",
    ]

    for r in results:
        if not r.issues:
            continue
        lines.append("")
        lines.append(f"File: {r.file_path}")
        for issue in r.issues:
            sev = issue.severity.upper()
            lines.append(f"  [{sev}] L{issue.line_number}: {issue.message}")
            lines.append(f"    {issue.code_snippet}")
            lines.append(f"    -> {issue.suggestion}")

    encoder = ToonEncoder()
    return {
        "content": [
            {"type": "text", "text": encoder.encode("\n".join(lines))}
        ],
        "format": "toon",
        "total_issues": total_issues,
    }


class ErrorQualityTool(BaseMCPTool):
    """Unified MCP tool for comprehensive error quality analysis."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "error_quality",
            "description": (
                "Comprehensive error quality analysis: detect anti-patterns, "
                "missing exception context, and generic error messages."
                "\n\n"
                "Anti-patterns Detected:\n"
                "- bare_except: except: without exception type (ERROR)\n"
                "- swallowed_error: empty except/catch blocks (WARNING)\n"
                "- broad_exception: except Exception, catch (Exception) (WARNING)\n"
                "- unchecked_error: Go err := without if err != nil (WARNING)\n"
                "- missing_context: raise inside except without chaining (INFO)\n"
                "- generic_error_message: unhelpful hardcoded error string (INFO)"
                "\n\n"
                "Supported Languages: Python, JS/TS, Java, Go"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to file to analyze.",
                    },
                    "check": {
                        "type": "string",
                        "description": (
                            "Filter: 'patterns' for anti-patterns, "
                            "'context' for missing chaining, "
                            "'messages' for generic messages, "
                            "'all' (default)."
                        ),
                        "enum": ["patterns", "context", "messages", "all"],
                        "default": "all",
                    },
                    "format": {
                        "type": "string",
                        "description": "Output format: toon (default) or json",
                        "enum": ["toon", "json"],
                        "default": "toon",
                    },
                    "project_root": {
                        "type": "string",
                        "description": "Project root for project-wide scanning.",
                    },
                    "severity": {
                        "type": "string",
                        "description": "Minimum severity: error, warning, info.",
                        "enum": ["error", "warning", "info"],
                    },
                    "pattern_type": {
                        "type": "string",
                        "description": "Filter by specific pattern type.",
                        "enum": [
                            "bare_except",
                            "swallowed_error",
                            "broad_exception",
                            "unchecked_error",
                            "missing_context",
                            "generic_error_message",
                        ],
                    },
                },
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        file_path = arguments.get("file_path", "")
        project_root = arguments.get("project_root", "")
        if not file_path and not project_root:
            raise ValueError("Either file_path or project_root must be provided")

        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")

        check = arguments.get("check", "all")
        if check not in _CHECK_MODES:
            raise ValueError(
                f"check must be one of {sorted(_CHECK_MODES)}, got '{check}'"
            )

        severity = arguments.get("severity", "")
        if severity and severity not in _SEVERITY_ORDER:
            raise ValueError(
                f"severity must be one of {sorted(_SEVERITY_ORDER)}"
            )

        return True

    @handle_mcp_errors(operation="execute")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path = arguments.get("file_path", "")
        project_root = arguments.get(
            "project_root", self.project_root or ""
        )
        output_format = arguments.get("format", "toon")
        min_severity = arguments.get("severity", "info")
        check = arguments.get("check", "all")

        analyzer = ErrorHandlingAnalyzer(
            project_root=project_root or ".",
            severity_threshold=min_severity,
        )

        if file_path:
            results = [analyzer.analyze_file(file_path)]
        elif project_root:
            results = analyzer.analyze_project(project_root)
        else:
            return {"error": "Either file_path or project_root required"}

        pattern_filter = self._check_to_pattern(check)
        filtered = _filter_results(results, min_severity, pattern_filter)

        if output_format == "json":
            return _format_json(filtered)
        return _format_toon(filtered)

    @staticmethod
    def _check_to_pattern(check: str) -> str:
        """Map check mode to pattern_type filter."""
        mapping: dict[str, str] = {
            "patterns": "",  # all pattern-related
            "context": "missing_context",
            "messages": "generic_error_message",
            "all": "",
        }
        return mapping.get(check, "")
