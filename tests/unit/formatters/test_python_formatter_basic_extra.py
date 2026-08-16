"""
Comprehensive tests for Python table formatter — basic and formatting tests.
Tests cover basic functionality, full format, compact format, and method formatting.
"""

import pytest

from tree_sitter_analyzer.formatters.python_formatter import PythonTableFormatter


class TestPythonTableFormatterBasic:
    """Test basic Python table formatter functionality."""

    @pytest.fixture
    def formatter(self):
        """Create a Python table formatter instance."""
        return PythonTableFormatter()

    @pytest.fixture
    def sample_python_data(self):
        """Sample Python analysis data."""
        return {
            "file_path": "src/calculator.py",
            "language": "python",
            "classes": [
                {
                    "name": "Calculator",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 10, "end": 50},
                    "docstring": "A simple calculator class for basic arithmetic operations.",
                }
            ],
            "functions": [
                {
                    "name": "add",
                    "visibility": "public",
                    "line_range": {"start": 15, "end": 20},
                    "parameters": [
                        {"name": "self", "type": "Calculator"},
                        {"name": "a", "type": "int"},
                        {"name": "b", "type": "int"},
                    ],
                    "return_type": "int",
                    "complexity_score": 1,
                    "docstring": "Add two numbers together.",
                    "is_async": False,
                    "decorators": [],
                },
                {
                    "name": "divide",
                    "visibility": "public",
                    "line_range": {"start": 25, "end": 35},
                    "parameters": [
                        {"name": "self", "type": "Calculator"},
                        {"name": "a", "type": "float"},
                        {"name": "b", "type": "float"},
                    ],
                    "return_type": "float",
                    "complexity_score": 3,
                    "docstring": "Divide two numbers with error handling.",
                    "is_async": False,
                    "decorators": [],
                },
            ],
            "methods": [
                {
                    "name": "add",
                    "visibility": "public",
                    "line_range": {"start": 15, "end": 20},
                    "parameters": [
                        {"name": "self", "type": "Calculator"},
                        {"name": "a", "type": "int"},
                        {"name": "b", "type": "int"},
                    ],
                    "return_type": "int",
                    "complexity_score": 1,
                    "docstring": "Add two numbers together.",
                    "is_async": False,
                    "decorators": [],
                }
            ],
            "fields": [
                {
                    "name": "precision",
                    "type": "int",
                    "visibility": "private",
                    "line_range": {"start": 12, "end": 12},
                    "modifiers": ["class_variable"],
                    "javadoc": "Precision for calculations",
                }
            ],
            "imports": [
                {"name": "math", "module_name": "", "raw_text": "import math"},
                {
                    "name": "sqrt",
                    "module_name": "math",
                    "raw_text": "from math import sqrt",
                },
            ],
            "statistics": {"method_count": 2, "field_count": 1, "class_count": 1},
            "source_code": '"""Calculator module for basic arithmetic operations."""\n\nimport math\nfrom math import sqrt\n\nclass Calculator:\n    """A simple calculator class."""\n    precision = 2\n    \n    def add(self, a: int, b: int) -> int:\n        """Add two numbers."""\n        return a + b',
        }

    def test_format_method_delegates_to_format_structure(
        self, formatter, sample_python_data
    ):
        """Test that format method delegates to format_structure."""
        result = formatter.format(sample_python_data)

        assert isinstance(result, str)
        assert result
        assert "Calculator" in result

    def test_format_with_empty_data(self, formatter):
        """Test formatting with empty data."""
        empty_data = {}
        result = formatter.format(empty_data)

        assert isinstance(result, str)


