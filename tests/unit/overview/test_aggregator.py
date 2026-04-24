"""Tests for overview/aggregator.py module."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.overview.aggregator import (
    AnalysisResult,
    OverviewAggregator,
    OverviewReport,
)


@pytest.fixture
def sample_project(tmp_path: Path) -> Path:
    """Create a sample project with test files."""
    (tmp_path / "test.py").write_text("""
def hello():
    print("Hello, world!")

class Foo:
    def method(self):
        pass
""")
    (tmp_path / "test.js").write_text("""
function hello() {
    console.log("Hello");
}
""")
    return tmp_path


class TestOverviewReport:
    """Tests for OverviewReport dataclass."""

    def test_to_dict(self) -> None:
        """Test converting report to dictionary."""
        report = OverviewReport(
            project_path="/test",
            dependency_graph={"node_count": 10},
            health_scores={"avg_score": 80},
            errors={},
        )

        result = report.to_dict()

        assert result["project_path"] == "/test"
        assert result["dependency_graph"]["node_count"] == 10
        assert result["health_scores"]["avg_score"] == 80
        assert result["errors"] == {}

    def test_to_dict_with_errors(self) -> None:
        """Test converting report with errors to dictionary."""
        report = OverviewReport(
            project_path="/test",
            dependency_graph=None,
            errors={"security_scan": "Tool not found"},
        )

        result = report.to_dict()

        assert result["dependency_graph"] is None
        assert result["errors"]["security_scan"] == "Tool not found"


class TestAnalysisResult:
    """Tests for AnalysisResult dataclass."""

    def test_success_result(self) -> None:
        """Test successful analysis result."""
        result = AnalysisResult(
            name="health_score",
            success=True,
            data={"avg_score": 80},
        )

        assert result.name == "health_score"
        assert result.success is True
        assert result.data is not None
        assert result.error is None

    def test_failure_result(self) -> None:
        """Test failed analysis result."""
        result = AnalysisResult(
            name="security_scan",
            success=False,
            error="Tool not found",
        )

        assert result.name == "security_scan"
        assert result.success is False
        assert result.data is None
        assert result.error == "Tool not found"


class TestOverviewAggregator:
    """Tests for OverviewAggregator class."""

    def test_init(self, sample_project: Path) -> None:
        """Test aggregator initialization."""
        aggregator = OverviewAggregator(sample_project)

        assert aggregator.project_path == sample_project.resolve()
        assert aggregator.parallel is True

    def test_init_sequential(self, sample_project: Path) -> None:
        """Test aggregator with sequential execution."""
        aggregator = OverviewAggregator(sample_project, parallel=False)

        assert aggregator.parallel is False

    def test_generate_overview_returns_report(self, sample_project: Path) -> None:
        """Test generating overview returns OverviewReport."""
        with patch("tree_sitter_analyzer.overview.aggregator.GitAnalyzer"):
            aggregator = OverviewAggregator(sample_project, parallel=False)
            report = aggregator.generate_overview()

            assert isinstance(report, OverviewReport)
            assert report.project_path == str(sample_project.resolve())

    def test_generate_overview_include_specific(self, sample_project: Path) -> None:
        """Test generating overview with specific analyses only."""
        aggregator = OverviewAggregator(sample_project, parallel=False)

        # Mock the _safe_run method to return ownership data
        original_safe_run = aggregator._safe_run

        def mock_safe_run(analysis: Any) -> AnalysisResult:
            if analysis.__name__ == "_run_ownership_analysis":
                return AnalysisResult(
                    name="ownership",
                    success=True,
                    data={"file_count": 10},
                )
            return original_safe_run(analysis)

        with patch.object(aggregator, "_safe_run", side_effect=mock_safe_run):
            report = aggregator.generate_overview(include=["ownership"])

            # Should have ownership data
            assert report.ownership is not None

    def test_safe_run_success(self, sample_project: Path) -> None:
        """Test _safe_run with successful execution."""
        aggregator = OverviewAggregator(sample_project)

        def mock_analysis() -> dict[str, int]:
            return {"count": 42}

        result = aggregator._safe_run(mock_analysis)

        assert result.success is True
        assert result.data == {"count": 42}
        assert result.error is None

    def test_safe_run_file_not_found(self, sample_project: Path) -> None:
        """Test _safe_run with FileNotFoundError."""
        aggregator = OverviewAggregator(sample_project)

        def mock_analysis() -> dict[str, int]:
            raise FileNotFoundError("Not found")

        result = aggregator._safe_run(mock_analysis)

        assert result.success is False
        assert result.error is not None
        assert "File not found" in result.error

    def test_safe_run_value_error(self, sample_project: Path) -> None:
        """Test _safe_run with ValueError."""
        aggregator = OverviewAggregator(sample_project)

        def mock_analysis() -> dict[str, int]:
            raise ValueError("Invalid value")

        result = aggregator._safe_run(mock_analysis)

        assert result.success is False
        assert result.error is not None
        assert "Invalid input" in result.error

    def test_safe_run_generic_exception(self, sample_project: Path) -> None:
        """Test _safe_run with generic exception."""
        aggregator = OverviewAggregator(sample_project)

        def mock_analysis() -> dict[str, int]:
            raise RuntimeError("Unexpected error")

        result = aggregator._safe_run(mock_analysis)

        assert result.success is False
        assert result.error is not None
        assert "RuntimeError" in result.error

    def test_build_report(self, sample_project: Path) -> None:
        """Test _build_report method."""
        aggregator = OverviewAggregator(sample_project)

        results = [
            AnalysisResult(
                name="health_score",
                success=True,
                data={"avg_score": 80},
            ),
            AnalysisResult(
                name="security_scan",
                success=False,
                error="Tool not found",
            ),
        ]

        report = aggregator._build_report(results)

        assert report.health_scores == {"avg_score": 80}
        assert report.errors["security_scan"] == "Tool not found"

    def test_run_sequential(self, sample_project: Path) -> None:
        """Test sequential execution."""
        aggregator = OverviewAggregator(sample_project, parallel=False)

        def mock_analysis_1() -> dict[str, int]:
            return {"count": 1}

        def mock_analysis_2() -> dict[str, int]:
            return {"count": 2}

        analyses = [mock_analysis_1, mock_analysis_2]
        results = aggregator._run_sequential(analyses)

        assert len(results) == 2
        assert results[0].data == {"count": 1}
        assert results[1].data == {"count": 2}

    def test_overview_report_fields(self) -> None:
        """Test that OverviewReport has expected fields."""
        report = OverviewReport(project_path="/test")

        assert report.project_path == "/test"
        assert report.dependency_graph is None
        assert report.errors == {}

    def test_overview_report_to_dict_includes_all_fields(self) -> None:
        """Test that to_dict includes all analysis fields."""
        report = OverviewReport(
            project_path="/test",
            dependency_graph={"nodes": 10},
            health_scores={"avg": 80},
            design_patterns={"patterns": 5},
            security_issues={"issues": 0},
            dead_code={"dead": 0},
            ownership={"owners": 5},
            blast_radius={"radius": 10},
            errors={},
        )

        result = report.to_dict()

        assert "dependency_graph" in result
        assert "health_scores" in result
        assert "design_patterns" in result
        assert "security_issues" in result
        assert "dead_code" in result
        assert "ownership" in result
        assert "blast_radius" in result
        assert "errors" in result

    def test_analysis_result_name_extraction(self) -> None:
        """Test that analysis name is correctly extracted."""
        result = AnalysisResult(
            name="test_analysis",
            success=True,
        )

        assert result.name == "test_analysis"

    def test_parallel_execution_with_timeout(self, sample_project: Path) -> None:
        """Test parallel execution with timeout handling."""
        with patch("tree_sitter_analyzer.overview.aggregator.GitAnalyzer"):
            aggregator = OverviewAggregator(sample_project, parallel=True)
            report = aggregator.generate_overview()

            assert isinstance(report, OverviewReport)

    def test_empty_project(self, tmp_path: Path) -> None:
        """Test handling of empty project directory."""
        with patch("tree_sitter_analyzer.overview.aggregator.GitAnalyzer"):
            aggregator = OverviewAggregator(tmp_path)
            report = aggregator.generate_overview()

            assert isinstance(report, OverviewReport)

    def test_partial_failure_isolation(self, sample_project: Path) -> None:
        """Test that failures in one analysis don't affect others."""
        with patch(
            "tree_sitter_analyzer.overview.aggregator.DependencyGraphBuilder",
            side_effect=Exception("Dependency analysis failed"),
        ), patch("tree_sitter_analyzer.overview.aggregator.GitAnalyzer"):
            aggregator = OverviewAggregator(sample_project, parallel=False)
            report = aggregator.generate_overview()

            # Should have errors for failed analysis
            assert "dependency_graph" in report.errors or len(report.errors) > 0

    def test_error_accumulation(self, sample_project: Path) -> None:
        """Test that multiple errors are accumulated correctly."""
        aggregator = OverviewAggregator(sample_project)

        results = [
            AnalysisResult(
                name="analysis1",
                success=False,
                error="Error 1",
            ),
            AnalysisResult(
                name="analysis2",
                success=False,
                error="Error 2",
            ),
        ]

        report = aggregator._build_report(results)

        assert len(report.errors) == 2
        assert "Error 1" in report.errors.values()
        assert "Error 2" in report.errors.values()

    def test_successful_analysis_data_included(self, sample_project: Path) -> None:
        """Test that successful analysis data is included in report."""
        aggregator = OverviewAggregator(sample_project)

        results = [
            AnalysisResult(
                name="health_score",
                success=True,
                data={"avg_score": 85},
            ),
        ]

        report = aggregator._build_report(results)

        assert report.health_scores == {"avg_score": 85}
