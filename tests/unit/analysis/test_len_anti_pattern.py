"""Tests for Len Anti-pattern Detector (merged len_comparison + range_len)."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.len_anti_pattern import (
    ISSUE_LEN_EQ_ZERO,
    ISSUE_LEN_GE_ONE,
    ISSUE_LEN_GT_ZERO,
    ISSUE_LEN_LT_ONE,
    ISSUE_LEN_NE_ZERO,
    ISSUE_RANGE_LEN_FOR,
    LenAntiPatternAnalyzer,
    LenAntiPatternIssue,
)


@pytest.fixture
def analyzer() -> LenAntiPatternAnalyzer:
    return LenAntiPatternAnalyzer()


@pytest.fixture
def tmp_py(tmp_path: Path) -> Path:
    return tmp_path / "test.py"


@pytest.fixture
def tmp_js(tmp_path: Path) -> Path:
    return tmp_path / "test.js"


@pytest.fixture
def tmp_ts(tmp_path: Path) -> Path:
    return tmp_path / "test.ts"


@pytest.fixture
def tmp_java(tmp_path: Path) -> Path:
    return tmp_path / "Test.java"


@pytest.fixture
def tmp_go(tmp_path: Path) -> Path:
    return tmp_path / "test.go"


def _write(path: Path, code: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(code), encoding="utf-8")
    return path


# --- Python len-comparison tests ---


class TestPythonLenComparison:
    def test_len_eq_zero(self, analyzer: LenAntiPatternAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, 'if len(items) == 0:\n    pass\n')
        r = analyzer.analyze_file(p)
        assert r.issue_count == 1
        assert r.issues[0].issue_type == ISSUE_LEN_EQ_ZERO
        assert r.issues[0].line == 1

    def test_len_ne_zero(self, analyzer: LenAntiPatternAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, 'if len(items) != 0:\n    pass\n')
        r = analyzer.analyze_file(p)
        assert r.issue_count == 1
        assert r.issues[0].issue_type == ISSUE_LEN_NE_ZERO

    def test_len_gt_zero(self, analyzer: LenAntiPatternAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, 'if len(items) > 0:\n    pass\n')
        r = analyzer.analyze_file(p)
        assert r.issue_count == 1
        assert r.issues[0].issue_type == ISSUE_LEN_GT_ZERO

    def test_len_ge_one(self, analyzer: LenAntiPatternAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, 'if len(items) >= 1:\n    pass\n')
        r = analyzer.analyze_file(p)
        assert r.issue_count == 1
        assert r.issues[0].issue_type == ISSUE_LEN_GE_ONE

    def test_len_lt_one(self, analyzer: LenAntiPatternAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, 'if len(items) < 1:\n    pass\n')
        r = analyzer.analyze_file(p)
        assert r.issue_count == 1
        assert r.issues[0].issue_type == ISSUE_LEN_LT_ONE

    def test_multiple_issues(self, analyzer: LenAntiPatternAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            if len(a) == 0:
                pass
            if len(b) > 0:
                pass
            if len(c) >= 1:
                pass
        """))
        r = analyzer.analyze_file(p)
        assert r.issue_count == 3
        types = {i.issue_type for i in r.issues}
        assert types == {ISSUE_LEN_EQ_ZERO, ISSUE_LEN_GT_ZERO, ISSUE_LEN_GE_ONE}


class TestPythonNoIssue:
    def test_len_ge_zero(self, analyzer: LenAntiPatternAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, 'if len(items) >= 0:\n    pass\n')
        r = analyzer.analyze_file(p)
        assert r.issue_count == 0

    def test_len_gt_one(self, analyzer: LenAntiPatternAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, 'if len(items) > 1:\n    pass\n')
        r = analyzer.analyze_file(p)
        assert r.issue_count == 0

    def test_len_eq_five(self, analyzer: LenAntiPatternAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, 'if len(items) == 5:\n    pass\n')
        r = analyzer.analyze_file(p)
        assert r.issue_count == 0

    def test_non_len_comparison(self, analyzer: LenAntiPatternAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, 'if x == 0:\n    pass\n')
        r = analyzer.analyze_file(p)
        assert r.issue_count == 0

    def test_len_as_argument(self, analyzer: LenAntiPatternAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, 'x = len(items)\n')
        r = analyzer.analyze_file(p)
        assert r.issue_count == 0

    def test_empty_file(self, analyzer: LenAntiPatternAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, '')
        r = analyzer.analyze_file(p)
        assert r.issue_count == 0
        assert r.total_checks == 0


