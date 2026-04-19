"""Tests for Variable Shadowing Detector."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.variable_shadowing import (
    ISSUE_COMPREHENSION_SHADOWS,
    ISSUE_LOCAL_SHADOWS_OUTER,
    ISSUE_LOCAL_SHADOWS_PARAM,
    ISSUE_PARAM_SHADOWS_OUTER,
    ShadowIssue,
    ShadowResult,
    VariableShadowingAnalyzer,
)

ANALYZER = VariableShadowingAnalyzer


# ── Classification tests ──────────────────────────────────────────────────


class TestClassification:
    def test_param_shadows_outer_constant(self) -> None:
        assert ISSUE_PARAM_SHADOWS_OUTER == "param_shadows_outer"

    def test_local_shadows_param_constant(self) -> None:
        assert ISSUE_LOCAL_SHADOWS_PARAM == "local_shadows_param"

    def test_local_shadows_outer_constant(self) -> None:
        assert ISSUE_LOCAL_SHADOWS_OUTER == "local_shadows_outer"

    def test_comprehension_shadows_constant(self) -> None:
        assert ISSUE_COMPREHENSION_SHADOWS == "comprehension_shadows"


# ── Dataclass tests ──────────────────────────────────────────────────────


class TestDataclasses:
    def test_issue_frozen(self) -> None:
        issue = ShadowIssue(
            line_number=5,
            issue_type=ISSUE_LOCAL_SHADOWS_PARAM,
            variable_name="x",
            outer_scope="parameter",
            inner_scope="function_definition",
            severity="medium",
            description="test",
        )
        assert issue.line_number == 5
        with pytest.raises(AttributeError):
            issue.line_number = 10  # type: ignore[misc]

    def test_issue_to_dict(self) -> None:
        issue = ShadowIssue(
            line_number=3,
            issue_type=ISSUE_PARAM_SHADOWS_OUTER,
            variable_name="data",
            outer_scope="function_definition",
            inner_scope="lambda",
            severity="medium",
            description="test",
        )
        d = issue.to_dict()
        assert d["line_number"] == 3
        assert d["issue_type"] == ISSUE_PARAM_SHADOWS_OUTER
        assert d["variable_name"] == "data"
        assert "suggestion" in d

    def test_issue_suggestion(self) -> None:
        issue = ShadowIssue(
            line_number=1,
            issue_type=ISSUE_COMPREHENSION_SHADOWS,
            variable_name="x",
            outer_scope="function_definition",
            inner_scope="list_comprehension",
            severity="high",
            description="test",
        )
        assert "Rename" in issue.suggestion

    def test_result_frozen(self) -> None:
        result = ShadowResult(
            total_scopes=1,
            issues=(),
            file_path="test.py",
        )
        assert result.total_scopes == 1
        with pytest.raises(AttributeError):
            result.total_scopes = 5  # type: ignore[misc]

    def test_result_to_dict(self) -> None:
        result = ShadowResult(
            total_scopes=3,
            issues=(),
            file_path="test.py",
        )
        d = result.to_dict()
        assert d["total_scopes"] == 3
        assert d["issue_count"] == 0


# ── Edge case tests ──────────────────────────────────────────────────────


class TestEdgeCases:
    def test_nonexistent_file(self) -> None:
        analyzer = ANALYZER()
        result = analyzer.analyze_file("/nonexistent/file.py")
        assert result.total_scopes == 0
        assert len(result.issues) == 0

    def test_unsupported_extension(self) -> None:
        with tempfile.NamedTemporaryFile(
            suffix=".rs", mode="w", delete=False,
        ) as f:
            f.write("fn main() { let x = 1; }")
            f.flush()
            analyzer = ANALYZER()
            result = analyzer.analyze_file(f.name)
        assert result.total_scopes == 0

    def test_empty_file(self) -> None:
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False,
        ) as f:
            f.write("")
            f.flush()
            analyzer = ANALYZER()
            result = analyzer.analyze_file(f.name)
        assert result.total_scopes == 0
        assert len(result.issues) == 0

    def test_file_path_as_string(self) -> None:
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False,
        ) as f:
            f.write("x = 1\n")
            f.flush()
            analyzer = ANALYZER()
            result = analyzer.analyze_file(f.name)
        assert isinstance(result, ShadowResult)

    def test_file_path_as_path(self) -> None:
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False,
        ) as f:
            f.write("x = 1\n")
            f.flush()
            analyzer = ANALYZER()
            result = analyzer.analyze_file(Path(f.name))
        assert isinstance(result, ShadowResult)


# ── Python detection tests ──────────────────────────────────────────────


class TestPython:
    def test_param_shadows_outer_var(self) -> None:
        code = (
            "data = [1, 2, 3]\n"
            "def process(data):\n"
            "    return data\n"
        )
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False,
        ) as f:
            f.write(code)
            f.flush()
            analyzer = ANALYZER()
            result = analyzer.analyze_file(f.name)
        assert len(result.issues) == 1
        assert result.issues[0].issue_type == ISSUE_PARAM_SHADOWS_OUTER
        assert result.issues[0].variable_name == "data"

    def test_local_shadows_param(self) -> None:
        code = (
            "def process(x):\n"
            "    x = x + 1\n"
            "    return x\n"
        )
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False,
        ) as f:
            f.write(code)
            f.flush()
            analyzer = ANALYZER()
            result = analyzer.analyze_file(f.name)
        assert len(result.issues) == 1
        assert result.issues[0].issue_type == ISSUE_LOCAL_SHADOWS_PARAM
        assert result.issues[0].variable_name == "x"

    def test_comprehension_shadows_outer(self) -> None:
        code = (
            "x = 10\n"
            "result = [x for x in range(5)]\n"
        )
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False,
        ) as f:
            f.write(code)
            f.flush()
            analyzer = ANALYZER()
            result = analyzer.analyze_file(f.name)
        shadow_issues = [
            i for i in result.issues
            if i.issue_type == ISSUE_COMPREHENSION_SHADOWS
        ]
        assert len(shadow_issues) == 1
        assert shadow_issues[0].variable_name == "x"

    def test_no_shadowing(self) -> None:
        code = (
            "x = 1\n"
            "def process():\n"
            "    y = 2\n"
            "    return x + y\n"
        )
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False,
        ) as f:
            f.write(code)
            f.flush()
            analyzer = ANALYZER()
            result = analyzer.analyze_file(f.name)
        assert len(result.issues) == 0

    def test_nested_function_shadowing(self) -> None:
        code = (
            "def outer():\n"
            "    value = 10\n"
            "    def inner():\n"
            "        value = 20\n"
            "        return value\n"
            "    return inner\n"
        )
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False,
        ) as f:
            f.write(code)
            f.flush()
            analyzer = ANALYZER()
            result = analyzer.analyze_file(f.name)
        assert len(result.issues) >= 1
        types = [i.issue_type for i in result.issues]
        assert ISSUE_LOCAL_SHADOWS_OUTER in types

    def test_lambda_param_shadow(self) -> None:
        code = (
            "x = 5\n"
            "f = lambda x: x + 1\n"
        )
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False,
        ) as f:
            f.write(code)
            f.flush()
            analyzer = ANALYZER()
            result = analyzer.analyze_file(f.name)
        assert len(result.issues) == 1
        assert result.issues[0].issue_type == ISSUE_PARAM_SHADOWS_OUTER

    def test_for_loop_shadows_outer(self) -> None:
        code = (
            "i = 0\n"
            "def process(items):\n"
            "    for i in items:\n"
            "        pass\n"
        )
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False,
        ) as f:
            f.write(code)
            f.flush()
            analyzer = ANALYZER()
            result = analyzer.analyze_file(f.name)
        assert len(result.issues) >= 1
        loop_issues = [
            i for i in result.issues
            if i.issue_type == ISSUE_LOCAL_SHADOWS_OUTER
            and i.variable_name == "i"
        ]
        assert len(loop_issues) >= 1

    def test_set_comprehension_shadow(self) -> None:
        code = (
            "x = 10\n"
            "result = {x for x in [1, 2, 3]}\n"
        )
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False,
        ) as f:
            f.write(code)
            f.flush()
            analyzer = ANALYZER()
            result = analyzer.analyze_file(f.name)
        shadow_issues = [
            i for i in result.issues
            if i.issue_type == ISSUE_COMPREHENSION_SHADOWS
        ]
        assert len(shadow_issues) == 1

    def test_dict_comprehension_shadow(self) -> None:
        code = (
            "k = 0\n"
            "result = {k: v for k, v in [(1, 2)]}\n"
        )
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False,
        ) as f:
            f.write(code)
            f.flush()
            analyzer = ANALYZER()
            result = analyzer.analyze_file(f.name)
        shadow_issues = [
            i for i in result.issues
            if i.issue_type == ISSUE_COMPREHENSION_SHADOWS
        ]
        assert len(shadow_issues) >= 1


# ── JavaScript detection tests ──────────────────────────────────────────


class TestJavaScript:
    def test_function_param_shadows_outer(self) -> None:
        code = (
            "var data = [1, 2, 3];\n"
            "function process(data) {\n"
            "    return data;\n"
            "}\n"
        )
        with tempfile.NamedTemporaryFile(
            suffix=".js", mode="w", delete=False,
        ) as f:
            f.write(code)
            f.flush()
            analyzer = ANALYZER()
            result = analyzer.analyze_file(f.name)
        assert len(result.issues) == 1
        assert result.issues[0].issue_type == ISSUE_PARAM_SHADOWS_OUTER
        assert result.issues[0].variable_name == "data"

    def test_arrow_function_shadow(self) -> None:
        code = (
            "const x = 5;\n"
            "const f = (x) => x + 1;\n"
        )
        with tempfile.NamedTemporaryFile(
            suffix=".js", mode="w", delete=False,
        ) as f:
            f.write(code)
            f.flush()
            analyzer = ANALYZER()
            result = analyzer.analyze_file(f.name)
        assert len(result.issues) == 1
        assert result.issues[0].issue_type == ISSUE_PARAM_SHADOWS_OUTER

    def test_block_scope_shadow(self) -> None:
        code = (
            "function process() {\n"
            "    let x = 1;\n"
            "    {\n"
            "        let x = 2;\n"
            "    }\n"
            "}\n"
        )
        with tempfile.NamedTemporaryFile(
            suffix=".js", mode="w", delete=False,
        ) as f:
            f.write(code)
            f.flush()
            analyzer = ANALYZER()
            result = analyzer.analyze_file(f.name)
        assert len(result.issues) >= 1

    def test_no_shadowing(self) -> None:
        code = (
            "function process(items) {\n"
            "    const result = items.map(x => x + 1);\n"
            "    return result;\n"
            "}\n"
        )
        with tempfile.NamedTemporaryFile(
            suffix=".js", mode="w", delete=False,
        ) as f:
            f.write(code)
            f.flush()
            analyzer = ANALYZER()
            result = analyzer.analyze_file(f.name)
        assert len(result.issues) == 0

    def test_for_loop_shadow(self) -> None:
        code = (
            "var i = 0;\n"
            "function process(arr) {\n"
            "    for (var i = 0; i < arr.length; i++) {\n"
            "        console.log(arr[i]);\n"
            "    }\n"
            "}\n"
        )
        with tempfile.NamedTemporaryFile(
            suffix=".js", mode="w", delete=False,
        ) as f:
            f.write(code)
            f.flush()
            analyzer = ANALYZER()
            result = analyzer.analyze_file(f.name)
        assert len(result.issues) >= 1


# ── TypeScript detection tests ──────────────────────────────────────────


class TestTypeScript:
    def test_param_shadow_ts(self) -> None:
        code = (
            "const name = 'world';\n"
            "function greet(name: string) {\n"
            "    return `Hello ${name}`;\n"
            "}\n"
        )
        with tempfile.NamedTemporaryFile(
            suffix=".ts", mode="w", delete=False,
        ) as f:
            f.write(code)
            f.flush()
            analyzer = ANALYZER()
            result = analyzer.analyze_file(f.name)
        assert len(result.issues) == 1
        assert result.issues[0].issue_type == ISSUE_PARAM_SHADOWS_OUTER

    def test_no_shadow_ts(self) -> None:
        code = (
            "function greet(userName: string) {\n"
            "    return `Hello ${userName}`;\n"
            "}\n"
        )
        with tempfile.NamedTemporaryFile(
            suffix=".ts", mode="w", delete=False,
        ) as f:
            f.write(code)
            f.flush()
            analyzer = ANALYZER()
            result = analyzer.analyze_file(f.name)
        assert len(result.issues) == 0


# ── Java detection tests ──────────────────────────────────────────────


class TestJava:
    def test_method_param_shadow_field(self) -> None:
        code = (
            "public class Service {\n"
            "    private String name;\n"
            "    public void setName(String name) {\n"
            "        this.name = name;\n"
            "    }\n"
            "}\n"
        )
        with tempfile.NamedTemporaryFile(
            suffix=".java", mode="w", delete=False,
        ) as f:
            f.write(code)
            f.flush()
            analyzer = ANALYZER()
            result = analyzer.analyze_file(f.name)
        assert len(result.issues) >= 1

    def test_lambda_param_shadow(self) -> None:
        code = (
            "public class App {\n"
            "    public void process() {\n"
            "        String value = \"hello\";\n"
            "        Runnable r = () -> {\n"
            "            System.out.println(\"run\");\n"
            "        };\n"
            "    }\n"
            "}\n"
        )
        with tempfile.NamedTemporaryFile(
            suffix=".java", mode="w", delete=False,
        ) as f:
            f.write(code)
            f.flush()
            analyzer = ANALYZER()
            result = analyzer.analyze_file(f.name)
        assert isinstance(result, ShadowResult)

    def test_no_shadow_java(self) -> None:
        code = (
            "public class App {\n"
            "    public int compute(int a, int b) {\n"
            "        return a + b;\n"
            "    }\n"
            "}\n"
        )
        with tempfile.NamedTemporaryFile(
            suffix=".java", mode="w", delete=False,
        ) as f:
            f.write(code)
            f.flush()
            analyzer = ANALYZER()
            result = analyzer.analyze_file(f.name)
        assert len(result.issues) == 0

    def test_for_loop_shadow_java(self) -> None:
        code = (
            "public class App {\n"
            "    public void process(java.util.List<String> items) {\n"
            "        int i = 0;\n"
            "        for (String i : items) {\n"
            "            System.out.println(i);\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
        with tempfile.NamedTemporaryFile(
            suffix=".java", mode="w", delete=False,
        ) as f:
            f.write(code)
            f.flush()
            analyzer = ANALYZER()
            result = analyzer.analyze_file(f.name)
        assert len(result.issues) >= 1


# ── Go detection tests ──────────────────────────────────────────────


class TestGo:
    def test_function_param_shadow(self) -> None:
        code = (
            "package main\n"
            "\n"
            'var data = []int{1, 2, 3}\n'
            "\n"
            "func process(data []int) int {\n"
            "    return len(data)\n"
            "}\n"
        )
        with tempfile.NamedTemporaryFile(
            suffix=".go", mode="w", delete=False,
        ) as f:
            f.write(code)
            f.flush()
            analyzer = ANALYZER()
            result = analyzer.analyze_file(f.name)
        assert len(result.issues) >= 1

    def test_if_block_shadow(self) -> None:
        code = (
            "package main\n"
            "\n"
            "func process() {\n"
            "    x := 1\n"
            "    if true {\n"
            "        x := 2\n"
            "        _ = x\n"
            "    }\n"
            "}\n"
        )
        with tempfile.NamedTemporaryFile(
            suffix=".go", mode="w", delete=False,
        ) as f:
            f.write(code)
            f.flush()
            analyzer = ANALYZER()
            result = analyzer.analyze_file(f.name)
        assert len(result.issues) >= 1

    def test_no_shadow_go(self) -> None:
        code = (
            "package main\n"
            "\n"
            "func compute(a int, b int) int {\n"
            "    return a + b\n"
            "}\n"
        )
        with tempfile.NamedTemporaryFile(
            suffix=".go", mode="w", delete=False,
        ) as f:
            f.write(code)
            f.flush()
            analyzer = ANALYZER()
            result = analyzer.analyze_file(f.name)
        assert len(result.issues) == 0

    def test_for_loop_shadow_go(self) -> None:
        code = (
            "package main\n"
            "\n"
            "func process() {\n"
            "    i := 0\n"
            "    for i := 0; i < 10; i++ {\n"
            "        _ = i\n"
            "    }\n"
            "}\n"
        )
        with tempfile.NamedTemporaryFile(
            suffix=".go", mode="w", delete=False,
        ) as f:
            f.write(code)
            f.flush()
            analyzer = ANALYZER()
            result = analyzer.analyze_file(f.name)
        assert len(result.issues) >= 1


# ── Severity tests ──────────────────────────────────────────────────────


class TestSeverities:
    def test_param_shadow_severity(self) -> None:
        assert (
            VariableShadowingAnalyzer is not None
        )  # just verify import
        from tree_sitter_analyzer.analysis.variable_shadowing import (
            _SEVERITY_MAP,
        )
        assert _SEVERITY_MAP[ISSUE_COMPREHENSION_SHADOWS] == "high"
        assert _SEVERITY_MAP[ISSUE_PARAM_SHADOWS_OUTER] == "medium"
        assert _SEVERITY_MAP[ISSUE_LOCAL_SHADOWS_PARAM] == "medium"
        assert _SEVERITY_MAP[ISSUE_LOCAL_SHADOWS_OUTER] == "low"
