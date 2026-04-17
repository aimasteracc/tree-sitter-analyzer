#!/usr/bin/env python3
"""
CI Report Tool — MCP Tool

Generates CI/CD friendly analysis reports with pass/fail status.
Uses the CI report generation for quality gate enforcement.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...analysis.ci_report import generate_ci_report
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class CIReportTool(BaseMCPTool):
    """
    MCP tool for generating CI/CD friendly reports.

    Generates machine-readable reports suitable for CI/CD pipelines
    including exit codes, JSON output, and grade-based pass/fail
    thresholds.
    """

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "ci_report",
            "description": (
                "Generate CI/CD friendly analysis report with pass/fail status. "
                "\n\n"
                "Report includes:\n"
                "- Total files analyzed\n"
                "- Grade distribution (A-F)\n"
                "- Average health score\n"
                "- Dependency cycle count\n"
                "- Critical files list\n"
                "- Failed checks with pass/fail status\n"
                "\n"
                "Configurable Thresholds:\n"
                "- min_grade: Minimum acceptable grade (default: 'C')\n"
                "- max_cycles: Maximum allowed dependency cycles (default: 0)\n"
                "- max_critical: Maximum allowed critical files (default: 10)\n"
                "\n"
                "WHEN TO USE:\n"
                "- In CI/CD pipelines as quality gates\n"
                "- To enforce code quality standards\n"
                "- To track technical debt trends\n"
                "- For pre-commit quality checks\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For interactive analysis (use health_score instead)\n"
                "- For detailed file-by-file breakdown"
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project_root": {
                        "type": "string",
                        "description": (
                            "Project root directory to analyze. "
                            "Default: current project root."
                        ),
                    },
                    "min_grade": {
                        "type": "string",
                        "enum": ["A", "B", "C", "D", "F"],
                        "description": (
                            "Minimum acceptable grade. "
                            "Files below this grade trigger a failed check. Default: 'C'."
                        ),
                    },
                    "max_cycles": {
                        "type": "integer",
                        "description": (
                            "Maximum allowed dependency cycles. "
                            "Exceeding this triggers a failed check. Default: 0."
                        ),
                    },
                    "max_critical": {
                        "type": "integer",
                        "description": (
                            "Maximum allowed critical files (score < 25). "
                            "Exceeding this triggers a failed check. Default: 10."
                        ),
                    },
                    "output_format": {
                        "type": "string",
                        "enum": ["json", "summary"],
                        "description": (
                            "Output format. 'json' for machine-readable, "
                            "'summary' for human-readable. Default: 'summary'."
                        ),
                    },
                },
                "examples": [
                    {"project_root": "/project"},
                    {"project_root": "/project", "min_grade": "B"},
                    {"project_root": "/project", "max_cycles": 5, "max_critical": 5},
                    {"project_root": "/project", "output_format": "json"},
                ],
                "additionalProperties": False,
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        project_root = arguments.get("project_root")
        if project_root is not None and not isinstance(project_root, str):
            raise ValueError("project_root must be a string")

        min_grade = arguments.get("min_grade")
        if min_grade is not None:
            valid = {"A", "B", "C", "D", "F"}
            if min_grade not in valid:
                raise ValueError(
                    f"min_grade must be one of {valid}, got '{min_grade}'"
                )

        max_cycles = arguments.get("max_cycles")
        if max_cycles is not None:
            if not isinstance(max_cycles, int) or max_cycles < 0:
                raise ValueError("max_cycles must be a non-negative integer")

        max_critical = arguments.get("max_critical")
        if max_critical is not None:
            if not isinstance(max_critical, int) or max_critical < 0:
                raise ValueError("max_critical must be a non-negative integer")

        output_format = arguments.get("output_format")
        if output_format is not None:
            valid = {"json", "summary"}
            if output_format not in valid:
                raise ValueError(
                    f"output_format must be one of {valid}, got '{output_format}'"
                )

        return True

    @handle_mcp_errors("ci_report")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        project_root_arg = arguments.get("project_root")
        min_grade = arguments.get("min_grade", "C")
        max_cycles = arguments.get("max_cycles", 0)
        max_critical = arguments.get("max_critical", 10)
        output_format = arguments.get("output_format", "summary")

        # Determine project root
        root = project_root_arg or self.project_root or str(Path.cwd())
        root = self.resolve_and_validate_directory_path(root)

        # Generate CI report
        report = generate_ci_report(
            root,
            min_grade=min_grade,
            max_cycles=max_cycles,
            max_critical=max_critical,
        )

        # Format response
        if output_format == "json":
            return {
                "success": True,
                "format": "json",
                "data": report.to_json(),
                "passed": report.passed,
            }

        # Summary format
        response: dict[str, Any] = {
            "success": True,
            "passed": report.passed,
            "project_root": report.project_root,
            "total_files": report.total_files,
            "grade_distribution": report.grade_distribution,
            "avg_health_score": round(report.health_score_avg, 1),
            "cycle_count": report.cycle_count,
            "critical_files": list(report.critical_files),
            "failed_checks": list(report.failed_checks),
        }

        if not report.passed:
            response["error"] = (
                f"CI check failed with {len(report.failed_checks)} failed check(s). "
                "See failed_checks for details."
            )

        return response
