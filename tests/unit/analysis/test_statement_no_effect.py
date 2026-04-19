"""Tests for Statement-with-No-Effect Detector."""
from __future__ import annotations

import tempfile
from pathlib import Path

from tree_sitter_analyzer.analysis.statement_no_effect import (
    ISSUE_ARITHMETIC,
    ISSUE_COMPARISON,
    ISSUE_LITERAL,
    StatementNoEffectAnalyzer,
)

analyzer = StatementNoEffectAnalyzer()


def _write_tmp(content: str, suffix: str = ".py") -> Path:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False,
    )
    f.write(content)
    f.close()
    return Path(f.name)


# ── Python: comparison as statement ──


def test_python_eq_as_statement() -> None:
    path = _write_tmp("x == 5\n")
    result = analyzer.analyze_file(path)
    assert result.issue_count >= 1
    assert any(i.issue_type == ISSUE_COMPARISON for i in result.issues)


def test_python_ne_as_statement() -> None:
    path = _write_tmp("x != 5\n")
    result = analyzer.analyze_file(path)
    assert result.issue_count >= 1


def test_python_lt_as_statement() -> None:
    path = _write_tmp("x < 10\n")
    result = analyzer.analyze_file(path)
    assert result.issue_count >= 1


def test_python_arithmetic_as_statement() -> None:
    path = _write_tmp("a + b\n")
    result = analyzer.analyze_file(path)
    assert result.issue_count >= 1
    assert any(i.issue_type == ISSUE_ARITHMETIC for i in result.issues)


def test_python_string_literal_as_statement() -> None:
    path = _write_tmp('"hello"\n')
    result = analyzer.analyze_file(path)
    assert result.issue_count >= 1
    assert any(i.issue_type == ISSUE_LITERAL for i in result.issues)


# ── Python: valid statements (no issues) ──


def test_python_assignment_ok() -> None:
    path = _write_tmp("x = 5\n")
    result = analyzer.analyze_file(path)
    assert result.issue_count == 0


def test_python_function_call_ok() -> None:
    path = _write_tmp("print(x)\n")
    result = analyzer.analyze_file(path)
    assert result.issue_count == 0


def test_python_return_ok() -> None:
    path = _write_tmp("def f():\n    return x == 5\n")
    result = analyzer.analyze_file(path)
    assert result.issue_count == 0


def test_python_if_condition_ok() -> None:
    path = _write_tmp("if x == 5:\n    pass\n")
    result = analyzer.analyze_file(path)
    assert result.issue_count == 0


# ── JavaScript ──


def test_js_comparison_as_statement() -> None:
    path = _write_tmp("x == 5;\n", suffix=".js")
    result = analyzer.analyze_file(path)
    assert result.issue_count >= 1


def test_js_strict_eq_as_statement() -> None:
    path = _write_tmp("x === 5;\n", suffix=".js")
    result = analyzer.analyze_file(path)
    assert result.issue_count >= 1


def test_js_arithmetic_as_statement() -> None:
    path = _write_tmp("a + b;\n", suffix=".js")
    result = analyzer.analyze_file(path)
    assert result.issue_count >= 1


def test_js_function_call_ok() -> None:
    path = _write_tmp("console.log(x);\n", suffix=".js")
    result = analyzer.analyze_file(path)
    assert result.issue_count == 0


# ── TypeScript ──


def test_ts_comparison_as_statement() -> None:
    path = _write_tmp("x == 5;\n", suffix=".ts")
    result = analyzer.analyze_file(path)
    assert result.issue_count >= 1


# ── Java ──


def test_java_comparison_as_statement() -> None:
    path = _write_tmp(
        "class Foo {\n"
        "  void bar() {\n"
        "    x == 5;\n"
        "  }\n"
        "}\n",
        suffix=".java",
    )
    result = analyzer.analyze_file(path)
    assert result.issue_count >= 1


# ── Edge cases ──


def test_empty_file() -> None:
    path = _write_tmp("", suffix=".py")
    result = analyzer.analyze_file(path)
    assert result.issue_count == 0


def test_file_not_found() -> None:
    result = analyzer.analyze_file("/nonexistent/file.py")
    assert result.issue_count == 0


def test_unsupported_extension() -> None:
    path = _write_tmp("x == 5\n", suffix=".rb")
    result = analyzer.analyze_file(path)
    assert result.issue_count == 0


def test_result_to_dict() -> None:
    path = _write_tmp("x == 5\n")
    result = analyzer.analyze_file(path)
    d = result.to_dict()
    assert "file_path" in d
    assert "total_statements" in d
    assert "issue_count" in d
    assert "issues" in d


def test_issue_to_dict() -> None:
    path = _write_tmp("x == 5\n")
    result = analyzer.analyze_file(path)
    if result.issues:
        d = result.issues[0].to_dict()
        assert "line" in d
        assert "issue_type" in d
        assert "severity" in d


def test_comparison_high_severity() -> None:
    path = _write_tmp("x == 5\n")
    result = analyzer.analyze_file(path)
    assert any(i.severity == "high" for i in result.issues)


def test_literal_low_severity() -> None:
    path = _write_tmp('"hello"\n')
    result = analyzer.analyze_file(path)
    assert any(i.severity == "low" for i in result.issues)


def test_go_comparison_not_supported() -> None:
    """Go doesn't have expression_statement in the same way."""
    path = _write_tmp(
        "package main\nfunc main() {}\n",
        suffix=".go",
    )
    result = analyzer.analyze_file(path)
    assert result.file_path.endswith(".go")
