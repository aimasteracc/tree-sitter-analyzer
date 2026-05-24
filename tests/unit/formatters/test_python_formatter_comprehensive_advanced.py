"""
Comprehensive tests for Python table formatter — advanced tests.
Tests cover signatures, type shortening, utilities, and edge cases.
"""

import pytest

from tree_sitter_analyzer.formatters.python_formatter import PythonTableFormatter


class TestPythonTableFormatterSignatures:
    """Test Python table formatter signature creation."""

    @pytest.fixture
    def formatter(self):
        """Create a Python table formatter instance."""
        return PythonTableFormatter()

    def test_create_compact_signature_basic(self, formatter):
        """Test basic compact signature creation."""
        method = {
            "parameters": [
                {"name": "self", "type": "Calculator"},
                {"name": "a", "type": "int"},
                {"name": "b", "type": "str"},
            ],
            "return_type": "bool",
        }

        result = formatter._create_compact_signature(method)

        assert result == "(Calculator,int,str):bool"

    def test_create_compact_signature_complex_types(self, formatter):
        """Test compact signature with complex types."""
        method = {
            "parameters": [
                {"name": "data", "type": "List[str]"},
                {"name": "mapping", "type": "Dict[str, int]"},
                {"name": "optional", "type": "Optional[float]"},
            ],
            "return_type": "Union[str, None]",
        }

        result = formatter._create_compact_signature(method)

        assert "List[str]" in result
        assert "Dict[str, int]" in result
        assert "Optional[float]" in result

    def test_create_compact_signature_no_types(self, formatter):
        """Test compact signature with no type information."""
        method = {
            "parameters": [{"name": "param1"}, {"name": "param2"}],
            "return_type": "Any",
        }

        result = formatter._create_compact_signature(method)

        assert result == "(Any,Any):Any"

    def test_format_python_signature_with_types(self, formatter):
        """Test Python signature formatting with types."""
        method = {
            "parameters": [
                {"name": "self", "type": "Calculator"},
                {"name": "value", "type": "int"},
                {"name": "precision", "type": "float"},
            ],
            "return_type": "Decimal",
        }

        result = formatter._format_python_signature(method)

        assert result == "(self: Calculator, value: int, precision: float) -> Decimal"

    def test_format_python_signature_without_types(self, formatter):
        """Test Python signature formatting without types."""
        method = {
            "parameters": [{"name": "self"}, {"name": "value"}],
            "return_type": "",
        }

        result = formatter._format_python_signature(method)

        assert result == "(self, value)"

    def test_format_python_signature_mixed_types(self, formatter):
        """Test Python signature formatting with mixed type information."""
        method = {
            "parameters": [
                {"name": "self", "type": "Service"},
                {"name": "data"},
                {"name": "callback", "type": "Callable[[str], bool]"},
            ],
            "return_type": "Any",
        }

        result = formatter._format_python_signature(method)

        assert "self: Service" in result
        assert "data," in result
        assert "callback: Callable[[str], bool]" in result


class TestPythonTableFormatterTypeShortening:
    """Test Python table formatter type shortening functionality."""

    @pytest.fixture
    def formatter(self):
        """Create a Python table formatter instance."""
        return PythonTableFormatter()

    def test_shorten_basic_types(self, formatter):
        """Test shortening of basic Python types."""
        assert formatter._shorten_type("str") == "s"
        assert formatter._shorten_type("int") == "i"
        assert formatter._shorten_type("float") == "f"
        assert formatter._shorten_type("bool") == "b"
        assert formatter._shorten_type("None") == "N"
        assert formatter._shorten_type("Any") == "A"

    def test_shorten_collection_types(self, formatter):
        """Test shortening of collection types."""
        assert formatter._shorten_type("List") == "L"
        assert formatter._shorten_type("Dict") == "D"
        assert formatter._shorten_type("Optional") == "O"
        assert formatter._shorten_type("Union") == "U"

    def test_shorten_generic_types(self, formatter):
        """Test shortening of generic types."""
        assert formatter._shorten_type("List[str]") == "L[s]"
        assert formatter._shorten_type("List[int]") == "L[i]"
        assert formatter._shorten_type("Dict[str, int]") == "D[s,i]"
        assert formatter._shorten_type("Optional[str]") == "O[s]"

    def test_shorten_custom_types(self, formatter):
        """Test shortening of custom types."""
        assert formatter._shorten_type("CustomClass") == "Cus"
        assert formatter._shorten_type("VeryLongTypeName") == "Ver"
        assert formatter._shorten_type("ABC") == "ABC"

    def test_shorten_none_type(self, formatter):
        """Test shortening of None type."""
        assert formatter._shorten_type(None) == "Any"

    def test_shorten_non_string_type(self, formatter):
        """Test shortening of non-string types."""
        assert formatter._shorten_type(123) == "123"
        assert formatter._shorten_type([]) == "[]"


