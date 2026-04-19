"""Tests for List-in-Membership Performance Detector."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.list_membership import (
    ISSUE_ARRAY_INCLUDES,
    ISSUE_LIST_IN,
    ISSUE_LIST_NOT_IN,
    ListMembershipAnalyzer,
)


@pytest.fixture
def analyzer() -> ListMembershipAnalyzer:
    return ListMembershipAnalyzer()


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


class TestPythonListInMembership:
    def test_list_in_membership(self, analyzer: ListMembershipAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x in [1, 2, 3]\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_LIST_IN
        assert r.issues[0].line == 1

    def test_list_not_in_membership(self, analyzer: ListMembershipAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x not in [1, 2, 3]\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_LIST_NOT_IN

    def test_set_in_no_issue(self, analyzer: ListMembershipAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x in {1, 2, 3}\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_tuple_in_no_issue(self, analyzer: ListMembershipAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x in (1, 2, 3)\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_var_in_var_no_issue(self, analyzer: ListMembershipAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x in items\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_list_in_if(self, analyzer: ListMembershipAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "if x in [1, 2]:\n    pass\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1

    def test_empty_list_in(self, analyzer: ListMembershipAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x in []\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1

    def test_total_count(self, analyzer: ListMembershipAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x in [1]\ny not in [2]\nz in {3}\n")
        r = analyzer.analyze_file(p)
        assert r.total_membership_tests == 3

    def test_string_eq_no_issue(self, analyzer: ListMembershipAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, 'x == [1, 2, 3]\n')
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0


class TestJavaScriptListMembership:
    def test_array_includes_literal(self, analyzer: ListMembershipAnalyzer, tmp_js: Path) -> None:
        p = _write(tmp_js, "[1, 2, 3].includes(x)\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_ARRAY_INCLUDES

    def test_var_includes_no_issue(self, analyzer: ListMembershipAnalyzer, tmp_js: Path) -> None:
        p = _write(tmp_js, "items.includes(x)\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_set_has_no_issue(self, analyzer: ListMembershipAnalyzer, tmp_js: Path) -> None:
        p = _write(tmp_js, "new Set([1, 2, 3]).has(x)\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0


class TestStructureAndEdge:
    def test_result_to_dict(self, analyzer: ListMembershipAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x in [1]\n")
        r = analyzer.analyze_file(p)
        d = r.to_dict()
        assert "file_path" in d
        assert "total_membership_tests" in d

    def test_issue_to_dict(self, analyzer: ListMembershipAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "x in [1]\n")
        r = analyzer.analyze_file(p)
        d = r.issues[0].to_dict()
        assert "issue_type" in d

    def test_empty_file(self, analyzer: ListMembershipAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_unsupported_extension(self, analyzer: ListMembershipAnalyzer, tmp_path: Path) -> None:
        p = tmp_path / "test.go"
        _write(p, "if x in [] {}\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_nonexistent_file(self, analyzer: ListMembershipAnalyzer) -> None:
        r = analyzer.analyze_file("/nonexistent/file.py")
        assert r.total_membership_tests == 0
