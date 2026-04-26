"""Tests for Unused Parameter Detector."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.unused_parameter import (
    ISSUE_UNUSED_CALLBACK_PARAM,
    ISSUE_UNUSED_PARAMETER,
    ISSUE_UNUSED_SELF_PARAM,
    UnusedParameterAnalyzer,
    UnusedParameterIssue,
    UnusedParameterResult,
)

ANALYZER = UnusedParameterAnalyzer()


def _analyze(code: str, ext: str = ".py") -> UnusedParameterResult:
    with tempfile.NamedTemporaryFile(
        suffix=ext, mode="w", delete=False, encoding="utf-8",
    ) as f:
        f.write(code)
        f.flush()
        return ANALYZER.analyze_file(f.name)


def _issue_names(result: UnusedParameterResult) -> set[str]:
    return {i.parameter_name for i in result.issues}


def _issue_types(result: UnusedParameterResult) -> dict[str, str]:
    return {i.parameter_name: i.issue_type for i in result.issues}


# ── Classification tests ──────────────────────────────────────────────────


class TestClassification:
    def test_unused_parameter_constant(self) -> None:
        assert ISSUE_UNUSED_PARAMETER == "unused_parameter"

    def test_unused_callback_param_constant(self) -> None:
        assert ISSUE_UNUSED_CALLBACK_PARAM == "unused_callback_param"

    def test_unused_self_param_constant(self) -> None:
        assert ISSUE_UNUSED_SELF_PARAM == "unused_self_param"


# ── Dataclass tests ──────────────────────────────────────────────────────


class TestDataclasses:
    def test_issue_frozen(self) -> None:
        issue = UnusedParameterIssue(
            line_number=5,
            issue_type=ISSUE_UNUSED_PARAMETER,
            parameter_name="x",
            severity="medium",
            description="test",
        )
        assert issue.line_number == 5
        with pytest.raises(AttributeError):
            issue.line_number = 10  # type: ignore[misc]

    def test_issue_to_dict(self) -> None:
        issue = UnusedParameterIssue(
            line_number=3,
            issue_type=ISSUE_UNUSED_PARAMETER,
            parameter_name="unused_var",
            severity="medium",
            description="test desc",
        )
        d = issue.to_dict()
        assert d["line_number"] == 3
        assert d["issue_type"] == ISSUE_UNUSED_PARAMETER
        assert d["parameter_name"] == "unused_var"
        assert "suggestion" in d

    def test_result_frozen(self) -> None:
        result = UnusedParameterResult(
            total_functions=1,
            issues=(),
            file_path="test.py",
        )
        assert result.total_functions == 1
        with pytest.raises(AttributeError):
            result.total_functions = 5  # type: ignore[misc]

    def test_result_to_dict(self) -> None:
        result = UnusedParameterResult(
            total_functions=2,
            issues=(),
            file_path="test.py",
        )
        d = result.to_dict()
        assert d["total_functions"] == 2
        assert d["issue_count"] == 0
        assert d["issues"] == []


# ── Edge case tests ──────────────────────────────────────────────────────


class TestEdgeCases:
    def test_file_path_as_path_object(self) -> None:
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False, encoding="utf-8",
        ) as f:
            f.write("def foo(x): return x\n")
            f.flush()
            result = ANALYZER.analyze_file(Path(f.name))
        assert result.total_functions == 1

    def test_result_file_path_preserved(self) -> None:
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False, encoding="utf-8",
        ) as f:
            f.write("def foo(x): return x\n")
            f.flush()
            result = ANALYZER.analyze_file(f.name)
        assert result.file_path == f.name


# ── Python tests ──────────────────────────────────────────────────────────


class TestPython:
    def test_unused_parameter(self) -> None:
        result = _analyze("def foo(x, y):\n    return x\n")
        assert "y" in _issue_names(result)
        assert _issue_types(result)["y"] == ISSUE_UNUSED_PARAMETER

    def test_all_parameters_used(self) -> None:
        result = _analyze("def foo(x, y):\n    return x + y\n")
        assert len(result.issues) == 0

    def test_unused_self(self) -> None:
        result = _analyze("class C:\n    def foo(self):\n        pass\n")
        types = _issue_types(result)
        assert "self" in types
        assert types["self"] == ISSUE_UNUSED_SELF_PARAM

    def test_used_self(self) -> None:
        result = _analyze("class C:\n    def foo(self):\n        return self.x\n")
        assert "self" not in _issue_names(result)

    def test_unused_cls(self) -> None:
        result = _analyze("class C:\n    @classmethod\n    def foo(cls):\n        pass\n")
        types = _issue_types(result)
        assert "cls" in types
        assert types["cls"] == ISSUE_UNUSED_SELF_PARAM

    def test_underscore_prefix_param(self) -> None:
        result = _analyze("def foo(x, _unused):\n    return x\n")
        types = _issue_types(result)
        assert "_unused" in types
        assert types["_unused"] == ISSUE_UNUSED_CALLBACK_PARAM

    def test_no_parameters(self) -> None:
        result = _analyze("def foo():\n    return 42\n")
        assert len(result.issues) == 0

    def test_typed_parameter(self) -> None:
        result = _analyze("def foo(x: int, y: int) -> int:\n    return x\n")
        assert "y" in _issue_names(result)

    def test_default_parameter(self) -> None:
        result = _analyze("def foo(x, y=10):\n    return x\n")
        assert "y" in _issue_names(result)

    def test_star_args(self) -> None:
        result = _analyze("def foo(x, *args, **kwargs):\n    return x\n")
        assert "args" in _issue_names(result)
        assert "kwargs" in _issue_names(result)

    def test_nested_function_params_not_counted(self) -> None:
        code = (
            "def outer(x):\n"
            "    def inner(y):\n"
            "        return y\n"
            "    return inner(x)\n"
        )
        result = _analyze(code)
        assert "x" not in _issue_names(result)

    def test_multiple_functions(self) -> None:
        code = (
            "def foo(x):\n"
            "    return x\n"
            "def bar(a, b):\n"
            "    return a\n"
        )
        result = _analyze(code)
        assert result.total_functions == 2
        assert "b" in _issue_names(result)
        assert "x" not in _issue_names(result)

    def test_parameter_used_in_expression(self) -> None:
        result = _analyze("def foo(x, y):\n    z = x + y\n    return z\n")
        assert len(result.issues) == 0

    def test_parameter_used_in_if(self) -> None:
        result = _analyze("def foo(x, y):\n    if x > 0:\n        return y\n")
        assert len(result.issues) == 0

    def test_function_count(self) -> None:
        code = (
            "def a(): pass\n"
            "def b(x): return x\n"
            "def c(x, y): return x\n"
        )
        result = _analyze(code)
        assert result.total_functions == 3


# ── JavaScript/TypeScript tests ──────────────────────────────────────────


class TestJavaScript:
    def test_unused_parameter(self) -> None:
        code = "function foo(x, y) { return x; }\n"
        result = _analyze(code, ".js")
        assert "y" in _issue_names(result)

    def test_all_parameters_used(self) -> None:
        code = "function foo(x, y) { return x + y; }\n"
        result = _analyze(code, ".js")
        assert len(result.issues) == 0

    def test_arrow_function(self) -> None:
        code = "const foo = (x, y) => x;\n"
        result = _analyze(code, ".js")
        assert "y" in _issue_names(result)

    def test_underscore_param(self) -> None:
        code = "const foo = (x, _cb) => x;\n"
        result = _analyze(code, ".js")
        types = _issue_types(result)
        assert "_cb" in types
        assert types["_cb"] == ISSUE_UNUSED_CALLBACK_PARAM

    def test_method_definition(self) -> None:
        code = (
            "class C {\n"
            "    method(x, y) {\n"
            "        return x;\n"
            "    }\n"
            "}\n"
        )
        result = _analyze(code, ".js")
        assert "y" in _issue_names(result)

    def test_function_expression(self) -> None:
        code = "const foo = function(x, y) { return x; };\n"
        result = _analyze(code, ".js")
        assert "y" in _issue_names(result)

    def test_no_params(self) -> None:
        code = "function foo() { return 42; }\n"
        result = _analyze(code, ".js")
        assert len(result.issues) == 0


class TestTypeScript:
    def test_unused_parameter(self) -> None:
        code = "function foo(x: number, y: number): number { return x; }\n"
        result = _analyze(code, ".ts")
        assert "y" in _issue_names(result)

    def test_arrow_function(self) -> None:
        code = "const foo = (x: string, y: string) => x;\n"
        result = _analyze(code, ".ts")
        assert "y" in _issue_names(result)

    def test_all_used(self) -> None:
        code = "function add(a: number, b: number) { return a + b; }\n"
        result = _analyze(code, ".ts")
        assert len(result.issues) == 0


# ── Java tests ──────────────────────────────────────────────────────────


class TestJava:
    def test_unused_parameter(self) -> None:
        code = (
            "public class C {\n"
            "    public int foo(int x, int y) {\n"
            "        return x;\n"
            "    }\n"
            "}\n"
        )
        result = _analyze(code, ".java")
        assert "y" in _issue_names(result)

    def test_all_parameters_used(self) -> None:
        code = (
            "public class C {\n"
            "    public int add(int a, int b) {\n"
            "        return a + b;\n"
            "    }\n"
            "}\n"
        )
        result = _analyze(code, ".java")
        assert len(result.issues) == 0

    def test_this_not_used(self) -> None:
        code = (
            "public class C {\n"
            "    public static void foo() {\n"
            "        return;\n"
            "    }\n"
            "}\n"
        )
        result = _analyze(code, ".java")
        # static method has no 'this' parameter to check
        assert len(result.issues) == 0

    def test_constructor_parameter(self) -> None:
        code = (
            "public class C {\n"
            "    private int x;\n"
            "    public C(int x, int unused) {\n"
            "        this.x = x;\n"
            "    }\n"
            "}\n"
        )
        result = _analyze(code, ".java")
        assert "unused" in _issue_names(result)

    def test_lambda_parameter(self) -> None:
        code = (
            "import java.util.*;\n"
            "public class C {\n"
            "    public void foo() {\n"
            "        List<Integer> list = Arrays.asList(1, 2, 3);\n"
            "        list.stream().map(x -> x);\n"
            "    }\n"
            "}\n"
        )
        result = _analyze(code, ".java")
        # x is used in lambda, but foo has no params
        assert len(result.issues) == 0

    def test_no_params(self) -> None:
        code = (
            "public class C {\n"
            "    public void foo() {}\n"
            "}\n"
        )
        result = _analyze(code, ".java")
        assert len(result.issues) == 0


# ── Go tests ──────────────────────────────────────────────────────────────


class TestGo:
    def test_unused_parameter(self) -> None:
        code = (
            "package main\n\n"
            "func foo(x int, y int) int {\n"
            "    return x\n"
            "}\n"
        )
        result = _analyze(code, ".go")
        assert "y" in _issue_names(result)

    def test_all_parameters_used(self) -> None:
        code = (
            "package main\n\n"
            "func add(a int, b int) int {\n"
            "    return a + b\n"
            "}\n"
        )
        result = _analyze(code, ".go")
        assert len(result.issues) == 0

    def test_underscore_param(self) -> None:
        code = (
            "package main\n\n"
            "func foo(x int, _ int) int {\n"
            "    return x\n"
            "}\n"
        )
        result = _analyze(code, ".go")
        types = _issue_types(result)
        assert "_" in types
        assert types["_"] == ISSUE_UNUSED_CALLBACK_PARAM

    def test_method_declaration(self) -> None:
        code = (
            "package main\n\n"
            "type T struct{}\n\n"
            "func (t T) foo(x int, y int) int {\n"
            "    return x\n"
            "}\n"
        )
        result = _analyze(code, ".go")
        assert "y" in _issue_names(result)

    def test_func_literal(self) -> None:
        code = (
            "package main\n\n"
            "func main() {\n"
            "    f := func(x int, y int) int {\n"
            "        return x\n"
            "    }\n"
            "    _ = f\n"
            "}\n"
        )
        result = _analyze(code, ".go")
        assert "y" in _issue_names(result)

    def test_no_params(self) -> None:
        code = (
            "package main\n\n"
            "func main() {\n"
            "}\n"
        )
        result = _analyze(code, ".go")
        assert len(result.issues) == 0

    def test_multiple_returns(self) -> None:
        code = (
            "package main\n\n"
            "func div(a int, b int) (int, error) {\n"
            "    return a / b, nil\n"
            "}\n"
        )
        result = _analyze(code, ".go")
        assert len(result.issues) == 0


# ── Suggestion tests ──────────────────────────────────────────────────────


class TestSuggestions:
    def test_unused_parameter_has_suggestion(self) -> None:
        issue = UnusedParameterIssue(
            line_number=1,
            issue_type=ISSUE_UNUSED_PARAMETER,
            parameter_name="x",
            severity="medium",
            description="test",
        )
        assert issue.suggestion != ""

    def test_callback_param_has_suggestion(self) -> None:
        issue = UnusedParameterIssue(
            line_number=1,
            issue_type=ISSUE_UNUSED_CALLBACK_PARAM,
            parameter_name="_x",
            severity="low",
            description="test",
        )
        assert issue.suggestion != ""

    def test_self_param_has_suggestion(self) -> None:
        issue = UnusedParameterIssue(
            line_number=1,
            issue_type=ISSUE_UNUSED_SELF_PARAM,
            parameter_name="self",
            severity="low",
            description="test",
        )
        assert issue.suggestion != ""
