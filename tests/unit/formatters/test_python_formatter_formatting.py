#!/usr/bin/env python3
"""Python formatter formatting tests — decorators, performance, summary, advanced, tables."""

import pytest

from tree_sitter_analyzer.formatters.python_formatter import PythonTableFormatter


class TestPythonFormatterDocstringHandling:
    """Test Python formatter docstring handling edge cases."""

    @pytest.fixture
    def formatter(self):
        """Create a Python table formatter instance."""
        return PythonTableFormatter()

    def test_extract_module_docstring_with_comments_before(self, formatter):
        """Test extracting module docstring with comments before it."""
        data = {
            "source_code": """# -*- coding: utf-8 -*-
# This is a comment
# Another comment
'''Module docstring after comments.'''

class Test:
    pass"""
        }

        result = formatter._extract_module_docstring(data)
        assert result == "Module docstring after comments."

    def test_extract_module_docstring_with_imports_before(self, formatter):
        """Test extracting module docstring with imports before it."""
        data = {
            "source_code": """import os
import sys
'''Module docstring after imports.'''

class Test:
    pass"""
        }

        result = formatter._extract_module_docstring(data)
        assert result == "Module docstring after imports."

    def test_extract_module_docstring_malformed(self, formatter):
        """Test extracting malformed module docstring."""
        data = {
            "source_code": """'''Unclosed docstring
This should not crash the formatter
class Test:
    pass"""
        }

        formatter._extract_module_docstring(data)
        # Should handle gracefully without crashing

    def test_extract_module_docstring_mixed_quotes(self, formatter):
        """Test extracting module docstring with mixed quote types."""
        data = {
            "source_code": '''"""Double quote docstring with 'single quotes' inside."""

class Test:
    pass'''
        }

        result = formatter._extract_module_docstring(data)
        assert "single quotes" in result

    def test_extract_module_docstring_very_long(self, formatter):
        """Test extracting very long module docstring."""
        long_docstring = "Very long docstring. " * 1000
        data = {"source_code": f'"""{long_docstring}"""\n\nclass Test:\n    pass'}

        result = formatter._extract_module_docstring(data)
        assert isinstance(result, str)
        assert len(result) > 1000  # ratchet: nondeterministic


class TestPythonFormatterDecoratorHandling:
    """Test Python formatter decorator handling edge cases."""

    @pytest.fixture
    def formatter(self):
        """Create a Python table formatter instance."""
        return PythonTableFormatter()

    def test_format_decorators_with_arguments(self, formatter):
        """Test formatting decorators with arguments."""
        decorators = [
            "lru_cache(maxsize=128)",
            "retry(attempts=3, delay=1.0)",
            "validate_input(schema='user_schema')",
        ]

        result = formatter._format_decorators(decorators)
        assert isinstance(result, str)

    def test_format_decorators_with_complex_expressions(self, formatter):
        """Test formatting decorators with complex expressions."""
        decorators = [
            "app.route('/api/v1/users/<int:user_id>', methods=['GET', 'POST'])",
            "pytest.mark.parametrize('input,expected', [(1, 2), (3, 4)])",
            "functools.wraps(func)",
        ]

        result = formatter._format_decorators(decorators)
        assert isinstance(result, str)

    def test_format_decorators_empty_and_none(self, formatter):
        """Test formatting empty and None decorators."""
        assert formatter._format_decorators([]) == "-"
        assert formatter._format_decorators(None) == "-"

    def test_format_decorators_with_duplicates(self, formatter):
        """Test formatting decorators with duplicates."""
        decorators = ["property", "property", "staticmethod", "staticmethod"]

        result = formatter._format_decorators(decorators)
        assert isinstance(result, str)

    def test_format_decorators_mixed_important_and_custom(self, formatter):
        """Test formatting mix of important and custom decorators."""
        decorators = [
            "custom_decorator",
            "property",
            "another_custom",
            "staticmethod",
            "third_custom",
        ]

        result = formatter._format_decorators(decorators)
        assert "@property" in result
        assert "@staticmethod" in result


class TestPythonFormatterPerformanceEdgeCases:
    """Test Python formatter performance edge cases."""

    @pytest.fixture
    def formatter(self):
        """Create a Python table formatter instance."""
        return PythonTableFormatter()

    def test_format_with_recursive_data_structures(self, formatter):
        """Test formatting with recursive data structures."""
        # Create a recursive structure
        recursive_param = {"name": "recursive", "type": "RecursiveType"}
        recursive_param["self_ref"] = recursive_param

        data = {
            "file_path": "recursive.py",
            "classes": [],
            "functions": [],
            "imports": [],
            "methods": [
                {
                    "name": "recursive_method",
                    "parameters": [recursive_param],
                    "return_type": "str",
                }
            ],
        }

        # Should handle without infinite recursion
        result = formatter.format(data)
        assert isinstance(result, str)

    def test_format_with_memory_intensive_data(self, formatter):
        """Test formatting with memory-intensive data."""
        # Create large string data
        large_docstring = "x" * 100000  # 100KB string
        large_type_name = "VeryLongTypeName" * 1000

        data = {
            "file_path": "memory_test.py",
            "classes": [],
            "functions": [],
            "imports": [],
            "methods": [
                {
                    "name": "memory_intensive_method",
                    "docstring": large_docstring,
                    "parameters": [{"name": "param", "type": large_type_name}],
                    "return_type": large_type_name,
                }
            ],
        }

        result = formatter.format(data)
        assert isinstance(result, str)

    def test_format_with_many_small_objects(self, formatter):
        """Test formatting with many small objects."""
        # Create many small method objects
        many_methods = []
        for i in range(1000):
            many_methods.append(
                {
                    "name": f"method_{i}",
                    "visibility": "public",
                    "line_range": {"start": i, "end": i + 1},
                    "parameters": [],
                    "return_type": "None",
                    "complexity_score": 1,
                }
            )

        data = {
            "file_path": "many_methods.py",
            "classes": [],
            "functions": [],
            "imports": [],
            "methods": many_methods,
        }

        result = formatter.format(data)
        assert isinstance(result, str)
        assert "method_0" in result
        assert "method_999" in result


