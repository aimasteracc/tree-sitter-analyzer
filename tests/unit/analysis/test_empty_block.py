"""Tests for Empty Block Detector."""
from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.empty_block import (
    ISSUE_EMPTY_BLOCK,
    ISSUE_EMPTY_CATCH,
    ISSUE_EMPTY_FUNCTION,
    ISSUE_EMPTY_LOOP,
    EmptyBlockAnalyzer,
    EmptyBlockIssue,
    EmptyBlockResult,
)

ANALYZER = EmptyBlockAnalyzer


# ── Classification tests ──────────────────────────────────────────────────


class TestClassification:
    def test_empty_function_constant(self) -> None:
        assert ISSUE_EMPTY_FUNCTION == "empty_function"

    def test_empty_catch_constant(self) -> None:
        assert ISSUE_EMPTY_CATCH == "empty_catch"

    def test_empty_loop_constant(self) -> None:
        assert ISSUE_EMPTY_LOOP == "empty_loop"

    def test_empty_block_constant(self) -> None:
        assert ISSUE_EMPTY_BLOCK == "empty_block"


# ── Dataclass tests ──────────────────────────────────────────────────────


class TestDataclasses:
    def test_issue_frozen(self) -> None:
        issue = EmptyBlockIssue(
            line_number=5,
            issue_type=ISSUE_EMPTY_FUNCTION,
            description="test",
            severity="medium",
            context="pass",
        )
        assert issue.line_number == 5
        with pytest.raises(AttributeError):
            issue.line_number = 10  # type: ignore[misc]

    def test_issue_to_dict(self) -> None:
        issue = EmptyBlockIssue(
            line_number=5,
            issue_type=ISSUE_EMPTY_CATCH,
            description="test",
            severity="high",
            context="pass",
        )
        d = issue.to_dict()
        assert d["line_number"] == 5
        assert d["issue_type"] == ISSUE_EMPTY_CATCH
        assert "suggestion" in d

    def test_result_to_dict(self) -> None:
        result = EmptyBlockResult(
            total_blocks=3,
            issues=(),
            file_path="test.py",
        )
        d = result.to_dict()
        assert d["total_blocks"] == 3
        assert d["issue_count"] == 0

    def test_issue_suggestion_not_empty(self) -> None:
        issue = EmptyBlockIssue(
            line_number=1,
            issue_type=ISSUE_EMPTY_FUNCTION,
            description="test",
            severity="medium",
            context="pass",
        )
        assert len(issue.suggestion) > 0


# ── Edge case tests ──────────────────────────────────────────────────────


