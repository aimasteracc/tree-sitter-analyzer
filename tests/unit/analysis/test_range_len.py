"""Tests for Range-Len Anti-pattern Detector."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.range_len import (
    RangeLenAnalyzer,
    RangeLenIssue,
    RangeLenResult,
    ISSUE_RANGE_LEN_FOR,
)


@pytest.fixture
def analyzer() -> RangeLenAnalyzer:
    return RangeLenAnalyzer()


@pytest.fixture
def tmp_py(tmp_path: Path) -> Path:
    return tmp_path / "test.py"


def _write(path: Path, code: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(code), encoding="utf-8")
    return path


class TestRangeLenDetection:
    def test_basic_range_len(
        self, analyzer: RangeLenAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, "for i in range(len(items)):\n    print(items[i])\n")
        r = analyzer.analyze_file(p)
        assert r.issue_count == 1
        assert r.issues[0].issue_type == ISSUE_RANGE_LEN_FOR
        assert r.issues[0].line == 1

    def test_range_len_with_complex_expr(
        self, analyzer: RangeLenAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, "for i in range(len(data.get_list())):\n    pass\n")
        r = analyzer.analyze_file(p)
        assert r.issue_count == 1

    def test_multiple_range_len(
        self, analyzer: RangeLenAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            for i in range(len(a)):
                pass
            for j in range(len(b)):
                pass
        """))
        r = analyzer.analyze_file(p)
        assert r.issue_count == 2

    def test_range_len_total_loops(
        self, analyzer: RangeLenAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            for i in range(len(a)):
                pass
            for item in b:
                pass
        """))
        r = analyzer.analyze_file(p)
        assert r.total_for_loops == 2
        assert r.issue_count == 1


class TestNoIssue:
    def test_direct_iteration(
        self, analyzer: RangeLenAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, "for item in items:\n    print(item)\n")
        r = analyzer.analyze_file(p)
        assert r.issue_count == 0

    def test_enumerate(
        self, analyzer: RangeLenAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, "for i, item in enumerate(items):\n    print(i, item)\n")
        r = analyzer.analyze_file(p)
        assert r.issue_count == 0

    def test_range_with_constant(
        self, analyzer: RangeLenAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, "for i in range(10):\n    print(i)\n")
        r = analyzer.analyze_file(p)
        assert r.issue_count == 0

    def test_range_with_variable(
        self, analyzer: RangeLenAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, "for i in range(n):\n    print(i)\n")
        r = analyzer.analyze_file(p)
        assert r.issue_count == 0

    def test_range_with_len_but_not_for(
        self, analyzer: RangeLenAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, "x = range(len(items))\n")
        r = analyzer.analyze_file(p)
        assert r.issue_count == 0

    def test_empty_file(
        self, analyzer: RangeLenAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, "")
        r = analyzer.analyze_file(p)
        assert r.issue_count == 0
        assert r.total_for_loops == 0


class TestEdgeCases:
    def test_unsupported_extension(
        self, analyzer: RangeLenAnalyzer, tmp_path: Path,
    ) -> None:
        p = tmp_path / "test.js"
        _write(p, "for (let i = 0; i < arr.length; i++) {}\n")
        r = analyzer.analyze_file(p)
        assert r.issue_count == 0

    def test_nonexistent_file(self, analyzer: RangeLenAnalyzer) -> None:
        r = analyzer.analyze_file("/nonexistent/file.py")
        assert r.issue_count == 0

    def test_to_dict(
        self, analyzer: RangeLenAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, "for i in range(len(x)):\n    pass\n")
        r = analyzer.analyze_file(p)
        d = r.to_dict()
        assert "file_path" in d
        assert "total_for_loops" in d
        assert "issues" in d
        assert d["issues"][0]["issue_type"] == ISSUE_RANGE_LEN_FOR

    def test_issue_frozen(self) -> None:
        issue = RangeLenIssue(
            line=1,
            issue_type=ISSUE_RANGE_LEN_FOR,
            severity="low",
            description="test",
            suggestion="test",
            context="for i in range(len(x))",
        )
        d = issue.to_dict()
        assert d["line"] == 1

    def test_nested_for_range_len(
        self, analyzer: RangeLenAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            for i in range(len(matrix)):
                for j in range(len(matrix[i])):
                    pass
        """))
        r = analyzer.analyze_file(p)
        assert r.issue_count == 2
