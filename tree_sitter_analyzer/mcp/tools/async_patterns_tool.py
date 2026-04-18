"""
Async/Await Pattern Analyzer Tool — MCP Tool.

Detects async/await anti-patterns across Python, JavaScript/TypeScript, Java, and Go.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...analysis.async_patterns import (
    AsyncPatternAnalyzer,
    AsyncPatternResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class AsyncPatternsTool(BaseMCPTool):
    """
    MCP tool for detecting async/await anti-patterns.

    Finds silent bugs in async code: missing await, fire-and-forget,
    unhandled promises, and blocking in async contexts.
    """

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate tool arguments."""
        file_path = arguments.get("file_path", "")
        directory = arguments.get("directory", "")
        if not file_path and not directory:
            raise ValueError("Either file_path or directory must be provided")
        return True

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "async_patterns",
            "description": (
                "Detect async/await anti-patterns that cause silent bugs. "
                "\n\n"
                "Supported Languages:\n"
                "- Python: async without await, missing await, fire-and-forget\n"
                "- JavaScript/TypeScript: unhandled promises, missing await, "
                "promise chain mixing\n"
                "- Java: @Async misuse, blocking in async methods\n"
                "- Go: fire-and-forget goroutines, unchecked channels\n"
                "\n"
                "WHEN TO USE:\n"
                "- When reviewing async/concurrent code for correctness\n"
                "- Before deploying async-heavy services\n"
                "- To find bugs invisible to normal code review\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For error handling patterns (use error_handling tool)\n"
                "- For code complexity analysis (use cognitive_complexity tool)"
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
                    "directory": {
                        "type": "string",
                        "description": (
                            "Directory to scan for async patterns. "
                            "Scans all supported files recursively."
                        ),
                    },
                    "severity": {
                        "type": "string",
                        "description": (
                            "Minimum severity to report: error, warning, info. "
                            "Default: warning."
                        ),
                        "enum": ["error", "warning", "info"],
                    },
                    "pattern_type": {
                        "type": "string",
                        "description": (
                            "Filter by pattern type. "
                            "Options: async_without_await, missing_await, "
                            "fire_and_forget, unhandled_promise, "
                            "promise_chain_mix, goroutine_leak, "
                            "unchecked_channel, blocking_in_async."
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
        """Execute the async pattern analysis."""
        file_path = arguments.get("file_path", "")
        directory = arguments.get("directory", "")
        min_severity = arguments.get("severity", "warning")
        pattern_filter = arguments.get("pattern_type", "")
        output_format = arguments.get("format", "toon")

        if not file_path and not directory:
            return {
                "error": "Either file_path or directory must be provided",
                "format": output_format,
            }

        analyzer = AsyncPatternAnalyzer()
        results: list[AsyncPatternResult] = []

        if file_path:
            result = analyzer.analyze_file(file_path)
            results.append(result)
        else:
            root = Path(directory)
            extensions = {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go"}
            for f in root.rglob("*"):
                if f.suffix in extensions and f.is_file():
                    try:
                        result = analyzer.analyze_file(f)
                        results.append(result)
                    except Exception as e:
                        logger.warning("Failed to analyze %s: %s", f, e)

        severity_order = {"error": 0, "warning": 1, "info": 2}
        min_level = severity_order.get(min_severity, 1)

        filtered_results = self._filter_results(
            results, min_level, pattern_filter,
        )

        if output_format == "json":
            return self._format_json(filtered_results)
        else:
            return self._format_toon(filtered_results)

    def _filter_results(
        self,
        results: list[AsyncPatternResult],
        min_level: int,
        pattern_filter: str,
    ) -> list[AsyncPatternResult]:
        """Filter results by severity and pattern type."""
        severity_order = {"error": 0, "warning": 1, "info": 2}
        filtered: list[AsyncPatternResult] = []

        for result in results:
            new_result = AsyncPatternResult(
                file_path=result.file_path,
                language=result.language,
                total_async_functions=result.total_async_functions,
                total_await_expressions=result.total_await_expressions,
                total_goroutines=result.total_goroutines,
            )

            for pattern in result.patterns:
                level = severity_order.get(pattern.severity.value, 2)
                if level > min_level:
                    continue
                if pattern_filter and pattern.pattern_type.value != pattern_filter:
                    continue
                new_result.patterns.append(pattern)

            if new_result.patterns or new_result.total_async_functions > 0:
                filtered.append(new_result)

        return filtered

    def _format_json(self, results: list[AsyncPatternResult]) -> dict[str, Any]:
        """Format results as JSON."""
        total_patterns = sum(len(r.patterns) for r in results)
        total_errors = sum(r.error_count for r in results)
        total_warnings = sum(r.warning_count for r in results)

        return {
            "summary": {
                "files_analyzed": len(results),
                "total_patterns": total_patterns,
                "errors": total_errors,
                "warnings": total_warnings,
            },
            "results": [
                {
                    "file": r.file_path,
                    "language": r.language,
                    "async_functions": r.total_async_functions,
                    "await_expressions": r.total_await_expressions,
                    "goroutines": r.total_goroutines,
                    "patterns": [
                        {
                            "type": p.pattern_type.value,
                            "severity": p.severity.value,
                            "line": p.line,
                            "column": p.column,
                            "message": p.message,
                            "function": p.function_name,
                            "suggestion": p.suggestion,
                        }
                        for p in r.patterns
                    ],
                }
                for r in results
                if r.patterns
            ],
        }

    def _format_toon(self, results: list[AsyncPatternResult]) -> dict[str, Any]:
        """Format results as TOON."""
        lines: list[str] = []
        lines.append("Async Pattern Analysis")

        total_patterns = sum(len(r.patterns) for r in results)
        total_errors = sum(r.error_count for r in results)
        total_warnings = sum(r.warning_count for r in results)

        lines.append(f"Files: {len(results)}")
        lines.append(f"Patterns: {total_patterns} ({total_errors} errors, {total_warnings} warnings)")
        lines.append("")

        for result in results:
            if not result.patterns:
                continue

            lines.append(f"  {result.file_path} ({result.language})")
            lines.append(f"    async functions: {result.total_async_functions}")

            for pattern in result.patterns:
                icon = {"error": "ERR", "warning": "WRN", "info": "INF"}[
                    pattern.severity.value
                ]
                lines.append(
                    f"    [{icon}] L{pattern.line}: {pattern.message}"
                )
                lines.append(f"         -> {pattern.suggestion}")

            lines.append("")

        encoder = ToonEncoder()
        toon = encoder.encode("\n".join(lines))
        return {"result": toon, "format": "toon"}
