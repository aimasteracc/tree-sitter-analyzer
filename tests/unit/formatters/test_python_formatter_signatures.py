#!/usr/bin/env python3
"""Python formatter signature, visibility, decorator, class method, compact tests."""


import pytest

from tree_sitter_analyzer.formatters.python_formatter import PythonTableFormatter


class TestPythonFormatterFormatPythonSignature:
    """Test _format_python_signature"""

    @pytest.fixture
    def formatter(self):
        return PythonTableFormatter()

    def test_python_signature_with_return_type(self, formatter):
        method = {
            "name": "func",
            "parameters": [{"name": "x", "type": "int"}],
            "return_type": "str",
        }
        result = formatter._format_python_signature(method)
        assert "-> str" in result

    def test_python_signature_no_return_type(self, formatter):
        method = {
            "name": "func",
            "parameters": [{"name": "x", "type": "int"}],
            "return_type": "",
        }
        result = formatter._format_python_signature(method)
        assert "->" not in result

    def test_python_signature_none_params(self, formatter):
        method = {
            "name": "func",
            "parameters": None,
            "return_type": "None",
        }
        result = formatter._format_python_signature(method)
        assert result == "() -> None"


class TestPythonFormatterVisibilitySymbol:
    """Test _get_python_visibility_symbol"""

    @pytest.fixture
    def formatter(self):
        return PythonTableFormatter()

    def test_visibility_public(self, formatter):
        assert formatter._get_python_visibility_symbol("public") == "🔓"

    def test_visibility_private(self, formatter):
        assert formatter._get_python_visibility_symbol("private") == "🔒"

    def test_visibility_protected(self, formatter):
        assert formatter._get_python_visibility_symbol("protected") == "🔐"

    def test_visibility_magic(self, formatter):
        assert formatter._get_python_visibility_symbol("magic") == "✨"

    def test_visibility_unknown(self, formatter):
        assert formatter._get_python_visibility_symbol("unknown") == "🔓"


class TestPythonFormatterDecoratorsEdge:
    """Test _format_decorators edge cases"""

    @pytest.fixture
    def formatter(self):
        return PythonTableFormatter()

    def test_decorators_important_classmethod(self, formatter):
        result = formatter._format_decorators(["classmethod"])
        assert "@classmethod" in result

    def test_decorators_important_abstractmethod(self, formatter):
        result = formatter._format_decorators(["abstractmethod"])
        assert "@abstractmethod" in result

    def test_decorators_important_dataclass(self, formatter):
        result = formatter._format_decorators(["dataclass"])
        assert "@dataclass" in result

    def test_decorators_important_property(self, formatter):
        result = formatter._format_decorators(["property"])
        assert "@property" in result

    def test_decorators_multiple_with_plus(self, formatter):
        result = formatter._format_decorators(["a", "b", "c"])
        assert "+2" in result


class TestPythonFormatterClassMethodRow:
    """Test _format_class_method_row"""

    @pytest.fixture
    def formatter(self):
        return PythonTableFormatter()

    def test_class_method_row_basic(self, formatter):
        method = {
            "name": "do_stuff",
            "visibility": "public",
            "line_range": {"start": 5, "end": 7},
            "parameters": [{"name": "self", "type": "MyClass"}],
            "return_type": "None",
            "complexity_score": 1,
            "docstring": "",
        }
        result = formatter._format_class_method_row(method)
        assert "do_stuff" in result
        assert "|" in result

    def test_class_method_row_static(self, formatter):
        method = {
            "name": "helper",
            "visibility": "public",
            "line_range": {"start": 10, "end": 12},
            "parameters": [],
            "return_type": "int",
            "complexity_score": 0,
            "is_static": True,
            "docstring": "",
        }
        result = formatter._format_class_method_row(method)
        assert "static" in result

    def test_class_method_row_magic(self, formatter):
        method = {
            "name": "__str__",
            "visibility": "public",
            "line_range": {"start": 15, "end": 17},
            "parameters": [{"name": "self", "type": "MyClass"}],
            "return_type": "str",
            "complexity_score": 0,
            "docstring": "",
        }
        result = formatter._format_class_method_row(method)
        assert "+" in result  # magic = public symbol

    def test_class_method_row_private(self, formatter):
        method = {
            "name": "_internal",
            "visibility": "public",
            "line_range": {"start": 20, "end": 22},
            "parameters": [{"name": "self", "type": "MyClass"}],
            "return_type": "None",
            "complexity_score": 0,
            "docstring": "",
        }
        result = formatter._format_class_method_row(method)
        assert "-" in result  # private = - symbol

    def test_class_method_row_malformed_line_range(self, formatter):
        method = {
            "name": "bad",
            "visibility": "public",
            "line_range": "not_a_dict",
            "parameters": [],
            "return_type": "None",
            "complexity_score": 0,
            "docstring": "",
        }
        result = formatter._format_class_method_row(method)
        assert "0-0" in result

    def test_class_method_row_with_docstring(self, formatter):
        method = {
            "name": "good_func",
            "visibility": "public",
            "line_range": {"start": 1, "end": 5},
            "parameters": [],
            "return_type": "int",
            "complexity_score": 0,
            "docstring": "Does something useful",
        }
        result = formatter._format_class_method_row(method)
        assert "useful" in result


class TestPythonFormatterSignatureCompact:
    """Test _format_python_signature_compact"""

    @pytest.fixture
    def formatter(self):
        return PythonTableFormatter()

    def test_python_signature_compact_with_return(self, formatter):
        method = {
            "name": "f",
            "parameters": [],
            "return_type": "int",
        }
        result = formatter._format_python_signature_compact(method)
        assert "int" in result

    def test_python_signature_compact_no_return(self, formatter):
        method = {
            "name": "f",
            "parameters": [],
            "return_type": "",
        }
        result = formatter._format_python_signature_compact(method)
        assert "Any" in result

    def test_python_signature_compact_none_params(self, formatter):
        method = {
            "name": "f",
            "parameters": None,
            "return_type": "None",
        }
        result = formatter._format_python_signature_compact(method)
        assert "None" in result
