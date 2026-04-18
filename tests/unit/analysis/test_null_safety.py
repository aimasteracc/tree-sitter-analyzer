"""Tests for Null Safety Analyzer — Python + Multi-Language."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.null_safety import (
    ISSUE_CHAINED_ACCESS,
    ISSUE_DICT_UNSAFE_ACCESS,
    ISSUE_MISSING_NULL_CHECK,
    ISSUE_UNCHECKED_ACCESS,
    NullSafetyAnalyzer,
    NullSafetyIssue,
    NullSafetyResult,
    _empty_result,
    _severity_counts,
)

ANALYZER = NullSafetyAnalyzer


def _write_tmp(content: str, suffix: str) -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


# ── Dataclass tests ──────────────────────────────────────────────────────


class TestDataclasses:
    def test_issue_frozen(self) -> None:
        issue = NullSafetyIssue(
            line=1,
            issue_type=ISSUE_UNCHECKED_ACCESS,
            severity="high",
            variable="x",
            description="x may be None",
            suggestion="Add check",
        )
        assert issue.line == 1
        with pytest.raises(AttributeError):
            issue.line = 5  # type: ignore[misc]

    def test_result_frozen(self) -> None:
        result = NullSafetyResult(
            issues=(),
            total_issues=0,
            high_severity=0,
            medium_severity=0,
            low_severity=0,
            file_path="test.py",
            language="python",
        )
        assert result.total_issues == 0
        with pytest.raises(AttributeError):
            result.total_issues = 99  # type: ignore[misc]

    def test_result_to_dict(self) -> None:
        issue = NullSafetyIssue(
            line=1,
            issue_type=ISSUE_UNCHECKED_ACCESS,
            severity="high",
            variable="x",
            description="desc",
            suggestion="fix",
        )
        result = NullSafetyResult(
            issues=(issue,),
            total_issues=1,
            high_severity=1,
            medium_severity=0,
            low_severity=0,
            file_path="test.py",
            language="python",
        )
        d = result.to_dict()
        assert d["total_issues"] == 1
        assert len(d["issues"]) == 1
        assert d["issues"][0]["variable"] == "x"

    def test_empty_result(self) -> None:
        result = _empty_result("f.py", "python")
        assert result.total_issues == 0
        assert result.file_path == "f.py"

    def test_severity_counts(self) -> None:
        issues = (
            NullSafetyIssue(1, "a", "high", "x", "d", "s"),
            NullSafetyIssue(2, "b", "high", "y", "d", "s"),
            NullSafetyIssue(3, "c", "medium", "z", "d", "s"),
        )
        h, m, l = _severity_counts(issues)
        assert h == 2
        assert m == 1
        assert l == 0


# ── Edge case tests ──────────────────────────────────────────────────────


class TestEdgeCases:
    def test_nonexistent_file(self) -> None:
        analyzer = ANALYZER()
        result = analyzer.analyze_file("/nonexistent/file.py")
        assert result.total_issues == 0

    def test_unsupported_extension(self) -> None:
        p = _write_tmp("x = 1", ".txt")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert result.language == "unknown"

    def test_empty_file(self) -> None:
        p = _write_tmp("", ".py")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert result.total_issues == 0

    def test_safe_code_no_issues(self) -> None:
        p = _write_tmp("x = 42\nprint(x)\n", ".py")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert result.total_issues == 0


# ── Python analysis tests ────────────────────────────────────────────────


class TestPythonAnalysis:
    def test_none_assignment_unchecked_access(self) -> None:
        code = """\
def foo():
    result = None
    return result.strip()
"""
        p = _write_tmp(code, ".py")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert result.total_issues >= 1
        assert any(i.issue_type == ISSUE_UNCHECKED_ACCESS for i in result.issues)

    def test_none_assignment_with_check_safe(self) -> None:
        code = """\
def foo():
    result = None
    if result is not None:
        return result.strip()
    return ""
