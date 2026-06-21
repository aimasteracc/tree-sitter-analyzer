#!/usr/bin/env python3
"""Python formatter error handling, boundary conditions, special chars, type/docstring handling."""


import pytest

from tree_sitter_analyzer.formatters.python_formatter import PythonTableFormatter


class TestPythonFormatterErrorHandling:
    """Test Python formatter error handling."""

    @pytest.fixture
    def formatter(self):
        """Create a Python table formatter instance."""
        return PythonTableFormatter()

    def test_format_with_none_data(self, formatter):
        """Test formatting with None data."""
        with pytest.raises((TypeError, AttributeError)):
            formatter.format(None)

    def test_format_with_invalid_data_type(self, formatter):
        """Test formatting with invalid data type."""
        with pytest.raises((TypeError, AttributeError)):
            formatter.format("invalid_string_data")

    def test_format_with_circular_reference(self, formatter):
        """Test formatting with circular reference in data."""
        data = {"file_path": "test.py"}
        data["self_ref"] = data  # Circular reference

        # Should handle gracefully without infinite recursion
        result = formatter.format(data)
        assert isinstance(result, str)

    def test_format_with_deeply_nested_data(self, formatter):
        """Test formatting with deeply nested data structures."""
        nested_data = {"level": 0}
        current = nested_data

        # Create deep nesting
        for i in range(100):
            current["next"] = {"level": i + 1}
            current = current["next"]

        data = {
            "file_path": "deep.py",
            "classes": [],
            "functions": [],
            "imports": [],
            "nested": nested_data,
        }

        result = formatter.format(data)
        assert isinstance(result, str)

    def test_format_with_malformed_parameters(self, formatter):
        """Test formatting with malformed parameter data."""
        data = {
            "file_path": "malformed.py",
            "classes": [],
            "functions": [],
            "imports": [],
            "methods": [
                {
                    "name": "test_method",
                    "parameters": "invalid_string_instead_of_list",  # Should be list
                    "return_type": {
                        "invalid": "dict_instead_of_string"
                    },  # Should be string
                    "line_range": "invalid_string_instead_of_dict",  # Should be dict
                }
            ],
        }

        result = formatter.format(data)
        assert isinstance(result, str)
        assert "test_method" in result

    def test_format_with_missing_required_fields(self, formatter):
        """Test formatting with missing required fields."""
        data = {
            "file_path": "incomplete.py",
            "methods": [
                {
                    # Missing name, parameters, etc.
                    "visibility": "public"
                }
            ],
        }

        result = formatter.format(data)
        assert isinstance(result, str)

    def test_format_with_extremely_large_values(self, formatter):
        """Test formatting with extremely large numeric values."""
        data = {
            "file_path": "large_values.py",
            "classes": [],
            "functions": [],
            "imports": [],
            "methods": [
                {
                    "name": "large_method",
                    "line_range": {"start": 999999999, "end": 9999999999},
                    "complexity_score": 999999999,
                    "parameters": [],
                }
            ],
        }

        result = formatter.format(data)
        assert isinstance(result, str)
        assert "999999999" in result


