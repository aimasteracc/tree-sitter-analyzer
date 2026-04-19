"""Tests for Await-in-Loop Detector."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.await_in_loop import (
    ISSUE_AWAIT_IN_FOR,
    ISSUE_AWAIT_IN_WHILE,
    AwaitInLoopAnalyzer,
)


@pytest.fixture
def analyzer() -> AwaitInLoopAnalyzer:
    return AwaitInLoopAnalyzer()


@pytest.fixture
def tmp_py(tmp_path: Path) -> Path:
    return tmp_path / "test.py"


@pytest.fixture
def tmp_js(tmp_path: Path) -> Path:
    return tmp_path / "test.js"


@pytest.fixture
def tmp_ts(tmp_path: Path) -> Path:
    return tmp_path / "test.ts"


def _write(path: Path, code: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(code), encoding="utf-8")
    return path


class TestPythonForLoop:
    def test_await_in_for_loop(self, analyzer: AwaitInLoopAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            async def f():
                for x in items:
                    await fetch(x)
        """))
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_AWAIT_IN_FOR

    def test_await_in_nested_for(self, analyzer: AwaitInLoopAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            async def f():
                for x in items:
                    for y in x:
                        await fetch(y)
        """))
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_AWAIT_IN_FOR
        assert r.total_loops == 2

    def test_no_await_in_for(self, analyzer: AwaitInLoopAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            for x in items:
                print(x)
        """))
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_multiple_awaits_in_for(self, analyzer: AwaitInLoopAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            async def f():
                for x in items:
                    await a(x)
                    await b(x)
        """))
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 2


class TestPythonWhileLoop:
    def test_await_in_while(self, analyzer: AwaitInLoopAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            async def f():
                while True:
                    await poll()
        """))
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_AWAIT_IN_WHILE

    def test_no_await_in_while(self, analyzer: AwaitInLoopAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            while True:
                print("hello")
        """))
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0


class TestPythonNestedFunction:
    def test_await_in_nested_async_function_not_flagged(
        self, analyzer: AwaitInLoopAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            async def f():
                for x in items:
                    async def inner():
                        await fetch(x)
        """))
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_await_in_loop_and_nested_function(
        self, analyzer: AwaitInLoopAnalyzer, tmp_py: Path,
    ) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            async def f():
                for x in items:
                    await a(x)
                    async def inner():
                        await b(x)
        """))
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_AWAIT_IN_FOR


class TestJavaScript:
    def test_await_in_for_of(self, analyzer: AwaitInLoopAnalyzer, tmp_js: Path) -> None:
        p = _write(tmp_js, textwrap.dedent("""\
            async function f() {
                for (const x of items) {
                    await fetch(x);
                }
            }
        """))
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_AWAIT_IN_FOR

    def test_await_in_for_loop(self, analyzer: AwaitInLoopAnalyzer, tmp_js: Path) -> None:
        p = _write(tmp_js, textwrap.dedent("""\
            async function f() {
                for (let i = 0; i < n; i++) {
                    await process(i);
                }
            }
        """))
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1

    def test_await_in_while(self, analyzer: AwaitInLoopAnalyzer, tmp_js: Path) -> None:
        p = _write(tmp_js, textwrap.dedent("""\
            async function f() {
                while (true) {
                    await poll();
                }
            }
        """))
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1
        assert r.issues[0].issue_type == ISSUE_AWAIT_IN_WHILE

    def test_no_await_in_for(self, analyzer: AwaitInLoopAnalyzer, tmp_js: Path) -> None:
        p = _write(tmp_js, textwrap.dedent("""\
            for (const x of items) {
                console.log(x);
            }
        """))
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0


class TestTypeScript:
    def test_await_in_for_of(self, analyzer: AwaitInLoopAnalyzer, tmp_ts: Path) -> None:
        p = _write(tmp_ts, textwrap.dedent("""\
            async function f() {
                for (const x of items) {
                    await fetch(x);
                }
            }
        """))
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 1


class TestNonSupportedFiles:
    def test_java_skipped(self, analyzer: AwaitInLoopAnalyzer, tmp_path: Path) -> None:
        p = tmp_path / "Test.java"
        p.write_text("for (int i = 0; i < n; i++) { Thread.sleep(100); }", encoding="utf-8")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0
        assert r.total_loops == 0

    def test_nonexistent_file(self, analyzer: AwaitInLoopAnalyzer, tmp_path: Path) -> None:
        r = analyzer.analyze_file(tmp_path / "nope.py")
        assert len(r.issues) == 0


class TestResultStructure:
    def test_issue_to_dict(self, analyzer: AwaitInLoopAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            async def f():
                for x in items:
                    await fetch(x)
        """))
        r = analyzer.analyze_file(p)
        d = r.issues[0].to_dict()
        assert "issue_type" in d
        assert "line" in d
        assert d["issue_type"] == ISSUE_AWAIT_IN_FOR
        assert d["severity"] == "medium"

    def test_result_to_dict(self, analyzer: AwaitInLoopAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            for x in items:
                print(x)
        """))
        r = analyzer.analyze_file(p)
        d = r.to_dict()
        assert d["file_path"] == str(p)
        assert d["total_loops"] == 1
        assert d["issue_count"] == 0


class TestEdgeCases:
    def test_empty_file(self, analyzer: AwaitInLoopAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_syntax_error(self, analyzer: AwaitInLoopAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, "def def def\n")
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0

    def test_await_outside_loop(self, analyzer: AwaitInLoopAnalyzer, tmp_py: Path) -> None:
        p = _write(tmp_py, textwrap.dedent("""\
            async def f():
                await fetch(x)
        """))
        r = analyzer.analyze_file(p)
        assert len(r.issues) == 0