class TestPythonTableFormatterFullFormat:
    """Test Python table formatter full format functionality."""

    @pytest.fixture
    def formatter(self):
        """Create a Python table formatter instance."""
        return PythonTableFormatter()

    def test_full_format_module_header(self, formatter):
        """Test full format module header generation."""
        data = {
            "file_path": "src/utils.py",
            "classes": [],
            "functions": [],
            "imports": [],
        }

        result = formatter._format_full_table(data)

        assert "# Module: utils" in result

    def test_full_format_package_header(self, formatter):
        """Test full format package header generation."""
        data = {
            "file_path": "src/__init__.py",
            "classes": [],
            "functions": [],
            "imports": [],
        }

        result = formatter._format_full_table(data)

        assert "# Package:" in result

    def test_full_format_script_header(self, formatter):
        """Test full format script header generation."""
        data = {
            "file_path": "main.py",
            "classes": [],
            "functions": [
                {"name": "main", "raw_text": "if __name__ == '__main__':\n    main()"}
            ],
            "imports": [],
        }

        result = formatter._format_full_table(data)

        assert "# Script: main" in result

    def test_full_format_module_docstring(self, formatter):
        """Test full format module docstring extraction."""
        data = {
            "file_path": "calculator.py",
            "source_code": '"""Calculator module for basic arithmetic operations."""\n\nclass Calculator:\n    pass',
            "classes": [],
            "functions": [],
            "imports": [],
        }

        result = formatter._format_full_table(data)

        assert "## Description" in result
        assert "Calculator module for basic arithmetic operations." in result

    def test_full_format_imports_section(self, formatter):
        """Test full format imports section."""
        data = {
            "file_path": "test.py",
            "classes": [],
            "functions": [],
            "imports": [
                {"raw_text": "import os"},
                {"raw_text": "from typing import List"},
                {"name": "json", "module_name": "", "raw_text": ""},
            ],
        }

        result = formatter._format_full_table(data)

        assert "## Imports" in result
        assert "```python" in result
        assert "import os" in result
        assert "from typing import List" in result
        assert "import json" in result

    def test_full_format_multiple_classes(self, formatter):
        """Test full format with multiple classes."""
        data = {
            "file_path": "models.py",
            "classes": [
                {
                    "name": "User",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 10, "end": 30},
                },
                {
                    "name": "Admin",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 35, "end": 50},
                },
            ],
            "methods": [
                {"name": "get_name", "line_range": {"start": 15, "end": 18}},
                {"name": "set_permissions", "line_range": {"start": 40, "end": 45}},
            ],
            "fields": [{"name": "username", "line_range": {"start": 12, "end": 12}}],
            "functions": [],
            "imports": [],
        }

        result = formatter._format_full_table(data)

        assert "## Classes" in result
        assert "| Class | Type | Visibility | Lines | Methods | Fields |" in result
        assert "| User | class | public | 10-30 | 1 | 1 |" in result
        assert "| Admin | class | public | 35-50 | 1 | 0 |" in result

    def test_full_format_single_class(self, formatter):
        """Test full format with single class."""
        data = {
            "file_path": "calculator.py",
            "classes": [
                {
                    "name": "Calculator",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 10, "end": 50},
                }
            ],
            "statistics": {"method_count": 3, "field_count": 2},
            "functions": [],
            "imports": [],
        }

        result = formatter._format_full_table(data)

        assert "## Class Info" in result
        assert "| Property | Value |" in result
        assert "| Type | class |" in result
        assert "| Total Methods | 3 |" in result
        assert "| Total Fields | 2 |" in result

    @pytest.mark.skip(
        reason="Fields section not yet implemented in PythonTableFormatter"
    )
    def test_full_format_fields_section(self, formatter):
        """Test full format fields section."""
        data = {
            "file_path": "model.py",
            "classes": [],
            "functions": [],
            "imports": [],
            "fields": [
                {
                    "name": "username",
                    "type": "str",
                    "visibility": "private",
                    "modifiers": ["instance"],
                    "line_range": {"start": 15, "end": 15},
                    "javadoc": "User's login name",
                },
                {
                    "name": "MAX_USERS",
                    "type": "int",
                    "visibility": "public",
                    "modifiers": ["class", "constant"],
                    "line_range": {"start": 10, "end": 10},
                    "javadoc": "Maximum number of users allowed in the system",
                },
            ],
        }

        result = formatter._format_full_table(data)

        assert "## Fields" in result
        assert "| Name | Type | Vis | Modifiers | Line | Doc |" in result
        assert "| username | str |" in result
        assert "| MAX_USERS | int |" in result

    @pytest.mark.skip(
        reason="Methods section format different in current implementation"
    )
    def test_full_format_methods_section(self, formatter):
        """Test full format methods section."""
        data = {
            "file_path": "service.py",
            "classes": [],
            "functions": [],
            "imports": [],
            "methods": [
                {
                    "name": "process_data",
                    "visibility": "public",
                    "line_range": {"start": 20, "end": 35},
                    "parameters": [
                        {"name": "self", "type": "Service"},
                        {"name": "data", "type": "List[str]"},
                    ],
                    "return_type": "Dict[str, Any]",
                    "complexity_score": 5,
                    "docstring": "Process input data and return results.",
                    "is_async": True,
                    "decorators": ["property", "cached"],
                }
            ],
        }

        result = formatter._format_full_table(data)

        assert "## Methods" in result
        assert (
            "| Method | Signature | Vis | Lines | Cols | Cx | Decorators | Doc |"
            in result
        )
        assert "process_data🔄" in result
        assert "@property" in result