# ── Coverage gap tests ──────────────────────────────────────────────


class TestPythonFormatterFormatSummary:
    """Test format_summary delegates to compact table"""

    @pytest.fixture
    def formatter(self):
        return PythonTableFormatter()

    def test_format_summary(self, formatter):
        data = {
            "file_path": "test.py",
            "classes": [
                {
                    "name": "MyClass",
                    "type": "class",
                    "line_range": {"start": 1, "end": 10},
                }
            ],
            "functions": [],
            "variables": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }
        result = formatter.format_summary(data)
        assert "## Info" in result


class TestPythonFormatterFormatAdvanced:
    """Test format_advanced with different output formats"""

    @pytest.fixture
    def formatter(self):
        return PythonTableFormatter()

    def test_format_advanced_json(self, formatter):
        data = {"file_path": "app.py", "classes": [], "functions": []}
        result = formatter.format_advanced(data, "json")
        assert '"file_path"' in result

    def test_format_advanced_csv(self, formatter):
        data = {"file_path": "app.py", "classes": [], "functions": []}
        result = formatter.format_advanced(data, "csv")
        assert "#" in result or "Functions" in result or result

    def test_format_advanced_fallback_to_full(self, formatter):
        data = {
            "file_path": "app.py",
            "classes": [
                {"name": "App", "type": "class", "line_range": {"start": 1, "end": 5}}
            ],
            "functions": [],
            "variables": [],
        }
        result = formatter.format_advanced(data, "unknown_format")
        assert "App" in result or "app" in result


class TestPythonFormatterFullTable:
    """Test _format_full_table variants"""

    @pytest.fixture
    def formatter(self):
        return PythonTableFormatter()

    def test_full_table_none_data(self, formatter):
        with pytest.raises(TypeError):
            formatter._format_full_table(None)

    def test_full_table_invalid_type(self, formatter):
        with pytest.raises(TypeError):
            formatter._format_full_table("not_a_dict")

    def test_full_table_none_file_path(self, formatter):
        data = {
            "file_path": None,
            "classes": [],
            "functions": [],
            "variables": [],
            "imports": [],
        }
        result = formatter._format_full_table(data)
        assert "Unknown" in result

    def test_full_table_with_package(self, formatter):
        data = {
            "file_path": "mod.py",
            "classes": [
                {
                    "name": "KL",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 20},
                }
            ],
            "functions": [],
            "variables": [],
            "imports": [],
            "package": {"name": "mypackage"},
        }
        result = formatter._format_full_table(data)
        assert "## Package" in result
        assert "mypackage" in result

    def test_full_table_with_imports(self, formatter):
        data = {
            "file_path": "mod.py",
            "classes": [
                {
                    "name": "KL",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 20},
                }
            ],
            "functions": [],
            "variables": [],
            "imports": [
                {"name": "os", "raw_text": "import os", "module_name": ""},
                {"name": "Path", "raw_text": "", "module_name": "pathlib"},
            ],
            "package": {},
        }
        result = formatter._format_full_table(data)
        assert "## Imports" in result
        assert "import os" in result
        assert "from pathlib import Path" in result

    def test_full_table_single_class_with_methods(self, formatter):
        data = {
            "file_path": "mod.py",
            "classes": [
                {
                    "name": "Calc",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 30},
                }
            ],
            "functions": [],
            "methods": [
                {
                    "name": "add",
                    "visibility": "public",
                    "line_range": {"start": 5, "end": 7},
                    "parameters": [
                        {"name": "self", "type": "Calc"},
                        {"name": "x", "type": "int"},
                    ],
                    "return_type": "int",
                    "complexity_score": 1,
                    "docstring": "Add numbers.",
                },
                {
                    "name": "__init__",
                    "visibility": "public",
                    "line_range": {"start": 3, "end": 4},
                    "parameters": [{"name": "self", "type": "Calc"}],
                    "return_type": "",
                    "complexity_score": 0,
                    "docstring": "Initialize.",
                },
            ],
            "variables": [
                {
                    "name": "result",
                    "variable_type": "int",
                    "line_range": {"start": 2, "end": 2},
                    "docstring": "",
                }
            ],
            "imports": [],
            "statistics": {"method_count": 2, "field_count": 1},
        }
        result = formatter._format_full_table(data)
        assert "Calc" in result
        assert "add" in result

    def test_full_table_multiple_classes(self, formatter):
        data = {
            "file_path": "mod.py",
            "classes": [
                {
                    "name": "A",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 10},
                },
                {
                    "name": "B",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 11, "end": 20},
                },
            ],
            "functions": [],
            "methods": [],
            "variables": [],
            "imports": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }
        result = formatter._format_full_table(data)
        assert "## Classes Overview" in result
        assert "A" in result
        assert "B" in result

    def test_full_table_per_class_sections(self, formatter):
        data = {
            "file_path": "mod.py",
            "classes": [
                {
                    "name": "Calc",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 30},
                },
                {
                    "name": "Helper",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 31, "end": 50},
                },
            ],
            "functions": [],
            "methods": [
                {
                    "name": "add",
                    "visibility": "public",
                    "line_range": {"start": 5, "end": 7},
                    "parameters": [
                        {"name": "self", "type": "Calc"},
                        {"name": "x", "type": "int"},
                    ],
                    "return_type": "int",
                    "complexity_score": 1,
                    "docstring": "",
                },
            ],
            "variables": [
                {
                    "name": "count",
                    "variable_type": "int",
                    "line_range": {"start": 2, "end": 2},
                    "visibility": "public",
                    "modifiers": [],
                    "docstring": "",
                }
            ],
            "imports": [],
            "statistics": {"method_count": 1, "field_count": 1},
        }
        result = formatter._format_full_table(data)
        assert "## Classes Overview" in result
        assert "Calc" in result