class TestPythonFormatterBoundaryConditions:
    """Test Python formatter boundary conditions."""

    @pytest.fixture
    def formatter(self):
        """Create a Python table formatter instance."""
        return PythonTableFormatter()

    def test_format_empty_string_values(self, formatter):
        """Test formatting with empty string values."""
        data = {
            "file_path": "",
            "classes": [
                {
                    "name": "",
                    "type": "",
                    "visibility": "",
                    "line_range": {"start": 0, "end": 0},
                }
            ],
            "functions": [],
            "imports": [],
            "methods": [
                {
                    "name": "",
                    "visibility": "",
                    "return_type": "",
                    "docstring": "",
                    "parameters": [],
                }
            ],
        }

        result = formatter.format(data)
        assert isinstance(result, str)

    def test_format_zero_values(self, formatter):
        """Test formatting with zero values."""
        data = {
            "file_path": "zero.py",
            "classes": [],
            "functions": [],
            "imports": [],
            "methods": [
                {
                    "name": "zero_method",
                    "line_range": {"start": 0, "end": 0},
                    "complexity_score": 0,
                    "parameters": [],
                }
            ],
            "statistics": {"method_count": 0, "field_count": 0, "class_count": 0},
        }

        result = formatter.format(data)
        assert isinstance(result, str)
        assert "0" in result

    def test_format_negative_values(self, formatter):
        """Test formatting with negative values."""
        data = {
            "file_path": "negative.py",
            "classes": [],
            "functions": [],
            "imports": [],
            "methods": [
                {
                    "name": "negative_method",
                    "line_range": {"start": -1, "end": -1},
                    "complexity_score": -5,
                    "parameters": [],
                }
            ],
        }

        result = formatter.format(data)
        assert isinstance(result, str)
        assert "-1" in result or "-5" in result

    def test_format_single_character_names(self, formatter):
        """Test formatting with single character names."""
        data = {
            "file_path": "a.py",
            "classes": [
                {
                    "name": "A",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 5},
                }
            ],
            "functions": [],
            "imports": [],
            "methods": [
                {
                    "name": "f",
                    "visibility": "public",
                    "parameters": [{"name": "x", "type": "int"}],
                    "return_type": "int",
                }
            ],
        }

        result = formatter.format(data)
        assert isinstance(result, str)
        # Single character class names appear in module header
        assert "a" in result  # Module name is lowercase
        assert "f" in result

    def test_format_maximum_length_strings(self, formatter):
        """Test formatting with maximum length strings."""
        max_length_name = "a" * 1000
        max_length_docstring = "This is a very long docstring. " * 100

        data = {
            "file_path": "max_length.py",
            "classes": [
                {
                    "name": max_length_name,
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 100},
                }
            ],
            "functions": [],
            "imports": [],
            "methods": [
                {
                    "name": max_length_name,
                    "visibility": "public",
                    "docstring": max_length_docstring,
                    "parameters": [],
                }
            ],
        }

        result = formatter.format(data)
        assert isinstance(result, str)
        # Should handle very long strings without crashing


class TestPythonFormatterSpecialCharacters:
    """Test Python formatter with special characters."""

    @pytest.fixture
    def formatter(self):
        """Create a Python table formatter instance."""
        return PythonTableFormatter()

    def test_format_with_unicode_characters(self, formatter):
        """Test formatting with Unicode characters."""
        data = {
            "file_path": "unicode_测试.py",
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
                    "docstring": "处理输入数据并返回结果。包含中文字符。",
                    "parameters": [{"name": "数据", "type": "str"}],
                    "return_type": "bool",
                }
            ],
        }

        result = formatter.format(data)
        assert isinstance(result, str)
        # Unicode characters are escaped in output
        assert "\u6d4b\u8bd5" in result  # Part of unicode_测试
        assert "处理数据" in result

    def test_format_with_emoji_characters(self, formatter):
        """Test formatting with emoji characters."""
        data = {
            "file_path": "emoji_test.py",
            "classes": [
                {
                    "name": "EmojiClass🚀",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 10},
                }
            ],
            "functions": [],
            "imports": [],
            "methods": [
                {
                    "name": "process_data_🔥",
                    "visibility": "public",
                    "docstring": "Process data with fire! 🔥🚀✨",
                    "parameters": [],
                    "return_type": "str",
                }
            ],
        }

        result = formatter.format(data)
        assert isinstance(result, str)
        assert "🚀" in result
        assert "🔥" in result

    def test_format_with_special_symbols(self, formatter):
        """Test formatting with special symbols."""
        data = {
            "file_path": "special@symbols#test$.py",
            "classes": [
                {
                    "name": "Class_With_$pecial_Ch@rs",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 10},
                }
            ],
            "functions": [],
            "imports": [],
            "methods": [
                {
                    "name": "method_with_$ymbol$",
                    "visibility": "public",
                    "docstring": "Method with special symbols: @#$%^&*()",
                    "parameters": [],
                }
            ],
        }

        result = formatter.format(data)
        assert isinstance(result, str)

    def test_format_with_newlines_and_tabs(self, formatter):
        """Test formatting with newlines and tabs in content."""
        data = {
            "file_path": "newlines.py",
            "classes": [],
            "functions": [],
            "imports": [],
            "methods": [
                {
                    "name": "multiline_method",
                    "visibility": "public",
                    "docstring": "This is a\nmultiline docstring\nwith\ttabs\tand\nnewlines.",
                    "parameters": [],
                }
            ],
        }

        result = formatter.format(data)
        assert isinstance(result, str)
        # Should handle newlines and tabs appropriately

    def test_format_with_markdown_characters(self, formatter):
        """Test formatting with Markdown special characters."""
        data = {
            "file_path": "markdown.py",
            "classes": [],
            "functions": [],
            "imports": [],
            "methods": [
                {
                    "name": "markdown_method",
                    "visibility": "public",
                    "docstring": "Method with **bold**, *italic*, `code`, and |pipe| characters.",
                    "parameters": [],
                }
            ],
        }

        result = formatter.format(data)
        assert isinstance(result, str)
        # Should escape or handle Markdown characters properly