class TestPythonTableFormatterUtilities:
    """Test Python table formatter utility functions."""

    @pytest.fixture
    def formatter(self):
        """Create a Python table formatter instance."""
        return PythonTableFormatter()

    def test_extract_module_docstring_single_line(self, formatter):
        """Test extracting single-line module docstring."""
        data = {
            "source_code": '"""Single line module docstring."""\n\nclass Test:\n    pass'
        }

        result = formatter._extract_module_docstring(data)

        assert result == "Single line module docstring."

    def test_extract_module_docstring_multi_line(self, formatter):
        """Test extracting multi-line module docstring."""
        data = {
            "source_code": '"""Multi-line\nmodule docstring\nwith details."""\n\nclass Test:\n    pass'
        }

        result = formatter._extract_module_docstring(data)

        assert "Multi-line" in result
        assert "module docstring" in result
        assert "with details." in result

    def test_extract_module_docstring_single_quotes(self, formatter):
        """Test extracting module docstring with single quotes."""
        data = {
            "source_code": "'''Module docstring with single quotes.'''\n\nclass Test:\n    pass"
        }

        result = formatter._extract_module_docstring(data)

        assert result == "Module docstring with single quotes."

    def test_extract_module_docstring_none(self, formatter):
        """Test extracting module docstring when none exists."""
        data = {"source_code": "import os\n\nclass Test:\n    pass"}

        result = formatter._extract_module_docstring(data)

        assert result is None

    def test_extract_module_docstring_no_source(self, formatter):
        """Test extracting module docstring with no source code."""
        data = {}

        result = formatter._extract_module_docstring(data)

        assert result is None

    def test_get_python_visibility_symbol(self, formatter):
        """Test Python visibility symbol mapping."""
        assert formatter._get_python_visibility_symbol("public") == "🔓"
        assert formatter._get_python_visibility_symbol("private") == "🔒"
        assert formatter._get_python_visibility_symbol("protected") == "🔐"
        assert formatter._get_python_visibility_symbol("magic") == "✨"
        assert formatter._get_python_visibility_symbol("unknown") == "🔓"

    def test_format_decorators_empty(self, formatter):
        """Test formatting empty decorators list."""
        result = formatter._format_decorators([])

        assert result == "-"

    def test_format_decorators_important(self, formatter):
        """Test formatting important decorators."""
        decorators = ["property", "staticmethod", "custom"]
        result = formatter._format_decorators(decorators)

        assert "@property" in result
        assert "@staticmethod" in result

    def test_format_decorators_single(self, formatter):
        """Test formatting single decorator."""
        decorators = ["custom_decorator"]
        result = formatter._format_decorators(decorators)

        assert result == "@custom_decorator"

    def test_format_decorators_multiple_non_important(self, formatter):
        """Test formatting multiple non-important decorators."""
        decorators = ["custom1", "custom2", "custom3"]
        result = formatter._format_decorators(decorators)

        assert result == "@custom1 (+2)"


