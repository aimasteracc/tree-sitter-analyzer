"""Error Handling Pattern Tool — MCP Tool.

Detects error handling anti-patterns across codebases using AST analysis.

Supports: Python, JavaScript/TypeScript, Java, Go
"""
from __future__ import annotations

from typing import Any

from ...analysis.error_handling import (
    ErrorHandlingAnalyzer,
    ErrorHandlingResult,
)
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class ErrorHandlingTool(BaseMCPTool):
    """
    MCP tool for detecting error handling anti-patterns.

    Detects bare except clauses, swallowed errors, broad exception types,
    and unchecked Go error returns.
    """

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "error_handling",
            "description": (
                "Detect error handling anti-patterns in your codebase. "
                "\n\n"
                "Supported Languages:\n"
                "- Python: bare except, swallowed errors, broad exceptions\n"
                "- JavaScript/TypeScript: empty catch, catch without type check\n"
                "- Java: empty catch, broad exception types\n"
                "- Go: unchecked error returns\n"
                "\n"
                "Detects:\n"
                "- Bare except: except: without exception type\n"
                "- Swallowed errors: empty except/catch blocks\n"
                "- Broad exceptions: except Exception, catch (Exception e)\n"
                "- Unchecked errors: Go err := without if err != nil\n"
                "\n"
                "WHEN TO USE:\n"
                "- To find production failure risks from bad error handling\n"
                "- During code review to catch anti-patterns\n"
                "- As part of quality assurance checks\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For security vulnerabilities (use security_scan)\n"
                "- For code smell detection (use code_smell_detector)"
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
                    "project_root": {
                        "type": "string",
                        "description": (
                            "Project root directory. "
                            "If provided without file_path, scans entire project."
                        ),
                    },
                    "severity": {
                        "type": "string",
                        "description": (
                            "Minimum severity to report: error, warning, info. "
                            "Default: info (show all)."
                        ),
                        "enum": ["error", "warning", "info"],
                    },
                    "pattern_type": {
                        "type": "string",
                        "description": (
                            "Filter by pattern type. Default: all patterns."
                        ),
                        "enum": [
                            "bare_except", "swallowed_error",
                            "broad_exception", "unchecked_error",
                        ],
                    },
                    "format": {
                        "type": "string",
                        "description": "Output format: toon (default) or json",
                        "enum": ["toon", "json"],
                    },
                },
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        file_path = arguments.get("file_path", "")
        project_root = arguments.get("project_root", "")
        return bool(file_path or project_root)

    @handle_mcp_errors(operation="execute")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path = arguments.get("file_path", "")
        project_root = arguments.get(
            "project_root", self.project_root or ""
        )
        min_severity = arguments.get("severity", "info")
        pattern_filter = arguments.get("pattern_type", "")
        output_format = arguments.get("format", "toon")

        if not file_path and not project_root:
            return {
                "error": "Either file_path or project_root must be provided",
                "format": output_format,
            }

        analyzer = ErrorHandlingAnalyzer(
            project_root=project_root or ".",
            severity_threshold=min_severity,
        )

        if file_path:
            results = [analyzer.analyze_file(file_path)]
        else:
            results = analyzer.analyze_project(project_root)

        # Filter by severity and pattern
        severity_order = {"error": 0, "warning": 1, "info": 2}
        min_level = severity_order.get(min_severity, 2)

        filtered: list[ErrorHandlingResult] = []
        for r in results:
            filtered_issues = [
                i for i in r.issues
                if severity_order.get(i.severity, 2) <= min_level
                and (not pattern_filter or i.pattern_type == pattern_filter)
            ]
            if filtered_issues:
                new_result = ErrorHandlingResult(file_path=r.file_path)
                for issue in filtered_issues:
                    new_result.add_issue(issue)
                filtered.append(new_result)

        if output_format == "json":
            return self._format_json(filtered)
        return self._format_toon(filtered)

    def _format_json(self, results: list[ErrorHandlingResult]) -> dict[str, Any]:
        total_issues = sum(r.total_issues for r in results)
        files_with_issues = len(results)

        by_severity: dict[str, int] = {}
        by_pattern: dict[str, int] = {}
        all_issues: list[dict[str, Any]] = []

        for r in results:
            for s, c in r.by_severity.items():
                by_severity[s] = by_severity.get(s, 0) + c
            for p, c in r.by_pattern.items():
                by_pattern[p] = by_pattern.get(p, 0) + c
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

    def _format_toon(self, results: list[ErrorHandlingResult]) -> dict[str, Any]:
        total_issues = sum(r.total_issues for r in results)

        lines: list[str] = []
        lines.append("Error Handling Analysis")
        lines.append(f"Files: {len(results)} with issues")
        lines.append(f"Total issues: {total_issues}")

        for r in results:
            if not r.issues:
                continue
            lines.append("")
            lines.append(f"File: {r.file_path}")

            for issue in r.issues:
                sev = issue.severity.upper()
                lines.append(
                    f"  [{sev}] L{issue.line_number}: {issue.message}"
                )
                lines.append(f"    {issue.code_snippet}")
                lines.append(f"    -> {issue.suggestion}")

        return {
            "content": [{"type": "text", "text": "\n".join(lines)}],
            "format": "toon",
            "total_issues": total_issues,
        }
