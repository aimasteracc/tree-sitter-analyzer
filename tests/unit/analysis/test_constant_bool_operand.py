"""Tests for ConstantBoolOperandAnalyzer."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.constant_bool_operand import (
    ISSUE_CONSTANT_BOOL_OPERAND,
    ConstantBoolOperandAnalyzer,
    ConstantBoolOperandIssue,
    ConstantBoolOperandResult,
)

SEVERITY_MEDIUM = "medium"


@pytest.fixture
def analyzer() -> ConstantBoolOperandAnalyzer:
    return ConstantBoolOperandAnalyzer()


def _write_tmp(content: str, suffix: str = ".py") -> str:
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="test_cbo_")
    with open(fd, "w") as f:
        f.write(content)
    return path


class TestConstantBoolOperandIssue:
    def test_frozen(self) -> None:
        issue = ConstantBoolOperandIssue(
            line_number=1,
            issue_type=ISSUE_CONSTANT_BOOL_OPERAND,
            severity=SEVERITY_MEDIUM,
            description="desc",
            operand_snippet="'hello'",
        )
        with pytest.raises(AttributeError):
            issue.line_number = 2  # type: ignore[misc]

    def test_to_dict(self) -> None:
        issue = ConstantBoolOperandIssue(
            line_number=5,
            issue_type=ISSUE_CONSTANT_BOOL_OPERAND,
            severity=SEVERITY_MEDIUM,
            description="Non-boolean constant used",
            operand_snippet="'b'",
        )
        d = issue.to_dict()
        assert d["line_number"] == 5
        assert d["issue_type"] == ISSUE_CONSTANT_BOOL_OPERAND
        assert d["severity"] == SEVERITY_MEDIUM
        assert d["operand_snippet"] == "'b'"
        assert "suggestion" in d

    def test_suggestion(self) -> None:
        issue = ConstantBoolOperandIssue(
            line_number=1,
            issue_type=ISSUE_CONSTANT_BOOL_OPERAND,
            severity=SEVERITY_MEDIUM,
            description="d",
            operand_snippet="s",
        )
        assert issue.suggestion != ""


class TestConstantBoolOperandResult:
    def test_to_dict(self) -> None:
        result = ConstantBoolOperandResult(
            total_boolean_expressions=3,
            issues=(
                ConstantBoolOperandIssue(
                    line_number=1,
                    issue_type=ISSUE_CONSTANT_BOOL_OPERAND,
                    severity=SEVERITY_MEDIUM,
                    description="d",
                    operand_snippet="s",
                ),
            ),
            file_path="test.py",
        )
        d = result.to_dict()
        assert d["total_boolean_expressions"] == 3
        assert d["issue_count"] == 1
        assert d["file_path"] == "test.py"
        assert len(d["issues"]) == 1

    def test_empty_issues(self) -> None:
        result = ConstantBoolOperandResult(
            total_boolean_expressions=0,
            issues=(),
            file_path="test.py",
        )
        d = result.to_dict()
        assert d["issue_count"] == 0
        assert d["issues"] == []


class TestAnalyzerBasic:
    def test_nonexistent_file(self, analyzer: ConstantBoolOperandAnalyzer) -> None:
        result = analyzer.analyze_file("/nonexistent/file.py")
        assert result.total_boolean_expressions == 0
        assert result.issues == ()

    def test_unsupported_extension(self, analyzer: ConstantBoolOperandAnalyzer) -> None:
        path = _write_tmp("x = 1", suffix=".js")
        result = analyzer.analyze_file(path)
        assert result.total_boolean_expressions == 0
        assert result.issues == ()

    def test_empty_file(self, analyzer: ConstantBoolOperandAnalyzer) -> None:
        path = _write_tmp("")
        result = analyzer.analyze_file(path)
        assert result.total_boolean_expressions == 0
        assert result.issues == ()

    def test_no_boolean_expressions(self, analyzer: ConstantBoolOperandAnalyzer) -> None:
        path = _write_tmp("x = 1\ny = 2\nz = x + y\n")
        result = analyzer.analyze_file(path)
        assert result.total_boolean_expressions == 0
        assert result.issues == ()


class TestStringConstants:
    def test_or_with_string_constant(self, analyzer: ConstantBoolOperandAnalyzer) -> None:
        path = _write_tmp('if x == "a" or "b":\n    pass\n')
        result = analyzer.analyze_file(path)
        assert result.total_boolean_expressions >= 1
        assert len(result.issues) >= 1
        snippets = [i.operand_snippet for i in result.issues]
        assert any('"b"' in s or "'b'" in s for s in snippets)

    def test_and_with_string_constant(self, analyzer: ConstantBoolOperandAnalyzer) -> None:
        path = _write_tmp('if x == "a" and "b":\n    pass\n')
        result = analyzer.analyze_file(path)
        assert len(result.issues) >= 1

    def test_multiple_string_constants(self, analyzer: ConstantBoolOperandAnalyzer) -> None:
        code = 'if "a" or "b" or "c":\n    pass\n'
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        assert len(result.issues) >= 2


class TestNumericConstants:
    def test_or_with_number(self, analyzer: ConstantBoolOperandAnalyzer) -> None:
        path = _write_tmp("if x or 42:\n    pass\n")
        result = analyzer.analyze_file(path)
        assert len(result.issues) >= 1
        assert any("42" in i.operand_snippet for i in result.issues)

    def test_and_with_zero(self, analyzer: ConstantBoolOperandAnalyzer) -> None:
        path = _write_tmp("if x and 0:\n    pass\n")
        result = analyzer.analyze_file(path)
        assert len(result.issues) >= 1

    def test_negative_number(self, analyzer: ConstantBoolOperandAnalyzer) -> None:
        path = _write_tmp("if x or -1:\n    pass\n")
        result = analyzer.analyze_file(path)
        assert len(result.issues) >= 1

    def test_float_constant(self, analyzer: ConstantBoolOperandAnalyzer) -> None:
        path = _write_tmp("if x or 3.14:\n    pass\n")
        result = analyzer.analyze_file(path)
        assert len(result.issues) >= 1


class TestCollectionConstants:
    def test_or_with_list(self, analyzer: ConstantBoolOperandAnalyzer) -> None:
        path = _write_tmp("if x or [1, 2, 3]:\n    pass\n")
        result = analyzer.analyze_file(path)
        assert len(result.issues) >= 1

    def test_or_with_dict(self, analyzer: ConstantBoolOperandAnalyzer) -> None:
        path = _write_tmp("if x or {'a': 1}:\n    pass\n")
        result = analyzer.analyze_file(path)
        assert len(result.issues) >= 1

    def test_or_with_tuple(self, analyzer: ConstantBoolOperandAnalyzer) -> None:
        path = _write_tmp("if x or (1, 2):\n    pass\n")
        result = analyzer.analyze_file(path)
        assert len(result.issues) >= 1


class TestBooleanConstants:
    def test_true_not_flagged(self, analyzer: ConstantBoolOperandAnalyzer) -> None:
        path = _write_tmp("if x or True:\n    pass\n")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0

    def test_false_not_flagged(self, analyzer: ConstantBoolOperandAnalyzer) -> None:
        path = _write_tmp("if x and False:\n    pass\n")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0

    def test_none_not_flagged(self, analyzer: ConstantBoolOperandAnalyzer) -> None:
        path = _write_tmp("if x or None:\n    pass\n")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0


class TestCleanCode:
    def test_normal_or(self, analyzer: ConstantBoolOperandAnalyzer) -> None:
        path = _write_tmp("if x or y:\n    pass\n")
        result = analyzer.analyze_file(path)
        assert result.total_boolean_expressions >= 1
        assert len(result.issues) == 0

    def test_normal_and(self, analyzer: ConstantBoolOperandAnalyzer) -> None:
        path = _write_tmp("if x and y:\n    pass\n")
        result = analyzer.analyze_file(path)
        assert result.total_boolean_expressions >= 1
        assert len(result.issues) == 0

    def test_comparison_or_comparison(self, analyzer: ConstantBoolOperandAnalyzer) -> None:
        code = 'if x == "a" or x == "b":\n    pass\n'
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0

    def test_function_call_operand(self, analyzer: ConstantBoolOperandAnalyzer) -> None:
        path = _write_tmp("if check() or validate():\n    pass\n")
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0

    def test_chained_comparisons(self, analyzer: ConstantBoolOperandAnalyzer) -> None:
        code = "if a > 0 and b > 0 and c > 0:\n    pass\n"
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        assert len(result.issues) == 0


class TestRealWorldPatterns:
    def test_classic_pitfall(self, analyzer: ConstantBoolOperandAnalyzer) -> None:
        """if x == 'a' or 'b' — the classic Python mistake."""
        code = 'if status == "active" or "pending":\n    process()\n'
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        assert len(result.issues) >= 1
        assert result.issues[0].issue_type == ISSUE_CONSTANT_BOOL_OPERAND
        assert result.issues[0].severity == SEVERITY_MEDIUM

    def test_nested_boolean(self, analyzer: ConstantBoolOperandAnalyzer) -> None:
        code = 'if (x or "fallback") and y:\n    pass\n'
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        assert len(result.issues) >= 1

    def test_assignment_with_or(self, analyzer: ConstantBoolOperandAnalyzer) -> None:
        code = 'result = x or "default"\n'
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        assert len(result.issues) >= 1

    def test_while_condition(self, analyzer: ConstantBoolOperandAnalyzer) -> None:
        code = 'while x or "stop":\n    break\n'
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        assert len(result.issues) >= 1

    def test_return_with_or(self, analyzer: ConstantBoolOperandAnalyzer) -> None:
        code = 'def f():\n    return x or "fallback"\n'
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        assert len(result.issues) >= 1


class TestEdgeCases:
    def test_parenthesized_constant(self, analyzer: ConstantBoolOperandAnalyzer) -> None:
        code = 'if x or ("hello"):\n    pass\n'
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        assert len(result.issues) >= 1

    def test_fstring_constant(self, analyzer: ConstantBoolOperandAnalyzer) -> None:
        code = 'if x or f"hello {name}":\n    pass\n'
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        assert len(result.issues) >= 1

    def test_long_snippet_truncated(self, analyzer: ConstantBoolOperandAnalyzer) -> None:
        long_str = "x" * 100
        code = f'if a or "{long_str}":\n    pass\n'
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        if result.issues:
            assert len(result.issues[0].operand_snippet) <= 53

    def test_analyze_file_with_path_object(self, analyzer: ConstantBoolOperandAnalyzer) -> None:
        path = _write_tmp("x = 1\n")
        result = analyzer.analyze_file(Path(path))
        assert result.file_path == path
