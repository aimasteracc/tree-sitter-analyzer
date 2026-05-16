#!/usr/bin/env python3
"""
Project Health MCP Tool

Bulk health scoring for an entire project in one call.
Returns grade distribution, F/D file list with recommendations, and top refactoring targets.
"""

from collections import Counter
from typing import Any

from ...health_scorer import DIMENSION_WEIGHTS, HealthScorer
from ...utils import setup_logger
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)

_SOURCE_EXTS = {
    ".py",
    ".java",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".go",
    ".rs",
    ".kt",
    ".cs",
    ".rb",
    ".php",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".sql",
    ".html",
    ".css",
    ".yaml",
    ".yml",
    ".md",
}

_EXCLUDE_DIRS = {
    "node_modules",
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    "egg-info",
    ".eggs",
    ".idea",
    ".vscode",
    "htmlcov",
    ".cache",
    ".claude",
    ".deepseek",
    ".autonomous-runtime",
}


class ProjectHealthTool(BaseMCPTool):
    """MCP Tool that scores every source file and returns a project health report."""

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "check_project_health",
            "description": (
                "Score ALL files: grade distribution (A-F), worst files, smells, "
                "top refactoring targets. First call on any project."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "min_grade": {
                    "type": "string",
                    "enum": ["A", "B", "C", "D", "F"],
                    "description": "Minimum grade to include in detail list (default: D — shows D and F)",
                    "default": "D",
                },
                "max_files": {
                    "type": "integer",
                    "description": "Max files to include in detail list (default: 20)",
                    "default": 20,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json", "toon"],
                    "description": "Output format: 'toon' (default, token-efficient) or 'json'",
                    "default": "toon",
                },
            },
            "additionalProperties": False,
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.validate_arguments(arguments)
        if not self.project_root:
            raise ValueError("Project root not set. Call set_project_path first.")

        root = self.project_root
        min_grade = arguments.get("min_grade", "D")
        max_files = arguments.get("max_files", 20)
        output_format = arguments.get("output_format", "toon")

        grade_order = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}
        min_rank = grade_order.get(min_grade, 3)

        scorer = HealthScorer()
        all_scores = scorer.score_project(root)

        # Grade distribution
        grade_counts = Counter(s.grade for s in all_scores)

        # Weakest dimension across project
        dim_avgs: dict[str, float] = {}
        for dim in DIMENSION_WEIGHTS:
            vals = [s.dimensions.get(dim, 0) for s in all_scores if dim in s.dimensions]
            dim_avgs[dim] = round(sum(vals) / len(vals), 1) if vals else 0.0

        # Filter to files at or below min_grade
        worst = [s for s in all_scores if grade_order.get(s.grade, 4) >= min_rank]
        worst.sort(key=lambda s: s.total)

        file_details = []
        for s in worst[:max_files]:
            file_details.append(
                {
                    "file": s.file_path,
                    "grade": s.grade,
                    "total_score": s.total,
                    "weakest_dimension": min(
                        s.dimensions, key=lambda k: s.dimensions[k]
                    )
                    if s.dimensions
                    else "",
                    "dimensions": s.dimensions,
                }
            )

        # Top refactoring targets: files with lowest total score
        top_targets = [
            {"file": s.file_path, "grade": s.grade, "score": s.total} for s in worst[:5]
        ]

        # Weakest dimension
        weakest_dim = min(dim_avgs, key=lambda k: dim_avgs[k]) if dim_avgs else ""

        result: dict[str, Any] = {
            "success": True,
            "project_root": root,
            "total_files": len(all_scores),
            "grade_distribution": {g: grade_counts.get(g, 0) for g in "ABCDF"},
            "average_dimensions": dim_avgs,
            "weakest_dimension": weakest_dim,
            "top_refactoring_targets": top_targets,
            "files": file_details,
            "recommendation": _build_project_recommendation(
                grade_counts, weakest_dim, len(all_scores)
            ),
        }

        from ..utils.format_helper import apply_toon_format_to_response

        return apply_toon_format_to_response(result, output_format)


_GRADE_RECOMMENDATIONS = {
    "F": "has critical issues — split or rewrite recommended",
    "D": "needs attention — refactor the weakest dimension first",
}


def _build_project_recommendation(
    grade_counts: Counter, weakest_dim: str, total: int
) -> str:
    f_count = grade_counts.get("F", 0)
    d_count = grade_counts.get("D", 0)

    if f_count > 0:
        return (
            f"{f_count} file(s) graded F and {d_count} graded D out of {total}. "
            f"Focus on F-grade files first — they have the worst code health. "
            f"Project-wide weakest dimension: '{weakest_dim}'."
        )

    if d_count > 0:
        return (
            f"{d_count} file(s) graded D out of {total}. "
            f"Improve the '{weakest_dim}' dimension for the biggest overall gain."
        )

    return f"All {total} files are grade C or better. Project health looks good."
