"""Test Smell Detector Tool — MCP Tool.

Detects anti-patterns in test code: empty assertions, broad exception
catches, sleep calls, and low assertion counts. Supports Python,
JavaScript/TypeScript, Java, and Go.
"""
from __future__ import annotations

from typing import Any

from ...analysis.test_smells import (
    TestSmellDetector,
    TestSmellResult,
)
from ...formatters.toon_encoder import ToonEncoder
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class TestSmellsTool(BaseMCPTool):
    """MCP tool for detecting test smells."""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "test_smells",
            "description": (
                "Detect test code anti-patterns: empty tests, broad exception "
                "catches, sleep calls, and low assertion counts."
                "\n\n"
                "Catches the gap between 'code is covered' and 'code is actually "
                "tested'. A test with 100% coverage but zero assertions gives "
                "false confidence."
                "\n\n"
                "Smells Detected:\n"
                "- assert_none: test body has zero assertions (HIGH severity)\n"
                "- broad_except: test catches generic Exception (MEDIUM)\n"
                "- sleep_in_test: time.sleep/setTimeout in tests (MEDIUM)\n"
                "- low_assert: fewer assertions than min_assertions (LOW)\n"
                "\n"
                "Supported Languages:\n"
                "- Python: pytest, unittest, nose\n"
                "- JavaScript/TypeScript: Jest, Mocha, AVA\n"
                "- Java: JUnit 4/5, TestNG\n"
                "- Go: testing package, testify\n"
                "\n"
                "WHEN TO USE:\n"
                "- After running test_coverage to verify test quality\n"
                "- During code review to flag unreliable tests\n"
                "- To find tests that pass but test nothing\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For coverage metrics (use test_coverage)\n"
                "- For dead code detection (use dead_code)\n"
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
                    "min_assertions": {
                        "type": "integer",
                        "description": (
                            "Minimum number of assertions per test function. "
                            "Tests below this threshold are flagged as low_assert."
                        ),
                        "default": 1,
                    },
                    "format": {
                        "type": "string",
                        "enum": ["toon", "json"],
                        "description": "Output format (default: toon)",
                        "default": "toon",
                    },
                },
            },
        }

    @handle_mcp_errors(operation="execute")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        file_path = arguments.get("file_path", "")
        min_assertions = arguments.get("min_assertions", 1)
        output_format = arguments.get("format", "toon")

        if not file_path:
            return {"error": "file_path must be provided", "format": output_format}

        detector = TestSmellDetector()
        result = detector.analyze_file(file_path, min_assertions=min_assertions)

        if output_format == "json":
            return self._format_json(result)
        return self._format_toon(result)

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        fmt = arguments.get("format", "toon")
        if fmt not in ("toon", "json"):
            raise ValueError("format must be 'toon' or 'json'")
        file_path = arguments.get("file_path", "")
        if not file_path:
            raise ValueError("file_path must be provided")
        return True

    def _format_json(self, result: TestSmellResult) -> dict[str, Any]:
        return result.to_dict()

    def _format_toon(self, result: TestSmellResult) -> dict[str, Any]:
        lines: list[str] = []
        lines.append("Test Smell Analysis")
        lines.append(f"File: {result.file_path}")
        lines.append(f"Total Tests: {result.total_tests}")
        lines.append(f"Total Smells: {result.total_smells}")

        if result.smell_counts:
            lines.append("")
            lines.append("Smell Breakdown:")
            for smell_type, count in sorted(result.smell_counts.items()):
                lines.append(f"  {smell_type}: {count}")

        if result.test_functions:
            lines.append("")
            lines.append("Functions:")
            for fn in result.test_functions:
                status = "CLEAN" if not fn.smells else f"{len(fn.smells)} smell(s)"
                lines.append(f"  [{status}] {fn.name} (L{fn.start_line}-{fn.end_line})")
                if fn.smells:
                    for s in fn.smells:
                        lines.append(f"    - [{s.severity}] {s.smell_type}: {s.detail}")

        high = result.get_high_severity_smells()
        if high:
            lines.append("")
            lines.append(f"HIGH SEVERITY: {len(high)} test(s) have zero assertions")

        toon = ToonEncoder()
        return {
            "content": toon.encode("\n".join(lines)),
            "total_tests": result.total_tests,
            "total_smells": result.total_smells,
            "high_severity_count": len(high),
        }