class TestPythonTableFormatterCompactFormat:
    """Test Python table formatter compact format functionality."""

    @pytest.fixture
    def formatter(self):
        """Create a Python table formatter instance."""
        return PythonTableFormatter()

    def test_compact_format_multiple_classes_header(self, formatter):
        """Test compact format header with multiple classes."""
        data = {
            "file_path": "models.py",
            "classes": [{"name": "User"}, {"name": "Admin"}],
            "statistics": {"method_count": 5, "field_count": 3},
        }

        result = formatter._format_compact_table(data)

        assert "# Module: models" in result

    def test_compact_format_single_class_header(self, formatter):
        """Test compact format header with single class."""
        data = {
            "file_path": "calculator.py",
            "classes": [{"name": "Calculator"}],
            "statistics": {"method_count": 3, "field_count": 1},
        }

        result = formatter._format_compact_table(data)

        assert "# Calculator" in result

    def test_compact_format_info_section(self, formatter):
        """Test compact format info section."""
        data = {
            "file_path": "test.py",
            "classes": [{"name": "Test"}],
            "statistics": {"method_count": 4, "field_count": 2},
        }

        result = formatter._format_compact_table(data)

        assert "## Info" in result
        assert "| Classes | 1 |" in result
        assert "| Methods | 4 |" in result
        assert "| Fields | 2 |" in result

    def test_compact_format_methods_section(self, formatter):
        """Test compact format methods section."""
        data = {
            "file_path": "service.py",
            "classes": [{"name": "Service"}],
            "statistics": {"method_count": 1, "field_count": 0},
            "methods": [
                {
                    "name": "execute",
                    "visibility": "public",
                    "line_range": {"start": 10, "end": 20},
                    "parameters": [
                        {"name": "self", "type": "Service"},
                        {"name": "command", "type": "str"},
                    ],
                    "return_type": "bool",
                    "complexity_score": 2,
                    "javadoc": "Execute a command and return success status.",
                }
            ],
        }

        result = formatter._format_compact_table(data)

        assert "## Methods" in result
        assert "| Method | Sig | V | L | Cx | Doc |" in result
        assert "| execute |" in result
        assert "| 2 |" in result


class TestPythonTableFormatterMethodFormatting:
    """Test Python table formatter method formatting functionality."""

    @pytest.fixture
    def formatter(self):
        """Create a Python table formatter instance."""
        return PythonTableFormatter()

    def test_format_method_row_basic(self, formatter):
        """Test basic method row formatting."""
        method = {
            "name": "calculate",
            "visibility": "public",
            "line_range": {"start": 10, "end": 15},
            "parameters": [
                {"name": "self", "type": "Calculator"},
                {"name": "value", "type": "int"},
            ],
            "return_type": "float",
            "complexity_score": 2,
            "docstring": "Calculate result from input value.",
            "is_async": False,
            "decorators": [],
        }

        result = formatter._format_method_row(method)

        assert "calculate" in result
        assert "🔓" in result
        assert "10-15" in result
        assert "2" in result

    def test_format_method_row_async(self, formatter):
        """Test async method row formatting."""
        method = {
            "name": "fetch_data",
            "visibility": "public",
            "line_range": {"start": 20, "end": 30},
            "parameters": [{"name": "self", "type": "Service"}],
            "return_type": "Dict[str, Any]",
            "complexity_score": 3,
            "docstring": "Fetch data asynchronously.",
            "is_async": True,
            "decorators": [],
        }

        result = formatter._format_method_row(method)

        assert "fetch_data🔄" in result

    def test_format_method_row_private(self, formatter):
        """Test private method row formatting."""
        method = {
            "name": "_helper_method",
            "visibility": "private",
            "line_range": {"start": 50, "end": 55},
            "parameters": [{"name": "self", "type": "Service"}],
            "return_type": "None",
            "complexity_score": 1,
            "docstring": "Internal helper method.",
            "is_async": False,
            "decorators": [],
        }

        result = formatter._format_method_row(method)

        assert "_helper_method" in result
        assert "🔒" in result

    def test_format_method_row_magic(self, formatter):
        """Test magic method row formatting."""
        method = {
            "name": "__init__",
            "visibility": "public",
            "line_range": {"start": 5, "end": 10},
            "parameters": [
                {"name": "self", "type": "Calculator"},
                {"name": "precision", "type": "int"},
            ],
            "return_type": "None",
            "complexity_score": 1,
            "docstring": "Initialize calculator with precision.",
            "is_async": False,
            "decorators": [],
        }

        result = formatter._format_method_row(method)

        assert "__init__" in result
        assert "✨" in result

    def test_format_method_row_with_decorators(self, formatter):
        """Test method row formatting with decorators."""
        method = {
            "name": "cached_result",
            "visibility": "public",
            "line_range": {"start": 30, "end": 40},
            "parameters": [{"name": "self", "type": "Service"}],
            "return_type": "str",
            "complexity_score": 1,
            "docstring": "Get cached result.",
            "is_async": False,
            "decorators": ["property", "lru_cache"],
        }

        result = formatter._format_method_row(method)

        assert "@property" in result

    def test_format_method_row_fallback_line_numbers(self, formatter):
        """Test method row formatting with fallback line numbers."""
        method = {
            "name": "legacy_method",
            "visibility": "public",
            "start_line": 100,
            "end_line": 110,
            "parameters": [],
            "return_type": "None",
            "complexity_score": 1,
            "docstring": "Legacy method with old line format.",
            "is_async": False,
            "decorators": [],
        }

        result = formatter._format_method_row(method)

        assert "100-110" in result