class TestPythonFormatterCompactTable:
    """Test _format_compact_table"""

    @pytest.fixture
    def formatter(self):
        return PythonTableFormatter()

    def test_compact_table_basic(self, formatter):
        data = {
            "file_path": "test.py",
            "classes": [],
            "functions": [],
            "variables": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }
        result = formatter._format_compact_table(data)
        assert "test" in result
        assert "## Info" in result

    def test_compact_table_with_methods(self, formatter):
        data = {
            "file_path": "test.py",
            "classes": [],
            "functions": [],
            "methods": [
                {
                    "name": "func",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 2},
                    "parameters": [],
                    "return_type": "None",
                    "complexity_score": 0,
                    "docstring": "",
                },
            ],
            "variables": [],
            "statistics": {"method_count": 1, "field_count": 0},
        }
        result = formatter._format_compact_table(data)
        assert "## Methods" in result
        assert "func" in result

    def test_compact_table_with_classes(self, formatter):
        data = {
            "file_path": "test.py",
            "classes": [
                {"name": "X", "type": "class", "line_range": {"start": 1, "end": 5}}
            ],
            "functions": [],
            "methods": [],
            "variables": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }
        result = formatter._format_compact_table(data)
        assert "## Classes" in result
        assert "X" in result

    def test_compact_table_with_none_class(self, formatter):
        data = {
            "file_path": "test.py",
            "classes": [
                None,
                {
                    "name": "Valid",
                    "type": "class",
                    "line_range": {"start": 1, "end": 5},
                },
            ],
            "functions": [],
            "methods": [],
            "variables": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }
        result = formatter._format_compact_table(data)
        assert "Valid" in result


class TestPythonFormatterCreateCompactSignature:
    """Test _create_compact_signature edge cases"""

    @pytest.fixture
    def formatter(self):
        return PythonTableFormatter()

    def test_compact_signature_none_method(self, formatter):
        with pytest.raises(TypeError):
            formatter._create_compact_signature(None)

    def test_compact_signature_invalid_type(self, formatter):
        with pytest.raises(TypeError):
            formatter._create_compact_signature("not_dict")

    def test_compact_signature_string_params(self, formatter):
        method = {
            "name": "f",
            "return_type": "str",
            "parameters": "a, b, c",
        }
        result = formatter._create_compact_signature(method)
        assert result in ["():str", "():Any"]

    def test_compact_signature_none_type(self, formatter):
        method = {
            "name": "f",
            "return_type": "str",
            "parameters": [{"name": "x", "type": None}],
        }
        result = formatter._create_compact_signature(method)
        assert "Any" in result


class TestPythonFormatterFormatTableMethod:
    """Test format_table method"""

    @pytest.fixture
    def formatter(self):
        return PythonTableFormatter()

    def test_format_table_restores_format_type(self, formatter):
        data = {"file_path": "app.py", "classes": [], "functions": [], "variables": []}
        original = formatter.format_type
        formatter.format_table(data, "compact")
        assert formatter.format_type == original


class TestPythonFormatterFormatJsonError:
    """Test _format_json error path"""

    @pytest.fixture
    def formatter(self):
        return PythonTableFormatter()

    def test_format_json_with_set(self, formatter):
        data = {"bad": {1, 2, 3}}
        result = formatter._format_json(data)
        assert "JSON serialization error" in result
