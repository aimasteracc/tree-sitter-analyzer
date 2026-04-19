"""Tests for Unused Loop Variable Detector."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.unused_loop_variable import (
    ISSUE_UNUSED_FOR_VAR,
    UnusedLoopVariableAnalyzer,
)


@pytest.fixture
def analyzer() -> UnusedLoopVariableAnalyzer:
    return UnusedLoopVariableAnalyzer()


@pytest.fixture
def tmp_py(tmp_path: Path) -> Path:
    return tmp_path / "test.py"


@pytest.fixture
def tmp_js(tmp_path: Path) -> Path:
    return tmp_path / "test.js"


def _write(path: Path, code: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(code), encoding="utf-8")
    return path


class TestPythonUnusedForVariable:
    def test_unused_for_variable(self, analyzer: UnusedLoopVariableAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "for x in items:\n    process()\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_UNUSED_FOR_VAR
        assert r.issues[0].variable_name == "x"

    def test_used_for_variable_no_issue(self, analyzer: UnusedLoopVariableAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "for x in items:\n    print(x)\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_underscore_no_issue(self, analyzer: UnusedLoopVariableAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "for _ in items:\n    process()\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_underscore_prefix_no_issue(self, analyzer: UnusedLoopVariableAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "for _x in items:\n    process()\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_unused_in_nested_expression(self, analyzer: UnusedLoopVariableAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "for item in items:\n    other_func()\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].variable_name == "item"

    def test_used_in_nested_call(self, analyzer: UnusedLoopVariableAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "for item in items:\n    print(item)\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_unpacking_unused_first(self, analyzer: UnusedLoopVariableAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "for idx, val in items:\n    print(val)\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].variable_name == "idx"

    def test_unpacking_both_used(self, analyzer: UnusedLoopVariableAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "for idx, val in items:\n    print(idx, val)\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_unpacking_underscore_first(self, analyzer: UnusedLoopVariableAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "for _, val in items:\n    print(val)\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_multiple_loops(self, analyzer: UnusedLoopVariableAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "for x in a:\n    pass\nfor y in b:\n    print(y)\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].variable_name == "x"

    def test_total_loops_count(self, analyzer: UnusedLoopVariableAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "for x in a:\n    pass\nfor y in b:\n    pass\n")
        r = analyzer.analyze_file(p)
        assert r.total_loops == 2

    def test_line_number(self, analyzer: UnusedLoopVariableAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "for x in items:\n    process()\n")
        r = analyzer.analyze_file(p)
        assert r.issues[0].line == 1

    def test_used_in_assignment(self, analyzer: UnusedLoopVariableAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "for x in items:\n    y = x + 1\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0


class TestJavaScriptUnusedForVariable:
    def test_unused_for_of_variable(self, analyzer: UnusedLoopVariableAnalyzer, tmp_js: Path) -> None:
        p = _write(tmp_js, "for (const x of items) { process(); }\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].variable_name == "x"

    def test_used_for_of_no_issue(self, analyzer: UnusedLoopVariableAnalyzer, tmp_js: Path) -> None:
        p = _write(tmp_js, "for (const x of items) { console.log(x); }\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_unused_for_in_variable(self, analyzer: UnusedLoopVariableAnalyzer, tmp_js: Path) -> None:
        p = _write(tmp_js, "for (const k in obj) { doSomething(); }\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].variable_name == "k"


class TestStructureAndEdge:
    def test_result_to_dict(self, analyzer: UnusedLoopVariableAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "for x in items:\n    pass\n")
        r = analyzer.analyze_file(p)
        d = r.to_dict()
        assert "file_path" in d
        assert "total_loops" in d
        assert "issue_count" in d

    def test_issue_to_dict(self, analyzer: UnusedLoopVariableAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "for x in items:\n    pass\n")
        r = analyzer.analyze_file(p)
        d = r.issues[0].to_dict()
        assert "variable_name" in d
        assert "issue_type" in d

    def test_empty_file(self, analyzer: UnusedLoopVariableAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0
        assert r.total_loops == 0

    def test_unsupported_extension(self, analyzer: UnusedLoopVariableAnalyzer, tmp_path: Path) -> None:
        p = tmp_path / "test.go"
        _write(p, "for x := range items {\n}\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_nonexistent_file(self, analyzer: UnusedLoopVariableAnalyzer) -> None:
        r = analyzer.analyze_file("/nonexistent/file.py")
        assert r.total_loops == 0
