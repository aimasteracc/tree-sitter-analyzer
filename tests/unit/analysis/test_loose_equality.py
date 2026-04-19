"""Tests for Loose Equality Comparison Detector."""
from __future__ import annotations

import tempfile

import pytest

from tree_sitter_analyzer.analysis.loose_equality import (
    ISSUE_LOOSE_EQ,
    ISSUE_LOOSE_NEQ,
    LooseEqualityAnalyzer,
)


@pytest.fixture
def analyzer() -> LooseEqualityAnalyzer:
    return LooseEqualityAnalyzer()


def _write_tmp(content: str, suffix: str) -> str:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8",
    )
    f.write(content)
    f.close()
    return f.name


# ── JavaScript tests ──────────────────────────────────────


class TestJavaScriptLooseEquality:
    def test_loose_eq_detected(self, analyzer: LooseEqualityAnalyzer) -> None:
        code = "if (x == y) { }\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_LOOSE_EQ for i in result.issues)

    def test_loose_neq_detected(self, analyzer: LooseEqualityAnalyzer) -> None:
        code = "if (x != y) { }\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_LOOSE_NEQ for i in result.issues)

    def test_strict_eq_not_flagged(self, analyzer: LooseEqualityAnalyzer) -> None:
        code = "if (x === y) { }\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0

    def test_strict_neq_not_flagged(self, analyzer: LooseEqualityAnalyzer) -> None:
        code = "if (x !== y) { }\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0

    def test_null_comparison_not_flagged(self, analyzer: LooseEqualityAnalyzer) -> None:
        code = "if (x == null) { }\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0

    def test_undefined_comparison_not_flagged(self, analyzer: LooseEqualityAnalyzer) -> None:
        code = "if (x != undefined) { }\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0

    def test_null_on_left_not_flagged(self, analyzer: LooseEqualityAnalyzer) -> None:
        code = "if (null == x) { }\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0

    def test_multiple_loose_comparisons(self, analyzer: LooseEqualityAnalyzer) -> None:
        code = "if (a == b && c != d) { }\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        eq_issues = [i for i in result.issues if i.issue_type == ISSUE_LOOSE_EQ]
        neq_issues = [i for i in result.issues if i.issue_type == ISSUE_LOOSE_NEQ]
        assert len(eq_issues) == 1
        assert len(neq_issues) == 1

    def test_loose_eq_line_number(self, analyzer: LooseEqualityAnalyzer) -> None:
        code = "const a = 1;\nif (x == y) { }\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 1
        assert result.issues[0].line == 2

    def test_loose_eq_context(self, analyzer: LooseEqualityAnalyzer) -> None:
        code = "if (x == y) { }\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 1
        assert "x == y" in result.issues[0].context

    def test_loose_eq_severity(self, analyzer: LooseEqualityAnalyzer) -> None:
        code = "if (x == y) { }\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert result.issues[0].severity == "medium"

    def test_function_call_comparison(self, analyzer: LooseEqualityAnalyzer) -> None:
        code = "if (getName() == 'foo') { }\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_LOOSE_EQ for i in result.issues)

    def test_number_comparison(self, analyzer: LooseEqualityAnalyzer) -> None:
        code = "if (count == 5) { }\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_LOOSE_EQ for i in result.issues)

    def test_no_comparisons_clean(self, analyzer: LooseEqualityAnalyzer) -> None:
        code = "const x = 1 + 2;\nconsole.log(x);\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0


# ── TypeScript tests ──────────────────────────────────────


