#!/usr/bin/env python3
"""
Test Coverage Tool — MCP Tool

Analyzes test coverage by comparing source code elements against test files.
Identifies untested functions, classes, and methods without requiring pytest execution.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...analysis.test_coverage import TestCoverageAnalyzer
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class TestCoverageTool(BaseMCPTool):
    """
    MCP tool for analyzing test coverage.

    Identifies code elements (functions, classes, methods) that lack
    test coverage by comparing source code structure against test files.
    Uses AST-based analysis without requiring pytest execution.
    """

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)
        self.analyzer = TestCoverageAnalyzer()

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "test_coverage",
            "description": (
                "Analyze test coverage by identifying untested code elements. "
                "\n\n"
                "Uses AST-based analysis to compare source code elements (functions, "
                "classes, methods) against test files. Does not require pytest execution.\n\n"
                "Grading Scale:\n"
                "- A (80-100%): Excellent coverage\n"
                "- B (60-79%): Good coverage\n"
                "- C (40-59%): Fair coverage - needs improvement\n"
                "- D (20-39%): Poor coverage - significant gaps\n"
                "- F (0-19%): Critical coverage - many untested elements\n\n"
                "Supported Languages:\n"
                "- Python: functions, classes, methods\n"
                "- JavaScript/TypeScript: functions, classes\n"
                "- Java: classes, methods\n"
                "- Go: functions, methods\n\n"
                "WHEN TO USE:\n"
                "- During code review to identify untested code\n"
                "- Before refactoring to ensure test coverage\n"
                "- To track test coverage trends over time\n"
                "- As part of CI/CD quality gates\n\n"
                "WHEN NOT TO USE:\n"
                "- For runtime coverage analysis (use pytest-cov instead)\n"
                "- For branch/line coverage (this tool does element-level analysis)"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Path to a specific source file to analyze. "
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
                    "include_tested": {
                        "type": "boolean",
                        "description": (
                            "Include tested elements in output. "
                            "If False, only shows untested elements."
                        ),
                        "default": False,
                    },
                    "output_format": {
                        "type": "string",
                        "enum": ["toon", "json"],
                        "description": "Output format: toon (compact with emoji) or json (structured)",
                        "default": "toon",
                    },
                },
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """Validate tool arguments."""
        file_path = arguments.get("file_path")
        if file_path is not None and not isinstance(file_path, str):
            raise ValueError("file_path must be a string")

        project_root = arguments.get("project_root")
        if project_root is not None and not isinstance(project_root, str):
            raise ValueError("project_root must be a string")

        include_tested = arguments.get("include_tested")
        if include_tested is not None and not isinstance(include_tested, bool):
            raise ValueError("include_tested must be a boolean")

        output_format = arguments.get("output_format")
        if output_format is not None:
            valid_formats = {"toon", "json"}
            if output_format not in valid_formats:
                raise ValueError(
                    f"output_format must be one of {valid_formats}, got '{output_format}'"
                )

        return True

    @handle_mcp_errors("test_coverage")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute test coverage analysis.

        Args:
            arguments: Tool arguments (file_path, project_root, include_tested, output_format)

        Returns:
            Analysis results in requested format
        """
        file_path = arguments.get("file_path")
        project_root = arguments.get("project_root") or self.project_root
        include_tested = arguments.get("include_tested", False)
        output_format = arguments.get("output_format", "toon")

        # Resolve project root
        if project_root:
            project_path_str = self.path_resolver.resolve(project_root)
        else:
            project_path_str = str(Path.cwd())

        # Single file analysis
        if file_path:
            resolved_path = self.resolve_and_validate_file_path(file_path)

            # Find corresponding test files
            test_files = self._find_test_files(project_path_str)

            result = self.analyzer.analyze_file(
                str(resolved_path),
                test_files=[str(tf) for tf in test_files],
            )

            if output_format == "json":
                return self._format_result_json(result, include_tested)
            else:
                return self._format_result_toon(result, include_tested)

        # Project-wide analysis
        results = self.analyzer.analyze_project(project_path_str)

        # Filter out test files from results
        source_results = {
            fp: r
            for fp, r in results.items()
            if not self.analyzer.is_test_file(fp)
        }

        if output_format == "json":
            return self._format_project_json(source_results, include_tested)
        else:
            return self._format_project_toon(source_results, include_tested)

    def _find_test_files(self, project_root: str) -> list[Path]:
        """Find all test files in the project."""
        test_files: list[Path] = []
        project_path = Path(project_root)

        for ext in [".py", ".js", ".ts", ".java", ".go"]:
            for path in project_path.rglob(f"*{ext}"):
                if self.analyzer.is_test_file(str(path)):
                    test_files.append(path)

        return test_files

    def _format_result_toon(
        self, result: Any, include_tested: bool
    ) -> dict[str, Any]:
        """Format single file result as TOON."""
        lines = [
            "📊 Test Coverage Report",
            "",
            f"📁 {result.source_file}",
            f"🌐 Language: {result.language}",
            f"📈 Coverage: {result.coverage_percent:.1f}% ({result.coverage_grade} grade)",
            f"✅ Tested: {result.tested_elements}/{result.total_elements}",
            "",
        ]

        # Untested elements
        if result.untested_elements:
            lines.extend([
                "⚠️  Untested Elements:",
                "",
            ])
            for elem in result.untested_elements:
                emoji = self._element_emoji(elem.element_type.value)
                lines.append(f"  {emoji} {elem.name}:{elem.line} ({elem.element_type.value})")
        elif include_tested:
            lines.append("✨ All elements are tested!")

        lines.append("")

        return {
            "format": "toon",
            "content": "\n".join(lines),
            "summary": {
                "file": result.source_file,
                "coverage_percent": result.coverage_percent,
                "grade": result.coverage_grade,
                "tested": result.tested_elements,
                "total": result.total_elements,
                "untested_count": len(result.untested_elements),
            },
        }

    def _format_result_json(
        self, result: Any, include_tested: bool
    ) -> dict[str, Any]:
        """Format single file result as JSON."""
        return {
            "file": result.source_file,
            "language": result.language,
            "coverage_percent": result.coverage_percent,
            "grade": result.coverage_grade,
            "tested_elements": result.tested_elements,
            "total_elements": result.total_elements,
            "untested_elements": [
                {
                    "name": e.name,
                    "type": e.element_type.value,
                    "line": e.line,
                }
                for e in result.untested_elements
            ],
            "is_fully_covered": result.is_fully_covered,
        }

    def _format_project_toon(
        self, results: dict[str, Any], include_tested: bool
    ) -> dict[str, Any]:
        """Format project results as TOON."""
        # Calculate aggregate stats
        total_elements = sum(r.total_elements for r in results.values())
        total_tested = sum(r.tested_elements for r in results.values())
        total_untested = sum(len(r.untested_elements) for r in results.values())

        overall_coverage = (
            (total_tested / total_elements * 100) if total_elements > 0 else 100.0
        )

        # Calculate grade
        if overall_coverage >= 80:
            grade = "A"
        elif overall_coverage >= 60:
            grade = "B"
        elif overall_coverage >= 40:
            grade = "C"
        elif overall_coverage >= 20:
            grade = "D"
        else:
            grade = "F"

        lines = [
            "📊 Test Coverage Report (Project)",
            "",
            f"📈 Overall Coverage: {overall_coverage:.1f}% ({grade} grade)",
            f"✅ Tested: {total_tested}/{total_elements} elements",
            f"⚠️  Untested: {total_untested} elements",
            f"📁 Files Analyzed: {len(results)}",
            "",
        ]

        # Group by grade
        by_grade: dict[str, list[tuple[str, Any]]] = {
            "A": [], "B": [], "C": [], "D": [], "F": []
        }
        for fp, result in results.items():
            by_grade[result.coverage_grade].append((fp, result))

        for grade_letter in ["A", "B", "C", "D", "F"]:
            files = by_grade[grade_letter]
            if files:
                emoji = self._grade_emoji(grade_letter)
                lines.append(f"{emoji} Grade {grade_letter} ({len(files)} files):")
                for fp, result in files[:10]:  # Limit to 10 per grade
                    lines.append(f"    {result.coverage_percent:.1f}% - {Path(fp).name}")
                if len(files) > 10:
                    lines.append(f"    ... and {len(files) - 10} more")
                lines.append("")

        return {
            "format": "toon",
            "content": "\n".join(lines),
            "summary": {
                "coverage_percent": round(overall_coverage, 1),
                "grade": grade,
                "tested_elements": total_tested,
                "total_elements": total_elements,
                "untested_count": total_untested,
                "files_analyzed": len(results),
            },
        }

    def _format_project_json(
        self, results: dict[str, Any], include_tested: bool
    ) -> dict[str, Any]:
        """Format project results as JSON."""
        total_elements = sum(r.total_elements for r in results.values())
        total_tested = sum(r.tested_elements for r in results.values())

        overall_coverage = (
            (total_tested / total_elements * 100) if total_elements > 0 else 100.0
        )

        # Calculate grade
        if overall_coverage >= 80:
            grade = "A"
        elif overall_coverage >= 60:
            grade = "B"
        elif overall_coverage >= 40:
            grade = "C"
        elif overall_coverage >= 20:
            grade = "D"
        else:
            grade = "F"

        return {
            "summary": {
                "coverage_percent": round(overall_coverage, 1),
                "grade": grade,
                "tested_elements": total_tested,
                "total_elements": total_elements,
                "untested_count": sum(len(r.untested_elements) for r in results.values()),
                "files_analyzed": len(results),
            },
            "files": {
                fp: self._format_result_json(r, include_tested)
                for fp, r in results.items()
            },
        }

    def _element_emoji(self, element_type: str) -> str:
        """Get emoji for element type."""
        return {
            "function": "🔷",
            "class": "📦",
            "method": "⚙️",
        }.get(element_type, "📍")

    def _grade_emoji(self, grade: str) -> str:
        """Get emoji for grade."""
        return {
            "A": "🟢",
            "B": "🔵",
            "C": "🟡",
            "D": "🟠",
            "F": "🔴",
        }.get(grade, "⚪")
