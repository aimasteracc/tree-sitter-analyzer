"""Tests for Magic String Detector."""
from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.magic_string import (
    ISSUE_MAGIC_STRING,
    ISSUE_REPEATED_STRING,
    MagicStringAnalyzer,
    MagicStringIssue,
    MagicStringResult,
)

ANALYZER = MagicStringAnalyzer


# ── Classification tests ──────────────────────────────────────────────────


class TestClassification:
    def test_magic_string_constant(self) -> None:
        assert ISSUE_MAGIC_STRING == "magic_string"

    def test_repeated_string_constant(self) -> None:
        assert ISSUE_REPEATED_STRING == "repeated_string"


# ── Dataclass tests ──────────────────────────────────────────────────────


class TestDataclasses:
    def test_issue_frozen(self) -> None:
        issue = MagicStringIssue(
            line_number=5,
            issue_type=ISSUE_MAGIC_STRING,
            description="test",
            severity="low",
            string_value="hello",
        )
        assert issue.line_number == 5
        with pytest.raises(AttributeError):
            issue.line_number = 10  # type: ignore[misc]

    def test_issue_to_dict(self) -> None:
        issue = MagicStringIssue(
            line_number=5,
            issue_type=ISSUE_MAGIC_STRING,
            description="test",
            severity="low",
            string_value="hello",
        )
        d = issue.to_dict()
        assert d["line_number"] == 5
        assert d["issue_type"] == ISSUE_MAGIC_STRING
        assert "suggestion" in d

    def test_result_to_dict(self) -> None:
        result = MagicStringResult(
            total_functions=3,
            total_strings=5,
            issues=(),
            file_path="test.py",
        )
        d = result.to_dict()
        assert d["total_functions"] == 3
        assert d["total_strings"] == 5
        assert d["issue_count"] == 0

    def test_issue_suggestion_not_empty(self) -> None:
        issue = MagicStringIssue(
            line_number=1,
            issue_type=ISSUE_MAGIC_STRING,
            description="test",
            severity="low",
            string_value="hello",
        )
        assert len(issue.suggestion) > 0


# ── Edge case tests ──────────────────────────────────────────────────────


