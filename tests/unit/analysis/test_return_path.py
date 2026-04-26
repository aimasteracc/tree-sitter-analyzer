"""Tests for Return Path Analyzer — Python + Multi-Language."""
from __future__ import annotations

import tempfile

import pytest

from tree_sitter_analyzer.analysis.return_path import (
    ISSUE_COMPLEX_RETURN_PATH,
    ISSUE_EMPTY_RETURN,
    ISSUE_IMPLICIT_NONE,
    ISSUE_INCONSISTENT_RETURN,
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    FunctionReturnPath,
    ReturnPathAnalyzer,
    ReturnPathIssue,
    ReturnPathResult,
    ReturnPoint,
    _severity,
)

ANALYZER = ReturnPathAnalyzer


# ── Severity tests ──────────────────────────────────────────────────────


class TestSeverity:
    def test_inconsistent_return_is_high(self) -> None:
        assert _severity(ISSUE_INCONSISTENT_RETURN) == SEVERITY_HIGH

    def test_implicit_none_is_medium(self) -> None:
        assert _severity(ISSUE_IMPLICIT_NONE) == SEVERITY_MEDIUM

    def test_complex_return_is_low(self) -> None:
        assert _severity(ISSUE_COMPLEX_RETURN_PATH) == SEVERITY_LOW

    def test_empty_return_is_low(self) -> None:
        assert _severity(ISSUE_EMPTY_RETURN) == SEVERITY_LOW


# ── Dataclass tests ────────────────────────────────────────────────────


class TestDataclasses:
    def test_return_point_frozen(self) -> None:
        rp = ReturnPoint(line_number=5, has_value=True, node_type="return_statement")
        assert rp.line_number == 5
        with pytest.raises(AttributeError):
            rp.line_number = 10  # type: ignore[misc]

    def test_function_return_path_properties(self) -> None:
        fn = FunctionReturnPath(
            name="foo",
            start_line=1,
            end_line=10,
            return_points=(
                ReturnPoint(line_number=3, has_value=True, node_type="return_statement"),
                ReturnPoint(line_number=5, has_value=False, node_type="return_statement"),
                ReturnPoint(line_number=8, has_value=True, node_type="return_statement"),
            ),
            has_implicit_none=False,
            issues=(),
            element_type="function",
        )
        assert fn.return_count == 3
        assert fn.value_returns == 2
        assert fn.empty_returns == 1

    def test_result_get_functions_with_issues(self) -> None:
        fn_ok = FunctionReturnPath(
            name="ok", start_line=1, end_line=2,
            return_points=(), has_implicit_none=False,
            issues=(), element_type="function",
        )
        fn_bad = FunctionReturnPath(
            name="bad", start_line=3, end_line=10,
            return_points=(), has_implicit_none=False,
            issues=(
                ReturnPathIssue(
                    issue_type=ISSUE_INCONSISTENT_RETURN,
                    severity=SEVERITY_HIGH,
                    line_number=5,
                    message="inconsistent",
                ),
            ),
            element_type="function",
        )
        result = ReturnPathResult(
            functions=(fn_ok, fn_bad),
            total_functions=2,
            functions_with_issues=1,
            total_issues=1,
            file_path="test.py",
        )
        with_issues = result.get_functions_with_issues()
        assert len(with_issues) == 1
        assert with_issues[0].name == "bad"


# ── Python analysis tests ──────────────────────────────────────────────


