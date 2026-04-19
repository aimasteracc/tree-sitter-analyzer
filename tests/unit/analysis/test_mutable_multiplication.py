"""Tests for Mutable Multiplication Alias Detector."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.mutable_multiplication import (
    ISSUE_MUTABLE_LIST_MULT,
    ISSUE_MUTABLE_TUPLE_MULT,
    MutableMultiplicationAnalyzer,
)


@pytest.fixture
def analyzer() -> MutableMultiplicationAnalyzer:
    return MutableMultiplicationAnalyzer()


@pytest.fixture
def tmp_py(tmp_path: Path) -> Path:
    return tmp_path / "test.py"


def _write(path: Path, code: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(code), encoding="utf-8")
    return path


class TestListMultiplication:
    def test_empty_list_in_list(self, analyzer: MutableMultiplicationAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x = [[]] * n\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_MUTABLE_LIST_MULT

    def test_nonempty_list_in_list(self, analyzer: MutableMultiplicationAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x = [[1, 2]] * 3\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1

    def test_dict_in_list(self, analyzer: MutableMultiplicationAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x = [{}] * n\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1

    def test_set_in_list(self, analyzer: MutableMultiplicationAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x = [set()] * n\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1

    def test_nested_list(self, analyzer: MutableMultiplicationAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x = [[[]]] * n\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1

    def test_mixed_mutable(self, analyzer: MutableMultiplicationAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, 'x = [[], {}] * n\n')
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1


class TestTupleMultiplication:
    def test_list_in_tuple(self, analyzer: MutableMultiplicationAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x = ([],) * n\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_MUTABLE_TUPLE_MULT

    def test_dict_in_tuple(self, analyzer: MutableMultiplicationAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x = ({},) * n\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1


class TestSafeMultiplication:
    def test_int_list_mult_ok(self, analyzer: MutableMultiplicationAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x = [1, 2, 3] * 2\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_string_list_mult_ok(self, analyzer: MutableMultiplicationAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, 'x = ["a", "b"] * 3\n')
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_empty_list_mult_ok(self, analyzer: MutableMultiplicationAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x = [] * n\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_float_list_mult_ok(self, analyzer: MutableMultiplicationAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x = [1.0, 2.0] * 3\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_tuple_of_ints_mult_ok(self, analyzer: MutableMultiplicationAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x = (1, 2, 3) * 2\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_string_mult_ok(self, analyzer: MutableMultiplicationAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, 'x = "abc" * 3\n')
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_int_mult_ok(self, analyzer: MutableMultiplicationAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x = 5 * 3\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0


class TestNonPythonFiles:
    def test_js_skipped(self, analyzer: MutableMultiplicationAnalyzer, tmp_path: Path) -> None:
        p = tmp_path / "test.js"
        p.write_text("x = [[]] * n\n", encoding="utf-8")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_nonexistent_file(self, analyzer: MutableMultiplicationAnalyzer, tmp_path: Path) -> None:
        r = analyzer.analyze_file(tmp_path / "nope.py")
        assert len(r.issues) == 0


class TestResultStructure:
    def test_issue_to_dict(self, analyzer: MutableMultiplicationAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x = [[]] * n\n")
        r = analyzer.analyze_file(p)
        d = r.issues[0].to_dict()
        assert d["issue_type"] == ISSUE_MUTABLE_LIST_MULT
        assert d["severity"] == "high"
        assert "line" in d

    def test_result_to_dict(self, analyzer: MutableMultiplicationAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x = [[]] * n\n")
        r = analyzer.analyze_file(p)
        d = r.to_dict()
        assert d["file_path"] == str(p)
        assert d["issue_count"] == 1
        assert d["total_multiplications"] == 1


class TestEdgeCases:
    def test_multiple_issues(self, analyzer: MutableMultiplicationAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            x = [[]] * n
            y = [{}] * m
            z = [1, 2] * 3
        """))
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 2

    def test_empty_file(self, analyzer: MutableMultiplicationAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_syntax_error(self, analyzer: MutableMultiplicationAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "def def def\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_inside_function(self, analyzer: MutableMultiplicationAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            def f():
                grid = [[]] * 10
        """))
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1

    def test_inside_class(self, analyzer: MutableMultiplicationAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            class C:
                data = [[]] * 5
        """))
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