class TestPythonFormatterTypeHandling:
    """Test Python formatter type handling edge cases."""

    @pytest.fixture
    def formatter(self):
        """Create a Python table formatter instance."""
        return PythonTableFormatter()

    def test_shorten_type_with_complex_generics(self, formatter):
        """Test type shortening with complex generic types."""
        complex_types = [
            "Dict[str, List[Optional[Union[int, float]]]]",
            "Callable[[str, int], Awaitable[Optional[bool]]]",
            "TypeVar('T', bound=Union[str, int])",
            "Literal['option1', 'option2', 'option3']",
            "Final[ClassVar[Optional[List[str]]]]",
        ]

        for type_name in complex_types:
            result = formatter._shorten_type(type_name)
            assert isinstance(result, str)
            assert result

    def test_shorten_type_with_invalid_syntax(self, formatter):
        """Test type shortening with invalid type syntax."""
        invalid_types = [
            "List[",  # Unclosed bracket
            "Dict[str,",  # Incomplete
            "Optional[]",  # Empty brackets
            "Union[|]",  # Invalid characters
            "123InvalidType",  # Starts with number
            "",  # Empty string
        ]

        for type_name in invalid_types:
            result = formatter._shorten_type(type_name)
            assert isinstance(result, str)

    def test_shorten_type_with_nested_brackets(self, formatter):
        """Test type shortening with deeply nested brackets."""
        nested_type = (
            "List[Dict[str, List[Optional[Union[int, Dict[str, List[bool]]]]]]]"
        )

        result = formatter._shorten_type(nested_type)
        assert isinstance(result, str)
        assert result

    def test_format_signature_with_complex_types(self, formatter):
        """Test signature formatting with complex types."""
        method = {
            "parameters": [
                {"name": "self", "type": "MyClass"},
                {"name": "data", "type": "Dict[str, List[Optional[int]]]"},
                {"name": "callback", "type": "Callable[[str], Awaitable[bool]]"},
                {"name": "options", "type": "Union[str, int, None]"},
            ],
            "return_type": "AsyncGenerator[Tuple[str, int], None]",
        }

        result = formatter._format_python_signature(method)
        assert isinstance(result, str)
        assert "data: Dict[str, List[Optional[int]]]" in result

    def test_format_signature_with_malformed_parameters(self, formatter):
        """Test signature formatting with malformed parameters."""
        method = {
            "parameters": [
                "invalid_string_parameter",  # Should be dict
                {"name": "valid_param"},  # Missing type
                {"type": "str"},  # Missing name
                {},  # Empty dict
            ],
            "return_type": "str",
        }

        result = formatter._format_python_signature(method)
        assert isinstance(result, str)


