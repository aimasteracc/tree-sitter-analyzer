"""Tests for Redundant Else Detector."""
from __future__ import annotations

import tempfile

import pytest

from tree_sitter_analyzer.analysis.redundant_else import (
    ISSUE_REDUNDANT_ELSE,
    RedundantElseAnalyzer,
    RedundantElseIssue,
    RedundantElseResult,
)

ANALYZER = RedundantElseAnalyzer()


def _analyze(code: str, ext: str = ".py") -> RedundantElseResult:
    with tempfile.NamedTemporaryFile(
        suffix=ext, mode="w", delete=False, encoding="utf-8",
    ) as f:
        f.write(code)
        f.flush()
        return ANALYZER.analyze_file(f.name)


# ── Classification tests ──────────────────────────────────────────────────


class TestClassification:
    def test_redundant_else_constant(self) -> None:
        assert ISSUE_REDUNDANT_ELSE == "redundant_else"


# ── Dataclass tests ──────────────────────────────────────────────────────


class TestDataclasses:
    def test_issue_frozen(self) -> None:
        issue = RedundantElseIssue(
            line_number=5,
            issue_type=ISSUE_REDUNDANT_ELSE,
            variable_name="else",
            severity="low",
            description="test",
        )
        assert issue.line_number == 5
        with pytest.raises(AttributeError):
            issue.line_number = 10  # type: ignore[misc]

    def test_issue_to_dict(self) -> None:
        issue = RedundantElseIssue(
            line_number=3,
            issue_type=ISSUE_REDUNDANT_ELSE,
            variable_name="else",
            severity="low",
            description="test",
        )
        d = issue.to_dict()
        assert d["line_number"] == 3
        assert d["issue_type"] == ISSUE_REDUNDANT_ELSE
        assert "suggestion" in d

    def test_result_to_dict(self) -> None:
        issue = RedundantElseIssue(
            line_number=1,
            issue_type=ISSUE_REDUNDANT_ELSE,
            variable_name="else",
            severity="low",
            description="test",
        )
        result = RedundantElseResult(
            total_ifs=3,
            issues=(issue,),
            file_path="test.py",
        )
        d = result.to_dict()
        assert d["total_ifs"] == 3
        assert d["issue_count"] == 1


# ── Python redundant else detection ──────────────────────────────────────


class TestPythonRedundantElse:
    def test_redundant_else_return(self) -> None:
        code = """\
def foo(x):
    if x > 0:
        return "pos"
    else:
        return "non-pos"
"""
        result = _analyze(code)
        assert any(i.issue_type == ISSUE_REDUNDANT_ELSE for i in result.issues)

    def test_redundant_else_raise(self) -> None:
        code = """\
def foo(x):
    if x is None:
        raise ValueError()
    else:
        return x
"""
        result = _analyze(code)
        assert any(i.issue_type == ISSUE_REDUNDANT_ELSE for i in result.issues)

    def test_no_issue_without_else(self) -> None:
        code = """\
def foo(x):
    if x > 0:
        return "pos"
    return "non-pos"
"""
        result = _analyze(code)
        assert len(result.issues) == 0

    def test_no_issue_if_not_terminating(self) -> None:
        code = """\
def foo(x):
    if x > 0:
        print("pos")
    else:
        print("non-pos")
"""
        result = _analyze(code)
        assert len(result.issues) == 0

    def test_redundant_else_break(self) -> None:
        code = """\
def foo():
    for i in range(10):
        if i == 5:
            break
        else:
            continue
"""
        result = _analyze(code)
        assert any(i.issue_type == ISSUE_REDUNDANT_ELSE for i in result.issues)

    def test_no_else_no_issue(self) -> None:
        code = """\
def foo(x):
    if x > 0:
        return "pos"
"""
        result = _analyze(code)
        assert len(result.issues) == 0

    def test_if_count(self) -> None:
        code = """\
def foo():
    if True:
        pass
    if False:
        pass
"""
        result = _analyze(code)
        assert result.total_ifs == 2

    def test_empty_file(self) -> None:
        result = _analyze("")
        assert result.total_ifs == 0
        assert len(result.issues) == 0


# ── JavaScript redundant else detection ──────────────────────────────────


