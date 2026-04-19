"""Tests for Simplified Conditional Expression Detector."""
from __future__ import annotations

import tempfile

import pytest

from tree_sitter_analyzer.analysis.simplified_conditional import (
    ISSUE_IDENTICAL_BRANCHES,
    ISSUE_REDUNDANT_FALSE,
    ISSUE_REDUNDANT_TRUE,
    SimplifiedConditionalAnalyzer,
)


@pytest.fixture
def analyzer() -> SimplifiedConditionalAnalyzer:
    return SimplifiedConditionalAnalyzer()


def _write_tmp(content: str, suffix: str) -> str:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8",
    )
    f.write(content)
    f.close()
    return f.name


# ── JavaScript tests ──────────────────────────────────────


class TestJavaScriptSimplifiedConditional:
    def test_redundant_true_branch(self, analyzer: SimplifiedConditionalAnalyzer) -> None:
        code = "const x = flag ? true : false;\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_REDUNDANT_TRUE for i in result.issues)

    def test_redundant_false_branch(self, analyzer: SimplifiedConditionalAnalyzer) -> None:
        code = "const x = flag ? false : true;\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_REDUNDANT_FALSE for i in result.issues)

    def test_identical_branches(self, analyzer: SimplifiedConditionalAnalyzer) -> None:
        code = "const x = flag ? 42 : 42;\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_IDENTICAL_BRANCHES for i in result.issues)

    def test_normal_ternary_not_flagged(self, analyzer: SimplifiedConditionalAnalyzer) -> None:
        code = "const x = flag ? 'yes' : 'no';\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0

    def test_identical_string_branches(self, analyzer: SimplifiedConditionalAnalyzer) -> None:
        code = "const x = flag ? 'same' : 'same';\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_IDENTICAL_BRANCHES for i in result.issues)

    def test_line_number(self, analyzer: SimplifiedConditionalAnalyzer) -> None:
        code = "const a = 1;\nconst x = flag ? true : false;\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 1
        assert result.issues[0].line == 2

    def test_context_text(self, analyzer: SimplifiedConditionalAnalyzer) -> None:
        code = "const x = flag ? true : false;\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 1
        assert "true" in result.issues[0].context and "false" in result.issues[0].context

    def test_severity(self, analyzer: SimplifiedConditionalAnalyzer) -> None:
        code = "const x = flag ? true : false;\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert result.issues[0].severity == "low"

    def test_identical_branches_severity(self, analyzer: SimplifiedConditionalAnalyzer) -> None:
        code = "const x = flag ? 42 : 42;\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert result.issues[0].severity == "medium"

    def test_suggestion_present(self, analyzer: SimplifiedConditionalAnalyzer) -> None:
        code = "const x = flag ? true : false;\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert "cond" in result.issues[0].suggestion

    def test_multiple_issues(self, analyzer: SimplifiedConditionalAnalyzer) -> None:
        code = "const a = f1 ? true : false;\nconst b = f2 ? false : true;\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 2

    def test_no_ternaries(self, analyzer: SimplifiedConditionalAnalyzer) -> None:
        code = "const x = 1 + 2;\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0
        assert result.total_ternaries == 0

    def test_different_values_not_flagged(self, analyzer: SimplifiedConditionalAnalyzer) -> None:
        code = "const x = flag ? 0 : 1;\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0


# ── TypeScript tests ──────────────────────────────────────


class TestTypeScriptSimplifiedConditional:
    def test_redundant_true_branch(self, analyzer: SimplifiedConditionalAnalyzer) -> None:
        code = "const x: boolean = flag ? true : false;\n"
        path = _write_tmp(code, ".ts")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_REDUNDANT_TRUE for i in result.issues)

    def test_normal_ternary_not_flagged(self, analyzer: SimplifiedConditionalAnalyzer) -> None:
        code = "const x: string = flag ? 'a' : 'b';\n"
        path = _write_tmp(code, ".ts")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0


# ── Python tests ──────────────────────────────────────────


class TestPythonSimplifiedConditional:
    def test_redundant_true_branch(self, analyzer: SimplifiedConditionalAnalyzer) -> None:
        code = "x = True if flag else False\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_REDUNDANT_TRUE for i in result.issues)

    def test_redundant_false_branch(self, analyzer: SimplifiedConditionalAnalyzer) -> None:
        code = "x = False if flag else True\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_REDUNDANT_FALSE for i in result.issues)

    def test_identical_branches(self, analyzer: SimplifiedConditionalAnalyzer) -> None:
        code = "x = 42 if flag else 42\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_IDENTICAL_BRANCHES for i in result.issues)

    def test_normal_conditional_not_flagged(self, analyzer: SimplifiedConditionalAnalyzer) -> None:
        code = "x = 'yes' if flag else 'no'\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0


# ── Java tests ────────────────────────────────────────────


class TestJavaSimplifiedConditional:
    def test_redundant_true_branch(self, analyzer: SimplifiedConditionalAnalyzer) -> None:
        code = "boolean x = flag ? true : false;\n"
        path = _write_tmp(code, ".java")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_REDUNDANT_TRUE for i in result.issues)

    def test_normal_ternary_not_flagged(self, analyzer: SimplifiedConditionalAnalyzer) -> None:
        code = "String x = flag ? \"yes\" : \"no\";\n"
        path = _write_tmp(code, ".java")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0


# ── Go tests (unsupported) ────────────────────────────────


class TestGoUnsupported:
    def test_go_not_analyzed(self, analyzer: SimplifiedConditionalAnalyzer) -> None:
        code = "x := true\n"
        path = _write_tmp(code, ".go")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0
        assert result.total_ternaries == 0


# ── Edge cases ────────────────────────────────────────────


class TestEdgeCases:
    def test_nonexistent_file(self, analyzer: SimplifiedConditionalAnalyzer) -> None:
        result = analyzer.analyze_file("/nonexistent/file.js")
        assert len(result.issues) == 0
        assert result.total_ternaries == 0

    def test_empty_file(self, analyzer: SimplifiedConditionalAnalyzer) -> None:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".js", delete=False, encoding="utf-8",
        )
        f.write("")
        f.close()
        result = analyzer.analyze_file(f.name)
        assert len(result.issues) == 0

    def test_to_dict(self, analyzer: SimplifiedConditionalAnalyzer) -> None:
        code = "const x = flag ? true : false;\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        d = result.to_dict()
        assert "file_path" in d
        assert "total_ternaries" in d
        assert "issue_count" in d
        assert "issues" in d

    def test_issue_to_dict(self, analyzer: SimplifiedConditionalAnalyzer) -> None:
        code = "const x = flag ? true : false;\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 1
        d = result.issues[0].to_dict()
        assert d["issue_type"] == ISSUE_REDUNDANT_TRUE
        assert "line" in d
        assert "context" in d