class TestPythonTableFormatterEdgeCases:
    """Test Python table formatter edge cases."""

    @pytest.fixture
    def formatter(self):
        """Create a Python table formatter instance."""
        return PythonTableFormatter()

    def test_format_with_missing_data_fields(self, formatter):
        """Test formatting with missing data fields."""
        data = {
            "file_path": "incomplete.py"
        }

        result = formatter._format_full_table(data)

        assert isinstance(result, str)
        assert "# Module: incomplete" in result

    def test_format_with_malformed_line_ranges(self, formatter):
        """Test formatting with malformed line ranges."""
        data = {
            "file_path": "test.py",
            "classes": [],
            "functions": [],
            "imports": [],
            "methods": [
                {
                    "name": "broken_method",
                    "line_range": {},
                    "parameters": [],
                    "complexity_score": 0,
                }
            ],
        }

        result = formatter._format_full_table(data)

        assert "broken_method" in result
        assert "0-0" in result

    def test_format_with_unicode_content(self, formatter):
        """Test formatting with Unicode content."""
        data = {
            "file_path": "unicode_test.py",
            "classes": [
                {
                    "name": "测试类",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 10},
                }
            ],
            "functions": [],
            "imports": [],
            "methods": [
                {
                    "name": "处理数据",
                    "visibility": "public",
                    "line_range": {"start": 5, "end": 8},
                    "parameters": [{"name": "数据", "type": "str"}],
                    "return_type": "bool",
                    "complexity_score": 1,
                    "docstring": "处理输入数据并返回结果。",
                }
            ],
        }

        result = formatter._format_full_table(data)

        assert "\u5904\u7406\u6570\u636e" in result
        assert "\u6570\u636e" in result

    def test_format_with_very_long_names(self, formatter):
        """Test formatting with very long names."""
        data = {
            "file_path": "long_names.py",
            "classes": [
                {
                    "name": "VeryLongClassNameThatExceedsNormalLengthLimits",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 50},
                }
            ],
            "functions": [],
            "imports": [],
            "methods": [
                {
                    "name": "extremely_long_method_name_that_should_be_handled_gracefully",
                    "visibility": "public",
                    "line_range": {"start": 10, "end": 20},
                    "parameters": [
                        {"name": "very_long_parameter_name", "type": "VeryLongTypeName"}
                    ],
                    "return_type": "AnotherVeryLongTypeName",
                    "complexity_score": 1,
                    "docstring": "This is a very long docstring that should be truncated appropriately.",
                }
            ],
        }

        result = formatter._format_full_table(data)

        assert (
            "VeryLongClassNameThatExceedsNormalLengthLimits" in result
            or "Ver" in result
        )
        assert "extremely_long_method_name_that_should_be_handled_gracefully" in result

    def test_format_with_empty_collections(self, formatter):
        """Test formatting with empty collections."""
        data = {
            "file_path": "empty.py",
            "classes": [],
            "functions": [],
            "imports": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0, "class_count": 0},
        }

        result = formatter._format_full_table(data)

        assert "# Module: empty" in result

    def test_format_with_none_values(self, formatter):
        """Test formatting with None values in data."""
        data = {
            "file_path": "test.py",
            "classes": [
                {"name": None, "type": None, "visibility": None, "line_range": None}
            ],
            "functions": [],
            "imports": [],
            "methods": [
                {
                    "name": None,
                    "visibility": None,
                    "line_range": None,
                    "parameters": None,
                    "return_type": None,
                    "complexity_score": None,
                    "docstring": None,
                }
            ],
        }

        result = formatter._format_full_table(data)

        assert isinstance(result, str)

    def test_format_performance_with_large_data(self, formatter):
        """Test formatting performance with large datasets."""
        large_methods = []
        for i in range(100):
            large_methods.append(
                {
                    "name": f"method_{i}",
                    "visibility": "public",
                    "line_range": {"start": i * 10, "end": i * 10 + 5},
                    "parameters": [{"name": "self", "type": "TestClass"}]
                    + [{"name": f"param_{j}", "type": "str"} for j in range(5)],
                    "return_type": "bool",
                    "complexity_score": i % 10,
                    "docstring": f"Method {i} documentation.",
                    "is_async": i % 2 == 0,
                    "decorators": [f"decorator_{j}" for j in range(3)],
                }
            )

        data = {
            "file_path": "large_file.py",
            "classes": [
                {"name": "LargeClass", "type": "class", "visibility": "public"}
            ],
            "functions": [],
            "imports": [],
            "methods": large_methods,
            "statistics": {"method_count": 100, "field_count": 0, "class_count": 1},
        }

        result = formatter._format_full_table(data)

        assert isinstance(result, str)
        assert len(result) > 1000
        assert "method_0" in result
        assert "method_99" in result