"""
        p = _write_tmp(code, ".py")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert not any(
            i.issue_type == ISSUE_UNCHECKED_ACCESS and i.variable == "result"
            for i in result.issues
        )

    def test_optional_param_used_directly(self) -> None:
        code = """\
def greet(name=None):
    return name.upper()
"""
        p = _write_tmp(code, ".py")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert result.total_issues >= 1

    def test_optional_param_with_check_safe(self) -> None:
        code = """\
def greet(name=None):
    if name is not None:
        return name.upper()
    return "HELLO"
"""
        p = _write_tmp(code, ".py")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert not any(
            i.issue_type == ISSUE_UNCHECKED_ACCESS and i.variable == "name"
            for i in result.issues
        )

    def test_dict_bracket_access(self) -> None:
        code = """\
data = {"key": "value"}
x = data["missing_key"]
"""
        p = _write_tmp(code, ".py")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert any(
            i.issue_type == ISSUE_DICT_UNSAFE_ACCESS for i in result.issues
        )

    def test_dict_get_safe(self) -> None:
        code = """\
data = {"key": "value"}
x = data.get("missing_key", "default")
"""
        p = _write_tmp(code, ".py")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert not any(
            i.issue_type == ISSUE_DICT_UNSAFE_ACCESS and i.variable == "data"
            for i in result.issues
        )

    def test_multiple_none_sources(self) -> None:
        code = """\
def foo():
    a = None
    b = None
    return a.strip() + b.upper()
"""
        p = _write_tmp(code, ".py")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert result.total_issues >= 2

    def test_isinstance_check_safe(self) -> None:
        code = """\
def foo(val=None):
    if isinstance(val, str):
        return val.upper()
    return ""
"""
        p = _write_tmp(code, ".py")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert not any(
            i.issue_type == ISSUE_UNCHECKED_ACCESS and i.variable == "val"
            for i in result.issues
        )

    def test_result_has_correct_language(self) -> None:
        p = _write_tmp("x = 1\n", ".py")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert result.language == "python"

    def test_severity_is_correct(self) -> None:
        code = """\
def foo():
    result = None
    return result.strip()
"""
        p = _write_tmp(code, ".py")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        unchecked = [i for i in result.issues if i.issue_type == ISSUE_UNCHECKED_ACCESS]
        assert all(i.severity == "high" for i in unchecked)


# ── JavaScript/TypeScript analysis tests ─────────────────────────────────


class TestJavaScriptAnalysis:
    def test_null_assignment_unchecked_access(self) -> None:
        code = """\
function foo() {
    let result = null;
    return result.toString();
}
"""
        p = _write_tmp(code, ".js")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert result.total_issues >= 1
        assert any(i.issue_type == ISSUE_UNCHECKED_ACCESS for i in result.issues)

    def test_undefined_assignment_unchecked_access(self) -> None:
        code = """\
function foo() {
    let result = undefined;
    return result.toString();
}
"""
        p = _write_tmp(code, ".js")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert result.total_issues >= 1

    def test_null_with_check_safe(self) -> None:
        code = """\
function foo() {
    let result = null;
    if (result !== null) {
        return result.toString();
    }
}
"""
        p = _write_tmp(code, ".js")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert not any(
            i.issue_type == ISSUE_UNCHECKED_ACCESS and i.variable == "result"
            for i in result.issues
        )

    def test_chained_access_without_optional(self) -> None:
        code = """\
function foo() {
    return user.profile.name;
}
"""
        p = _write_tmp(code, ".js")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert any(
            i.issue_type == ISSUE_CHAINED_ACCESS for i in result.issues
        )

    def test_language_detected_js(self) -> None:
        p = _write_tmp("let x = 1;\n", ".js")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert result.language == "javascript"

    def test_language_detected_ts(self) -> None:
        p = _write_tmp("let x: number = 1;\n", ".ts")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert result.language == "typescript"


# ── Java analysis tests ──────────────────────────────────────────────────


class TestJavaAnalysis:
    def test_null_assignment_unchecked_access(self) -> None:
        code = """\