class TestPythonAnalysis:
    def _analyze(self, code: str) -> ReturnPathResult:
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False
        ) as f:
            f.write(code)
            f.flush()
            return ANALYZER().analyze_file(f.name)

    def test_consistent_return_value(self) -> None:
        code = "def foo():\n    return 42\n"
        result = self._analyze(code)
        assert result.total_functions == 1
        assert result.functions_with_issues == 0

    def test_consistent_return_none(self) -> None:
        code = "def foo():\n    return\n"
        result = self._analyze(code)
        assert result.total_functions == 1
        assert result.functions_with_issues == 0

    def test_inconsistent_return_if_else(self) -> None:
        code = (
            "def foo(x):\n"
            "    if x > 0:\n"
            "        return x\n"
            "    else:\n"
            "        return\n"
        )
        result = self._analyze(code)
        assert result.functions_with_issues == 1
        issues = result.functions[0].issues
        issue_types = {i.issue_type for i in issues}
        assert ISSUE_INCONSISTENT_RETURN in issue_types
        assert ISSUE_EMPTY_RETURN in issue_types

    def test_implicit_none_return(self) -> None:
        code = (
            "def foo(x):\n"
            "    if x > 0:\n"
            "        return x\n"
            "    # falls through\n"
        )
        result = self._analyze(code)
        assert result.functions_with_issues == 1
        assert result.functions[0].has_implicit_none

    def test_complex_return_path(self) -> None:
        # Function with 6 return statements
        code = (
            "def foo(a, b, c, d, e, f):\n"
            "    if a: return 1\n"
            "    if b: return 2\n"
            "    if c: return 3\n"
            "    if d: return 4\n"
            "    if e: return 5\n"
            "    if f: return 6\n"
            "    return 0\n"
        )
        result = self._analyze(code)
        issue_types = {i.issue_type for i in result.functions[0].issues}
        assert ISSUE_COMPLEX_RETURN_PATH in issue_types

    def test_function_with_no_return(self) -> None:
        code = "def foo():\n    pass\n"
        result = self._analyze(code)
        assert result.total_functions == 1
        assert result.functions_with_issues == 0

    def test_method_in_class(self) -> None:
        code = (
            "class MyClass:\n"
            "    def method(self):\n"
            "        if True:\n"
            "            return 1\n"
            "        return\n"
        )
        result = self._analyze(code)
        assert result.total_functions == 1
        fn = result.functions[0]
        assert fn.element_type == "method"
        assert fn.name == "method"

    def test_nested_function(self) -> None:
        code = (
            "def outer():\n"
            "    def inner():\n"
            "        if True:\n"
            "            return 1\n"
            "        return\n"
            "    return inner\n"
        )
        result = self._analyze(code)
        assert result.total_functions == 2

    def test_yield_function(self) -> None:
        code = (
            "def gen():\n"
            "    yield 1\n"
            "    yield 2\n"
        )
        result = self._analyze(code)
        assert result.total_functions == 1
        # yield doesn't cause inconsistency on its own
        assert result.functions_with_issues == 0

    def test_multiple_functions_mixed(self) -> None:
        code = (
            "def good():\n"
            "    return 42\n"
            "\n"
            "def bad(x):\n"
            "    if x:\n"
            "        return x\n"
            "\n"
            "def also_good():\n"
            "    pass\n"
        )
        result = self._analyze(code)
        assert result.total_functions == 3
        assert result.functions_with_issues == 1
        assert result.functions[1].name == "bad"

    def test_all_paths_return_value(self) -> None:
        code = (
            "def foo(x):\n"
            "    if x > 0:\n"
            "        return 'positive'\n"
            "    return 'non-positive'\n"
        )
        result = self._analyze(code)
        assert result.functions_with_issues == 0

    def test_decorated_function(self) -> None:
        code = (
            "from functools import lru_cache\n"
            "@lru_cache\n"
            "def foo(x):\n"
            "    if x > 0:\n"
            "        return x\n"
            "    return 0\n"
        )
        result = self._analyze(code)
        assert result.total_functions == 1
        assert result.functions_with_issues == 0


# ── JavaScript / TypeScript analysis tests ──────────────────────────────


class TestJavaScriptAnalysis:
    def _analyze(self, code: str, suffix: str = ".js") -> ReturnPathResult:
        with tempfile.NamedTemporaryFile(
            suffix=suffix, mode="w", delete=False
        ) as f:
            f.write(code)
            f.flush()
            return ANALYZER().analyze_file(f.name)

    def test_consistent_return(self) -> None:
        code = "function foo() { return 42; }\n"
        result = self._analyze(code)
        assert result.total_functions == 1
        assert result.functions_with_issues == 0

    def test_inconsistent_return(self) -> None:
        code = (
            "function foo(x) {\n"
            "  if (x > 0) {\n"
            "    return x;\n"
            "  }\n"
            "  return;\n"
            "}\n"
        )
        result = self._analyze(code)
        assert result.functions_with_issues == 1

    def test_arrow_function_expression(self) -> None:
        code = "const foo = (x) => x + 1;\n"
        result = self._analyze(code)
        assert result.total_functions == 1
        assert result.functions_with_issues == 0

    def test_arrow_function_block(self) -> None:
        code = (
            "const foo = (x) => {\n"
            "  if (x > 0) return x;\n"
            "  return;\n"
            "};\n"
        )
        result = self._analyze(code)
        assert result.functions_with_issues == 1

    def test_method_in_class(self) -> None:
        code = (
            "class MyClass {\n"
            "  method() {\n"
            "    return 42;\n"
            "  }\n"
            "}\n"
        )
        result = self._analyze(code)
        assert result.total_functions == 1
        fn = result.functions[0]
        assert fn.element_type == "method"

    def test_typescript_function(self) -> None:
        code = (
            "function foo(x: number): number {\n"
            "  if (x > 0) {\n"
            "    return x;\n"
            "  }\n"
            "  return 0;\n"
            "}\n"
        )
        result = self._analyze(code, ".ts")
        assert result.total_functions == 1
        assert result.functions_with_issues == 0

    def test_throw_in_function(self) -> None:
        code = (
            "function foo(x) {\n"
            "  if (x < 0) throw new Error('negative');\n"
            "  return x;\n"
            "}\n"
        )
        result = self._analyze(code)
        assert result.total_functions == 1
        # throw + return is not inconsistent (both are terminal)
        assert result.functions_with_issues == 0


