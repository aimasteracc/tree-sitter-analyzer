"""Tests for Float Equality Comparison Detector."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.float_equality import (
    ISSUE_FLOAT_EQ,
    ISSUE_FLOAT_NEQ,
    FloatEqualityAnalyzer,
)


@pytest.fixture
def analyzer() -> FloatEqualityAnalyzer:
    return FloatEqualityAnalyzer()


@pytest.fixture
def tmp_py(tmp_path: Path) -> Path:
    return tmp_path / "test.py"


@pytest.fixture
def tmp_js(tmp_path: Path) -> Path:
    return tmp_path / "test.js"


@pytest.fixture
def tmp_go(tmp_path: Path) -> Path:
    return tmp_path / "test.go"


@pytest.fixture
def tmp_java(tmp_path: Path) -> Path:
    return tmp_path / "Test.java"


def _write(path: Path, code: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(code), encoding="utf-8")
    return path


class TestPythonFloatEqDetection:
    def test_float_eq_literal(self, analyzer: FloatEqualityAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x == 0.1\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_FLOAT_EQ
        assert r.issues[0].line == 1

    def test_float_neq_literal(self, analyzer: FloatEqualityAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x != 3.14\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_FLOAT_NEQ

    def test_float_literal_on_left(self, analyzer: FloatEqualityAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "0.1 == x\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_FLOAT_EQ

    def test_float_eq_both_sides(self, analyzer: FloatEqualityAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "0.1 == 0.2\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1

    def test_float_eq_scientific(self, analyzer: FloatEqualityAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x == 1e-10\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1

    def test_float_eq_in_if(self, analyzer: FloatEqualityAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "if x == 2.5:\n    pass\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1

    def test_float_eq_negative(self, analyzer: FloatEqualityAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x == -1.5\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1

    def test_float_eq_parenthesized(self, analyzer: FloatEqualityAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x == (0.1)\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1

    def test_multiple_comparisons(self, analyzer: FloatEqualityAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x == 0.1\ny != 3.14\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 2

    def test_integer_eq_no_issue(self, analyzer: FloatEqualityAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x == 5\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_string_eq_no_issue(self, analyzer: FloatEqualityAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, 'x == "hello"\n')
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_greater_than_no_issue(self, analyzer: FloatEqualityAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x > 0.1\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_less_than_no_issue(self, analyzer: FloatEqualityAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x < 3.14\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_var_eq_var_no_issue(self, analyzer: FloatEqualityAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x == y\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0


class TestJavaScriptFloatEqDetection:
    def test_js_float_eq(self, analyzer: FloatEqualityAnalyzer, tmp_js: Path) -> None:
        p = _write(tmp_js, "x === 0.1\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_FLOAT_EQ

    def test_js_float_neq(self, analyzer: FloatEqualityAnalyzer, tmp_js: Path) -> None:
        p = _write(tmp_js, "x !== 3.14\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_FLOAT_NEQ

    def test_js_float_loose_eq(self, analyzer: FloatEqualityAnalyzer, tmp_js: Path) -> None:
        p = _write(tmp_js, "x == 2.5\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1

    def test_js_int_eq_no_issue(self, analyzer: FloatEqualityAnalyzer, tmp_js: Path) -> None:
        p = _write(tmp_js, "x === 5\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0


class TestGoFloatEqDetection:
    def test_go_float_eq(self, analyzer: FloatEqualityAnalyzer, tmp_go: Path) -> None:
        p = _write(tmp_go, "if x == 3.14 {\n}\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_FLOAT_EQ

    def test_go_float_neq(self, analyzer: FloatEqualityAnalyzer, tmp_go: Path) -> None:
        p = _write(tmp_go, "if x != 0.1 {\n}\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1

    def test_go_int_eq_no_issue(self, analyzer: FloatEqualityAnalyzer, tmp_go: Path) -> None:
        p = _write(tmp_go, "if x == 5 {\n}\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0


class TestJavaFloatEqDetection:
    def test_java_float_eq(self, analyzer: FloatEqualityAnalyzer, tmp_java: Path) -> None:
        p = _write(tmp_java, "class T {{ void f() {{ if (x == 3.14) {{}} }} }}\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_FLOAT_EQ

    def test_java_int_eq_no_issue(self, analyzer: FloatEqualityAnalyzer, tmp_java: Path) -> None:
        p = _write(tmp_java, "class T {{ void f() {{ if (x == 5) {{}} }} }}\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0


class TestStructureAndEdge:
    def test_result_to_dict(self, analyzer: FloatEqualityAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x == 0.1\n")
        r = analyzer.analyze_file(p)
        d = r.to_dict()
        assert "file_path" in d
        assert "total_float_comparisons" in d
        assert "issue_count" in d
        assert "issues" in d

    def test_issue_to_dict(self, analyzer: FloatEqualityAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x == 0.1\n")
        r = analyzer.analyze_file(p)
        d = r.issues[0].to_dict()
        assert "issue_type" in d
        assert "line" in d
        assert "severity" in d

    def test_empty_file(self, analyzer: FloatEqualityAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0
        assert r.total_float_comparisons == 0

    def test_unsupported_extension(self, analyzer: FloatEqualityAnalyzer, tmp_path: Path) -> None:
        p = tmp_path / "test.rb"
        _write(p, "x == 0.1\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_nonexistent_file(self, analyzer: FloatEqualityAnalyzer) -> None:
        r = analyzer.analyze_file("/nonexistent/file.py")
        assert r.total_float_comparisons == 0
