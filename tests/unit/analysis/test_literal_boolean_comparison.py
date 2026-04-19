"""Tests for Literal Boolean Comparison Detector."""
from __future__ import annotations

import tempfile
from pathlib import Path

from tree_sitter_analyzer.analysis.literal_boolean_comparison import (
    LiteralBooleanComparisonAnalyzer,
    ISSUE_EQ_TRUE,
    ISSUE_EQ_FALSE,
    ISSUE_EQ_NONE,
    ISSUE_NE_NONE,
    ISSUE_EQ_NULL_LOOSE,
    ISSUE_NE_NULL_LOOSE,
)

import pytest


@pytest.fixture
def analyzer() -> LiteralBooleanComparisonAnalyzer:
    return LiteralBooleanComparisonAnalyzer()


def _write_tmp(content: str, suffix: str) -> str:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8",
    )
    f.write(content)
    f.close()
    return f.name


# ── Python tests ──────────────────────────────────────────


class TestPythonLiteralBooleanComparison:
    def test_eq_true(self, analyzer: LiteralBooleanComparisonAnalyzer) -> None:
        code = "if x == True:\n    pass\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_EQ_TRUE for i in result.issues)

    def test_eq_false(self, analyzer: LiteralBooleanComparisonAnalyzer) -> None:
        code = "if x == False:\n    pass\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_EQ_FALSE for i in result.issues)

    def test_eq_none(self, analyzer: LiteralBooleanComparisonAnalyzer) -> None:
        code = "if x == None:\n    pass\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_EQ_NONE for i in result.issues)

    def test_ne_none(self, analyzer: LiteralBooleanComparisonAnalyzer) -> None:
        code = "if x != None:\n    pass\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_NE_NONE for i in result.issues)

    def test_is_none_not_flagged(self, analyzer: LiteralBooleanComparisonAnalyzer) -> None:
        code = "if x is None:\n    pass\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert not any(ISSUE_EQ_NONE in i.issue_type for i in result.issues)

    def test_is_not_none_not_flagged(self, analyzer: LiteralBooleanComparisonAnalyzer) -> None:
        code = "if x is not None:\n    pass\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert not any(ISSUE_NE_NONE in i.issue_type for i in result.issues)

    def test_plain_bool_not_flagged(self, analyzer: LiteralBooleanComparisonAnalyzer) -> None:
        code = "if x:\n    pass\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0

    def test_eq_true_reversed(self, analyzer: LiteralBooleanComparisonAnalyzer) -> None:
        code = "if True == x:\n    pass\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_EQ_TRUE for i in result.issues)

    def test_multiple_issues(self, analyzer: LiteralBooleanComparisonAnalyzer) -> None:
        code = "if x == True:\n    pass\nif y == None:\n    pass\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        types = {i.issue_type for i in result.issues}
        assert ISSUE_EQ_TRUE in types
        assert ISSUE_EQ_NONE in types

    def test_empty_file(self, analyzer: LiteralBooleanComparisonAnalyzer) -> None:
        path = _write_tmp("", ".py")
        result = analyzer.analyze_file(path)
        assert result.total_comparisons == 0
        assert len(result.issues) == 0

    def test_result_to_dict(self, analyzer: LiteralBooleanComparisonAnalyzer) -> None:
        code = "if x == True:\n    pass\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        d = result.to_dict()
        assert "file_path" in d
        assert "total_comparisons" in d
        assert "issues" in d


# ── JavaScript/TypeScript tests ────────────────────────────


class TestJSLiteralBooleanComparison:
    def test_eq_null_loose(self, analyzer: LiteralBooleanComparisonAnalyzer) -> None:
        code = "if (x == null) {}\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_EQ_NULL_LOOSE for i in result.issues)

    def test_ne_null_loose(self, analyzer: LiteralBooleanComparisonAnalyzer) -> None:
        code = "if (x != null) {}\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_NE_NULL_LOOSE for i in result.issues)

    def test_strict_eq_not_flagged(self, analyzer: LiteralBooleanComparisonAnalyzer) -> None:
        code = "if (x === null) {}\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert not any(
            i.issue_type == ISSUE_EQ_NULL_LOOSE for i in result.issues
        )

    def test_strict_ne_not_flagged(self, analyzer: LiteralBooleanComparisonAnalyzer) -> None:
        code = "if (x !== null) {}\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert not any(
            i.issue_type == ISSUE_NE_NULL_LOOSE for i in result.issues
        )

    def test_eq_true_js(self, analyzer: LiteralBooleanComparisonAnalyzer) -> None:
        code = "if (x == true) {}\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_EQ_TRUE for i in result.issues)

    def test_typescript_eq_null(self, analyzer: LiteralBooleanComparisonAnalyzer) -> None:
        code = "if (x == null) {}\n"
        path = _write_tmp(code, ".ts")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_EQ_NULL_LOOSE for i in result.issues)


# ── Java tests ────────────────────────────────────────────


class TestJavaLiteralBooleanComparison:
    def test_eq_true(self, analyzer: LiteralBooleanComparisonAnalyzer) -> None:
        code = "class T { boolean f(boolean x) { return x == true; } }\n"
        path = _write_tmp(code, ".java")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_EQ_TRUE for i in result.issues)

    def test_eq_false(self, analyzer: LiteralBooleanComparisonAnalyzer) -> None:
        code = "class T { boolean f(boolean x) { return x == false; } }\n"
        path = _write_tmp(code, ".java")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_EQ_FALSE for i in result.issues)


# ── Go tests ──────────────────────────────────────────────


class TestGoLiteralBooleanComparison:
    def test_eq_true(self, analyzer: LiteralBooleanComparisonAnalyzer) -> None:
        code = 'package main\n\nfunc main() {\n\tif x == true {}\n}\n'
        path = _write_tmp(code, ".go")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_EQ_TRUE for i in result.issues)

    def test_eq_false(self, analyzer: LiteralBooleanComparisonAnalyzer) -> None:
        code = 'package main\n\nfunc main() {\n\tif x == false {}\n}\n'
        path = _write_tmp(code, ".go")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_EQ_FALSE for i in result.issues)

    def test_plain_bool_not_flagged(self, analyzer: LiteralBooleanComparisonAnalyzer) -> None:
        code = 'package main\n\nfunc main() {\n\tif x {}\n}\n'
        path = _write_tmp(code, ".go")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0


# ── Edge case tests ────────────────────────────────────────


class TestEdgeCases:
    def test_nonexistent_file(self, analyzer: LiteralBooleanComparisonAnalyzer) -> None:
        result = analyzer.analyze_file("/nonexistent/file.py")
        assert result.total_comparisons == 0
        assert len(result.issues) == 0

    def test_unsupported_extension(self, analyzer: LiteralBooleanComparisonAnalyzer) -> None:
        path = _write_tmp("x == True", ".txt")
        result = analyzer.analyze_file(path)
        assert result.total_comparisons == 0

    def test_issue_to_dict(self, analyzer: LiteralBooleanComparisonAnalyzer) -> None:
        code = "if x == True:\n    pass\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        if result.issues:
            d = result.issues[0].to_dict()
            assert "issue_type" in d
            assert "line" in d
            assert "severity" in d
