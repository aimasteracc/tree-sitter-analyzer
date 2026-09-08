#!/usr/bin/env python3

from pathlib import Path

import pytest

from tree_sitter_analyzer.test_gap_analyzer import (
    CoverageGapResult,
    ProductionSymbol,
    _collect_files,
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
        assert len(targets) == 2


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
        assert score == 0

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
    @pytest.mark.parametrize("parent", ["workspace", "pytest", "test", "tests"])
    @pytest.mark.parametrize("root_form", ["absolute", "relative", "dot"])
    def test_collection_ignores_project_ancestors(
        self, tmp_path, monkeypatch, parent, root_form
    ):
        # #1400：项目外的 pytest/test/tests 目录不能改变生产分类或文件预算。
        project = tmp_path / parent / "project"
        expected = {
            "src/service.py": False,
            "src/test/helper.py": True,
            "test/helper.py": True,
            "tests/helper.py": True,
            "test_support/service.py": False,
        }
        for relative in expected:
            path = project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("def work():\n    pass\n", encoding="utf-8")
        root = str(project)
        if root_form == "relative":
            monkeypatch.chdir(project.parent)
            root = "project"
        elif root_form == "dot":
            monkeypatch.chdir(project)
            root = "."

        files = _collect_files(root, max_files=2)

        assert {
            Path(path).resolve().relative_to(project.resolve()).as_posix(): is_test
            for path, language, is_test in files
        } == expected

    @pytest.mark.parametrize("parent", ["workspace", "pytest"])
    @pytest.mark.parametrize("target_file", [None, "service.py"])
    def test_gap_results_ignore_project_ancestors(self, tmp_path, parent, target_file):
        # #1400：真实解析必须保留未覆盖符号、命名覆盖及目标文件作用域。
        project = tmp_path / parent / "project"
        src = project / "src"
        src.mkdir(parents=True)
        (src / "service.py").write_text(
            "def alpha():\n    return 1\n\ndef beta():\n    return 2\n",
            encoding="utf-8",
        )
        (src / "other.py").write_text("def gamma():\n    return 3\n", encoding="utf-8")
        tests = project / "tests"
        tests.mkdir()
        (tests / "test_service.py").write_text(
            "def test_alpha():\n    assert alpha() == 1\n", encoding="utf-8"
        )

        result = analyze_coverage_gaps(
            str(project), target_file=target_file, include_covered=True
        )

        assert result.total_production_symbols == (2 if target_file else 3)
        assert result.total_test_symbols == 1
        assert result.covered_count == 1
        assert result.gap_count == (1 if target_file else 2)
        assert result.coverage_pct == (50.0 if target_file else 33.3)
        assert {gap.symbol.name for gap in result.gaps} == (
            {"beta"} if target_file else {"beta", "gamma"}
        )
        assert [symbol.name for symbol in result.covered] == ["alpha"]
        assert result.summary["production_files"] == (1 if target_file else 2)
        assert result.summary["test_files"] == 1

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
        assert result.total_production_symbols == 4
        assert result.gap_count == 3
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
        result = analyze_coverage_gaps(str(project_with_gaps), language_filter="python")
        assert result.total_production_symbols == 4

    def test_max_gaps(self, project_with_gaps):
        result = analyze_coverage_gaps(str(project_with_gaps), max_gaps=1)
        assert len(result.gaps) <= 1

    def test_include_covered(self, project_with_gaps):
        result = analyze_coverage_gaps(str(project_with_gaps), include_covered=True)
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
