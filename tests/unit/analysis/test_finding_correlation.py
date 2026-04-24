"""Tests for Cross-Analyzer Finding Correlation Engine."""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from tree_sitter_analyzer.analysis.finding_correlation import (
    FindingCorrelator,
    HotspotPattern,
    Severity,
    UnifiedFinding,
    _get_end_line,
    _get_line,
    _get_message,
    _get_name,
    _get_severity,
    normalize_findings,
)

# ── Fixtures: mock analyzer results ─────────────────────────────────


@dataclass
class MockFinding:
    """Mimics a typical analyzer finding with severity + line."""

    line: int
    severity: str
    name: str
    message: str


@dataclass
class MockResult:
    """Mimics a typical analyzer result with issues collection."""

    file_path: str
    issues: list[MockFinding]


@dataclass
class MockFindingAlt:
    """Mimics an analyzer finding using line_number instead of line."""

    line_number: int
    severity: str
    function_name: str
    description: str


@dataclass
class MockResultAlt:
    """Result with findings instead of issues."""

    findings: list[MockFindingAlt]


@dataclass
class MockRatingFinding:
    """Analyzer that uses rating instead of severity."""

    start_line: int
    end_line: int
    rating: str
    name: str


@dataclass
class MockRatingResult:
    items: list[MockRatingFinding]


def _make_finding(
    line: int = 10,
    severity: str = "medium",
    name: str = "foo",
    message: str = "issue found",
) -> MockFinding:
    return MockFinding(line=line, severity=severity, name=name, message=message)


def _make_unified(
    file_path: str = "test.py",
    line: int = 10,
    analyzer_name: str = "test_analyzer",
    severity: Severity = Severity.MEDIUM,
) -> UnifiedFinding:
    return UnifiedFinding(
        file_path=file_path,
        line=line,
        end_line=line,
        element_name="fn",
        severity=severity,
        analyzer_name=analyzer_name,
        finding_type="MockFinding",
        message="test",
    )


# ── Severity normalization ──────────────────────────────────────────


class TestSeverityNormalization:
    def test_standard_levels(self) -> None:
        assert _get_severity(MockFinding(1, "critical", "", "")) == Severity.CRITICAL
        assert _get_severity(MockFinding(1, "high", "", "")) == Severity.HIGH
        assert _get_severity(MockFinding(1, "medium", "", "")) == Severity.MEDIUM
        assert _get_severity(MockFinding(1, "low", "", "")) == Severity.LOW
        assert _get_severity(MockFinding(1, "info", "", "")) == Severity.INFO

    def test_warning_maps_to_high(self) -> None:
        assert _get_severity(MockFinding(1, "warning", "", "")) == Severity.HIGH

    def test_error_maps_to_critical(self) -> None:
        assert _get_severity(MockFinding(1, "error", "", "")) == Severity.CRITICAL

    def test_ok_maps_to_info(self) -> None:
        assert _get_severity(MockFinding(1, "ok", "", "")) == Severity.INFO

    def test_unknown_maps_to_info(self) -> None:
        assert _get_severity(MockFinding(1, "bizarre", "", "")) == Severity.INFO

    def test_rating_good(self) -> None:
        f = MockRatingFinding(1, 1, "good", "fn")
        assert _get_severity(f) == Severity.INFO

    def test_rating_warning(self) -> None:
        f = MockRatingFinding(1, 1, "warning", "fn")
        assert _get_severity(f) == Severity.HIGH

    def test_rating_critical(self) -> None:
        f = MockRatingFinding(1, 1, "critical", "fn")
        assert _get_severity(f) == Severity.CRITICAL

    def test_no_severity_field(self) -> None:
        @dataclass
        class NoSeverity:
            line: int = 1

        assert _get_severity(NoSeverity()) == Severity.INFO


# ── Line extraction ─────────────────────────────────────────────────


class TestLineExtraction:
    def test_line_field(self) -> None:
        assert _get_line(MockFinding(42, "high", "", "")) == 42

    def test_line_number_field(self) -> None:
        f = MockFindingAlt(99, "low", "fn", "desc")
        assert _get_line(f) == 99

    def test_start_line_field(self) -> None:
        f = MockRatingFinding(55, 60, "good", "fn")
        assert _get_line(f) == 55

    def test_no_line_field(self) -> None:
        @dataclass
        class NoLine:
            severity: str = "low"

        assert _get_line(NoLine()) == 0


class TestEndLine:
    def test_end_line_field(self) -> None:
        f = MockRatingFinding(10, 20, "good", "fn")
        assert _get_end_line(f, 10) == 20

    def test_fallback_to_start(self) -> None:
        f = MockFinding(42, "high", "", "")
        assert _get_end_line(f, 42) == 42


# ── Name extraction ─────────────────────────────────────────────────


