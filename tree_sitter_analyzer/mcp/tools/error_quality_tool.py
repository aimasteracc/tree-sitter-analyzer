"""Error Quality Tool — MCP Tool.

Unified error quality analysis combining three complementary analyzers:
- Error handling anti-pattern detection (patterns)
- Exception handler quality assessment (quality)
- Error message clarity analysis (messages)

Supports: Python, JavaScript/TypeScript, Java, Go
"""
from __future__ import annotations

from typing import Any

from ...analysis.error_handling import ErrorHandlingAnalyzer, ErrorHandlingResult
from ...analysis.error_message_quality import (
    ErrorMessageQualityAnalyzer,
    ErrorMessageResult,
)
from ...analysis.exception_quality import (
    ExceptionQualityAnalyzer,
    ExceptionQualityResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)

_CHECK_MODES = frozenset({"patterns", "quality", "messages", "all"})

_SEVERITY_ORDER: dict[str, int] = {"error": 0, "warning": 1, "info": 2}


def _filter_handling_results(
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


def _format_patterns_json(
    results: list[ErrorHandlingResult],
) -> dict[str, Any]:
    """Format error-handling results as JSON."""
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


def _format_patterns_toon(
    results: list[ErrorHandlingResult],
) -> dict[str, Any]:
    """Format error-handling results as TOON text."""
    total_issues = sum(r.total_issues for r in results)
    lines: list[str] = [
        "Error Handling Pattern Analysis",
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

    return {
        "content": [{"type": "text", "text": "\n".join(lines)}],
        "format": "toon",
        "total_issues": total_issues,
    }


def _format_quality_json(
    result: ExceptionQualityResult,
) -> dict[str, Any]:
    """Format exception quality results as JSON."""
    return {
        "file_path": result.file_path,
        "total_try_blocks": result.total_try_blocks,
        "total_issues": result.total_issues,
        "quality_score": result.quality_score,
        "issue_counts": result.issue_counts,
        "try_blocks": [
            {
                "start_line": b.start_line,
                "end_line": b.end_line,
                "handler_count": b.handler_count,
                "issues": [
                    {
                        "type": i.issue_type,
                        "line": i.line,
                        "severity": i.severity,
                        "description": i.description,
                        "suggestion": i.suggestion,
                    }
                    for i in b.issues
                ],
            }
            for b in result.try_blocks
        ],
    }


def _format_quality_toon(
    result: ExceptionQualityResult,
) -> dict[str, Any]:
    """Format exception quality results as TOON text."""
    lines: list[str] = [
        f"Exception Quality Analysis: {result.file_path}",
        (
            f"Try blocks: {result.total_try_blocks} | "
            f"Issues: {result.total_issues} | "
            f"Score: {result.quality_score:.0f}/100"
        ),
        "",
    ]

    if result.issue_counts:
        lines.append("Issue Summary:")
        for issue_type, count in sorted(result.issue_counts.items()):
            lines.append(f"  {issue_type}: {count}")
        lines.append("")

    for block in result.try_blocks:
        lines.append(
            f"  try block (L{block.start_line}-{block.end_line}): "
            f"{block.handler_count} handlers"
        )
        for issue in block.issues:
            lines.append(
                f"    [{issue.severity.upper()}] L{issue.line}: {issue.issue_type}"
            )
            lines.append(f"      {issue.description}")
            lines.append(f"      Suggestion: {issue.suggestion}")

    encoder = ToonEncoder()
    return {
        "content": [{"type": "text", "text": encoder.encode("\n".join(lines))}],
        "total_issues": result.total_issues,
        "quality_score": result.quality_score,
    }


def _format_messages_json(
    result: ErrorMessageResult,
) -> dict[str, Any]:
    """Format error message quality results as JSON."""
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


def _format_messages_toon(
    result: ErrorMessageResult,
) -> dict[str, Any]:
    """Format error message quality results as TOON text."""
    lines: list[str] = [
        "Error Message Quality Analysis",
        f"File: {result.file_path}",
        f"Total raises: {result.total_raises}",
        f"Poor messages: {result.poor_messages}",
        "",
    ]

    if result.messages:
        lines.append("Poor error messages:")
        for m in result.messages:
            msg_preview = m.message[:40] if m.message else "(empty)"
            lines.append(
                f"  L{m.line_number}: [{m.quality}] {m.error_type}: {msg_preview}"
            )
    else:
        lines.append("All error messages look good.")

    encoder = ToonEncoder()
    return {
        "content": [{"type": "text", "text": encoder.encode("\n".join(lines))}],
        "total_raises": result.total_raises,
        "poor_messages": result.poor_messages,
    }


class ErrorQualityTool(BaseMCPTool):
    """Unified MCP tool for comprehensive error quality analysis.

    Merges three analyzers into a single tool:
    - patterns: Error handling anti-patterns (bare except, swallowed errors, etc.)
    - quality: Exception handler quality (broad catches, missing context, etc.)
    - messages: Error message clarity (generic, empty, vague messages)
    """

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "error_quality",
            "description": (
                "Comprehensive error quality analysis combining anti-pattern "
                "detection, exception handler quality assessment, and error "
                "message clarity checks."
                "\n\n"
                "Check Modes:\n"
                "- patterns: Detect error handling anti-patterns (bare except, "
                "swallowed errors, broad exceptions, unchecked Go errors)\n"
                "- quality: Assess exception handler quality (broad catches, "
                "swallowed exceptions, missing context, generic messages)\n"
                "- messages: Analyze error message clarity (generic, empty, "
                "vague raise/throw messages)\n"
                "- all: Run all three checks and return combined results"
                "\n\n"
                "Supported Languages:\n"
                "- Python: try/except, raise\n"
                "- JavaScript/TypeScript: try/catch, throw\n"
                "- Java: try/catch/finally, throw\n"
                "- Go: defer/recover, errors.New/fmt.Errorf"
                "\n\n"
                "Anti-patterns Detected (patterns):\n"
                "- bare_except: except: without exception type (ERROR)\n"
                "- swallowed_error: empty except/catch blocks (WARNING)\n"
                "- broad_exception: except Exception, catch (Exception e) (WARNING)\n"
                "- unchecked_error: Go err := without if err != nil (WARNING)"
                "\n\n"
                "Quality Issues Detected (quality):\n"
                "- broad_catch: catches overly wide exception type (MEDIUM)\n"
                "- swallowed_exception: empty handler, silently swallowing (HIGH)\n"
                "- missing_context: raises without preserving original (MEDIUM)\n"
                "- generic_error_message: hardcoded error string (LOW)"
                "\n\n"
                "Message Quality Ratings (messages):\n"
                "- good: Includes context and is specific\n"
                "- generic: Uses vague words like 'error', 'failed'\n"
                "- empty: No message provided\n"
                "- vague: Too short to be helpful"
                "\n\n"
                "WHEN TO USE:\n"
                "- To find production failure risks from bad error handling\n"
                "- During code review to catch anti-patterns\n"
                "- To assess exception handler quality beyond simple patterns\n"
                "- To improve error messages for better developer experience\n"
                "- As part of quality assurance checks"
                "\n\n"
                "WHEN NOT TO USE:\n"
                "- For security vulnerabilities (use security_scan)\n"
                "- For code smell detection (use code_smell_detector)\n"
                "- For logging pattern analysis (use logging_patterns)"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Path to a specific file to analyze. "
                            "Required unless project_root is provided."
                        ),
                    },
                    "check": {
                        "type": "string",
                        "description": (
                            "Check mode: 'patterns' for anti-pattern detection, "
                            "'quality' for exception handler quality, "
                            "'messages' for error message clarity, "
                            "'all' for combined analysis (default)."
                        ),
                        "enum": ["patterns", "quality", "messages", "all"],
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
                        "description": (
                            "Project root directory for project-wide scanning. "
                            "Only used with check='patterns'. "
                            "If provided without file_path, scans entire project."
                        ),
                    },
                    "severity": {
                        "type": "string",
                        "description": (
                            "Minimum severity to report: error, warning, info. "
                            "Only used with check='patterns' or 'all'. "
                            "Default: info (show all)."
                        ),
                        "enum": ["error", "warning", "info"],
                    },
                    "pattern_type": {
                        "type": "string",
                        "description": (
                            "Filter by pattern type. "
                            "Only used with check='patterns' or 'all'. "
                            "Default: all patterns."
                        ),
                        "enum": [
                            "bare_except",
                            "swallowed_error",
                            "broad_exception",
                            "unchecked_error",
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
                f"severity must be one of {sorted(_SEVERITY_ORDER)}, got '{severity}'"
            )

        pattern_type = arguments.get("pattern_type", "")
        valid_patterns = {
            "bare_except", "swallowed_error",
            "broad_exception", "unchecked_error",
        }
        if pattern_type and pattern_type not in valid_patterns:
            raise ValueError(
                f"pattern_type must be one of {sorted(valid_patterns)}, "
                f"got '{pattern_type}'"
            )

        return True

    @handle_mcp_errors(operation="execute")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        check = arguments.get("check", "all")
        file_path = arguments.get("file_path", "")
        project_root = arguments.get(
            "project_root", self.project_root or ""
        )
        output_format = arguments.get("format", "toon")
        min_severity = arguments.get("severity", "info")
        pattern_filter = arguments.get("pattern_type", "")

        if check == "patterns":
            return self._execute_patterns(
                file_path, project_root, output_format,
                min_severity, pattern_filter,
            )
        if check == "quality":
            return self._execute_quality(file_path, output_format)
        if check == "messages":
            return self._execute_messages(file_path, output_format)

        return self._execute_all(
            file_path, project_root, output_format,
            min_severity, pattern_filter,
        )

    def _execute_patterns(
        self,
        file_path: str,
        project_root: str,
        output_format: str,
        min_severity: str,
        pattern_filter: str,
    ) -> dict[str, Any]:
        """Run error handling anti-pattern analysis."""
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
            raw_results = [analyzer.analyze_file(file_path)]
        else:
            raw_results = analyzer.analyze_project(project_root)

        results = _filter_handling_results(
            raw_results, min_severity, pattern_filter,
        )

        if output_format == "json":
            return _format_patterns_json(results)
        return _format_patterns_toon(results)

    def _execute_quality(
        self,
        file_path: str,
        output_format: str,
    ) -> dict[str, Any]:
        """Run exception quality analysis."""
        if not file_path:
            return {
                "error": "file_path must be provided for quality check",
                "format": output_format,
            }

        analyzer = ExceptionQualityAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return {"result": _format_quality_json(result)}
        return _format_quality_toon(result)

    def _execute_messages(
        self,
        file_path: str,
        output_format: str,
    ) -> dict[str, Any]:
        """Run error message quality analysis."""
        if not file_path:
            return {
                "error": "file_path must be provided for messages check",
                "format": output_format,
            }

        analyzer = ErrorMessageQualityAnalyzer()
        result = analyzer.analyze_file(file_path)

        if output_format == "json":
            return {"result": _format_messages_json(result)}
        return _format_messages_toon(result)

    def _execute_all(
        self,
        file_path: str,
        project_root: str,
        output_format: str,
        min_severity: str,
        pattern_filter: str,
    ) -> dict[str, Any]:
        """Run all three checks and return combined results."""
        combined: dict[str, Any] = {}

        # Patterns (supports both file_path and project_root)
        if file_path or project_root:
            patterns_result = self._execute_patterns(
                file_path, project_root, output_format,
                min_severity, pattern_filter,
            )
            combined["patterns"] = patterns_result
        else:
            combined["patterns"] = {
                "error": "Either file_path or project_root required for patterns",
            }

        # Quality and messages both require file_path
        if file_path:
            quality_result = self._execute_quality(file_path, output_format)
            combined["quality"] = quality_result

            messages_result = self._execute_messages(file_path, output_format)
            combined["messages"] = messages_result
        else:
            combined["quality"] = {
                "error": "file_path required for quality check",
            }
            combined["messages"] = {
                "error": "file_path required for messages check",
            }

        return combined
