"""Tests for Nested Class Analyzer."""
from __future__ import annotations

import tempfile
from pathlib import Path

from tree_sitter_analyzer.analysis.nested_class import (
    NestedClassAnalyzer,
    NestedClassResult,
)

ANALYZER = NestedClassAnalyzer()


def _analyze(code: str, suffix: str = ".py") -> NestedClassResult:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False
    ) as f:
        f.write(code)
        f.flush()
        return ANALYZER.analyze_file(f.name)


class TestNestedClassPython:
    """Tests for Python nested class detection."""

    def test_no_nesting(self) -> None:
        code = (
            "class Foo:\n"
            "    def bar(self):\n"
            "        pass\n"
            "\n"
            "class Baz:\n"
            "    def qux(self):\n"
            "        pass\n"
        )
        result = _analyze(code)
        assert result.total_issues == 0

    def test_single_nested_class(self) -> None:
        code = (
            "class Outer:\n"
            "    class Inner:\n"
            "        pass\n"
        )
        result = _analyze(code)
        assert result.total_issues == 1
        assert result.issues[0].inner_class == "Inner"
        assert result.issues[0].outer_class == "Outer"
        assert result.issues[0].nesting_depth == 1

    def test_deeply_nested(self) -> None:
        code = (
            "class Outer:\n"
            "    class Middle:\n"
            "        class Inner:\n"
            "            pass\n"
        )
        result = _analyze(code)
        assert result.total_issues == 2
        names = [i.inner_class for i in result.issues]
        assert "Middle" in names
        assert "Inner" in names

    def test_nested_class_severity_low(self) -> None:
        code = (
            "class Outer:\n"
            "    class Inner:\n"
            "        pass\n"
        )
        result = _analyze(code)
        assert result.issues[0].severity == "low"

    def test_multiple_nested_in_same_class(self) -> None:
        code = (
            "class Outer:\n"
            "    class Inner1:\n"
            "        pass\n"
            "\n"
            "    class Inner2:\n"
            "        pass\n"
        )
        result = _analyze(code)
        assert result.total_issues == 2

    def test_class_with_method_not_nested(self) -> None:
        code = (
            "class Foo:\n"
            "    def bar(self):\n"
            "        pass\n"
        )
        result = _analyze(code)
        assert result.total_issues == 0

    def test_class_with_nested_function_not_flagged(self) -> None:
        code = (
            "class Foo:\n"
            "    def bar(self):\n"
            "        def helper():\n"
            "            pass\n"
            "        return helper()\n"
        )
        result = _analyze(code)
        assert result.total_issues == 0


class TestNestedClassJava:
    """Tests for Java nested class detection."""

    def test_java_inner_class(self) -> None:
        code = (
            "public class Outer {\n"
            "    class Inner {\n"
            "        void foo() {}\n"
            "    }\n"
            "}\n"
        )
        result = _analyze(code, suffix=".java")
        assert result.total_issues == 1
        assert result.issues[0].inner_class == "Inner"

    def test_java_no_nesting(self) -> None:
        code = (
            "public class Foo {\n"
            "    void bar() {}\n"
            "}\n"
        )
        result = _analyze(code, suffix=".java")
        assert result.total_issues == 0


class TestNestedClassCSharp:
    """Tests for C# nested class detection."""

    def test_csharp_nested_class(self) -> None:
        code = (
            "public class Outer {\n"
            "    public class Inner {\n"
            "        void Foo() {}\n"
            "    }\n"
            "}\n"
        )
        result = _analyze(code, suffix=".cs")
        assert result.total_issues == 1


class TestNestedClassResult:
    """Tests for result object."""

    def test_to_dict(self) -> None:
        code = (
            "class Outer:\n"
            "    class Inner:\n"
            "        pass\n"
        )
        result = _analyze(code)
        d = result.to_dict()
        assert d["total_issues"] == 1
        assert d["issues"][0]["inner_class"] == "Inner"
        assert d["issues"][0]["outer_class"] == "Outer"
        assert d["issues"][0]["nesting_depth"] == 1

    def test_file_path_in_result(self) -> None:
        code = "x = 1\n"
        result = _analyze(code)
        assert result.file_path.endswith(".py")


class TestNestedClassEdgeCases:
    """Tests for edge cases."""

    def test_nonexistent_file(self) -> None:
        result = ANALYZER.analyze_file("/nonexistent/file.py")
        assert result.total_issues == 0

    def test_unsupported_extension(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".rb", delete=False
        ) as f:
            f.write("class Outer; class Inner; end; end")
            f.flush()
            result = ANALYZER.analyze_file(f.name)
        assert result.total_issues == 0

    def test_empty_file(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write("")
            f.flush()
            result = ANALYZER.analyze_file(f.name)
        assert result.total_issues == 0

    def test_only_module_level_classes(self) -> None:
        code = (
            "class Foo:\n"
            "    pass\n"
            "\n"
            "class Bar:\n"
            "    pass\n"
        )
        result = _analyze(code)
        assert result.total_issues == 0
