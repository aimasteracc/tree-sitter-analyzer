#!/usr/bin/env python3
"""
Health Score Tool — MCP Tool

Analyzes source file health based on maintainability metrics.
Uses the HealthScorer analysis engine to grade files A-F.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...analysis.health_score import HealthScorer
from ...utils import setup_logger
from ..utils.error_handler import handle_mcp_errors
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class HealthScoreTool(BaseMCPTool):
    """
    MCP tool for analyzing source file health.

    Grades each file A-F based on size, complexity, coupling,
    and annotation density. Provides actionable suggestions
    for improvement.
    """

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "health_score",
            "description": (
                "Analyze source file health based on maintainability metrics. "
                "\n\n"
                "Grading Scale:\n"
                "- A (90-100): Excellent - well-structured, maintainable\n"
                "- B (75-89): Good - minor improvements needed\n"
                "- C (60-74): Fair - needs attention\n"
                "- D (40-59): Poor - significant issues\n"
                "- F (0-39): Critical - requires immediate refactoring\n"
                "\n"
                "Metrics Analyzed:\n"
                "- File size (lines of code)\n"
                "- Method count and complexity\n"
                "- Import coupling\n"
                "- Cyclomatic complexity\n"
                "- Average function length\n"
                "\n"
                "WHEN TO USE:\n"
                "- During code review to identify files needing attention\n"
                "- Before refactoring to prioritize which files to tackle first\n"
                "- To track code quality trends over time\n"
                "- As part of CI/CD quality gates\n"
                "\n"
                "WHEN NOT TO USE:\n"
                "- For syntax error detection (use analyze_code_structure instead)\n"
                "- For security vulnerability scanning (use security tools)"
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
                    "min_grade": {
                        "type": "string",
                        "enum": ["A", "B", "C", "D", "F"],
                        "description": (
                            "Minimum acceptable grade. "
                            "Files below this grade are flagged. Default: 'C'."
                        ),
                    },
                    "include_suggestions": {
                        "type": "boolean",
                        "description": (
                            "Include actionable suggestions for improvement. "
                            "Default: true."
                        ),
                    },
                },
                "examples": [
                    {"project_root": "/project"},
                    {"file_path": "src/main/java/com/example/Service.java"},
                    {"project_root": "/project", "min_grade": "B"},
                    {"file_path": "src/app.py", "include_suggestions": True},
                ],
                "additionalProperties": False,
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        file_path = arguments.get("file_path")
        if file_path is not None and not isinstance(file_path, str):
            raise ValueError("file_path must be a string")

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

        include_suggestions = arguments.get("include_suggestions")
        if include_suggestions is not None and not isinstance(include_suggestions, bool):
            raise ValueError("include_suggestions must be a boolean")

        return True

    @handle_mcp_errors("health_score")
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)

        file_path = arguments.get("file_path")
        project_root_arg = arguments.get("project_root")
        min_grade = arguments.get("min_grade", "C")
        include_suggestions = arguments.get("include_suggestions", True)

        # Determine project root
        root = project_root_arg or self.project_root or str(Path.cwd())

        # Validate file path if provided
        if file_path:
            resolved = self.resolve_and_validate_file_path(file_path)
            # Use parent as project root for single file analysis
            root = str(Path(resolved).parent)
            file_path = str(Path(resolved).relative_to(root))
        else:
            root = self.resolve_and_validate_directory_path(root)

        # Create scorer
        scorer = HealthScorer(root)

        # Run analysis
        if file_path:
            scores = [scorer.score_file(file_path)]
        else:
            scores = scorer.score_all()

        # Filter and format results
        grade_order = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
        min_threshold = grade_order.get(min_grade, 3)

        all_results: list[dict[str, Any]] = []
        below_threshold: list[dict[str, Any]] = []
        summary: dict[str, int] = {}
        total_score = 0

        for score in scores:
            score_grade = score.grade
            score_level = grade_order.get(score_grade, 0)

            result = {
                "file": score.file_path,
                "score": score.score,
                "grade": score_grade,
                "lines": score.lines,
                "methods": score.methods,
                "imports": score.imports,
                "complexity": score.cyclomatic_complexity,
                "avg_function_length": round(score.avg_function_length, 1),
            }

            if include_suggestions:
                result["suggestions"] = list(score.suggestions)

            all_results.append(result)
            summary[score_grade] = summary.get(score_grade, 0) + 1
            total_score += score.score

            if score_level < min_threshold:
                below_threshold.append(result)

        total = len(all_results)
        avg_score = round(total_score / total, 1) if total > 0 else 0

        response: dict[str, Any] = {
            "success": True,
            "total_files": total,
            "avg_score": avg_score,
            "grade_distribution": summary,
            "below_threshold": below_threshold,
            "files": all_results if file_path or len(all_results) <= 100 else [],
        }

        if below_threshold:
            response["warning"] = (
                f"Found {len(below_threshold)} files below {min_grade} grade. "
                "These files may need refactoring attention."
            )

        if total == 0:
            response["message"] = "No source files found to analyze."

        return response