# ── Java analysis tests ────────────────────────────────────────────────


class TestJavaAnalysis:
    def _analyze(self, code: str) -> ReturnPathResult:
        with tempfile.NamedTemporaryFile(
            suffix=".java", mode="w", delete=False
        ) as f:
            f.write(code)
            f.flush()
            return ANALYZER().analyze_file(f.name)

    def test_consistent_return(self) -> None:
        code = (
            "public class Test {\n"
            "  public int foo() {\n"
            "    return 42;\n"
            "  }\n"
            "}\n"
        )
        result = self._analyze(code)
        assert result.total_functions == 1
        assert result.functions_with_issues == 0

    def test_inconsistent_return(self) -> None:
        code = (
            "public class Test {\n"
            "  public int foo(int x) {\n"
            "    if (x > 0) {\n"
            "      return x;\n"
            "    }\n"
            "    return;\n"
            "  }\n"
            "}\n"
        )
        result = self._analyze(code)
        assert result.functions_with_issues == 1

    def test_constructor(self) -> None:
        code = (
            "public class Test {\n"
            "  public Test() {\n"
            "    // init\n"
            "  }\n"
            "}\n"
        )
        result = self._analyze(code)
        assert result.total_functions == 1
        assert result.functions[0].name == "<init>"

    def test_void_method_no_return(self) -> None:
        code = (
            "public class Test {\n"
            "  public void doStuff() {\n"
            "    System.out.println(\"hello\");\n"
            "  }\n"
            "}\n"
        )
        result = self._analyze(code)
        assert result.total_functions == 1
        assert result.functions_with_issues == 0

    def test_throw_statement(self) -> None:
        code = (
            "public class Test {\n"
            "  public int foo(int x) {\n"
            "    if (x < 0) throw new IllegalArgumentException();\n"
            "    return x;\n"
            "  }\n"
            "}\n"
        )
        result = self._analyze(code)
        assert result.functions_with_issues == 0


# ── Go analysis tests ──────────────────────────────────────────────────


class TestGoAnalysis:
    def _analyze(self, code: str) -> ReturnPathResult:
        with tempfile.NamedTemporaryFile(
            suffix=".go", mode="w", delete=False
        ) as f:
            f.write(code)
            f.flush()
            return ANALYZER().analyze_file(f.name)

    def test_consistent_return(self) -> None:
        code = (
            "package main\n"
            "\n"
            "func foo() int {\n"
            "  return 42\n"
            "}\n"
        )
        result = self._analyze(code)
        assert result.total_functions == 1
        assert result.functions_with_issues == 0

    def test_multiple_returns(self) -> None:
        code = (
            "package main\n"
            "\n"
            "func foo(x int) int {\n"
            "  if x > 0 {\n"
            "    return x\n"
            "  }\n"
            "  return 0\n"
            "}\n"
        )
        result = self._analyze(code)
        assert result.total_functions == 1
        # Both return values, consistent
        assert result.functions_with_issues == 0

    def test_method(self) -> None:
        code = (
            "package main\n"
            "\n"
            "type MyStruct struct{}\n"
            "\n"
            "func (s MyStruct) foo() int {\n"
            "  return 42\n"
            "}\n"
        )
        result = self._analyze(code)
        assert result.total_functions == 1
        assert result.functions[0].element_type == "method"


# ── Edge case tests ────────────────────────────────────────────────────


class TestEdgeCases:
    def _analyze(self, code: str, suffix: str = ".py") -> ReturnPathResult:
        with tempfile.NamedTemporaryFile(
            suffix=suffix, mode="w", delete=False
        ) as f:
            f.write(code)
            f.flush()
            return ANALYZER().analyze_file(f.name)

    def test_return_none_explicitly(self) -> None:
        code = "def foo():\n    return None\n"
        result = self._analyze(code)
        assert result.total_functions == 1
        assert result.functions_with_issues == 0

    def test_return_string_literal(self) -> None:
        code = "def foo():\n    return 'hello'\n"
        result = self._analyze(code)
        assert result.total_functions == 1
        assert result.functions_with_issues == 0

    def test_lambda_not_detected(self) -> None:
        code = "foo = lambda x: x + 1\n"
        result = self._analyze(code)
        # Lambda is an expression, not a function_definition
        assert result.total_functions == 0

    def test_try_except_return(self) -> None:
        code = (
            "def foo(x):\n"
            "    try:\n"
            "        return int(x)\n"
            "    except ValueError:\n"
            "        return 0\n"
        )
        result = self._analyze(code)
        assert result.functions_with_issues == 0

    def test_try_except_inconsistent(self) -> None:
        code = (
            "def foo(x):\n"
            "    try:\n"
            "        return int(x)\n"
            "    except ValueError:\n"
            "        return\n"
        )
        result = self._analyze(code)
        assert result.functions_with_issues == 1