class TestJavaScriptRedundantElse:
    def test_js_redundant_else_return(self) -> None:
        code = """\
function foo(x) {
    if (x > 0) {
        return "pos";
    } else {
        return "non-pos";
    }
}
"""
        result = _analyze(code, ".js")
        assert any(i.issue_type == ISSUE_REDUNDANT_ELSE for i in result.issues)

    def test_js_no_issue_if_not_terminating(self) -> None:
        code = """\
function foo(x) {
    if (x > 0) {
        console.log("pos");
    } else {
        console.log("non-pos");
    }
}
"""
        result = _analyze(code, ".js")
        assert len(result.issues) == 0

    def test_js_redundant_else_throw(self) -> None:
        code = """\
function foo(x) {
    if (x === null) {
        throw new Error();
    } else {
        return x;
    }
}
"""
        result = _analyze(code, ".js")
        assert any(i.issue_type == ISSUE_REDUNDANT_ELSE for i in result.issues)


# ── TypeScript redundant else detection ──────────────────────────────────


class TestTypeScriptRedundantElse:
    def test_ts_redundant_else(self) -> None:
        code = """\
function foo(x: number): string {
    if (x > 0) {
        return "pos";
    } else {
        return "non-pos";
    }
}
"""
        result = _analyze(code, ".ts")
        assert any(i.issue_type == ISSUE_REDUNDANT_ELSE for i in result.issues)

    def test_ts_no_issue(self) -> None:
        code = """\
function foo(x: number): string {
    if (x > 0) {
        return "pos";
    }
    return "non-pos";
}
"""
        result = _analyze(code, ".ts")
        assert len(result.issues) == 0


# ── Java redundant else detection ────────────────────────────────────────


class TestJavaRedundantElse:
    def test_java_redundant_else_return(self) -> None:
        code = """\
public class Foo {
    public String bar(int x) {
        if (x > 0) {
            return "pos";
        } else {
            return "non-pos";
        }
    }
}
"""
        result = _analyze(code, ".java")
        assert any(i.issue_type == ISSUE_REDUNDANT_ELSE for i in result.issues)

    def test_java_redundant_else_throw(self) -> None:
        code = """\
public class Foo {
    public String bar(Integer x) {
        if (x == null) {
            throw new IllegalArgumentException();
        } else {
            return x.toString();
        }
    }
}
"""
        result = _analyze(code, ".java")
        assert any(i.issue_type == ISSUE_REDUNDANT_ELSE for i in result.issues)

    def test_java_no_issue(self) -> None:
        code = """\
public class Foo {
    public String bar(int x) {
        if (x > 0) {
            System.out.println("pos");
        } else {
            System.out.println("non-pos");
        }
        return "";
    }
}
"""
        result = _analyze(code, ".java")
        assert len(result.issues) == 0


# ── Go redundant else detection ──────────────────────────────────────────


class TestGoRedundantElse:
    def test_go_redundant_else_return(self) -> None:
        code = """\
package main

func foo(x int) string {
    if x > 0 {
        return "pos"
    } else {
        return "non-pos"
    }
}
"""
        result = _analyze(code, ".go")
        assert any(i.issue_type == ISSUE_REDUNDANT_ELSE for i in result.issues)

    def test_go_no_issue(self) -> None:
        code = """\
package main

func foo(x int) string {
    if x > 0 {
        return "pos"
    }
    return "non-pos"
}
"""
        result = _analyze(code, ".go")
        assert len(result.issues) == 0


# ── Edge cases ───────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_file_not_found(self) -> None:
        result = ANALYZER.analyze_file("/nonexistent/path/test.py")
        assert len(result.issues) == 0

    def test_unsupported_extension(self) -> None:
        with tempfile.NamedTemporaryFile(
            suffix=".xyz", mode="w", delete=False,
        ) as f:
            f.write("if True: pass")
            f.flush()
            result = ANALYZER.analyze_file(f.name)
        assert len(result.issues) == 0

    def test_nested_if(self) -> None:
        code = """\
def foo(x, y):
    if x > 0:
        if y > 0:
            return "both"
        else:
            return "x only"
    else:
        return "none"
"""
        result = _analyze(code)
        redundant = [i for i in result.issues if i.issue_type == ISSUE_REDUNDANT_ELSE]
        assert len(redundant) >= 1
