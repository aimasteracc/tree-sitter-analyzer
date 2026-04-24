"""Tests for overview/reporter.py module."""
from __future__ import annotations

import json

import pytest

from tree_sitter_analyzer.overview.aggregator import OverviewReport
from tree_sitter_analyzer.overview.reporter import (
    OutputFormat,
    OverviewReporter,
    format_score_bar,
    generate_health_badge,
)


@pytest.fixture
def sample_report() -> OverviewReport:
    """Create a sample overview report for testing."""
    return OverviewReport(
        project_path="/test/project",
        dependency_graph={
            "node_count": 10,
            "edge_count": 15,
            "has_cycles": False,
        },
        health_scores={
            "file_count": 5,
            "avg_score": 75.5,
            "grade_distribution": {"A": 2, "B": 2, "C": 1},
            "top_risk_files": [
                {"path": "risk1.py", "score": 40, "grade": "D"},
                {"path": "risk2.py", "score": 35, "grade": "F"},
            ],
        },
        security_issues={
            "issue_count": 3,
            "severity_distribution": {"high": 1, "medium": 2},
        },
        design_patterns={
            "pattern_count": 5,
            "pattern_distribution": {"singleton": 2, "factory": 3},
        },
        dead_code={
            "unused_class_count": 1,
            "unused_function_count": 2,
            "unused_import_count": 3,
        },
        ownership={
            "file_count": 10,
            "top_owned_files": [
                {"path": "file1.py", "owner": "alice", "ownership_percentage": 80.0},
            ],
            "high_churn_files": [
                {"path": "churn1.py", "commit_count": 50},
            ],
        },
        blast_radius={
            "high_impact_symbols": [
                {"name": "ComplexClass", "file": "complex.py", "complexity": 100, "risk_level": "high"},
            ]
        },
        errors={},
    )


class TestOverviewReporter:
    """Tests for OverviewReporter class."""

    def test_init(self, sample_report: OverviewReport) -> None:
        """Test reporter initialization."""
        reporter = OverviewReporter(sample_report)
        assert reporter.report == sample_report

    def test_generate_markdown(self, sample_report: OverviewReport) -> None:
        """Test Markdown generation."""
        reporter = OverviewReporter(sample_report)
        markdown = reporter.generate_markdown()

        assert "# Project Overview Report" in markdown
        assert "/test/project" in markdown
        assert "## Summary" in markdown
        assert "## Health Analysis" in markdown
        assert "## Dependency Analysis" in markdown
        assert "## Security Analysis" in markdown

    def test_generate_json(self, sample_report: OverviewReport) -> None:
        """Test JSON generation."""
        reporter = OverviewReporter(sample_report)
        json_output = reporter.generate_json()

        data = json.loads(json_output)
        assert data["project_path"] == "/test/project"
        assert "dependency_graph" in data
        assert "health_scores" in data

    def test_generate_toon(self, sample_report: OverviewReport) -> None:
        """Test TOON generation."""
        reporter = OverviewReporter(sample_report)
        toon = reporter.generate_toon()

        assert isinstance(toon, str)
        assert len(toon) > 0
        # TOON should be more compact than JSON
        json_data = json.loads(reporter.generate_json())
        assert len(toon) < len(json.dumps(json_data))

    def test_markdown_health_section(self, sample_report: OverviewReport) -> None:
        """Test health section in Markdown."""
        reporter = OverviewReporter(sample_report)
        markdown = reporter.generate_markdown()

        assert "75.5" in markdown
        assert "A: 2" in markdown or "A | 2" in markdown
        assert "risk1.py" in markdown
        assert "risk2.py" in markdown

    def test_markdown_dependency_section(self, sample_report: OverviewReport) -> None:
        """Test dependency section in Markdown."""
        reporter = OverviewReporter(sample_report)
        markdown = reporter.generate_markdown()

        assert "10" in markdown
        assert "15" in markdown
        assert "No Cycles" in markdown

    def test_markdown_security_section(self, sample_report: OverviewReport) -> None:
        """Test security section in Markdown."""
        reporter = OverviewReporter(sample_report)
        markdown = reporter.generate_markdown()

        assert "3" in markdown
        assert "high" in markdown.lower() or "High" in markdown
        assert "medium" in markdown.lower() or "Medium" in markdown

    def test_markdown_patterns_section(self, sample_report: OverviewReport) -> None:
        """Test design patterns section in Markdown."""
        reporter = OverviewReporter(sample_report)
        markdown = reporter.generate_markdown()

        assert "5" in markdown
        assert "singleton" in markdown.lower()
        assert "factory" in markdown.lower()

    def test_markdown_dead_code_section(self, sample_report: OverviewReport) -> None:
        """Test dead code section in Markdown."""
        reporter = OverviewReporter(sample_report)
        markdown = reporter.generate_markdown()

        assert "1" in markdown  # unused classes
        assert "2" in markdown  # unused functions
        assert "3" in markdown  # unused imports

    def test_markdown_ownership_section(self, sample_report: OverviewReport) -> None:
        """Test ownership section in Markdown."""
        reporter = OverviewReporter(sample_report)
        markdown = reporter.generate_markdown()

        assert "file1.py" in markdown
        assert "alice" in markdown
        assert "churn1.py" in markdown
        assert "50" in markdown

    def test_markdown_blast_section(self, sample_report: OverviewReport) -> None:
        """Test blast radius section in Markdown."""
        reporter = OverviewReporter(sample_report)
        markdown = reporter.generate_markdown()

        assert "ComplexClass" in markdown
        assert "complex.py" in markdown
        assert "high" in markdown.lower()

    def test_empty_report(self) -> None:
        """Test reporter with minimal data."""
        report = OverviewReport(project_path="/empty", errors={})
        reporter = OverviewReporter(report)
        markdown = reporter.generate_markdown()

        assert "# Project Overview Report" in markdown
        assert "/empty" in markdown

    def test_report_with_errors(self) -> None:
        """Test reporter includes errors."""
        report = OverviewReport(
            project_path="/test",
            errors={"security_scan": "Tool not found"},
        )
        reporter = OverviewReporter(report)
        markdown = reporter.generate_markdown()

        assert "## Errors" in markdown
        assert "security_scan" in markdown
        assert "Tool not found" in markdown

    def test_sections_ordering(self, sample_report: OverviewReport) -> None:
        """Test that sections appear in correct order."""
        reporter = OverviewReporter(sample_report)
        markdown = reporter.generate_markdown()

        # Find section positions
        sections = {
            "Summary": markdown.find("## Summary"),
            "Health Analysis": markdown.find("## Health Analysis"),
            "Dependency Analysis": markdown.find("## Dependency Analysis"),
            "Security Analysis": markdown.find("## Security Analysis"),
        }

        # Verify ordering (all should be found and in increasing order)
        assert all(pos >= 0 for pos in sections.values())

        order = sorted(sections.items(), key=lambda x: x[1])
        assert order[0][0] == "Summary"
        assert order[1][0] == "Health Analysis"

    def test_markdown_contains_tables(self, sample_report: OverviewReport) -> None:
        """Test that Markdown contains proper table formatting."""
        reporter = OverviewReporter(sample_report)
        markdown = reporter.generate_markdown()

        assert "|" in markdown  # Table delimiter
        assert "---" in markdown  # Table header separator

    def test_json_serializable(self, sample_report: OverviewReport) -> None:
        """Test that JSON output is properly serializable."""
        reporter = OverviewReporter(sample_report)
        json_output = reporter.generate_json()

        # Should not raise exception
        data = json.loads(json_output)
        assert isinstance(data, dict)

    def test_toon_output_structure(self, sample_report: OverviewReport) -> None:
        """Test TOON output structure."""
        reporter = OverviewReporter(sample_report)
        toon = reporter.generate_toon()

        # TOON should be valid string
        assert isinstance(toon, str)
        # Should not be empty
        assert len(toon) > 10