# --- Python range-len tests ---


class TestRangeLenDetection:
    def test_basic_range_len(
        self, analyzer: LenAntiPatternAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, "for i in range(len(items)):\n    print(items[i])\n")
        r = analyzer.analyze_file(p)
        assert r.issue_count == 1
        assert r.issues[0].issue_type == ISSUE_RANGE_LEN_FOR
        assert r.issues[0].line == 1

    def test_range_len_with_complex_expr(
        self, analyzer: LenAntiPatternAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, "for i in range(len(data.get_list())):\n    pass\n")
        r = analyzer.analyze_file(p)
        assert r.issue_count == 1

    def test_multiple_range_len(
        self, analyzer: LenAntiPatternAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            for i in range(len(a)):
                pass
            for j in range(len(b)):
                pass
        """))
        r = analyzer.analyze_file(p)
        assert r.issue_count == 2

    def test_nested_for_range_len(
        self, analyzer: LenAntiPatternAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            for i in range(len(matrix)):
                for j in range(len(matrix[i])):
                    pass
        """))
        r = analyzer.analyze_file(p)
        assert r.issue_count == 2


class TestRangeLenNoIssue:
    def test_direct_iteration(
        self, analyzer: LenAntiPatternAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, "for item in items:\n    print(item)\n")
        r = analyzer.analyze_file(p)
        range_issues = [i for i in r.issues if i.issue_type == ISSUE_RANGE_LEN_FOR]
        assert len(range_issues) == 0

    def test_enumerate(
        self, analyzer: LenAntiPatternAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, "for i, item in enumerate(items):\n    print(i, item)\n")
        r = analyzer.analyze_file(p)
        range_issues = [i for i in r.issues if i.issue_type == ISSUE_RANGE_LEN_FOR]
        assert len(range_issues) == 0

    def test_range_with_constant(
        self, analyzer: LenAntiPatternAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, "for i in range(10):\n    print(i)\n")
        r = analyzer.analyze_file(p)
        range_issues = [i for i in r.issues if i.issue_type == ISSUE_RANGE_LEN_FOR]
        assert len(range_issues) == 0

    def test_range_with_len_but_not_for(
        self, analyzer: LenAntiPatternAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, "x = range(len(items))\n")
        r = analyzer.analyze_file(p)
        range_issues = [i for i in r.issues if i.issue_type == ISSUE_RANGE_LEN_FOR]
        assert len(range_issues) == 0


# --- Combined detection test ---


