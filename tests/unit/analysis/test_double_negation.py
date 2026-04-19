"""Tests for Double Negation Detector."""
from __future__ import annotations

import tempfile
from pathlib import Path

from tree_sitter_analyzer.analysis.double_negation import (
    DoubleNegationAnalyzer,
    ISSUE_DOUBLE_NOT,
    ISSUE_DOUBLE_BANG,
    ISSUE_NOT_NOT_PARENS,
)

import pytest


@pytest.fixture
def analyzer() -> DoubleNegationAnalyzer:
    return DoubleNegationAnalyzer()


def _write_tmp(content: str, suffix: str) -> str:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8",
    )
    f.write(content)
    f.close()
    return f.name


# ── Python tests ──────────────────────────────────────────


class TestPythonDoubleNegation:
    def test_double_not(self, analyzer: DoubleNegationAnalyzer) -> None:
        code = "x = not not y\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_DOUBLE_NOT for i in result.issues)

    def test_not_not_parens(self, analyzer: DoubleNegationAnalyzer) -> None:
        code = "x = not (not y)\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_NOT_NOT_PARENS for i in result.issues)

    def test_single_not_not_flagged(self, analyzer: DoubleNegationAnalyzer) -> None:
        code = "x = not y\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0

    def test_bool_not_flagged(self, analyzer: DoubleNegationAnalyzer) -> None:
        code = "x = bool(y)\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0

    def test_if_not_not(self, analyzer: DoubleNegationAnalyzer) -> None:
        code = "if not not x:\n    pass\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_DOUBLE_NOT for i in result.issues)

    def test_empty_file(self, analyzer: DoubleNegationAnalyzer) -> None:
        path = _write_tmp("", ".py")
        result = analyzer.analyze_file(path)
        assert result.total_unary_ops == 0
        assert len(result.issues) == 0

    def test_result_to_dict(self, analyzer: DoubleNegationAnalyzer) -> None:
        code = "x = not not y\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        d = result.to_dict()
        assert "file_path" in d
        assert "total_unary_ops" in d


# ── JavaScript/TypeScript tests ────────────────────────────


class TestJSDoubleNegation:
    def test_double_bang(self, analyzer: DoubleNegationAnalyzer) -> None:
        code = "const x = !!y;\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_DOUBLE_BANG for i in result.issues)

    def test_single_bang_not_flagged(self, analyzer: DoubleNegationAnalyzer) -> None:
        code = "const x = !y;\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0

    def test_boolean_not_flagged(self, analyzer: DoubleNegationAnalyzer) -> None:
        code = "const x = Boolean(y);\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0

    def test_typescript_double_bang(self, analyzer: DoubleNegationAnalyzer) -> None:
        code = "const x = !!y;\n"
        path = _write_tmp(code, ".ts")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_DOUBLE_BANG for i in result.issues)


# ── Java tests ────────────────────────────────────────────


class TestJavaDoubleNegation:
    def test_double_bang(self, analyzer: DoubleNegationAnalyzer) -> None:
        code = "class T { boolean f(boolean x) { return !!x; } }\n"
        path = _write_tmp(code, ".java")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_DOUBLE_BANG for i in result.issues)

    def test_single_bang_not_flagged(self, analyzer: DoubleNegationAnalyzer) -> None:
        code = "class T { boolean f(boolean x) { return !x; } }\n"
        path = _write_tmp(code, ".java")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0


# ── Go tests ──────────────────────────────────────────────


class TestGoDoubleNegation:
    def test_no_double_bang_in_go(self, analyzer: DoubleNegationAnalyzer) -> None:
        # Go doesn't have !! operator, but test that the analyzer handles it
        code = 'package main\n\nfunc main() {\n\tx := !y\n}\n'
        path = _write_tmp(code, ".go")
        result = analyzer.analyze_file(path)
        # Go has unary expressions but not !!, should find no issues
        assert not any(i.issue_type == ISSUE_DOUBLE_BANG for i in result.issues)


# ── Edge case tests ────────────────────────────────────────


class TestEdgeCases:
    def test_nonexistent_file(self, analyzer: DoubleNegationAnalyzer) -> None:
        result = analyzer.analyze_file("/nonexistent/file.py")
        assert result.total_unary_ops == 0
        assert len(result.issues) == 0

    def test_unsupported_extension(self, analyzer: DoubleNegationAnalyzer) -> None:
        path = _write_tmp("not not x", ".txt")
        result = analyzer.analyze_file(path)
        assert result.total_unary_ops == 0

    def test_issue_to_dict(self, analyzer: DoubleNegationAnalyzer) -> None:
        code = "x = not not y\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        if result.issues:
            d = result.issues[0].to_dict()
            assert "issue_type" in d
            assert "line" in d
            assert "severity" in d