class TestTypeScriptLooseEquality:
    def test_loose_eq_detected(self, analyzer: LooseEqualityAnalyzer) -> None:
        code = "if (x == y) { }\n"
        path = _write_tmp(code, ".ts")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_LOOSE_EQ for i in result.issues)

    def test_loose_neq_detected(self, analyzer: LooseEqualityAnalyzer) -> None:
        code = "if (x != y) { }\n"
        path = _write_tmp(code, ".ts")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_LOOSE_NEQ for i in result.issues)

    def test_strict_eq_not_flagged(self, analyzer: LooseEqualityAnalyzer) -> None:
        code = "if (x === y) { }\n"
        path = _write_tmp(code, ".ts")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0

    def test_null_not_flagged(self, analyzer: LooseEqualityAnalyzer) -> None:
        code = "if (x == null) { }\n"
        path = _write_tmp(code, ".ts")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0

    def test_undefined_not_flagged(self, analyzer: LooseEqualityAnalyzer) -> None:
        code = "if (x != undefined) { }\n"
        path = _write_tmp(code, ".ts")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0


# ── TSX tests ─────────────────────────────────────────────


class TestTSXLooseEquality:
    def test_loose_eq_detected(self, analyzer: LooseEqualityAnalyzer) -> None:
        code = "if (props.count == 0) { return null; }\n"
        path = _write_tmp(code, ".tsx")
        result = analyzer.analyze_file(path)
        assert any(i.issue_type == ISSUE_LOOSE_EQ for i in result.issues)

    def test_strict_eq_not_flagged(self, analyzer: LooseEqualityAnalyzer) -> None:
        code = "if (props.count === 0) { return null; }\n"
        path = _write_tmp(code, ".tsx")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0


# ── Python tests (unsupported) ────────────────────────────


class TestPythonUnsupported:
    def test_python_not_analyzed(self, analyzer: LooseEqualityAnalyzer) -> None:
        code = "if x == y:\n    pass\n"
        path = _write_tmp(code, ".py")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0
        assert result.total_comparisons == 0


# ── Java tests (unsupported) ──────────────────────────────


class TestJavaUnsupported:
    def test_java_not_analyzed(self, analyzer: LooseEqualityAnalyzer) -> None:
        code = "public class A { boolean b = (x == y); }\n"
        path = _write_tmp(code, ".java")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0
        assert result.total_comparisons == 0


# ── Go tests (unsupported) ────────────────────────────────


class TestGoUnsupported:
    def test_go_not_analyzed(self, analyzer: LooseEqualityAnalyzer) -> None:
        code = "if x == y { }\n"
        path = _write_tmp(code, ".go")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0
        assert result.total_comparisons == 0


# ── Edge cases ────────────────────────────────────────────


class TestEdgeCases:
    def test_nonexistent_file(self, analyzer: LooseEqualityAnalyzer) -> None:
        result = analyzer.analyze_file("/nonexistent/file.js")
        assert len(result.issues) == 0
        assert result.total_comparisons == 0

    def test_empty_file(self, analyzer: LooseEqualityAnalyzer) -> None:
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".js", delete=False, encoding="utf-8",
        )
        f.write("")
        f.close()
        result = analyzer.analyze_file(f.name)
        assert len(result.issues) == 0

    def test_to_dict(self, analyzer: LooseEqualityAnalyzer) -> None:
        code = "if (x == y) { }\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        d = result.to_dict()
        assert "file_path" in d
        assert "total_comparisons" in d
        assert "issue_count" in d
        assert "issues" in d

    def test_issue_to_dict(self, analyzer: LooseEqualityAnalyzer) -> None:
        code = "if (x == y) { }\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 1
        d = result.issues[0].to_dict()
        assert d["issue_type"] == ISSUE_LOOSE_EQ
        assert d["severity"] == "medium"
        assert "line" in d
        assert "context" in d

    def test_suggestion_present(self, analyzer: LooseEqualityAnalyzer) -> None:
        code = "if (x == y) { }\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 1
        assert "===" in result.issues[0].suggestion

    def test_chained_comparisons(self, analyzer: LooseEqualityAnalyzer) -> None:
        code = "if (a == b && c == d && e != f) { }\n"
        path = _write_tmp(code, ".js")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 3