class TestCombinedDetection:
    def test_both_patterns_in_same_file(
        self, analyzer: LenAntiPatternAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            if len(items) == 0:
                pass
            for i in range(len(items)):
                pass
        """))
        r = analyzer.analyze_file(p)
        assert r.issue_count == 2
        types = {i.issue_type for i in r.issues}
        assert types == {ISSUE_LEN_EQ_ZERO, ISSUE_RANGE_LEN_FOR}


# --- JavaScript detection tests ---


class TestJavaScriptLengthComparison:
    def test_length_eq_zero(self, analyzer: LenAntiPatternAnalyzer, tmp_js: Path) -> None:
        p = _write(tmp_js, 'if (arr.length == 0) {}\n')
        r = analyzer.analyze_file(p)
        assert r.issue_count == 1
        assert r.issues[0].issue_type == ISSUE_LEN_EQ_ZERO

    def test_length_strict_eq_zero(self, analyzer: LenAntiPatternAnalyzer, tmp_js: Path) -> None:
        p = _write(tmp_js, 'if (arr.length === 0) {}\n')
        r = analyzer.analyze_file(p)
        assert r.issue_count == 1
        assert r.issues[0].issue_type == ISSUE_LEN_EQ_ZERO

    def test_length_gt_zero(self, analyzer: LenAntiPatternAnalyzer, tmp_js: Path) -> None:
        p = _write(tmp_js, 'if (arr.length > 0) {}\n')
        r = analyzer.analyze_file(p)
        assert r.issue_count == 1
        assert r.issues[0].issue_type == ISSUE_LEN_GT_ZERO

    def test_no_issue_non_length(self, analyzer: LenAntiPatternAnalyzer, tmp_js: Path) -> None:
        p = _write(tmp_js, 'if (x == 0) {}\n')
        r = analyzer.analyze_file(p)
        assert r.issue_count == 0


# --- TypeScript detection tests ---


class TestTypeScriptLengthComparison:
    def test_length_eq_zero(self, analyzer: LenAntiPatternAnalyzer, tmp_ts: Path) -> None:
        p = _write(tmp_ts, 'if (arr.length === 0) {}\n')
        r = analyzer.analyze_file(p)
        assert r.issue_count == 1
        assert r.issues[0].issue_type == ISSUE_LEN_EQ_ZERO


# --- Go detection tests ---


class TestGoLenComparison:
    def test_len_eq_zero(self, analyzer: LenAntiPatternAnalyzer, tmp_go: Path) -> None:
        p = _write(tmp_go, textwrap.dedent("""\
            package main
            func main() {
                if len(s) == 0 {
                }
            }
        """))
        r = analyzer.analyze_file(p)
        assert r.issue_count == 1
        assert r.issues[0].issue_type == ISSUE_LEN_EQ_ZERO

    def test_len_gt_zero(self, analyzer: LenAntiPatternAnalyzer, tmp_go: Path) -> None:
        p = _write(tmp_go, textwrap.dedent("""\
            package main
            func main() {
                if len(s) > 0 {
                }
            }
        """))
        r = analyzer.analyze_file(p)
        assert r.issue_count == 1
        assert r.issues[0].issue_type == ISSUE_LEN_GT_ZERO

    def test_no_issue(self, analyzer: LenAntiPatternAnalyzer, tmp_go: Path) -> None:
        p = _write(tmp_go, textwrap.dedent("""\
            package main
            func main() {
                if x == 0 {
                }
            }
        """))
        r = analyzer.analyze_file(p)
        assert r.issue_count == 0


# --- Edge case tests ---


class TestEdgeCases:
    def test_unsupported_extension(self, analyzer: LenAntiPatternAnalyzer, tmp_path: Path) -> None:
        p = tmp_path / "test.rb"
        _write(p, 'if length(x) == 0\nend\n')
        r = analyzer.analyze_file(p)
        assert r.issue_count == 0
        assert r.total_checks == 0

    def test_nonexistent_file(self, analyzer: LenAntiPatternAnalyzer) -> None:
        r = analyzer.analyze_file("/nonexistent/file.py")
        assert r.issue_count == 0

    def test_to_dict(self, analyzer: LenAntiPatternAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, 'if len(x) == 0:\n    pass\n')
        r = analyzer.analyze_file(p)
        d = r.to_dict()
        assert "file_path" in d
        assert "total_checks" in d
        assert "issues" in d
        assert len(d["issues"]) == 1
        assert "line" in d["issues"][0]
        assert "suggestion" in d["issues"][0]

    def test_result_properties(self, analyzer: LenAntiPatternAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, 'if len(x) == 0:\n    pass\n')
        r = analyzer.analyze_file(p)
        assert r.file_path == str(p)
        assert r.total_checks >= 1

    def test_issue_dataclass_frozen(self) -> None:
        issue = LenAntiPatternIssue(
            line=1,
            issue_type=ISSUE_LEN_EQ_ZERO,
            severity="low",
            description="test",
            suggestion="test",
            context="len(x) == 0",
        )
        d = issue.to_dict()
        assert d["line"] == 1
        assert d["issue_type"] == ISSUE_LEN_EQ_ZERO

    def test_range_len_unsupported_extension(
        self, analyzer: LenAntiPatternAnalyzer, tmp_path: Path,
    ) -> None:
        p = tmp_path / "test.js"
        _write(p, "for (let i = 0; i < arr.length; i++) {}\n")
        r = analyzer.analyze_file(p)
        range_issues = [i for i in r.issues if i.issue_type == ISSUE_RANGE_LEN_FOR]
        assert len(range_issues) == 0
