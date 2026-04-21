"""Tests for Dead Store Detector."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.dead_store import (
    ISSUE_DEAD_STORE,
    ISSUE_IMMEDIATE_REASSIGNMENT,
    DeadStoreAnalyzer,
    DeadStoreIssue,
    DeadStoreResult,
)

ANALYZER = DeadStoreAnalyzer()


def _analyze(code: str, ext: str = ".py") -> DeadStoreResult:
    with tempfile.NamedTemporaryFile(
        suffix=ext, mode="w", delete=False, encoding="utf-8",
    ) as f:
        f.write(code)
        f.flush()
        return ANALYZER.analyze_file(f.name)


# ── Classification tests ──────────────────────────────────────────────────


class TestClassification:
    def test_dead_store_constant(self) -> None:
        assert ISSUE_DEAD_STORE == "dead_store"

    def test_immediate_reassignment_constant(self) -> None:
        assert ISSUE_IMMEDIATE_REASSIGNMENT == "immediate_reassignment"


# ── Dataclass tests ──────────────────────────────────────────────────────


class TestDataclasses:
    def test_issue_frozen(self) -> None:
        issue = DeadStoreIssue(
            line_number=5,
            issue_type=ISSUE_DEAD_STORE,
            variable_name="x",
            severity="medium",
            description="test",
        )
        assert issue.line_number == 5
        with pytest.raises(AttributeError):
            issue.line_number = 10  # type: ignore[misc]

    def test_issue_to_dict(self) -> None:
        issue = DeadStoreIssue(
            line_number=3,
            issue_type=ISSUE_DEAD_STORE,
            variable_name="data",
            severity="medium",
            description="test",
        )
        d = issue.to_dict()
        assert d["line_number"] == 3
        assert d["issue_type"] == ISSUE_DEAD_STORE
        assert d["variable_name"] == "data"
        assert "suggestion" in d

    def test_issue_suggestion(self) -> None:
        issue = DeadStoreIssue(
            line_number=1,
            issue_type=ISSUE_DEAD_STORE,
            variable_name="x",
            severity="medium",
            description="test",
        )
        assert issue.suggestion != ""

    def test_result_to_dict(self) -> None:
        issue = DeadStoreIssue(
            line_number=1,
            issue_type=ISSUE_DEAD_STORE,
            variable_name="y",
            severity="medium",
            description="test",
        )
        result = DeadStoreResult(
            total_functions=2,
            issues=(issue,),
            file_path="test.py",
        )
        d = result.to_dict()
        assert d["total_functions"] == 2
        assert d["issue_count"] == 1
        assert len(d["issues"]) == 1  # type: ignore[arg-type]


# ── Python dead store detection ──────────────────────────────────────────


class TestPythonDeadStore:
    def test_dead_store_variable_never_read(self) -> None:
        code = """\
def foo():
    x = 10
"""
        result = _analyze(code)
        issues = [i for i in result.issues if i.issue_type == ISSUE_DEAD_STORE]
        assert len(issues) >= 1
        assert any(i.variable_name == "x" for i in issues)

    def test_no_issue_when_variable_is_read(self) -> None:
        code = """\
def foo():
    x = 10
    return x
"""
        result = _analyze(code)
        dead = [i for i in result.issues if i.issue_type == ISSUE_DEAD_STORE and i.variable_name == "x"]
        assert len(dead) == 0

    def test_dead_store_reassigned_without_read(self) -> None:
        code = """\
def foo():
    x = 10
    x = 20
    return x
"""
        result = _analyze(code)
        immediate = [i for i in result.issues if i.issue_type == ISSUE_IMMEDIATE_REASSIGNMENT]
        assert len(immediate) >= 1

    def test_no_issue_for_augmented_assignment(self) -> None:
        code = """\
def foo():
    x = 10
    x += 5
    return x
"""
        result = _analyze(code)
        x_issues = [i for i in result.issues if i.variable_name == "x"]
        # augmented assignment reads x first, so no dead store
        assert len(x_issues) == 0

    def test_multiple_variables(self) -> None:
        code = """\
def foo():
    a = 1
    b = 2
    return a
"""
        result = _analyze(code)
        dead = [i for i in result.issues if i.issue_type == ISSUE_DEAD_STORE]
        assert any(i.variable_name == "b" for i in dead)

    def test_empty_function(self) -> None:
        code = """\
def foo():
    pass
"""
        result = _analyze(code)
        assert len(result.issues) == 0

    def test_function_count(self) -> None:
        code = """\
def foo():
    pass

def bar():
    pass
"""
        result = _analyze(code)
        assert result.total_functions == 2

    def test_variable_used_in_expression(self) -> None:
        code = """\
def foo():
    x = 10
    y = x + 5
    return y
"""
        result = _analyze(code)
        x_dead = [i for i in result.issues if i.variable_name == "x" and i.issue_type == ISSUE_DEAD_STORE]
        assert len(x_dead) == 0


# ── JavaScript dead store detection ──────────────────────────────────────


class TestJavaScriptDeadStore:
    def test_js_dead_store(self) -> None:
        code = """\