class TestEdgeCases:
    def test_nonexistent_file(self) -> None:
        result = ANALYZER().analyze_file("/nonexistent/file.py")
        assert result.total_blocks == 0

    def test_unsupported_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "test.rb"
        f.write_text("class Foo; end")
        result = ANALYZER().analyze_file(f)
        assert result.total_blocks == 0

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.py"
        f.write_text("")
        result = ANALYZER().analyze_file(f)
        assert result.total_blocks == 0

    def test_path_as_string(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("x = 1\n")
        result = ANALYZER().analyze_file(str(f))
        assert result.total_blocks == 0


# ── Python tests ─────────────────────────────────────────────────────────


class TestPythonEmptyBlock:
    def test_no_blocks(self, tmp_path: Path) -> None:
        f = tmp_path / "nopy.py"
        f.write_text("x = 1\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_blocks == 0

    def test_non_empty_function(self, tmp_path: Path) -> None:
        code = (
            "def foo():\n"
            "    x = 1\n"
            "    return x\n"
        )
        f = tmp_path / "full.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert result.total_functions if hasattr(result, 'total_functions') else result.total_blocks >= 1
        assert not any(i.issue_type == ISSUE_EMPTY_FUNCTION for i in result.issues)

    def test_empty_function_pass(self, tmp_path: Path) -> None:
        code = "def foo():\n    pass\n"
        f = tmp_path / "pass.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert any(i.issue_type == ISSUE_EMPTY_FUNCTION for i in result.issues)

    def test_empty_function_ellipsis(self, tmp_path: Path) -> None:
        code = "def foo():\n    ...\n"
        f = tmp_path / "ellipsis.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert any(i.issue_type == ISSUE_EMPTY_FUNCTION for i in result.issues)

    def test_empty_except(self, tmp_path: Path) -> None:
        code = (
            "try:\n"
            "    x = 1\n"
            "except ValueError:\n"
            "    pass\n"
        )
        f = tmp_path / "empty_except.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert any(i.issue_type == ISSUE_EMPTY_CATCH for i in result.issues)

    def test_non_empty_except(self, tmp_path: Path) -> None:
        code = (
            "try:\n"
            "    x = 1\n"
            "except ValueError:\n"
            "    raise RuntimeError()\n"
        )
        f = tmp_path / "nonempty_except.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert not any(i.issue_type == ISSUE_EMPTY_CATCH for i in result.issues)

    def test_empty_for_loop(self, tmp_path: Path) -> None:
        code = "for i in range(10):\n    pass\n"
        f = tmp_path / "empty_for.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert any(i.issue_type == ISSUE_EMPTY_LOOP for i in result.issues)

    def test_empty_while_loop(self, tmp_path: Path) -> None:
        code = "while True:\n    pass\n"
        f = tmp_path / "empty_while.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert any(i.issue_type == ISSUE_EMPTY_LOOP for i in result.issues)

    def test_empty_if(self, tmp_path: Path) -> None:
        code = "if True:\n    pass\n"
        f = tmp_path / "empty_if.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert any(i.issue_type == ISSUE_EMPTY_BLOCK for i in result.issues)

    def test_multiple_functions(self, tmp_path: Path) -> None:
        code = (
            "def foo():\n"
            "    pass\n"
            "\n"
            "def bar():\n"
            "    return 1\n"
        )
        f = tmp_path / "multi.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        empty_foo = [i for i in result.issues if i.issue_type == ISSUE_EMPTY_FUNCTION]
        assert len(empty_foo) == 1

    def test_function_with_only_comment(self, tmp_path: Path) -> None:
        code = "def foo():\n    # just a comment\n    pass\n"
        f = tmp_path / "comment.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert any(i.issue_type == ISSUE_EMPTY_FUNCTION for i in result.issues)


# ── JavaScript/TypeScript tests ──────────────────────────────────────────


class TestJavaScriptEmptyBlock:
    def test_empty_function_js(self, tmp_path: Path) -> None:
        code = "function foo() {}\n"
        f = tmp_path / "empty.js"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert any(i.issue_type == ISSUE_EMPTY_FUNCTION for i in result.issues)

    def test_non_empty_function_js(self, tmp_path: Path) -> None:
        code = "function foo() { return 1; }\n"
        f = tmp_path / "full.js"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert not any(i.issue_type == ISSUE_EMPTY_FUNCTION for i in result.issues)

    def test_empty_catch_js(self, tmp_path: Path) -> None:
        code = (
            "try { x = 1; } catch (e) {}\n"
        )
        f = tmp_path / "empty_catch.js"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert any(i.issue_type == ISSUE_EMPTY_CATCH for i in result.issues)

    def test_empty_method_ts(self, tmp_path: Path) -> None:
        code = (
            "class Foo {\n"
            "  bar() {}\n"
            "}\n"
        )
        f = tmp_path / "empty_method.ts"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert any(i.issue_type == ISSUE_EMPTY_FUNCTION for i in result.issues)


# ── Java tests ────────────────────────────────────────────────────────────


class TestJavaEmptyBlock:
    def test_empty_method_java(self, tmp_path: Path) -> None:
        code = (
            "public class Foo {\n"
            "  public void bar() {}\n"
            "}\n"
        )
        f = tmp_path / "Empty.java"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert any(i.issue_type == ISSUE_EMPTY_FUNCTION for i in result.issues)

    def test_non_empty_method_java(self, tmp_path: Path) -> None:
        code = (
            "public class Foo {\n"
            "  public void bar() { int x = 1; }\n"
            "}\n"
        )
        f = tmp_path / "Full.java"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert not any(i.issue_type == ISSUE_EMPTY_FUNCTION for i in result.issues)

    def test_empty_catch_java(self, tmp_path: Path) -> None:
        code = (
            "public class Foo {\n"
            "  public void bar() {\n"
            "    try { int x = 1; } catch (Exception e) {}\n"
            "  }\n"
            "}\n"
        )
        f = tmp_path / "Catch.java"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert any(i.issue_type == ISSUE_EMPTY_CATCH for i in result.issues)


# ── Go tests ──────────────────────────────────────────────────────────────


class TestGoEmptyBlock:
    def test_empty_function_go(self, tmp_path: Path) -> None:
        code = (
            'package main\n\n'
            'func foo() {}\n'
        )
        f = tmp_path / "empty.go"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert any(i.issue_type == ISSUE_EMPTY_FUNCTION for i in result.issues)

    def test_non_empty_function_go(self, tmp_path: Path) -> None:
        code = (
            'package main\n\n'
            'func foo() int { return 1 }\n'
        )
        f = tmp_path / "full.go"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert not any(i.issue_type == ISSUE_EMPTY_FUNCTION for i in result.issues)

    def test_empty_for_loop_go(self, tmp_path: Path) -> None:
        code = (
            'package main\n\n'
            'func foo() {\n'
            '    for i := 0; i < 10; i++ {}\n'
            '}\n'
        )
        f = tmp_path / "empty_for.go"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert any(i.issue_type == ISSUE_EMPTY_LOOP for i in result.issues)


# ── Severity tests ──────────────────────────────────────────────────────


class TestSeverities:
    def test_empty_catch_high_severity(self, tmp_path: Path) -> None:
        code = "try:\n    x = 1\nexcept:\n    pass\n"
        f = tmp_path / "sev.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        catches = [i for i in result.issues if i.issue_type == ISSUE_EMPTY_CATCH]
        assert len(catches) >= 1
        assert catches[0].severity == "high"

    def test_empty_function_medium_severity(self, tmp_path: Path) -> None:
        code = "def foo():\n    pass\n"
        f = tmp_path / "sev2.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        funcs = [i for i in result.issues if i.issue_type == ISSUE_EMPTY_FUNCTION]
        assert len(funcs) >= 1
        assert funcs[0].severity == "medium"
