"""Tests for Dead Code Path Analyzer."""
from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.dead_code_path import (
    ISSUE_DEAD_BRANCH,
    ISSUE_UNREACHABLE_CODE,
    DeadCodePathAnalyzer,
    DeadCodePathIssue,
    DeadCodePathResult,
)

ANALYZER = DeadCodePathAnalyzer


# ── Classification tests ──────────────────────────────────────────────────


class TestClassification:
    def test_unreachable_code_constant(self) -> None:
        assert ISSUE_UNREACHABLE_CODE == "unreachable_code"

    def test_dead_branch_constant(self) -> None:
        assert ISSUE_DEAD_BRANCH == "dead_branch"


# ── Dataclass tests ──────────────────────────────────────────────────────


class TestDataclasses:
    def test_issue_frozen(self) -> None:
        issue = DeadCodePathIssue(
            line_number=5,
            issue_type=ISSUE_UNREACHABLE_CODE,
            description="test",
            severity="high",
            context="x = 1",
        )
        assert issue.line_number == 5
        with pytest.raises(AttributeError):
            issue.line_number = 10  # type: ignore[misc]

    def test_issue_to_dict(self) -> None:
        issue = DeadCodePathIssue(
            line_number=5,
            issue_type=ISSUE_UNREACHABLE_CODE,
            description="test",
            severity="high",
            context="x = 1",
        )
        d = issue.to_dict()
        assert d["line_number"] == 5
        assert d["issue_type"] == ISSUE_UNREACHABLE_CODE
        assert "suggestion" in d

    def test_result_to_dict(self) -> None:
        result = DeadCodePathResult(
            total_functions=3,
            issues=(),
            file_path="test.py",
        )
        d = result.to_dict()
        assert d["total_functions"] == 3
        assert d["issue_count"] == 0

    def test_issue_suggestion_not_empty(self) -> None:
        issue = DeadCodePathIssue(
            line_number=1,
            issue_type=ISSUE_UNREACHABLE_CODE,
            description="test",
            severity="high",
            context="x = 1",
        )
        assert len(issue.suggestion) > 0


# ── Edge case tests ──────────────────────────────────────────────────────


