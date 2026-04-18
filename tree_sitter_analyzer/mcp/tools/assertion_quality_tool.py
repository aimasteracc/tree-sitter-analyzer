"""Assertion Quality Tool — MCP Tool.

Analyzes test assertion quality: detects weak assertions, vague comparisons,
clustered assertions, and missing branch assertions. Fills the gap between
test_coverage and test_smells by examining WHAT assertions verify.
"""
from __future__ import annotations

from typing import Any

from ...analysis.assertion_quality import (
    AssertionQualityAnalyzer,
    AssertionQualityResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class AssertionQualityTool(BaseMCPTool):
    """MCP tool for analyzing test assertion quality."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "assertion_quality",
            "description": (
                "Analyze test assertion quality: detect weak, vague, clustered "
                "assertions and missing branch coverage in tests."
                "\n\n"
                "Fills the gap between test_coverage (are things tested?) and "
                "test_smells (are there anti-patterns?) by examining WHAT "
                "assertions actually verify."
                "\n\n"
                "Quality Issues Detected:\n"
                "- weak_assertion: checks existence only (MEDIUM)\n"
                "- vague_comparison: uses vague matchers (MEDIUM)\n"
                "- clustered_assertions: all bunched at end (LOW)\n"
                "- missing_branch_assertion: branch without assertion (HIGH)\n"
                "\n"
                "Supported Languages:\n"
                "- Python: assert, unittest, pytest\n"
                "- JavaScript/TypeScript: expect(), assert\n"
                "- Java: JUnit assertions, assertThat\n"
                "- Go: testify, testing package\n"
                "\n"
                "WHEN TO USE:\n"
                "- After test_coverage to verify assertion quality\n"
                "- After test_smells to dig deeper into weak assertions\n"
                "- During code review to find tests that pass but test nothing\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For coverage metrics (use test_coverage)\n"
                "- For anti-pattern detection (use test_smells)\n"
                "- For code complexity (use cognitive_complexity)"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Path to a test file to analyze. "
                            "Only files matching test naming conventions are analyzed."
                        ),
                    },
                    "cluster_threshold": {
                        "type": "number",
                        "description": (
                            "Threshold for clustered assertion detection. "
                            "Higher values require more clustering to trigger."
                        ),
                        "default": 0.8,
                    },
                    "format": {
                        "type": "string",
                        "enum": ["text", "json", "toon"],
                        "description": "Output format (default: text)",
                        "default": "text",
                    },
                },
                "required": ["file_path"],
            },
        }

    @handle_mcp_errors(operation="execute")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path = arguments.get("file_path", "")
        cluster_threshold = arguments.get("cluster_threshold", 0.8)
        output_format = arguments.get("format", "text")

        analyzer = AssertionQualityAnalyzer()
        result = analyzer.analyze_file(file_path, cluster_threshold=cluster_threshold)

        if output_format == "json":
            return {"result": self._to_json(result)}
        if output_format == "toon":
            return {"content": [{"type": "text", "text": self._to_toon(result)}]}
        return {"content": [{"type": "text", "text": self._to_text(result)}]}

    def _to_text(self, result: AssertionQualityResult) -> str:
        lines: list[str] = [
            f"Assertion Quality Analysis: {result.file_path}",
            f"Tests: {result.total_tests} | Issues: {result.total_issues} | Score: {result.quality_score:.0f}/100",
            "",
        ]

        if result.issue_counts:
            lines.append("Issue Summary:")
            for issue_type, count in sorted(result.issue_counts.items()):
                lines.append(f"  {issue_type}: {count}")
            lines.append("")

        for func in result.test_functions:
            lines.append(
                f"  {func.name} (L{func.start_line}-{func.end_line}): "
                f"{func.assertion_count} assertions, score={func.quality_score:.0f}"
            )
            for issue in func.issues:
                lines.append(
                    f"    [{issue.severity.upper()}] L{issue.line}: {issue.issue_type}"
                )
                lines.append(f"      {issue.description}")
                lines.append(f"      Suggestion: {issue.suggestion}")

        return "\n".join(lines)

    def _to_json(self, result: AssertionQualityResult) -> dict[str, Any]:
        return {
            "file_path": result.file_path,
            "total_tests": result.total_tests,
            "total_issues": result.total_issues,
            "quality_score": result.quality_score,
            "issue_counts": result.issue_counts,
            "test_functions": [
                {
                    "name": f.name,
                    "start_line": f.start_line,
                    "end_line": f.end_line,
                    "assertion_count": f.assertion_count,
                    "quality_score": f.quality_score,
                    "issues": [
                        {
                            "type": i.issue_type,
                            "line": i.line,
                            "severity": i.severity,
                            "description": i.description,
                            "suggestion": i.suggestion,
                        }
                        for i in f.issues
                    ],
                }
                for f in result.test_functions
            ],
        }

    def _to_toon(self, result: AssertionQualityResult) -> str:
        encoder = ToonEncoder()
        data = self._to_json(result)
        return encoder.encode(data)

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "text")
        if fmt not in ("text", "json", "toon"):
            raise ValueError(f"Invalid output format: {fmt}")
        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path is required")
        return True
