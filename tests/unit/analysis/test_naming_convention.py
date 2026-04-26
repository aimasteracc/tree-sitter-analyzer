"""Unit tests for NamingConventionAnalyzer."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.naming_convention import (
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    STYLE_CAMEL,
    STYLE_LOWER,
    STYLE_PASCAL,
    STYLE_SNAKE,
    STYLE_UNKNOWN,
    STYLE_UPPER_SNAKE,
    VIOLATION_LANGUAGE,
    VIOLATION_SINGLE_LETTER,
    NamingConventionAnalyzer,
    NamingResult,
    NamingViolation,
    StyleDistribution,
    _detect_style,
    _split_identifier,
    _suggest_style,
)


@pytest.fixture
def analyzer() -> NamingConventionAnalyzer:
    return NamingConventionAnalyzer()


def _write_tmp(content: str, suffix: str = ".py") -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return f.name


class TestDetectStyle:
    def test_snake_case(self) -> None:
        assert _detect_style("my_variable") == STYLE_SNAKE

    def test_camel_case(self) -> None:
        assert _detect_style("myVariable") == STYLE_CAMEL

    def test_pascal_case(self) -> None:
        assert _detect_style("MyClass") == STYLE_PASCAL

    def test_upper_snake(self) -> None:
        assert _detect_style("MY_CONST") == STYLE_UPPER_SNAKE

    def test_lower_before_camel(self) -> None:
        # "name" has no uppercase — lowercase, not camelCase
        assert _detect_style("name") == STYLE_LOWER
        assert _detect_style("myName") == STYLE_CAMEL

    def test_screaming_snake(self) -> None:
        assert _detect_style("MAX_RETRIES") == STYLE_UPPER_SNAKE

    def test_unknown(self) -> None:
        assert _detect_style("__init__") == STYLE_UNKNOWN


class TestSplitIdentifier:
    def test_snake(self) -> None:
        assert _split_identifier("my_var") == ["my", "var"]

    def test_camel(self) -> None:
        assert _split_identifier("myVar") == ["my", "var"]

    def test_pascal(self) -> None:
        assert _split_identifier("MyClass") == ["my", "class"]

    def test_upper_snake(self) -> None:
        assert _split_identifier("MY_CONST") == ["my", "const"]

    def test_single_word(self) -> None:
        assert _split_identifier("name") == ["name"]


class TestSuggestStyle:
    def test_camel_to_snake(self) -> None:
        result = _suggest_style("myVariable", STYLE_SNAKE)
        assert result == "my_variable"

    def test_snake_to_camel(self) -> None:
        result = _suggest_style("my_variable", STYLE_CAMEL)
        assert result == "myVariable"

    def test_snake_to_pascal(self) -> None:
        result = _suggest_style("my_class", STYLE_PASCAL)
        assert result == "MyClass"

    def test_already_correct(self) -> None:
        assert _suggest_style("my_var", STYLE_SNAKE) is None

    def test_camel_to_pascal(self) -> None:
        result = _suggest_style("myClass", STYLE_PASCAL)
        assert result == "MyClass"


class TestDataclasses:
    def test_naming_violation_to_dict(self) -> None:
        v = NamingViolation(
            name="BadName",
            line_number=5,
            element_type="function",
            violation_type=VIOLATION_LANGUAGE,
            severity=SEVERITY_HIGH,
            current_style=STYLE_PASCAL,
            expected_style=STYLE_SNAKE,
            suggestion="bad_name",
        )
        d = v.to_dict()
        assert d["name"] == "BadName"
        assert d["line_number"] == 5
        assert d["violation_type"] == VIOLATION_LANGUAGE

    def test_style_distribution_to_dict(self) -> None:
        s = StyleDistribution(style=STYLE_SNAKE, count=10, percentage=50.0)
        d = s.to_dict()
        assert d["style"] == STYLE_SNAKE
        assert d["count"] == 10
        assert d["percentage"] == 50.0

    def test_naming_result_to_dict(self) -> None:
        v = NamingViolation(
            name="X", line_number=1, element_type="variable",
            violation_type=VIOLATION_SINGLE_LETTER, severity=SEVERITY_MEDIUM,
            current_style=STYLE_LOWER, expected_style=STYLE_SNAKE,
            suggestion=None,
        )
        r = NamingResult(
            file_path="test.py", language="python",
            total_identifiers=5, violations=(v,),
            naming_score=80.0, style_distribution=(),
        )
        d = r.to_dict()
        assert d["file_path"] == "test.py"
        assert d["violation_count"] == 1
        assert len(d["violations"]) == 1

    def test_get_high_severity(self) -> None:
        v_high = NamingViolation(
            name="BadName", line_number=1, element_type="function",
            violation_type=VIOLATION_LANGUAGE, severity=SEVERITY_HIGH,
            current_style=STYLE_PASCAL, expected_style=STYLE_SNAKE,
            suggestion="bad_name",
        )
        v_med = NamingViolation(
            name="x", line_number=2, element_type="variable",
            violation_type=VIOLATION_SINGLE_LETTER, severity=SEVERITY_MEDIUM,
            current_style=STYLE_LOWER, expected_style=STYLE_SNAKE,
            suggestion=None,
        )
        r = NamingResult(
            file_path="t.py", language="python",
            total_identifiers=2, violations=(v_high, v_med),
            naming_score=0.0, style_distribution=(),
        )
        high = r.get_high_severity()
        assert len(high) == 1
        assert high[0].name == "BadName"


class TestPythonAnalysis:
    def test_no_violations(self, analyzer: NamingConventionAnalyzer) -> None:
        code = "def hello_world():\n    pass\n"
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            assert result.language == "python"
            assert result.naming_score == 100.0
            assert len(result.violations) == 0
        finally:
            Path(path).unlink()

    def test_function_violation(self, analyzer: NamingConventionAnalyzer) -> None:
        code = "def BadFunction():\n    pass\n"
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            assert len(result.violations) >= 1
            lang_violations = [
                v for v in result.violations
                if v.violation_type == VIOLATION_LANGUAGE
            ]
            assert len(lang_violations) >= 1
            assert lang_violations[0].name == "BadFunction"
            assert lang_violations[0].expected_style == STYLE_SNAKE
            assert lang_violations[0].current_style == STYLE_PASCAL
            assert lang_violations[0].suggestion == "bad_function"
        finally:
            Path(path).unlink()

    def test_class_pascal_case(self, analyzer: NamingConventionAnalyzer) -> None:
        code = "class MyGoodClass:\n    pass\n"
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            class_violations = [
                v for v in result.violations if v.element_type == "class"
            ]
            assert len(class_violations) == 0
        finally:
            Path(path).unlink()

    def test_class_violation(self, analyzer: NamingConventionAnalyzer) -> None:
        code = "class my_bad_class:\n    pass\n"
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            class_violations = [
                v for v in result.violations
                if v.element_type == "class"
                and v.violation_type == VIOLATION_LANGUAGE
            ]
            assert len(class_violations) >= 1
            assert class_violations[0].expected_style == STYLE_PASCAL
        finally:
            Path(path).unlink()

    def test_single_letter_var(self, analyzer: NamingConventionAnalyzer) -> None:
        code = "q = 42\n"
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            single_letter = [
                v for v in result.violations
                if v.violation_type == VIOLATION_SINGLE_LETTER
            ]
            assert len(single_letter) == 1
            assert single_letter[0].name == "q"
        finally:
            Path(path).unlink()

    def test_loop_vars_allowed(self, analyzer: NamingConventionAnalyzer) -> None:
        code = "for i in range(10):\n    pass\n"
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            single_letter = [
                v for v in result.violations
                if v.violation_type == VIOLATION_SINGLE_LETTER
            ]
            assert len(single_letter) == 0
        finally:
            Path(path).unlink()

    def test_variable_assignment(self, analyzer: NamingConventionAnalyzer) -> None:
        code = "myGoodVar = 42\n"
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            lang_violations = [
                v for v in result.violations
                if v.violation_type == VIOLATION_LANGUAGE
                and v.element_type == "variable"
            ]
            assert len(lang_violations) >= 1
            assert lang_violations[0].expected_style == STYLE_SNAKE
        finally:
            Path(path).unlink()

    def test_constant_upper_snake(self, analyzer: NamingConventionAnalyzer) -> None:
        code = "MY_CONST = 42\n"
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            violations = [
                v for v in result.violations
                if v.element_type == "variable"
            ]
            assert len(violations) == 0
        finally:
            Path(path).unlink()

    def test_style_distribution(self, analyzer: NamingConventionAnalyzer) -> None:
        code = (
            "def good_func():\n"
            "    my_var = 1\n"
            "    pass\n"
        )
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            assert len(result.style_distribution) > 0
            styles = {s.style for s in result.style_distribution}
            assert STYLE_SNAKE in styles
        finally:
            Path(path).unlink()

    def test_score_calculation(self, analyzer: NamingConventionAnalyzer) -> None:
        code = "def BadFunc():\n    pass\n"
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            assert result.naming_score < 100.0
        finally:
            Path(path).unlink()

    def test_for_loop_var(self, analyzer: NamingConventionAnalyzer) -> None:
        code = "for myItem in items:\n    pass\n"
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            violations = [
                v for v in result.violations
                if v.element_type == "variable"
                and v.name == "myItem"
            ]
            assert len(violations) >= 1
        finally:
            Path(path).unlink()


class TestJavaScriptAnalysis:
    def test_camel_case_function(
        self, analyzer: NamingConventionAnalyzer
    ) -> None:
        code = "function myFunc() { return 1; }\n"
        path = _write_tmp(code, suffix=".js")
        try:
            result = analyzer.analyze_file(path)
            assert result.language == "javascript"
            violations = [
                v for v in result.violations
                if v.element_type == "function"
                and v.violation_type == VIOLATION_LANGUAGE
            ]
            assert len(violations) == 0
        finally:
            Path(path).unlink()

    def test_pascal_function_violation(
        self, analyzer: NamingConventionAnalyzer
    ) -> None:
        code = "function MyBadFunc() { return 1; }\n"
        path = _write_tmp(code, suffix=".js")
        try:
            result = analyzer.analyze_file(path)
            violations = [
                v for v in result.violations
                if v.element_type == "function"
                and v.violation_type == VIOLATION_LANGUAGE
            ]
            assert len(violations) >= 1
            assert violations[0].expected_style == STYLE_CAMEL
        finally:
            Path(path).unlink()

    def test_class_pascal_ok(
        self, analyzer: NamingConventionAnalyzer
    ) -> None:
        code = "class MyComponent { constructor() {} }\n"
        path = _write_tmp(code, suffix=".js")
        try:
            result = analyzer.analyze_file(path)
            class_v = [
                v for v in result.violations
                if v.element_type == "class"
            ]
            assert len(class_v) == 0
        finally:
            Path(path).unlink()

    def test_var_declarator(
        self, analyzer: NamingConventionAnalyzer
    ) -> None:
        code = "const MyBadVar = 42;\n"
        path = _write_tmp(code, suffix=".js")
        try:
            result = analyzer.analyze_file(path)
            violations = [
                v for v in result.violations
                if v.element_type == "variable"
                and v.violation_type == VIOLATION_LANGUAGE
            ]
            assert len(violations) >= 1
        finally:
            Path(path).unlink()

    def test_arrow_function(
        self, analyzer: NamingConventionAnalyzer
    ) -> None:
        code = "const MyBadArrow = () => 42;\n"
        path = _write_tmp(code, suffix=".js")
        try:
            result = analyzer.analyze_file(path)
            violations = [
                v for v in result.violations
                if v.violation_type == VIOLATION_LANGUAGE
            ]
            assert len(violations) >= 1
        finally:
            Path(path).unlink()


class TestTypeScriptAnalysis:
    def test_ts_function(self, analyzer: NamingConventionAnalyzer) -> None:
        code = "function goodFunc(): number { return 1; }\n"
        path = _write_tmp(code, suffix=".ts")
        try:
            result = analyzer.analyze_file(path)
            assert result.language == "typescript"
            violations = [
                v for v in result.violations
                if v.element_type == "function"
                and v.violation_type == VIOLATION_LANGUAGE
            ]
            assert len(violations) == 0
        finally:
            Path(path).unlink()


class TestJavaAnalysis:
    def test_method_camel(self, analyzer: NamingConventionAnalyzer) -> None:
        code = (
            "public class Foo {\n"
            "    public void goodMethod() {}\n"
            "}\n"
        )
        path = _write_tmp(code, suffix=".java")
        try:
            result = analyzer.analyze_file(path)
            assert result.language == "java"
            method_v = [
                v for v in result.violations
                if v.element_type == "method"
                and v.violation_type == VIOLATION_LANGUAGE
            ]
            assert len(method_v) == 0
        finally:
            Path(path).unlink()

    def test_method_violation(
        self, analyzer: NamingConventionAnalyzer
    ) -> None:
        code = (
            "public class Foo {\n"
            "    public void BadMethod() {}\n"
            "}\n"
        )
        path = _write_tmp(code, suffix=".java")
        try:
            result = analyzer.analyze_file(path)
            method_v = [
                v for v in result.violations
                if v.element_type == "method"
                and v.violation_type == VIOLATION_LANGUAGE
            ]
            assert len(method_v) >= 1
            assert method_v[0].expected_style == STYLE_CAMEL
        finally:
            Path(path).unlink()

    def test_class_pascal(self, analyzer: NamingConventionAnalyzer) -> None:
        code = "public class GoodClass {}\n"
        path = _write_tmp(code, suffix=".java")
        try:
            result = analyzer.analyze_file(path)
            class_v = [
                v for v in result.violations
                if v.element_type == "class"
                and v.violation_type == VIOLATION_LANGUAGE
            ]
            assert len(class_v) == 0
        finally:
            Path(path).unlink()


class TestGoAnalysis:
    def test_function(self, analyzer: NamingConventionAnalyzer) -> None:
        code = (
            "package main\n\n"
            "func goodFunc() int {\n"
            "    return 1\n"
            "}\n"
        )
        path = _write_tmp(code, suffix=".go")
        try:
            result = analyzer.analyze_file(path)
            assert result.language == "go"
        finally:
            Path(path).unlink()

    def test_class_not_expected(
        self, analyzer: NamingConventionAnalyzer
    ) -> None:
        code = (
            "package main\n\n"
            "func main() {\n"
            "    fmt.Println(\"hello\")\n"
            "}\n"
        )
        path = _write_tmp(code, suffix=".go")
        try:
            result = analyzer.analyze_file(path)
            assert result.language == "go"
        finally:
            Path(path).unlink()


class TestEdgeCases:
    def test_unsupported_extension(
        self, analyzer: NamingConventionAnalyzer
    ) -> None:
        path = _write_tmp("x = 1\n", suffix=".txt")
        try:
            result = analyzer.analyze_file(path)
            assert result.language == "unknown"
            assert result.naming_score == 100.0
            assert len(result.violations) == 0
        finally:
            Path(path).unlink()

    def test_nonexistent_file(
        self, analyzer: NamingConventionAnalyzer
    ) -> None:
        result = analyzer.analyze_file("/nonexistent/file.py")
        assert result.naming_score == 0.0

    def test_multiple_functions_mixed(
        self, analyzer: NamingConventionAnalyzer
    ) -> None:
        code = (
            "def good_func():\n"
            "    pass\n"
            "\n"
            "def BadFunc():\n"
            "    pass\n"
            "\n"
            "class MyClass:\n"
            "    def ok_method(self):\n"
            "        pass\n"
        )
        path = _write_tmp(code)
        try:
            result = analyzer.analyze_file(path)
            assert result.total_identifiers >= 4
            lang_v = [
                v for v in result.violations
                if v.violation_type == VIOLATION_LANGUAGE
            ]
            assert any(v.name == "BadFunc" for v in lang_v)
        finally:
            Path(path).unlink()
