"""Unit tests for Assertion Quality Analyzer."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.assertion_quality import (
    QUALITY_CLUSTERED,
    QUALITY_MISSING_BRANCH,
    QUALITY_VAGUE,
    QUALITY_WEAK,
    AssertionQualityAnalyzer,
    _compute_quality_score,
    _empty_result,
)


@pytest.fixture
def analyzer() -> AssertionQualityAnalyzer:
    return AssertionQualityAnalyzer()


def _write_py(tmp_path: Path, code: str, name: str = "test_sample.py") -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(code))
    return p


# --- Core functionality ---

class TestAssertionQualityAnalyzer:
    def test_non_test_file(self, analyzer: AssertionQualityAnalyzer, tmp_path: Path) -> None:
        p = _write_py(tmp_path, "def hello():\n    pass\n", name="utils.py")
        result = analyzer.analyze_file(p)
        assert result.total_tests == 0


class TestWeakAssertions:
    def test_plain_assert_with_comparison_is_ok(
        self, analyzer: AssertionQualityAnalyzer, tmp_path: Path
    ) -> None:
        code = """\
        def test_ok():
            assert result == 42
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        assert result.total_tests == 1
        assert result.total_issues == 0

    def test_assert_is_not_none_is_weak(
        self, analyzer: AssertionQualityAnalyzer, tmp_path: Path
    ) -> None:
        code = """\
        def test_weak():
            result = get_value()
            assert result is not None
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        assert result.total_tests == 1
        weak = [i for i in result.test_functions[0].issues if i.issue_type == QUALITY_WEAK]
        assert len(weak) >= 1

    def test_assert_is_none_is_weak(
        self, analyzer: AssertionQualityAnalyzer, tmp_path: Path
    ) -> None:
        code = """\
        def test_weak():
            result = get_value()
            assert result is None
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        weak = [i for i in result.test_functions[0].issues if i.issue_type == QUALITY_WEAK]
        assert len(weak) >= 1

    def test_self_assert_true_is_weak(
        self, analyzer: AssertionQualityAnalyzer, tmp_path: Path
    ) -> None:
        code = """\
        class TestFoo:
            def test_weak(self):
                self.assertTrue(loaded)
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        weak = [i for i in result.test_functions[0].issues if i.issue_type == QUALITY_WEAK]
        assert len(weak) >= 1

    def test_self_assert_equal_is_ok(
        self, analyzer: AssertionQualityAnalyzer, tmp_path: Path
    ) -> None:
        code = """\
        class TestFoo:
            def test_ok(self):
                self.assertEqual(result, 42)
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        weak = [i for i in result.test_functions[0].issues if i.issue_type == QUALITY_WEAK]
        assert len(weak) == 0


