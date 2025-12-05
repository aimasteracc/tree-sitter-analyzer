#!/usr/bin/env python3
"""Tests for Go formatter to improve coverage."""

import pytest
from tree_sitter_analyzer.formatters.go_formatter import GoTableFormatter


class TestGoTableFormatterFullTable:
    """Test _format_full_table method."""

    def test_basic_package(self):
        """Test basic package formatting."""
        formatter = GoTableFormatter("full")
        data = {
            "file_path": "main.go",
            "packages": [{"name": "main"}],
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "statistics": {"function_count": 0, "class_count": 0, "variable_count": 0},
        }

        result = formatter.format_structure(data)
        assert "main" in result
        assert "## Package Info" in result

    def test_package_with_functions(self):
        """Test package with functions."""
        formatter = GoTableFormatter("full")
        data = {
            "file_path": "utils.go",
            "packages": [{"name": "utils"}],
            "classes": [],
            "methods": [
                {
                    "name": "Add",
                    "return_type": "int",
                    "visibility": "public",
                    "parameters": ["a int", "b int"],  # String format
                    "line_range": {"start": 5, "end": 10},
                },
                {
                    "name": "subtract",
                    "return_type": "int",
                    "visibility": "private",
                    "parameters": ["x int", "y int"],  # String format
                    "line_range": {"start": 15, "end": 20},
                },
            ],
            "fields": [],
            "imports": [{"import_statement": 'import "fmt"'}],
            "statistics": {"function_count": 2, "class_count": 0, "variable_count": 0},
        }

        result = formatter.format_structure(data)
        assert "Add" in result
        assert "## Imports" in result

    def test_package_with_structs(self):
        """Test package with structs."""
        formatter = GoTableFormatter("full")
        data = {
            "file_path": "models.go",
            "packages": [{"name": "models"}],
            "classes": [
                {
                    "name": "User",
                    "type": "struct",
                    "line_range": {"start": 5, "end": 15},
                    "interfaces": [],
                    "docstring": "User represents a user",
                },
                {
                    "name": "person",
                    "type": "struct",
                    "line_range": {"start": 20, "end": 30},
                    "interfaces": ["Stringer"],
                },
            ],
            "methods": [],
            "fields": [],
            "imports": [],
            "statistics": {"function_count": 0, "class_count": 2, "variable_count": 0},
        }

        result = formatter.format_structure(data)
        assert "## Structs" in result
        assert "User" in result
        assert "person" in result

    def test_package_with_interfaces(self):
        """Test package with interfaces."""
        formatter = GoTableFormatter("full")
        data = {
            "file_path": "interfaces.go",
            "packages": [{"name": "contracts"}],
            "classes": [
                {
                    "name": "Reader",
                    "type": "interface",
                    "line_range": {"start": 5, "end": 10},
                    "docstring": "Reader interface",
                },
                {
                    "name": "writer",
                    "type": "interface",
                    "line_range": {"start": 15, "end": 20},
                },
            ],
            "methods": [],
            "fields": [],
            "imports": [],
            "statistics": {"function_count": 0, "class_count": 2, "variable_count": 0},
        }

        result = formatter.format_structure(data)
        assert "## Interfaces" in result
        assert "Reader" in result

    def test_package_with_type_aliases(self):
        """Test package with type aliases."""
        formatter = GoTableFormatter("full")
        data = {
            "file_path": "types.go",
            "packages": [{"name": "types"}],
            "classes": [
                {
                    "name": "ID",
                    "type": "type_alias",
                    "line_range": {"start": 5, "end": 5},
                    "base_type": "int64",
                },
                {
                    "name": "Name",
                    "type": "type_alias",
                    "line_range": {"start": 6, "end": 6},
                    "base_type": "string",
                },
            ],
            "methods": [],
            "fields": [],
            "imports": [],
            "statistics": {"function_count": 0, "class_count": 2, "variable_count": 0},
        }

        result = formatter.format_structure(data)
        assert "ID" in result or "Type Aliases" in result

    def test_package_with_methods_receivers(self):
        """Test methods with receivers."""
        formatter = GoTableFormatter("full")
        data = {
            "file_path": "methods.go",
            "packages": [{"name": "pkg"}],
            "classes": [
                {
                    "name": "Calculator",
                    "type": "struct",
                    "line_range": {"start": 5, "end": 10},
                }
            ],
            "methods": [
                {
                    "name": "Add",
                    "return_type": "int",
                    "visibility": "public",
                    "parameters": ["b int"],  # String format
                    "line_range": {"start": 15, "end": 20},
                    "receiver": {"name": "c", "type": "*Calculator"},
                },
                {
                    "name": "getValue",
                    "return_type": "int",
                    "visibility": "private",
                    "parameters": [],
                    "line_range": {"start": 25, "end": 30},
                    "receiver": {"name": "c", "type": "Calculator"},
                },
            ],
            "fields": [],
            "imports": [],
            "statistics": {"function_count": 2, "class_count": 1, "variable_count": 0},
        }

        result = formatter.format_structure(data)
        assert "Calculator" in result
        assert "Add" in result

    def test_package_with_variables(self):
        """Test package with variables."""
        formatter = GoTableFormatter("full")
        data = {
            "file_path": "vars.go",
            "packages": [{"name": "config"}],
            "classes": [],
            "methods": [],
            "fields": [
                {
                    "name": "MaxSize",
                    "variable_type": "int",
                    "visibility": "public",
                    "line_range": {"start": 5, "end": 5},
                    "is_constant": True,
                },
                {
                    "name": "defaultName",
                    "variable_type": "string",
                    "visibility": "private",
                    "line_range": {"start": 6, "end": 6},
                    "is_constant": False,
                },
            ],
            "imports": [],
            "statistics": {"function_count": 0, "class_count": 0, "variable_count": 2},
        }

        result = formatter.format_structure(data)
        assert "MaxSize" in result or "Variables" in result or "Constants" in result

    def test_package_no_name(self):
        """Test package with no name (fallback to main)."""
        formatter = GoTableFormatter("full")
        data = {
            "file_path": "test.go",
            "packages": [],
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "statistics": {"function_count": 0, "class_count": 0, "variable_count": 0},
        }

        result = formatter.format_structure(data)
        assert "main" in result or "test.go" in result


