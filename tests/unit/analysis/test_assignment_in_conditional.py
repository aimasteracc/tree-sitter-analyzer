"""Tests for Assignment in Conditional Detector."""
from __future__ import annotations

import os
import tempfile

from tree_sitter_analyzer.analysis.assignment_in_conditional import (
    ISSUE_ASSIGNMENT_IN_CONDITIONAL,
    AssignmentInConditionalAnalyzer,
    AssignmentInConditionalResult,
)


def _write_tmp(content: str, suffix: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return f.name


# ── JavaScript Tests ──


class TestJSAssignmentInIf:
    def test_detects_assignment_in_if(self) -> None:
        code = """\
if (x = 5) {
    console.log(x);
}
"""
        path = _write_tmp(code, ".js")
        try:
            result = AssignmentInConditionalAnalyzer().analyze_file(path)
            assert isinstance(result, AssignmentInConditionalResult)
            assert result.total_issues >= 1
            assert result.issues[0].issue_type == ISSUE_ASSIGNMENT_IN_CONDITIONAL
        finally:
            os.unlink(path)

    def test_no_issue_comparison(self) -> None:
        code = """\
if (x === 5) {
    console.log(x);
}
"""
        path = _write_tmp(code, ".js")
        try:
            result = AssignmentInConditionalAnalyzer().analyze_file(path)
            assert result.total_issues == 0
        finally:
            os.unlink(path)

    def test_detects_assignment_in_while(self) -> None:
        code = """\
while (x = getNext()) {
    process(x);
}
"""
        path = _write_tmp(code, ".js")
        try:
            result = AssignmentInConditionalAnalyzer().analyze_file(path)
            assert result.total_issues >= 1
            assert result.issues[0].statement_type == "while"
        finally:
            os.unlink(path)


# ── TypeScript Tests ──


class TestTSAssignmentInIf:
    def test_detects_assignment_ts(self) -> None:
        code = """\
if (x = 5) {
    console.log(x);
}
"""
        path = _write_tmp(code, ".ts")
        try:
            result = AssignmentInConditionalAnalyzer().analyze_file(path)
            assert result.total_issues >= 1
        finally:
            os.unlink(path)

    def test_no_issue_comparison_ts(self) -> None:
        code = """\
if (x === 5) {
    console.log(x);
}
"""
        path = _write_tmp(code, ".ts")
        try:
            result = AssignmentInConditionalAnalyzer().analyze_file(path)
            assert result.total_issues == 0
        finally:
            os.unlink(path)


# ── Java Tests ──


class TestJavaAssignmentInIf:
    def test_detects_assignment_java(self) -> None:
        code = """\
public class Foo {
    public void bar() {
        if (x = 5) {
            System.out.println(x);
        }
    }
}
"""
        path = _write_tmp(code, ".java")
        try:
            result = AssignmentInConditionalAnalyzer().analyze_file(path)
            assert result.total_issues >= 1
        finally:
            os.unlink(path)

    def test_no_issue_comparison_java(self) -> None:
        code = """\
public class Foo {
    public void bar() {
        if (x == 5) {
            System.out.println(x);
        }
    }
}
"""
        path = _write_tmp(code, ".java")
        try:
            result = AssignmentInConditionalAnalyzer().analyze_file(path)
            assert result.total_issues == 0
        finally:
            os.unlink(path)


# ── C Tests ──


class TestCAssignmentInIf:
    def test_detects_assignment_c(self) -> None:
        code = """\
int main() {
    if (x = 5) {
        printf("%d", x);
    }
    return 0;
}
"""
        path = _write_tmp(code, ".c")
        try:
            result = AssignmentInConditionalAnalyzer().analyze_file(path)
            assert result.total_issues >= 1
        finally:
            os.unlink(path)

    def test_no_issue_comparison_c(self) -> None:
        code = """\
int main() {
    if (x == 5) {
        printf("%d", x);
    }
    return 0;
}
"""
        path = _write_tmp(code, ".c")
        try:
            result = AssignmentInConditionalAnalyzer().analyze_file(path)
            assert result.total_issues == 0
        finally:
            os.unlink(path)


# ── General Tests ──


class TestGeneral:
    def test_unsupported_python(self) -> None:
        path = _write_tmp("if x = 5:\n    pass", ".py")
        try:
            result = AssignmentInConditionalAnalyzer().analyze_file(path)
            assert result.total_issues == 0
        finally:
            os.unlink(path)

    def test_empty_file(self) -> None:
        path = _write_tmp("", ".js")
        try:
            result = AssignmentInConditionalAnalyzer().analyze_file(path)
            assert result.total_issues == 0
        finally:
            os.unlink(path)

    def test_result_to_dict(self) -> None:
        code = """\
if (x = 5) { console.log(x); }
"""
        path = _write_tmp(code, ".js")
        try:
            result = AssignmentInConditionalAnalyzer().analyze_file(path)
            d = result.to_dict()
            assert "file_path" in d
            assert "issues" in d
            assert "total_issues" in d
        finally:
            os.unlink(path)

    def test_issue_to_dict(self) -> None:
        code = """\
if (x = 5) { console.log(x); }
"""
        path = _write_tmp(code, ".js")
        try:
            result = AssignmentInConditionalAnalyzer().analyze_file(path)
            assert result.total_issues >= 1
            d = result.issues[0].to_dict()
            assert "issue_type" in d
            assert "line" in d
            assert "severity" in d
            assert "statement_type" in d
            assert "suggestion" in d
        finally:
            os.unlink(path)

    def test_severity_is_high(self) -> None:
        code = """\
if (x = 5) { console.log(x); }
"""
        path = _write_tmp(code, ".js")
        try:
            result = AssignmentInConditionalAnalyzer().analyze_file(path)
            assert result.total_issues >= 1
            assert result.issues[0].severity == "high"
        finally:
            os.unlink(path)