public class Test {
    public String foo() {
        String result = null;
        return result.toUpperCase();
    }
}
"""
        p = _write_tmp(code, ".java")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert result.total_issues >= 1
        assert any(i.issue_type == ISSUE_UNCHECKED_ACCESS for i in result.issues)

    def test_null_with_check_safe(self) -> None:
        code = """\
public class Test {
    public String foo() {
        String result = null;
        if (result != null) {
            return result.toUpperCase();
        }
        return "";
    }
}
"""
        p = _write_tmp(code, ".java")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert not any(
            i.issue_type == ISSUE_UNCHECKED_ACCESS and i.variable == "result"
            for i in result.issues
        )

    def test_chained_method_call(self) -> None:
        code = """\
public class Test {
    public String foo() {
        return getUser().getProfile().getName();
    }
}
"""
        p = _write_tmp(code, ".java")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert any(
            i.issue_type == ISSUE_CHAINED_ACCESS for i in result.issues
        )

    def test_language_detected_java(self) -> None:
        p = _write_tmp("public class T {}\n", ".java")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert result.language == "java"


# ── Go analysis tests ────────────────────────────────────────────────────


class TestGoAnalysis:
    def test_nil_dereference(self) -> None:
        code = """\
package main

func foo() {
    ptr := nil
    _ = *ptr
}
"""
        p = _write_tmp(code, ".go")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert result.total_issues >= 1

    def test_nil_with_check_safe(self) -> None:
        code = """\
package main

func foo() {
    ptr := nil
    if ptr != nil {
        _ = *ptr
    }
}
"""
        p = _write_tmp(code, ".go")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert not any(i.variable == "ptr" for i in result.issues)

    def test_map_access_without_comma_ok(self) -> None:
        code = """\
package main

func foo() {
    m := map[string]int{"a": 1}
    v := m["b"]
    _ = v
}
"""
        p = _write_tmp(code, ".go")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert any(
            i.issue_type == ISSUE_DICT_UNSAFE_ACCESS for i in result.issues
        )

    def test_map_access_with_comma_ok_safe(self) -> None:
        code = """\
package main

func foo() {
    m := map[string]int{"a": 1}
    v, ok := m["b"]
    _ = v
    _ = ok
}
"""
        p = _write_tmp(code, ".go")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert not any(
            i.issue_type == ISSUE_DICT_UNSAFE_ACCESS and i.variable == "m"
            for i in result.issues
        )

    def test_language_detected_go(self) -> None:
        p = _write_tmp("package main\n", ".go")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert result.language == "go"

    def test_nil_method_call(self) -> None:
        code = """\
package main

func main() {
    f := nil
    f.Bar()
}
"""
        p = _write_tmp(code, ".go")
        analyzer = ANALYZER()
        result = analyzer.analyze_file(p)
        assert any(
            i.issue_type == ISSUE_MISSING_NULL_CHECK for i in result.issues
        )


# ── Cross-language severity tests ────────────────────────────────────────


class TestCrossLanguageSeverity:
    def test_python_high_severity(self) -> None:
        code = """\
def foo():
    result = None
    return result.strip()
"""
        p = _write_tmp(code, ".py")
        result = ANALYZER().analyze_file(p)
        assert result.high_severity >= 1

    def test_python_dict_medium_severity(self) -> None:
        code = """\
data = {"a": 1}
x = data["b"]
"""
        p = _write_tmp(code, ".py")
        result = ANALYZER().analyze_file(p)
        assert result.medium_severity >= 1

    def test_js_chained_medium_severity(self) -> None:
        code = """\
function foo() {
    return user.profile.name;
}
"""
        p = _write_tmp(code, ".js")
        result = ANALYZER().analyze_file(p)
        assert result.medium_severity >= 1