class TestNameExtraction:
    def test_name_field(self) -> None:
        assert _get_name(MockFinding(1, "low", "my_func", "")) == "my_func"

    def test_function_name_field(self) -> None:
        f = MockFindingAlt(1, "low", "handler", "desc")
        assert _get_name(f) == "handler"

    def test_empty_name(self) -> None:
        @dataclass
        class NoName:
            line: int = 1
            severity: str = "low"

        assert _get_name(NoName()) == ""


# ── Message extraction ──────────────────────────────────────────────


class TestMessageExtraction:
    def test_message_field(self) -> None:
        assert _get_message(MockFinding(1, "low", "", "bad code")) == "bad code"

    def test_description_field(self) -> None:
        f = MockFindingAlt(1, "low", "fn", "something wrong")
        assert _get_message(f) == "something wrong"

    def test_fallback_to_type_and_name(self) -> None:
        @dataclass
        class BareItem:
            line: int = 1
            severity: str = "low"
            name: str = "target"

        assert _get_message(BareItem()) == "BareItem: target"


# ── normalize_findings ──────────────────────────────────────────────


class TestNormalizeFindings:
    def test_extracts_from_issues(self) -> None:
        result = MockResult(
            file_path="a.py",
            issues=[
                MockFinding(10, "high", "fn1", "bug"),
                MockFinding(20, "low", "fn2", "smell"),
            ],
        )
        findings = normalize_findings("test", result, "a.py")
        assert len(findings) == 2
        assert findings[0].line == 10
        assert findings[0].severity == Severity.HIGH
        assert findings[0].analyzer_name == "test"

    def test_extracts_from_findings(self) -> None:
        result = MockResultAlt(
            findings=[MockFindingAlt(5, "medium", "fn", "issue")],
        )
        findings = normalize_findings("alt", result, "b.py")
        assert len(findings) == 1
        assert findings[0].line == 5

    def test_extracts_from_items(self) -> None:
        result = MockRatingResult(
            items=[MockRatingFinding(30, 35, "warning", "fn")],
        )
        findings = normalize_findings("rating", result, "c.py")
        assert len(findings) == 1
        assert findings[0].line == 30
        assert findings[0].end_line == 35
        assert findings[0].severity == Severity.HIGH

    def test_skips_zero_line(self) -> None:
        result = MockResult(
            file_path="a.py",
            issues=[MockFinding(0, "high", "fn", "bug")],
        )
        findings = normalize_findings("test", result, "a.py")
        assert len(findings) == 0

    def test_empty_result(self) -> None:
        result = MockResult(file_path="a.py", issues=[])
        findings = normalize_findings("test", result, "a.py")
        assert len(findings) == 0


# ── FindingCorrelator ───────────────────────────────────────────────


class TestFindingCorrelator:
    def test_empty_correlation(self) -> None:
        corr = FindingCorrelator()
        result = corr.correlate()
        assert result.total_findings == 0
        assert len(result.hotspots) == 0
        assert len(result.analyzers_used) == 0

    def test_single_analyzer_no_hotspot(self) -> None:
        corr = FindingCorrelator()
        corr.add_unified([_make_unified(analyzer_name="a1")])
        result = corr.correlate()
        assert len(result.hotspots) == 0

    def test_two_analyvers_same_location(self) -> None:
        corr = FindingCorrelator()
        corr.add_unified([
            _make_unified(line=10, analyzer_name="a1"),
            _make_unified(line=10, analyzer_name="a2"),
        ])
        result = corr.correlate()
        assert len(result.hotspots) == 1
        assert result.hotspots[0].analyzer_count == 2
        assert len(result.warning_hotspots) == 1
        assert len(result.critical_hotspots) == 0

    def test_three_analyzers_critical_hotspot(self) -> None:
        corr = FindingCorrelator()
        corr.add_unified([
            _make_unified(line=10, analyzer_name="a1"),
            _make_unified(line=10, analyzer_name="a2"),
            _make_unified(line=10, analyzer_name="a3"),
        ])
        result = corr.correlate()
        assert len(result.hotspots) == 1
        assert result.hotspots[0].analyzer_count == 3
        assert len(result.critical_hotspots) == 1

    def test_proximity_grouping(self) -> None:
        corr = FindingCorrelator(line_proximity=5)
        corr.add_unified([
            _make_unified(line=11, analyzer_name="a1"),
            _make_unified(line=13, analyzer_name="a2"),
        ])
        result = corr.correlate()
        assert len(result.hotspots) == 1

    def test_different_files_no_correlation(self) -> None:
        corr = FindingCorrelator()
        corr.add_unified([
            _make_unified(file_path="a.py", line=10, analyzer_name="a1"),
            _make_unified(file_path="b.py", line=10, analyzer_name="a2"),
        ])
        result = corr.correlate()
        assert len(result.hotspots) == 0

    def test_sorted_by_analyzer_count(self) -> None:
        corr = FindingCorrelator()
        corr.add_unified([
            _make_unified(line=10, analyzer_name="a1"),
            _make_unified(line=10, analyzer_name="a2"),
            _make_unified(line=50, analyzer_name="a1"),
            _make_unified(line=50, analyzer_name="a2"),
            _make_unified(line=50, analyzer_name="a3"),
        ])
        result = corr.correlate()
        assert len(result.hotspots) == 2
        assert result.hotspots[0].analyzer_count == 3
        assert result.hotspots[1].analyzer_count == 2

    def test_add_findings_method(self) -> None:
        result = MockResult(
            file_path="test.py",
            issues=[
                MockFinding(10, "high", "fn", "bug"),
                MockFinding(10, "medium", "fn", "smell"),
            ],
        )
        corr = FindingCorrelator()
        corr.add_findings("mock_a", result, "test.py")
        corr.add_findings("mock_b", result, "test.py")
        correlated = corr.correlate()
        assert correlated.total_findings == 4
        assert "mock_a" in correlated.analyzers_used
        assert "mock_b" in correlated.analyzers_used