class TestGoTableFormatterCompactTable:
    """Test _format_compact_table method."""

    def test_compact_with_functions(self):
        """Test compact format with functions."""
        formatter = GoTableFormatter("compact")
        data = {
            "file_path": "main.go",
            "packages": [{"name": "main"}],
            "classes": [],
            "methods": [
                {
                    "name": "main",
                    "return_type": "",
                    "visibility": "private",
                    "parameters": [],
                    "line_range": {"start": 5, "end": 20},
                }
            ],
            "fields": [],
            "imports": [],
            "statistics": {"function_count": 1, "class_count": 0, "variable_count": 0},
        }

        result = formatter.format_structure(data)
        assert "main" in result

    def test_compact_empty_data(self):
        """Test compact format with empty data."""
        formatter = GoTableFormatter("compact")
        data = {
            "file_path": "empty.go",
            "packages": [],
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "statistics": {"function_count": 0, "class_count": 0, "variable_count": 0},
        }

        result = formatter.format_structure(data)
        assert isinstance(result, str)

    def test_compact_with_structs(self):
        """Test compact format with structs."""
        formatter = GoTableFormatter("compact")
        data = {
            "file_path": "models.go",
            "packages": [{"name": "models"}],
            "classes": [
                {
                    "name": "User",
                    "type": "struct",
                    "line_range": {"start": 5, "end": 15},
                }
            ],
            "methods": [],
            "fields": [],
            "imports": [],
            "statistics": {"function_count": 0, "class_count": 1, "variable_count": 0},
        }

        result = formatter.format_structure(data)
        # Compact format shows package info and types count
        assert "models" in result
        assert "Types" in result


class TestGoTableFormatterCSV:
    """Test CSV format."""

    def test_csv_format_basic(self):
        """Test basic CSV output."""
        formatter = GoTableFormatter("csv")
        data = {
            "file_path": "test.go",
            "packages": [{"name": "test"}],
            "classes": [
                {
                    "name": "TestStruct",
                    "type": "struct",
                    "line_range": {"start": 5, "end": 15},
                }
            ],
            "methods": [
                {
                    "name": "TestFunc",
                    "return_type": "error",
                    "visibility": "public",
                    "parameters": [],
                    "line_range": {"start": 20, "end": 30},
                    "complexity_score": 3,
                }
            ],
            "fields": [],
            "imports": [],
            "statistics": {"function_count": 1, "class_count": 1, "variable_count": 0},
        }

        result = formatter.format_structure(data)
        assert "Type" in result
        assert "Name" in result

    def test_csv_format_empty(self):
        """Test CSV with no data."""
        formatter = GoTableFormatter("csv")
        data = {
            "file_path": "empty.go",
            "packages": [],
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "statistics": {"function_count": 0, "class_count": 0, "variable_count": 0},
        }

        result = formatter.format_structure(data)
        assert "Type" in result


