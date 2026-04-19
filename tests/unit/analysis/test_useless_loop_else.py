"""Tests for Useless Loop Else Detector."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.useless_loop_else import (
    UselessLoopElseAnalyzer,
    UselessLoopElseIssue,
    ISSUE_USELESS_FOR_ELSE,
    ISSUE_USELESS_WHILE_ELSE,
)


@pytest.fixture
def analyzer() -> UselessLoopElseAnalyzer:
    return UselessLoopElseAnalyzer()


@pytest.fixture
def tmp_py(tmp_path: Path) -> Path:
    return tmp_path / "test.py"


def _write(path: Path, code: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(code), encoding="utf-8")
    return path


class TestForElseDetection:
    def test_for_else_no_break(
        self, analyzer: UselessLoopElseAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            for item in items:
                print(item)
            else:
                print("done")
        """))
        r = analyzer.analyze_file(p)
        assert r.issue_count == 1
        assert r.issues[0].issue_type == ISSUE_USELESS_FOR_ELSE
        assert r.issues[0].line == 1

    def test_for_else_with_break_not_useless(
        self, analyzer: UselessLoopElseAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            for item in items:
                if item == target:
                    break
            else:
                print("not found")
        """))
        r = analyzer.analyze_file(p)
        assert r.issue_count == 0

    def test_multiple_for_else(
        self, analyzer: UselessLoopElseAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            for x in a:
                pass
            else:
                pass
            for y in b:
                pass
            else:
                pass
        """))
        r = analyzer.analyze_file(p)
        assert r.issue_count == 2


class TestWhileElseDetection:
    def test_while_else_no_break(
        self, analyzer: UselessLoopElseAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            while True:
                x = 1
            else:
                pass
        """))
        r = analyzer.analyze_file(p)
        assert r.issue_count == 1
        assert r.issues[0].issue_type == ISSUE_USELESS_WHILE_ELSE

    def test_while_else_with_break(
        self, analyzer: UselessLoopElseAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            while True:
                if done:
                    break
            else:
                pass
        """))
        r = analyzer.analyze_file(p)
        assert r.issue_count == 0


class TestNoIssue:
    def test_for_without_else(
        self, analyzer: UselessLoopElseAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, "for x in items:\n    print(x)\n")
        r = analyzer.analyze_file(p)
        assert r.issue_count == 0

    def test_empty_file(
        self, analyzer: UselessLoopElseAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, "")
        r = analyzer.analyze_file(p)
        assert r.issue_count == 0
        assert r.total_loop_else == 0

    def test_non_for_loop(
        self, analyzer: UselessLoopElseAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, "if x:\n    pass\nelse:\n    pass\n")
        r = analyzer.analyze_file(p)
        assert r.issue_count == 0


class TestEdgeCases:
    def test_unsupported_extension(
        self, analyzer: UselessLoopElseAnalyzer, tmp_path: Path,
    ) -> None:
        p = tmp_path / "test.js"
        _write(p, "for (;;) {} else {}\n")
        r = analyzer.analyze_file(p)
        assert r.issue_count == 0

    def test_nonexistent_file(self, analyzer: UselessLoopElseAnalyzer) -> None:
        r = analyzer.analyze_file("/nonexistent/file.py")
        assert r.issue_count == 0

    def test_to_dict(
        self, analyzer: UselessLoopElseAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, "for x in items:\n    pass\nelse:\n    pass\n")
        r = analyzer.analyze_file(p)
        d = r.to_dict()
        assert "file_path" in d
        assert "total_loop_else" in d
        assert "issues" in d
        assert d["issues"][0]["issue_type"] == ISSUE_USELESS_FOR_ELSE

    def test_issue_frozen(self) -> None:
        issue = UselessLoopElseIssue(
            line=1,
            issue_type=ISSUE_USELESS_FOR_ELSE,
            severity="low",
            description="test",
            suggestion="test",
            context="for x in items: ... else: ...",
        )
        d = issue.to_dict()
        assert d["line"] == 1

    def test_break_in_nested_if(
        self, analyzer: UselessLoopElseAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            for x in items:
                if x == 5:
                    break
            else:
                print("done")
        """))
        r = analyzer.analyze_file(p)
        assert r.issue_count == 0

    def test_break_in_nested_loop_not_counted(
        self, analyzer: UselessLoopElseAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            for x in items:
                for y in other:
                    break
            else:
                pass
        """))
        r = analyzer.analyze_file(p)
        assert r.issue_count == 1
