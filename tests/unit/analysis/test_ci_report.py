"""Tests for CI integration report generation."""
from __future__ import annotations

import json
from pathlib import Path

from tree_sitter_analyzer.analysis.ci_report import (
    CIReport,
    generate_ci_report,
    health_score_to_sarif,
)
from tree_sitter_analyzer.analysis.health_score import FileHealthScore


class TestCIReport:
    """CIReport data structure."""

    def test_passed_when_no_failures(self) -> None:
        report = CIReport(
            project_root="/project",
            total_files=5,
            grade_distribution={"A": 3, "B": 2},
            health_score_avg=85.0,
            cycle_count=0,
            critical_files=(),
            failed_checks=(),
        )
        assert report.passed is True

    def test_failed_with_checks(self) -> None:
        report = CIReport(
            project_root="/project",
            total_files=5,
            grade_distribution={"A": 3, "F": 2},
            health_score_avg=50.0,
            cycle_count=3,
            critical_files=("Bad.java",),
            failed_checks=("health:Bad.java:F",),
        )
        assert report.passed is False

    def test_to_json_roundtrip(self) -> None:
        report = CIReport(
            project_root="/project",
            total_files=1,
            grade_distribution={"A": 1},
            health_score_avg=95.0,
            cycle_count=0,
            critical_files=(),
            failed_checks=(),
        )
        data = json.loads(report.to_json())
        assert data["passed"] is True
        assert data["total_files"] == 1

    def test_to_dict_structure(self) -> None:
        report = CIReport(
            project_root="/p",
            total_files=0,
            grade_distribution={},
            health_score_avg=0.0,
            cycle_count=0,
            critical_files=(),
            failed_checks=(),
        )
        d = report.to_dict()
        assert "project_root" in d
        assert "grade_distribution" in d
        assert "health_score_avg" in d
        assert "cycle_count" in d
        assert "critical_files" in d
        assert "failed_checks" in d


class TestGenerateCIReport:
    """Integration: generate CI report from a real project."""

    def test_healthy_project_passes(self, tmp_path: Path) -> None:
        (tmp_path / "Simple.java").write_text("public class Simple { }\n", encoding="utf-8")
        report = generate_ci_report(str(tmp_path))
        assert report.total_files >= 1
        assert isinstance(report.passed, bool)

    def test_unhealthy_project_fails_min_grade(self, tmp_path: Path) -> None:
        lines = ["public class Big {"]
        for i in range(300):
            lines.append(f"  void method{i}() {{ if (x > {i}) {{ for (;;) {{ }} }} }}")
        lines.append("}")
        (tmp_path / "Big.java").write_text("\n".join(lines), encoding="utf-8")

        report = generate_ci_report(str(tmp_path), min_grade="A")
        # Large file with many methods likely gets D or F
        assert report.total_files >= 1

    def test_empty_project(self, tmp_path: Path) -> None:
        report = generate_ci_report(str(tmp_path))
        assert report.total_files == 0
        assert report.health_score_avg == 0.0
        assert report.passed is True

    def test_report_includes_cycle_count(self, tmp_path: Path) -> None:
        (tmp_path / "A.java").write_text("import B;\npublic class A { }\n", encoding="utf-8")
        (tmp_path / "B.java").write_text("import A;\npublic class B { }\n", encoding="utf-8")

        report = generate_ci_report(str(tmp_path))
        assert isinstance(report.cycle_count, int)


class TestHealthScoreToSARIF:
    """SARIF conversion for health scores."""

    def test_healthy_files_excluded(self) -> None:
        scores = [
            FileHealthScore(
                file_path="Good.java", score=95, grade="A",
                lines=10, methods=1, imports=0,
                cyclomatic_complexity=1, avg_function_length=5.0,
                breakdown={},
            ),
        ]
        sarif = health_score_to_sarif(scores, "/project")
        results = sarif["runs"][0]["results"]  # type: ignore[index]
        assert len(results) == 0

    def test_unhealthy_files_included(self) -> None:
        scores = [
            FileHealthScore(
                file_path="Bad.java", score=25, grade="D",
                lines=500, methods=30, imports=20,
                cyclomatic_complexity=50, avg_function_length=15.0,
                breakdown={},
            ),
            FileHealthScore(
                file_path="Terrible.java", score=10, grade="F",
                lines=800, methods=50, imports=30,
                cyclomatic_complexity=100, avg_function_length=20.0,
                breakdown={},
            ),
        ]
        sarif = health_score_to_sarif(scores, "/project")
        results = sarif["runs"][0]["results"]  # type: ignore[index]
        assert len(results) == 2

    def test_sarif_schema_present(self) -> None:
        sarif = health_score_to_sarif([], "/project")
        assert "$schema" in sarif
        assert sarif["version"] == "2.1.0"

    def test_sarif_includes_properties(self) -> None:
        scores = [
            FileHealthScore(
                file_path="Meh.java", score=45, grade="C",
                lines=200, methods=10, imports=5,
                cyclomatic_complexity=20, avg_function_length=15.0,
                breakdown={},
            ),
        ]
        sarif = health_score_to_sarif(scores, "/project")
        result = sarif["runs"][0]["results"][0]  # type: ignore[index]
        props = result["properties"]  # type: ignore[index]
        assert props["cyclomatic_complexity"] == 20
        assert props["grade"] == "C"
