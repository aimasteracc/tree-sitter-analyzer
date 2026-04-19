"""Tests for Missing Static Method Analyzer."""
from __future__ import annotations

import tempfile
from pathlib import Path

from tree_sitter_analyzer.analysis.missing_static_method import (
    MissingStaticMethodAnalyzer,
    MissingStaticMethodResult,
)

ANALYZER = MissingStaticMethodAnalyzer()


def _analyze(code: str) -> MissingStaticMethodResult:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False
    ) as f:
        f.write(code)
        f.flush()
        return ANALYZER.analyze_file(f.name)


class TestMissingStaticMethodBasic:
    """Tests for basic detection."""

    def test_method_uses_self_attribute(self) -> None:
        code = (
            "class Foo:\n"
            "    def bar(self):\n"
            "        return self.x\n"
        )
        result = _analyze(code)
        assert result.total_issues == 0

    def test_method_uses_self_method_call(self) -> None:
        code = (
            "class Foo:\n"
            "    def bar(self):\n"
            "        return self.baz()\n"
        )
        result = _analyze(code)
        assert result.total_issues == 0

    def test_method_no_self_usage(self) -> None:
        code = (
            "class Foo:\n"
            "    def bar(self):\n"
            "        return 42\n"
        )
        result = _analyze(code)
        assert result.total_issues == 1
        assert result.issues[0].method_name == "bar"
        assert result.issues[0].class_name == "Foo"

    def test_method_self_in_expression(self) -> None:
        code = (
            "class Foo:\n"
            "    def bar(self, x):\n"
            "        return x + 1\n"
        )
        result = _analyze(code)
        assert result.total_issues == 1

    def test_method_self_in_body_but_not_param(self) -> None:
        code = (
            "class Foo:\n"
            "    def bar(self):\n"
            "        x = self.value\n"
            "        return x\n"
        )
        result = _analyze(code)
        assert result.total_issues == 0


class TestMissingStaticMethodDecorators:
    """Tests for decorator handling."""

    def test_already_staticmethod(self) -> None:
        code = (
            "class Foo:\n"
            "    @staticmethod\n"
            "    def bar():\n"
            "        return 42\n"
        )
        result = _analyze(code)
        assert result.total_issues == 0

    def test_already_classmethod(self) -> None:
        code = (
            "class Foo:\n"
            "    @classmethod\n"
            "    def bar(cls):\n"
            "        return 42\n"
        )
        result = _analyze(code)
        assert result.total_issues == 0

    def test_other_decorator_no_self(self) -> None:
        code = (
            "class Foo:\n"
            "    @property\n"
            "    def bar(self):\n"
            "        return 42\n"
        )
        result = _analyze(code)
        assert result.total_issues == 1


class TestMissingStaticMethodDunder:
    """Tests for dunder method handling."""

    def test_dunder_init_not_flagged(self) -> None:
        code = (
            "class Foo:\n"
            "    def __init__(self):\n"
            "        pass\n"
        )
        result = _analyze(code)
        assert result.total_issues == 0

    def test_dunder_str_not_flagged(self) -> None:
        code = (
            "class Foo:\n"
            "    def __str__(self):\n"
            "        return 'foo'\n"
        )
        result = _analyze(code)
        assert result.total_issues == 0

    def test_dunder_repr_not_flagged(self) -> None:
        code = (
            "class Foo:\n"
            "    def __repr__(self):\n"
            "        return 'Foo()'\n"
        )
        result = _analyze(code)
        assert result.total_issues == 0


class TestMissingStaticMethodMultiple:
    """Tests for multiple classes and methods."""

    def test_multiple_methods_in_class(self) -> None:
        code = (
            "class Foo:\n"
            "    def uses_self(self):\n"
            "        return self.x\n"
            "\n"
            "    def no_self(self):\n"
            "        return 42\n"
        )
        result = _analyze(code)
        assert result.total_issues == 1
        assert result.issues[0].method_name == "no_self"

    def test_multiple_classes(self) -> None:
        code = (
            "class Foo:\n"
            "    def bar(self):\n"
            "        return 42\n"
            "\n"
            "class Baz:\n"
            "    def qux(self):\n"
            "        return self.x\n"
        )
        result = _analyze(code)
        assert result.total_issues == 1
        assert result.issues[0].class_name == "Foo"


class TestMissingStaticMethodResult:
    """Tests for result object."""

    def test_to_dict(self) -> None:
        code = (
            "class Foo:\n"
            "    def bar(self):\n"
            "        return 42\n"
        )
        result = _analyze(code)
        d = result.to_dict()
        assert d["total_issues"] == 1
        assert d["issues"][0]["method_name"] == "bar"
        assert d["issues"][0]["class_name"] == "Foo"

    def test_file_path_in_result(self) -> None:
        code = "x = 1\n"
        result = _analyze(code)
        assert result.file_path.endswith(".py")


class TestMissingStaticMethodEdgeCases:
    """Tests for edge cases."""

    def test_nonexistent_file(self) -> None:
        result = ANALYZER.analyze_file("/nonexistent/file.py")
        assert result.total_issues == 0

    def test_unsupported_extension(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".js", delete=False
        ) as f:
            f.write("class Foo { bar() { return 42; } }")
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

    def test_standalone_function_not_flagged(self) -> None:
        code = "def helper(x):\n    return x + 1\n"
        result = _analyze(code)
        assert result.total_issues == 0

    def test_self_as_standalone_identifier(self) -> None:
        code = (
            "class Foo:\n"
            "    def bar(self):\n"
            "        return self\n"
        )
        result = _analyze(code)
        assert result.total_issues == 0