class TestVagueComparisons:
    def test_bare_assert_is_vague(
        self, analyzer: AssertionQualityAnalyzer, tmp_path: Path
    ) -> None:
        code = """\
        def test_vague():
            result = run()
            assert result
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        vague = [i for i in result.test_functions[0].issues if i.issue_type == QUALITY_VAGUE]
        assert len(vague) >= 1

    def test_assert_with_eq_is_not_vague(
        self, analyzer: AssertionQualityAnalyzer, tmp_path: Path
    ) -> None:
        code = """\
        def test_specific():
            result = run()
            assert result == "ok"
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        vague = [i for i in result.test_functions[0].issues if i.issue_type == QUALITY_VAGUE]
        assert len(vague) == 0

    def test_assert_with_in_is_not_vague(
        self, analyzer: AssertionQualityAnalyzer, tmp_path: Path
    ) -> None:
        code = """\
        def test_specific():
            result = run()
            assert "ok" in result
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        vague = [i for i in result.test_functions[0].issues if i.issue_type == QUALITY_VAGUE]
        assert len(vague) == 0


class TestClusteredAssertions:
    def test_clustered_assertions_detected(
        self, analyzer: AssertionQualityAnalyzer, tmp_path: Path
    ) -> None:
        code = """\
        def test_clustered():
            a = 1
            b = 2
            c = 3
            d = 4
            assert a == 1
            assert b == 2
            assert c == 3
            assert a + b == 3
            assert b + c == 5
            assert c + d == 7
            assert a + d == 5
            assert a + b + c == 6
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        clustered = [
            i
            for i in result.test_functions[0].issues
            if i.issue_type == QUALITY_CLUSTERED
        ]
        assert len(clustered) >= 1

    def test_distributed_assertions_ok(
        self, analyzer: AssertionQualityAnalyzer, tmp_path: Path
    ) -> None:
        code = """\
        def test_distributed():
            a = compute()
            assert a == 1

            b = process(a)
            assert b == 2

            c = transform(b)
            assert c == 3

            d = finalize(c)
            assert d == 6
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        clustered = [
            i
            for i in result.test_functions[0].issues
            if i.issue_type == QUALITY_CLUSTERED
        ]
        assert len(clustered) == 0


class TestMissingBranchAssertions:
    def test_if_without_assertion(
        self, analyzer: AssertionQualityAnalyzer, tmp_path: Path
    ) -> None:
        code = """\
        def test_missing_if():
            result = compute()
            if result > 0:
                process(result)
            assert result is not None
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        missing = [
            i
            for i in result.test_functions[0].issues
            if i.issue_type == QUALITY_MISSING_BRANCH
        ]
        assert len(missing) >= 1

    def test_if_with_assertion_ok(
        self, analyzer: AssertionQualityAnalyzer, tmp_path: Path
    ) -> None:
        code = """\
        def test_if_ok():
            result = compute()
            if result > 0:
                assert result == 42
            else:
                assert result <= 0
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        missing = [
            i
            for i in result.test_functions[0].issues
            if i.issue_type == QUALITY_MISSING_BRANCH
        ]
        assert len(missing) == 0

    def test_except_without_assertion(
        self, analyzer: AssertionQualityAnalyzer, tmp_path: Path
    ) -> None:
        code = """\
        def test_except_missing():
            try:
                risky()
                assert False, "should have raised"
            except ValueError:
                pass
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        missing = [
            i
            for i in result.test_functions[0].issues
            if i.issue_type == QUALITY_MISSING_BRANCH
        ]
        assert len(missing) >= 1

    def test_except_with_assertion_ok(
        self, analyzer: AssertionQualityAnalyzer, tmp_path: Path
    ) -> None:
        code = """\
        def test_except_ok():
            try:
                risky()
                assert False, "should have raised"
            except ValueError as e:
                assert "invalid" in str(e)
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        missing = [
            i
            for i in result.test_functions[0].issues
            if i.issue_type == QUALITY_MISSING_BRANCH
        ]
        assert len(missing) == 0


class TestQualityScore:
    def test_perfect_score(self, analyzer: AssertionQualityAnalyzer, tmp_path: Path) -> None:
        code = """\
        def test_perfect():
            result = compute()
            assert result == 42
            assert result > 0
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        assert result.test_functions[0].quality_score == 100.0

    def test_score_decreases_with_issues(
        self, analyzer: AssertionQualityAnalyzer, tmp_path: Path
    ) -> None:
        code = """\
        def test_weak():
            result = get_value()
            assert result is not None
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        assert result.test_functions[0].quality_score < 100.0

    def test_zero_assertions_gets_zero(
        self, analyzer: AssertionQualityAnalyzer, tmp_path: Path
    ) -> None:
        code = """\
        def test_no_assert():
            x = 1 + 1
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        assert result.test_functions[0].quality_score == 0.0

    def test_compute_score_directly(self) -> None:
        assert _compute_quality_score(0, []) == 0.0
        assert _compute_quality_score(1, []) == 100.0

    def test_empty_result(self) -> None:
        result = _empty_result("foo.py")
        assert result.total_tests == 0
        assert result.quality_score == 100.0


class TestMultiFunction:
    def test_multiple_functions(
        self, analyzer: AssertionQualityAnalyzer, tmp_path: Path
    ) -> None:
        code = """\
        def test_good():
            assert compute() == 42

        def test_bad():
            result = run()
            assert result is not None

        def test_ugly():
            x = 1
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        assert result.total_tests == 3
        assert result.test_functions[0].quality_score == 100.0
        assert result.test_functions[1].quality_score < 100.0
        assert result.test_functions[2].quality_score == 0.0

    def test_class_methods(
        self, analyzer: AssertionQualityAnalyzer, tmp_path: Path
    ) -> None:
        code = """\
        class TestCalculator:
            def test_add(self):
                self.assertEqual(add(1, 2), 3)

            def test_weak(self):
                self.assertTrue(loaded)
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        assert result.total_tests == 2
        weak_issues = [
            i for f in result.test_functions for i in f.issues if i.issue_type == QUALITY_WEAK
        ]
        assert len(weak_issues) == 1

    def test_issue_counts(self, analyzer: AssertionQualityAnalyzer, tmp_path: Path) -> None:
        code = """\
        def test_a():
            assert result is not None
        """
        p = _write_py(tmp_path, code)
        result = analyzer.analyze_file(p)
        assert result.total_issues > 0
        assert QUALITY_WEAK in result.issue_counts
