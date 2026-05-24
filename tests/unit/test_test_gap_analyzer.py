#!/usr/bin/env python3


import pytest

from tree_sitter_analyzer.test_gap_analyzer import (
    CoverageGapResult,
    ProductionSymbol,
    _extract_test_targets,
    _is_test_file,
    _make_reason,
    _make_suggestion,
    _priority_score,
    _risk_band,
    analyze_coverage_gaps,
)


def _make_prod(name, kind="function", **kw):
    return ProductionSymbol(
        name=name,
        kind=kind,
        file_path=kw.get("file_path", "src/mod.py"),
        language=kw.get("language", "python"),
        line=kw.get("line", 1),
        end_line=kw.get("end_line", 1),
        class_name=kw.get("class_name"),
        complexity=kw.get("complexity", 0),
        risk=kw.get("risk", "low"),
    )


class TestIsTestFile:
    def test_test_prefix(self):
        assert _is_test_file("test_foo.py")

    def test_test_suffix(self):
        assert _is_test_file("foo_test.py")

    def test_spec_suffix(self):
        assert _is_test_file("foo.spec.ts")

    def test_test_dir(self):
        assert _is_test_file("tests/test_mod.py")

    def test_production_file(self):
        assert not _is_test_file("mod.py")

    def test_src_file(self):
        assert not _is_test_file("src/calculator.py")


class TestExtractTestTargets:
    def test_test_prefix(self):
        targets = _extract_test_targets("test_analyze_file")
        assert "analyze_file" in targets
        assert "analyze_file" in targets

    def test_should_prefix(self):
        targets = _extract_test_targets("should_return_ok")
        assert "return_ok" in targets

    def test_no_prefix(self):
        targets = _extract_test_targets("analyze_file")
        assert isinstance(targets, list)

    def test_with_keyword(self):
        targets = _extract_test_targets("test_parse_raises_error")
        assert len(targets) > 0


class TestRiskBand:
    def test_low(self):
        assert _risk_band(1) == "low"
        assert _risk_band(5) == "low"

    def test_medium(self):
        assert _risk_band(6) == "medium"
        assert _risk_band(10) == "medium"

    def test_high(self):
        assert _risk_band(11) == "high"
        assert _risk_band(20) == "high"

    def test_critical(self):
        assert _risk_band(21) == "critical"


class TestPriorityScore:
    def test_simple_function(self):
        sym = _make_prod("foo")
        score = _priority_score(sym)
        assert score >= 0

    def test_class_bonus(self):
        cls = _make_prod("MyClass", kind="class")
        fn = _make_prod("my_func")
        assert _priority_score(cls) > _priority_score(fn)

    def test_risk_bonus(self):
        crit = _make_prod("f", risk="critical")
        low = _make_prod("f", risk="low")
        assert _priority_score(crit) > _priority_score(low)


class TestMakeSuggestion:
    def test_function(self):
        sym = _make_prod("parse_csv")
        s = _make_suggestion(sym)
        assert "test_parse_csv" in s

    def test_class(self):
        sym = _make_prod("Parser", kind="class")
        s = _make_suggestion(sym)
        assert "TestParser" in s

    def test_method(self):
        sym = _make_prod("run", class_name="Engine")
        s = _make_suggestion(sym)
        assert "TestEngine" in s
        assert "test_run" in s


class TestMakeReason:
    def test_function(self):
        sym = _make_prod("parse_csv")
        r = _make_reason(sym)
        assert "parse_csv" in r
        assert "no matching test" in r

    def test_class(self):
        sym = _make_prod("Parser", kind="class")
        r = _make_reason(sym)
        assert "class" in r.lower()
        assert "Parser" in r

    def test_high_complexity(self):
        sym = _make_prod("complex_fn", complexity=15, risk="high")
        r = _make_reason(sym)
        assert "complexity=15" in r


class TestAnalyzeCoverageGaps:
    @pytest.fixture
    def project_with_gaps(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "calculator.py").write_text(
            "def add(a, b):\n    return a + b\n\n"
            "def subtract(a, b):\n    return a - b\n\n"
            "class Calculator:\n"
            "    def multiply(self, a, b):\n"
            "        return a * b\n"
        )
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_calculator.py").write_text(
            "def test_add():\n    assert add(1, 2) == 3\n"
        )
        return tmp_path

    def test_finds_uncovered_symbols(self, project_with_gaps):
        result = analyze_coverage_gaps(str(project_with_gaps))
        assert isinstance(result, CoverageGapResult)
        assert result.total_production_symbols >= 1
        assert result.gap_count >= 1
        assert 0 <= result.coverage_pct <= 100

    def test_coverage_percentage(self, project_with_gaps):
        result = analyze_coverage_gaps(str(project_with_gaps))
        assert result.coverage_pct < 100

    def test_gaps_have_priority(self, project_with_gaps):
        result = analyze_coverage_gaps(str(project_with_gaps))
        for gap in result.gaps:
            assert gap.priority in ("low", "medium", "high", "critical")
            assert isinstance(gap.symbol, ProductionSymbol)
            assert isinstance(gap.reason, str)
            assert isinstance(gap.suggestion, str)

    def test_language_filter(self, project_with_gaps):
        result = analyze_coverage_gaps(
            str(project_with_gaps), language_filter="python"
        )
        assert result.total_production_symbols >= 1

    def test_max_gaps(self, project_with_gaps):
        result = analyze_coverage_gaps(str(project_with_gaps), max_gaps=1)
        assert len(result.gaps) <= 1

    def test_include_covered(self, project_with_gaps):
        result = analyze_coverage_gaps(
            str(project_with_gaps), include_covered=True
        )
        assert isinstance(result.covered, list)

    def test_empty_project(self, tmp_path):
        result = analyze_coverage_gaps(str(tmp_path))
        assert result.total_production_symbols == 0
        assert result.gap_count == 0
        assert result.coverage_pct == 0.0

    def test_summary_has_by_language(self, project_with_gaps):
        result = analyze_coverage_gaps(str(project_with_gaps))
        assert "by_language" in result.summary
        assert isinstance(result.summary["by_language"], dict)

    def test_summary_has_worst_files(self, project_with_gaps):
        result = analyze_coverage_gaps(str(project_with_gaps))
        assert "worst_files" in result.summary