class TestGoTableFormatterHelperMethods:
    """Test helper methods."""

    def test_get_package_name(self):
        """Test _get_package_name with packages."""
        formatter = GoTableFormatter("full")
        data = {"packages": [{"name": "mypackage"}]}
        result = formatter._get_package_name(data)
        assert result == "mypackage"

    def test_get_package_name_empty(self):
        """Test _get_package_name with no packages."""
        formatter = GoTableFormatter("full")
        data = {"packages": []}
        result = formatter._get_package_name(data)
        assert result == ""

    def test_get_package_name_no_key(self):
        """Test _get_package_name with missing key."""
        formatter = GoTableFormatter("full")
        data = {}
        result = formatter._get_package_name(data)
        assert result == ""

    def test_go_visibility_exported(self):
        """Test _go_visibility for exported names."""
        formatter = GoTableFormatter("full")
        assert formatter._go_visibility("ExportedFunc") == "exported"
        assert formatter._go_visibility("User") == "exported"

    def test_go_visibility_unexported(self):
        """Test _go_visibility for unexported names."""
        formatter = GoTableFormatter("full")
        assert formatter._go_visibility("privateFunc") == "unexported"
        assert formatter._go_visibility("user") == "unexported"

    def test_go_visibility_empty(self):
        """Test _go_visibility with empty string."""
        formatter = GoTableFormatter("full")
        result = formatter._go_visibility("")
        assert result in ["unexported", "exported", ""]

    def test_extract_doc_summary(self):
        """Test _extract_doc_summary."""
        formatter = GoTableFormatter("full")
        result = formatter._extract_doc_summary("This is a long docstring that should be truncated")
        assert len(result) <= 50 or "..." not in result

    def test_extract_doc_summary_empty(self):
        """Test _extract_doc_summary with empty string."""
        formatter = GoTableFormatter("full")
        result = formatter._extract_doc_summary("")
        # Empty string returns '-' as placeholder
        assert result in ["", "-"]

    def test_get_platform_newline(self):
        """Test _get_platform_newline returns string."""
        formatter = GoTableFormatter("full")
        result = formatter._get_platform_newline()
        assert result in ["\n", "\r\n"]


class TestGoTableFormatterEdgeCases:
    """Test edge cases and error handling."""

    def test_invalid_format_type(self):
        """Test with invalid format type."""
        formatter = GoTableFormatter("invalid_format")
        data = {"packages": [], "classes": [], "methods": [], "fields": []}
        with pytest.raises(ValueError, match="Unsupported format type"):
            formatter.format_structure(data)

    def test_function_with_multiple_returns(self):
        """Test function with multiple return values."""
        formatter = GoTableFormatter("full")
        data = {
            "file_path": "multi_return.go",
            "packages": [{"name": "pkg"}],
            "classes": [],
            "methods": [
                {
                    "name": "ReadFile",
                    "return_type": "([]byte, error)",
                    "visibility": "public",
                    "parameters": ["path string"],  # String format
                    "line_range": {"start": 5, "end": 15},
                }
            ],
            "fields": [],
            "imports": [],
            "statistics": {"function_count": 1, "class_count": 0, "variable_count": 0},
        }

        result = formatter.format_structure(data)
        assert "ReadFile" in result

    def test_method_with_pointer_receiver(self):
        """Test method with pointer receiver."""
        formatter = GoTableFormatter("full")
        data = {
            "file_path": "pointer.go",
            "packages": [{"name": "pkg"}],
            "classes": [
                {
                    "name": "Counter",
                    "type": "struct",
                    "line_range": {"start": 5, "end": 10},
                }
            ],
            "methods": [
                {
                    "name": "Increment",
                    "return_type": "",
                    "visibility": "public",
                    "parameters": [],
                    "line_range": {"start": 15, "end": 20},
                    "receiver": {"name": "c", "type": "*Counter"},
                }
            ],
            "fields": [],
            "imports": [],
            "statistics": {"function_count": 1, "class_count": 1, "variable_count": 0},
        }

        result = formatter.format_structure(data)
        assert "Counter" in result
        assert "Increment" in result

    def test_import_with_alias(self):
        """Test import with alias."""
        formatter = GoTableFormatter("full")
        data = {
            "file_path": "alias.go",
            "packages": [{"name": "main"}],
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [
                {"import_statement": 'import f "fmt"'},
                {"raw_text": "io"},
            ],
            "statistics": {"function_count": 0, "class_count": 0, "variable_count": 0},
        }

        result = formatter.format_structure(data)
        assert "## Imports" in result

    def test_empty_struct(self):
        """Test empty struct."""
        formatter = GoTableFormatter("full")
        data = {
            "file_path": "empty_struct.go",
            "packages": [{"name": "pkg"}],
            "classes": [
                {
                    "name": "Empty",
                    "type": "struct",
                    "line_range": {"start": 5, "end": 5},
                    "interfaces": [],
                }
            ],
            "methods": [],
            "fields": [],
            "imports": [],
            "statistics": {"function_count": 0, "class_count": 1, "variable_count": 0},
        }

        result = formatter.format_structure(data)
        assert "Empty" in result


class TestGoTableFormatterFormatTypeInit:
    """Test format type initialization."""

    def test_full_format_type(self):
        """Test creating formatter with full format type."""
        formatter = GoTableFormatter("full")
        assert formatter.format_type == "full"

    def test_compact_format_type(self):
        """Test creating formatter with compact format type."""
        formatter = GoTableFormatter("compact")
        assert formatter.format_type == "compact"

    def test_csv_format_type(self):
        """Test creating formatter with csv format type."""
        formatter = GoTableFormatter("csv")
        assert formatter.format_type == "csv"

    def test_default_format_type(self):
        """Test creating formatter with default format type."""
        formatter = GoTableFormatter()
        assert formatter.format_type == "full"