class TestOutputFormat:
    """Tests for OutputFormat enum."""

    def test_format_values(self) -> None:
        """Test OutputFormat enum values."""
        assert OutputFormat.MARKDOWN.value == "markdown"
        assert OutputFormat.JSON.value == "json"
        assert OutputFormat.TOON.value == "toon"


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_format_score_bar_full(self) -> None:
        """Test score bar at full value."""
        bar = format_score_bar(100, 100)
        assert len(bar) == 20
        assert "█" * 20 in bar or bar == "█" * 20

    def test_format_score_bar_half(self) -> None:
        """Test score bar at half value."""
        bar = format_score_bar(50, 100)
        assert len(bar) == 20
        # Should have half filled
        assert bar.count("█") == 10

    def test_format_score_bar_zero(self) -> None:
        """Test score bar at zero."""
        bar = format_score_bar(0, 100)
        assert len(bar) == 20
        assert bar == "░" * 20

    def test_generate_health_badge_a(self) -> None:
        """Test health badge for A grade."""
        badge = generate_health_badge("A")
        assert "🟢" in badge
        assert "A" in badge

    def test_generate_health_badge_b(self) -> None:
        """Test health badge for B grade."""
        badge = generate_health_badge("B")
        assert "🟢" in badge
        assert "B" in badge

    def test_generate_health_badge_c(self) -> None:
        """Test health badge for C grade."""
        badge = generate_health_badge("C")
        assert "🟡" in badge
        assert "C" in badge

    def test_generate_health_badge_d(self) -> None:
        """Test health badge for D grade."""
        badge = generate_health_badge("D")
        assert "🟠" in badge
        assert "D" in badge

    def test_generate_health_badge_f(self) -> None:
        """Test health badge for F grade."""
        badge = generate_health_badge("F")
        assert "🔴" in badge
        assert "F" in badge

    def test_generate_health_badge_invalid(self) -> None:
        """Test health badge for invalid grade."""
        badge = generate_health_badge("Z")
        assert "⚪" in badge
        assert "Z" in badge

    def test_format_score_bar_custom_max(self) -> None:
        """Test score bar with custom max value."""
        bar = format_score_bar(5, 10)
        assert len(bar) == 20
        # 5/10 = 50%, so 10 filled
        assert bar.count("█") == 10