class TestEdgeCases:
    def test_nonexistent_file(self) -> None:
        result = ANALYZER().analyze_file("/nonexistent/file.py")
        assert result.total_functions == 0

    def test_unsupported_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "test.rb"
        f.write_text("def foo; end")
        result = ANALYZER().analyze_file(f)
        assert result.total_functions == 0

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.py"
        f.write_text("")
        result = ANALYZER().analyze_file(f)
        assert result.total_functions == 0

    def test_path_as_string(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("x = 1\n")
        result = ANALYZER().analyze_file(str(f))
        assert result.total_functions == 0


# ── Python tests ─────────────────────────────────────────────────────────


class TestPythonMagicString:
    def test_no_functions(self, tmp_path: Path) -> None:
        f = tmp_path / "nopy.py"
        f.write_text('x = "hello"\n')
        result = ANALYZER().analyze_file(f)
        assert result.total_functions == 0

    def test_function_without_strings(self, tmp_path: Path) -> None:
        code = (
            "def foo():\n"
            "    return 42\n"
        )
        f = tmp_path / "clean.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert result.total_functions == 1
        assert len(result.issues) == 0

    def test_magic_string_detected(self, tmp_path: Path) -> None:
        code = (
            'def foo():\n'
            '    return "hello world"\n'
        )
        f = tmp_path / "magic.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert any(i.issue_type == ISSUE_MAGIC_STRING for i in result.issues)

    def test_short_string_not_flagged(self, tmp_path: Path) -> None:
        code = (
            'def foo():\n'
            '    return "ab"\n'
        )
        f = tmp_path / "short.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert len(result.issues) == 0

    def test_repeated_string_detected(self, tmp_path: Path) -> None:
        code = (
            'def foo():\n'
            '    a = "error message"\n'
            '    b = "error message"\n'
            '    c = "error message"\n'
        )
        f = tmp_path / "repeated.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert any(i.issue_type == ISSUE_REPEATED_STRING for i in result.issues)

    def test_import_string_not_flagged(self, tmp_path: Path) -> None:
        code = (
            'import os\n'
            'from os.path import join\n'
            '\n'
            'def foo():\n'
            '    return 1\n'
        )
        f = tmp_path / "import.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert not any(i.issue_type == ISSUE_MAGIC_STRING for i in result.issues)

    def test_empty_string_not_flagged(self, tmp_path: Path) -> None:
        code = (
            'def foo():\n'
            '    return ""\n'
        )
        f = tmp_path / "empty.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert len(result.issues) == 0

    def test_multiple_functions(self, tmp_path: Path) -> None:
        code = (
            'def foo():\n'
            '    return "hello"\n'
            '\n'
            'def bar():\n'
            '    return 42\n'
        )
        f = tmp_path / "multi.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert result.total_functions == 2

    def test_line_number_correct(self, tmp_path: Path) -> None:
        code = (
            '# comment\n'
            'def foo():\n'
            '    x = "hello world"\n'
        )
        f = tmp_path / "lines.py"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        issues = [i for i in result.issues if i.issue_type == ISSUE_MAGIC_STRING]
        assert len(issues) >= 1
        assert issues[0].line_number == 3


# ── JavaScript/TypeScript tests ──────────────────────────────────────────


class TestJavaScriptMagicString:
    def test_magic_string_js(self, tmp_path: Path) -> None:
        code = (
            'function foo() {\n'
            '  return "hello world";\n'
            '}\n'
        )
        f = tmp_path / "magic.js"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert result.total_functions == 1
        assert any(i.issue_type == ISSUE_MAGIC_STRING for i in result.issues)

    def test_clean_js_function(self, tmp_path: Path) -> None:
        code = (
            "function foo() {\n"
            "  return 42;\n"
            "}\n"
        )
        f = tmp_path / "clean.js"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert len(result.issues) == 0

    def test_repeated_string_ts(self, tmp_path: Path) -> None:
        code = (
            'function foo() {\n'
            '  const a = "error code";\n'
            '  const b = "error code";\n'
            '  const c = "error code";\n'
            '}\n'
        )
        f = tmp_path / "repeated.ts"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert any(i.issue_type == ISSUE_REPEATED_STRING for i in result.issues)


# ── Java tests ────────────────────────────────────────────────────────────


class TestJavaMagicString:
    def test_magic_string_java(self, tmp_path: Path) -> None:
        code = (
            'public class Foo {\n'
            '  public void bar() {\n'
            '    System.out.println("hello world");\n'
            '  }\n'
            '}\n'
        )
        f = tmp_path / "Foo.java"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert result.total_functions == 1
        assert any(i.issue_type == ISSUE_MAGIC_STRING for i in result.issues)

    def test_clean_java_function(self, tmp_path: Path) -> None:
        code = (
            "public class Foo {\n"
            "  public int bar() {\n"
            "    return 42;\n"
            "  }\n"
            "}\n"
        )
        f = tmp_path / "Clean.java"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert len(result.issues) == 0


# ── Go tests ──────────────────────────────────────────────────────────────


class TestGoMagicString:
    def test_magic_string_go(self, tmp_path: Path) -> None:
        code = (
            'package main\n\n'
            'import "fmt"\n\n'
            'func foo() {\n'
            '    fmt.Println("hello world")\n'
            '}\n'
        )
        f = tmp_path / "magic.go"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert result.total_functions == 1
        assert any(i.issue_type == ISSUE_MAGIC_STRING for i in result.issues)

    def test_clean_go_function(self, tmp_path: Path) -> None:
        code = (
            'package main\n\n'
            'func foo() int {\n'
            '    return 42\n'
            '}\n'
        )
        f = tmp_path / "clean.go"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert len(result.issues) == 0

    def test_repeated_string_go(self, tmp_path: Path) -> None:
        code = (
            'package main\n\n'
            'func foo() {\n'
            '    a := "error message"\n'
            '    b := "error message"\n'
            '    c := "error message"\n'
            '}\n'
        )
        f = tmp_path / "repeated.go"
        f.write_text(code)
        result = ANALYZER().analyze_file(f)
        assert any(i.issue_type == ISSUE_REPEATED_STRING for i in result.issues)
