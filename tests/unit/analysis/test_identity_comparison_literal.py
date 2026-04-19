"""Tests for Identity Comparison with Literals Detector."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.identity_comparison_literal import (
    ISSUE_IS_LITERAL,
    ISSUE_IS_NOT_LITERAL,
    IdentityComparisonLiteralAnalyzer,
)


@pytest.fixture
def analyzer() -> IdentityComparisonLiteralAnalyzer:
    return IdentityComparisonLiteralAnalyzer()


@pytest.fixture
def tmp_py(tmp_path: Path) -> Path:
    return tmp_path / "test.py"


def _write(path: Path, code: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(code), encoding="utf-8")
    return path


class TestIsLiteralDetection:
    def test_is_integer(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x is 5\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_IS_LITERAL
        assert r.issues[0].line == 1

    def test_is_float(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x is 3.14\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_IS_LITERAL

    def test_is_string(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, 'x is "hello"\n')
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_IS_LITERAL

    def test_is_empty_list(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x is []\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1

    def test_is_empty_dict(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x is {}\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1

    def test_is_tuple(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x is (1, 2)\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1

    def test_is_literal_on_left(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "5 is x\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_IS_LITERAL

    def test_is_zero(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x is 0\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1

    def test_is_negative_int(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x is -1\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1

    def test_is_single_char_string(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x is 'a'\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1

    def test_multiple_issues(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            x is 5
            y is "hello"
            z is []
        """))
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 3
        assert r.total_identity_comparisons == 3


class TestIsNotLiteralDetection:
    def test_is_not_integer(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x is not 5\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_IS_NOT_LITERAL

    def test_is_not_string(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, 'x is not "hello"\n')
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_IS_NOT_LITERAL

    def test_is_not_float(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x is not 0.0\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_IS_NOT_LITERAL

    def test_is_not_list(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x is not []\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1


class TestSingletonExclusions:
    def test_is_none_ok(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x is None\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_is_not_none_ok(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x is not None\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_is_true_ok(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x is True\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_is_false_ok(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x is False\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_is_ellipsis_ok(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x is ...\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_is_not_true_ok(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x is not True\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_is_not_false_ok(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x is not False\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0


class TestNonPythonFiles:
    def test_js_file_skipped(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_path: Path) -> None:
        p = tmp_path / "test.js"
        p.write_text("x is 5\n", encoding="utf-8")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0
        assert r.total_identity_comparisons == 0

    def test_nonexistent_file(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_path: Path) -> None:
        r = analyzer.analyze_file(tmp_path / "nope.py")
        assert len(r.issues) == 0


class TestNoIssues:
    def test_equality_comparison_ok(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x == 5\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0
        assert r.total_identity_comparisons == 0

    def test_variable_is_variable_ok(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x is y\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_is_not_variable_ok(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x is not y\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_empty_file(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0


class TestResultStructure:
    def test_issue_to_dict(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x is 5\n")
        r = analyzer.analyze_file(p)
        d = r.issues[0].to_dict()
        assert "issue_type" in d
        assert "line" in d
        assert "severity" in d
        assert d["issue_type"] == ISSUE_IS_LITERAL
        assert d["severity"] == "high"

    def test_result_to_dict(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x is 5\ny is None\n")
        r = analyzer.analyze_file(p)
        d = r.to_dict()
        assert d["file_path"] == str(p)
        assert d["issue_count"] == 1
        assert d["total_identity_comparisons"] == 2

    def test_context_includes_code(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x is 42\n")
        r = analyzer.analyze_file(p)
        assert "x is 42" in r.issues[0].context


class TestEdgeCases:
    def test_is_inside_if(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            if x is 5:
                pass
        """))
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1

    def test_is_inside_while(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            while x is not 0:
                pass
        """))
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_IS_NOT_LITERAL

    def test_is_in_return(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            def f():
                return x is 5
        """))
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1

    def test_is_in_assignment(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            flag = x is 5
        """))
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1

    def test_set_literal(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x is {1}\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1

    def test_syntax_error_file(self, analyzer: IdentityComparisonLiteralAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "def def def\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0