# ── CorrelationResult ───────────────────────────────────────────────


class TestCorrelationResult:
    def test_to_dict(self) -> None:
        corr = FindingCorrelator()
        corr.add_unified([
            _make_unified(line=10, analyzer_name="a1"),
            _make_unified(line=10, analyzer_name="a2"),
        ])
        result = corr.correlate()
        d = result.to_dict()
        assert d["total_findings"] == 2
        assert d["hotspot_count"] == 1
        assert d["critical_count"] == 0
        assert d["warning_count"] == 1

    def test_total_files(self) -> None:
        corr = FindingCorrelator()
        corr.add_unified([
            _make_unified(file_path="a.py", analyzer_name="a1"),
            _make_unified(file_path="b.py", analyzer_name="a2"),
        ])
        result = corr.correlate()
        assert result.total_files == 2


# ── Hotspot properties ──────────────────────────────────────────────


class TestHotspotProperties:
    def test_max_severity(self) -> None:
        corr = FindingCorrelator()
        corr.add_unified([
            _make_unified(line=10, analyzer_name="a1", severity=Severity.LOW),
            _make_unified(line=10, analyzer_name="a2", severity=Severity.CRITICAL),
        ])
        result = corr.correlate()
        assert result.hotspots[0].max_severity == Severity.CRITICAL

    def test_analyzer_names_sorted(self) -> None:
        corr = FindingCorrelator()
        corr.add_unified([
            _make_unified(line=10, analyzer_name="zebra"),
            _make_unified(line=10, analyzer_name="alpha"),
        ])
        result = corr.correlate()
        assert result.hotspots[0].analyzer_names == ["alpha", "zebra"]

    def test_finding_types(self) -> None:
        corr = FindingCorrelator()
        corr.add_unified([
            _make_unified(line=10, analyzer_name="a1"),
            _make_unified(line=10, analyzer_name="a2"),
        ])
        result = corr.correlate()
        # Both have same finding_type since they use _make_unified
        assert len(result.hotspots[0].finding_types) == 1


# ── UnifiedFinding ──────────────────────────────────────────────────


class TestUnifiedFinding:
    def test_location_key(self) -> None:
        f = _make_unified(file_path="a.py", line=42)
        assert f.location_key == ("a.py", 42)

    def test_frozen(self) -> None:
        f = _make_unified()
        with pytest.raises(AttributeError):
            f.line = 99  # type: ignore[misc]


# ── Priority Score ──────────────────────────────────────────────────


class TestPriorityScore:
    def test_basic_priority(self) -> None:
        corr = FindingCorrelator()
        corr.add_unified([
            _make_unified(line=10, analyzer_name="a1", severity=Severity.MEDIUM),
            _make_unified(line=10, analyzer_name="a2", severity=Severity.MEDIUM),
        ])
        result = corr.correlate()
        h = result.hotspots[0]
        # 2 analyzers * severity_weight(MEDIUM=2) = 4
        assert h.priority_score == 4

    def test_critical_higher_priority(self) -> None:
        corr = FindingCorrelator()
        corr.add_unified([
            _make_unified(line=10, analyzer_name="a1", severity=Severity.CRITICAL),
            _make_unified(line=10, analyzer_name="a2", severity=Severity.CRITICAL),
        ])
        result = corr.correlate()
        # 2 * 4 = 8
        assert result.hotspots[0].priority_score == 8

    def test_density_bonus(self) -> None:
        corr = FindingCorrelator()
        corr.add_unified([
            _make_unified(line=10, analyzer_name="a1", severity=Severity.MEDIUM),
            _make_unified(line=10, analyzer_name="a2", severity=Severity.MEDIUM),
            _make_unified(line=10, analyzer_name="a2", severity=Severity.HIGH),
        ])
        result = corr.correlate()
        h = result.hotspots[0]
        # 2 analyzers, max_severity = HIGH(3), density = 3-2 = 1
        # score = 2 * 3 + 1 = 7
        assert h.priority_score == 7

    def test_sorted_by_priority(self) -> None:
        corr = FindingCorrelator()
        corr.add_unified([
            _make_unified(line=10, analyzer_name="a1", severity=Severity.LOW),
            _make_unified(line=10, analyzer_name="a2", severity=Severity.LOW),
            _make_unified(line=50, analyzer_name="a1", severity=Severity.CRITICAL),
            _make_unified(line=50, analyzer_name="a2", severity=Severity.CRITICAL),
        ])
        result = corr.correlate()
        # L50: 2*4=8, L10: 2*1=2
        assert result.hotspots[0].line == 50
        assert result.hotspots[1].line == 10