function foo() {
    let x = 10;
}
"""
        result = _analyze(code, ".js")
        dead = [i for i in result.issues if i.issue_type == ISSUE_DEAD_STORE and i.variable_name == "x"]
        assert len(dead) >= 1

    def test_js_variable_used(self) -> None:
        code = """\
function foo() {
    let x = 10;
    return x;
}
"""
        result = _analyze(code, ".js")
        dead = [i for i in result.issues if i.variable_name == "x" and i.issue_type == ISSUE_DEAD_STORE]
        assert len(dead) == 0

    def test_js_arrow_function(self) -> None:
        code = """\
const foo = () => {
    let x = 10;
};
"""
        result = _analyze(code, ".js")
        assert result.total_functions >= 1

    def test_js_immediate_reassignment(self) -> None:
        code = """\
function foo() {
    let x = 10;
    x = 20;
    return x;
}
"""
        result = _analyze(code, ".js")
        immediate = [i for i in result.issues if i.issue_type == ISSUE_IMMEDIATE_REASSIGNMENT]
        assert len(immediate) >= 1


# ── TypeScript dead store detection ──────────────────────────────────────


class TestTypeScriptDeadStore:
    def test_ts_dead_store(self) -> None:
        code = """\
function foo(): number {
    let x = 10;
    return 0;
}
"""
        result = _analyze(code, ".ts")
        dead = [i for i in result.issues if i.issue_type == ISSUE_DEAD_STORE and i.variable_name == "x"]
        assert len(dead) >= 1

    def test_ts_variable_used(self) -> None:
        code = """\
function foo(): number {
    let x = 10;
    return x;
}
"""
        result = _analyze(code, ".ts")
        dead = [i for i in result.issues if i.variable_name == "x" and i.issue_type == ISSUE_DEAD_STORE]
        assert len(dead) == 0


# ── Java dead store detection ────────────────────────────────────────────


class TestJavaDeadStore:
    def test_java_dead_store(self) -> None:
        code = """\
public class Foo {
    public void bar() {
        int x = 10;
    }
}
"""
        result = _analyze(code, ".java")
        dead = [i for i in result.issues if i.issue_type == ISSUE_DEAD_STORE and i.variable_name == "x"]
        assert len(dead) >= 1

    def test_java_variable_used(self) -> None:
        code = """\
public class Foo {
    public int bar() {
        int x = 10;
        return x;
    }
}
"""
        result = _analyze(code, ".java")
        dead = [i for i in result.issues if i.variable_name == "x" and i.issue_type == ISSUE_DEAD_STORE]
        assert len(dead) == 0


# ── Go dead store detection ──────────────────────────────────────────────


class TestGoDeadStore:
    def test_go_dead_store(self) -> None:
        code = """\
package main

func foo() {
    x := 10
}
"""
        result = _analyze(code, ".go")
        dead = [i for i in result.issues if i.issue_type == ISSUE_DEAD_STORE and i.variable_name == "x"]
        assert len(dead) >= 1

    def test_go_variable_used(self) -> None:
        code = """\
package main

func foo() int {
    x := 10
    return x
}
"""
        result = _analyze(code, ".go")
        dead = [i for i in result.issues if i.variable_name == "x" and i.issue_type == ISSUE_DEAD_STORE]
        assert len(dead) == 0


# ── Edge cases ───────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_file_not_found(self) -> None:
        result = ANALYZER.analyze_file("/nonexistent/path/test.py")
        assert len(result.issues) == 0
        assert result.total_functions == 0

    def test_unsupported_extension(self) -> None:
        with tempfile.NamedTemporaryFile(
            suffix=".xyz", mode="w", delete=False,
        ) as f:
            f.write("def foo(): pass")
            f.flush()
            result = ANALYZER.analyze_file(f.name)
        assert len(result.issues) == 0

    def test_empty_file(self) -> None:
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False,
        ) as f:
            f.write("")
            f.flush()
            result = ANALYZER.analyze_file(f.name)
        assert len(result.issues) == 0

    def test_no_functions(self) -> None:
        code = "x = 10\n"
        result = _analyze(code)
        assert result.total_functions == 0

    def test_nested_function_not_analyzed_for_outer_vars(self) -> None:
        code = """\
def outer():
    x = 10
    def inner():
        y = 20
    return inner
"""
        result = _analyze(code)
        # inner function's dead store should be detected
        inner_dead = [i for i in result.issues if i.variable_name == "y"]
        assert len(inner_dead) >= 1

    def test_variable_used_in_print(self) -> None:
        code = """\
def foo():
    x = 10
    print(x)
"""
        result = _analyze(code)
        dead = [i for i in result.issues if i.variable_name == "x" and i.issue_type == ISSUE_DEAD_STORE]
        assert len(dead) == 0