class TestEdgeCases:
    def test_path_as_string(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("x = 1\n")
        result = ANALYZER().analyze_file(str(f))
        assert result.total_functions == 0


# ── Python tests ─────────────────────────────────────────────────────────


class TestPythonDeadCodePath:
    def test_no_functions(self, tmp_path: Path) -> None:
        f = tmp_path / "nopy.py"
        f.write_text("x = 1\n")
        result = ANALYZER().analyze_file(f)
        assert result.total_functions == 0

    def test_clean_function_no_issues(self, tmp_path: Path) -> None:
        code = (
            "def foo():\n"
            "    x = 1\n"
            "    return x\n"
        )
        f = tmp_path / "clean.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert result.total_functions == 1
        assert len(result.issues) == 0

    def test_code_after_return(self, tmp_path: Path) -> None:
        code = (
            "def foo():\n"
            "    return 1\n"
            "    x = 2\n"
        )
        f = tmp_path / "after_return.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert any(i.issue_type == ISSUE_UNREACHABLE_CODE for i in result.issues)
        unreachable = [i for i in result.issues if i.issue_type == ISSUE_UNREACHABLE_CODE]
        assert unreachable[0].line_number == 3

    def test_code_after_raise(self, tmp_path: Path) -> None:
        code = (
            "def foo():\n"
            "    raise ValueError()\n"
            "    x = 2\n"
        )
        f = tmp_path / "after_raise.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert any(i.issue_type == ISSUE_UNREACHABLE_CODE for i in result.issues)

    def test_if_false_branch(self, tmp_path: Path) -> None:
        code = (
            "def foo():\n"
            "    if False:\n"
            "        x = 1\n"
            "    return 0\n"
        )
        f = tmp_path / "if_false.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert any(i.issue_type == ISSUE_DEAD_BRANCH for i in result.issues)

    def test_if_true_else_dead(self, tmp_path: Path) -> None:
        code = (
            "def foo():\n"
            "    if True:\n"
            "        x = 1\n"
            "    else:\n"
            "        x = 2\n"
            "    return x\n"
        )
        f = tmp_path / "if_true.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        dead = [i for i in result.issues if i.issue_type == ISSUE_DEAD_BRANCH]
        assert len(dead) >= 1
        assert dead[0].line_number == 4

    def test_conditional_return_not_flagged(self, tmp_path: Path) -> None:
        code = (
            "def foo(x):\n"
            "    if x > 0:\n"
            "        return x\n"
            "    return -x\n"
        )
        f = tmp_path / "cond_return.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert len(result.issues) == 0

    def test_multiple_functions(self, tmp_path: Path) -> None:
        code = (
            "def foo():\n"
            "    return 1\n"
            "\n"
            "def bar():\n"
            "    return 2\n"
        )
        f = tmp_path / "multi.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert result.total_functions == 2
        assert len(result.issues) == 0

    def test_break_in_loop(self, tmp_path: Path) -> None:
        code = (
            "def foo():\n"
            "    for i in range(10):\n"
            "        break\n"
            "        x = 1\n"
        )
        f = tmp_path / "break.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert any(i.issue_type == ISSUE_UNREACHABLE_CODE for i in result.issues)

    def test_continue_in_loop(self, tmp_path: Path) -> None:
        code = (
            "def foo():\n"
            "    for i in range(10):\n"
            "        continue\n"
            "        x = 1\n"
        )
        f = tmp_path / "continue.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert any(i.issue_type == ISSUE_UNREACHABLE_CODE for i in result.issues)


# ── JavaScript/TypeScript tests ──────────────────────────────────────────


class TestJavaScriptDeadCodePath:
    def test_code_after_return_js(self, tmp_path: Path) -> None:
        code = (
            "function foo() {\n"
            "  return 1;\n"
            "  var x = 2;\n"
            "}\n"
        )
        f = tmp_path / "after_return.js"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert result.total_functions == 1
        assert any(i.issue_type == ISSUE_UNREACHABLE_CODE for i in result.issues)

    def test_clean_js_function(self, tmp_path: Path) -> None:
        code = (
            "function foo() {\n"
            "  var x = 1;\n"
            "  return x;\n"
            "}\n"
        )
        f = tmp_path / "clean.js"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert result.total_functions == 1
        assert len(result.issues) == 0

    def test_code_after_throw_js(self, tmp_path: Path) -> None:
        code = (
            "function foo() {\n"
            "  throw new Error();\n"
            "  var x = 2;\n"
            "}\n"
        )
        f = tmp_path / "after_throw.js"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert any(i.issue_type == ISSUE_UNREACHABLE_CODE for i in result.issues)

    def test_if_false_ts(self, tmp_path: Path) -> None:
        code = (
            "function foo() {\n"
            "  if (false) {\n"
            "    var x = 1;\n"
            "  }\n"
            "}\n"
        )
        f = tmp_path / "if_false.ts"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert any(i.issue_type == ISSUE_DEAD_BRANCH for i in result.issues)


# ── Java tests ────────────────────────────────────────────────────────────


class TestJavaDeadCodePath:
    def test_code_after_return_java(self, tmp_path: Path) -> None:
        code = (
            "public class Foo {\n"
            "  public void bar() {\n"
            "    return;\n"
            "    int x = 2;\n"
            "  }\n"
            "}\n"
        )
        f = tmp_path / "Foo.java"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert result.total_functions == 1
        assert any(i.issue_type == ISSUE_UNREACHABLE_CODE for i in result.issues)

    def test_clean_java_function(self, tmp_path: Path) -> None:
        code = (
            "public class Foo {\n"
            "  public int bar() {\n"
            "    return 1;\n"
            "  }\n"
            "}\n"
        )
        f = tmp_path / "Clean.java"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert len(result.issues) == 0

    def test_code_after_throw_java(self, tmp_path: Path) -> None:
        code = (
            "public class Foo {\n"
            "  public void bar() {\n"
            "    throw new RuntimeException();\n"
            "    int x = 1;\n"
            "  }\n"
            "}\n"
        )
        f = tmp_path / "Throw.java"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert any(i.issue_type == ISSUE_UNREACHABLE_CODE for i in result.issues)


# ── Go tests ──────────────────────────────────────────────────────────────


class TestGoDeadCodePath:
    def test_code_after_return_go(self, tmp_path: Path) -> None:
        code = (
            'package main\n\n'
            'func foo() int {\n'
            '    return 1\n'
            '    x := 2\n'
            '    return x\n'
            '}\n'
        )
        f = tmp_path / "foo.go"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert result.total_functions == 1
        assert any(i.issue_type == ISSUE_UNREACHABLE_CODE for i in result.issues)

    def test_clean_go_function(self, tmp_path: Path) -> None:
        code = (
            'package main\n\n'
            'func foo() int {\n'
            '    x := 1\n'
            '    return x\n'
            '}\n'
        )
        f = tmp_path / "clean.go"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert len(result.issues) == 0

    def test_code_after_panic_go(self, tmp_path: Path) -> None:
        code = (
            'package main\n\n'
            'func foo() {\n'
            '    panic("error")\n'
            '    x := 2\n'
            '}\n'
        )
        f = tmp_path / "panic.go"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert any(i.issue_type == ISSUE_UNREACHABLE_CODE for i in result.issues)

    def test_method_declaration(self, tmp_path: Path) -> None:
        code = (
            'package main\n\n'
            'type T struct{}\n\n'
            'func (t *T) Foo() int {\n'
            '    return 1\n'
            '    x := 2\n'
            '    return x\n'
            '}\n'
        )
        f = tmp_path / "method.go"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert result.total_functions == 1
        assert any(i.issue_type == ISSUE_UNREACHABLE_CODE for i in result.issues)


# ── Line number tests ────────────────────────────────────────────────────


class TestLineNumbers:
    def test_correct_line_after_return(self, tmp_path: Path) -> None:
        code = (
            "# comment\n"
            "# comment\n"
            "def foo():\n"
            "    return 1\n"
            "    x = 2\n"
        )
        f = tmp_path / "lines.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        unreachable = [i for i in result.issues if i.issue_type == ISSUE_UNREACHABLE_CODE]
        assert len(unreachable) >= 1
        assert unreachable[0].line_number == 5
