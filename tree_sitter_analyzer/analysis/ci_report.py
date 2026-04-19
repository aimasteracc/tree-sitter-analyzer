"""
CI integration interface for analysis results.

Generates machine-readable reports suitable for CI/CD pipelines:
exit codes, check-style JSON, SARIF-like health summaries, and
grade-based pass/fail thresholds.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from tree_sitter_analyzer.analysis.dependency_graph import DependencyGraphBuilder
from tree_sitter_analyzer.analysis.health_score import FileHealthScore, HealthScorer
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

@dataclass(frozen=True)
class CIReport:
    """CI-friendly analysis summary for a project."""

    project_root: str
    total_files: int
    grade_distribution: dict[str, int]
    health_score_avg: float
    cycle_count: int
    critical_files: tuple[str, ...]
    failed_checks: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return len(self.failed_checks) == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "project_root": self.project_root,
            "total_files": self.total_files,
            "grade_distribution": self.grade_distribution,
            "health_score_avg": round(self.health_score_avg, 1),
            "cycle_count": self.cycle_count,
            "critical_files": list(self.critical_files),
            "failed_checks": list(self.failed_checks),
            "passed": self.passed,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

def generate_ci_report(
    project_root: str,
    *,
    min_grade: str = "C",
    max_cycles: int = 0,
    max_critical: int = 10,
) -> CIReport:
    """Generate a CI report for the project.

    Args:
        project_root: path to the project root
        min_grade: minimum acceptable grade (A-F). Files below this trigger a failed check.
        max_cycles: maximum allowed dependency cycles. Exceeding triggers a failed check.
        max_critical: maximum allowed critical files (score < 25). Exceeding triggers a failed check.

    Returns:
        CIReport with pass/fail status and details
    """
    grade_order = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
    min_threshold = grade_order.get(min_grade.upper(), 3)

    # Health scores
    scorer = HealthScorer(project_root=project_root)
    scores = scorer.score_all()

    grade_dist: dict[str, int] = {}
    total_score = 0
    for s in scores:
        grade_dist[s.grade] = grade_dist.get(s.grade, 0) + 1
        total_score += s.score

    avg_score = total_score / len(scores) if scores else 0.0

    # Identify critical files (low health score)
    critical: list[str] = [
        s.file_path for s in scores if grade_order.get(s.grade, 0) <= 1
    ]

    # Dependency cycles
    builder = DependencyGraphBuilder(project_root=project_root)
    graph = builder.build()
    cycles = graph.find_cycles()

    # Check failures
    failed: list[str] = []
    for s in scores:
        if grade_order.get(s.grade, 0) < min_threshold:
            failed.append(f"health:{s.file_path}:{s.grade}")
            break  # one representative failure per category

    if len(cycles) > max_cycles:
        failed.append(f"cycles:{len(cycles)}:max_allowed={max_cycles}")

    if len(critical) > max_critical:
        failed.append(f"critical_files:{len(critical)}:max_allowed={max_critical}")

    return CIReport(
        project_root=project_root,
        total_files=len(scores),
        grade_distribution=grade_dist,
        health_score_avg=avg_score,
        cycle_count=len(cycles),
        critical_files=tuple(critical),
        failed_checks=tuple(failed),
    )

def health_score_to_sarif(
    scores: list[FileHealthScore],
    project_root: str,
) -> dict[str, object]:
    """Convert health scores to SARIF-like format for CI integrations.

    Returns a dict compatible with the SARIF (Static Analysis Results
    Interchange Format) v2.1 structure for health score findings.
    """
    grade_severity = {"A": "none", "B": "note", "C": "warning", "D": "error", "F": "error"}

    results: list[dict[str, object]] = []
    for s in scores:
        if s.grade in ("A", "B"):
            continue
        results.append({
            "ruleId": "health-score",
            "level": grade_severity.get(s.grade, "warning"),
            "message": {
                "text": (
                    f"{s.file_path}: grade {s.grade} (score {s.score}, "
                    f"CC={s.cyclomatic_complexity}, avg_fn_len={s.avg_function_length})"
                ),
            },
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": s.file_path},
                },
            }],
            "properties": {
                "score": s.score,
                "grade": s.grade,
                "lines": s.lines,
                "methods": s.methods,
                "imports": s.imports,
                "cyclomatic_complexity": s.cyclomatic_complexity,
            },
        })

    return {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/sarif-2.1/schema/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "tree-sitter-analyzer",
                    "rules": [{
                        "id": "health-score",
                        "shortDescription": {"text": "File health score grade"},
                    }],
                },
            },
            "results": results,
        }],
    }