# ── Pattern Detection ──────────────────────────────────────────────


class TestPatternDetection:
    def test_complexity_cluster(self) -> None:
        corr = FindingCorrelator()
        corr.add_unified([
            _make_unified(line=10, analyzer_name="cognitive_complexity"),
            _make_unified(line=10, analyzer_name="boolean_complexity"),
        ])
        result = corr.correlate()
        assert result.hotspots[0].pattern == HotspotPattern.COMPLEXITY_CLUSTER

    def test_dead_code_cluster(self) -> None:
        corr = FindingCorrelator()
        corr.add_unified([
            _make_unified(line=10, analyzer_name="dead_store"),
            _make_unified(line=10, analyzer_name="dead_code_path"),
        ])
        result = corr.correlate()
        assert result.hotspots[0].pattern == HotspotPattern.DEAD_CODE_CLUSTER

    def test_risk_cluster(self) -> None:
        corr = FindingCorrelator()
        corr.add_unified([
            _make_unified(line=10, analyzer_name="error_handling"),
            _make_unified(line=10, analyzer_name="security_scan"),
        ])
        result = corr.correlate()
        assert result.hotspots[0].pattern == HotspotPattern.RISK_CLUSTER

    def test_mixed_pattern(self) -> None:
        corr = FindingCorrelator()
        corr.add_unified([
            _make_unified(line=10, analyzer_name="cognitive_complexity"),
            _make_unified(line=10, analyzer_name="dead_store"),
        ])
        result = corr.correlate()
        assert result.hotspots[0].pattern == HotspotPattern.MIXED

    def test_pattern_in_to_dict(self) -> None:
        corr = FindingCorrelator()
        corr.add_unified([
            _make_unified(line=10, analyzer_name="dead_store"),
            _make_unified(line=10, analyzer_name="dead_code_path"),
        ])
        d = corr.correlate().to_dict()
        assert d["hotspots"][0]["pattern"] == "dead_code_cluster"


# ── File Summary ───────────────────────────────────────────────────


class TestFileSummary:
    def test_single_file_summary(self) -> None:
        corr = FindingCorrelator()
        corr.add_unified([
            _make_unified(file_path="a.py", line=10, analyzer_name="a1", severity=Severity.HIGH),
            _make_unified(file_path="a.py", line=10, analyzer_name="a2", severity=Severity.MEDIUM),
        ])
        result = corr.correlate()
        summaries = result.file_summary
        assert len(summaries) == 1
        assert summaries[0].file_path == "a.py"
        assert summaries[0].hotspot_count == 1
        assert summaries[0].max_priority_score > 0

    def test_multi_file_summary_sorted_by_priority(self) -> None:
        corr = FindingCorrelator()
        corr.add_unified([
            _make_unified(file_path="low.py", line=10, analyzer_name="a1", severity=Severity.LOW),
            _make_unified(file_path="low.py", line=10, analyzer_name="a2", severity=Severity.LOW),
            _make_unified(file_path="high.py", line=10, analyzer_name="a1", severity=Severity.CRITICAL),
            _make_unified(file_path="high.py", line=10, analyzer_name="a2", severity=Severity.CRITICAL),
        ])
        result = corr.correlate()
        summaries = result.file_summary
        assert len(summaries) == 2
        assert summaries[0].file_path == "high.py"
        assert summaries[1].file_path == "low.py"

    def test_file_summary_in_to_dict(self) -> None:
        corr = FindingCorrelator()
        corr.add_unified([
            _make_unified(file_path="a.py", line=10, analyzer_name="a1"),
            _make_unified(file_path="a.py", line=10, analyzer_name="a2"),
        ])
        d = corr.correlate().to_dict()
        assert len(d["file_summary"]) == 1
        assert d["file_summary"][0]["file_path"] == "a.py"
        assert "max_priority_score" in d["file_summary"][0]
        assert "top_pattern" in d["file_summary"][0]
