"""
Comprehensive tests for Base Formatter (formatters/base_formatter.py)

Tests for BaseFormatter and BaseTableFormatter classes, including abstract methods,
format conversion, helper methods, and platform-specific handling.
"""

import csv
import io
import os
from typing import Any
from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.formatters.base_formatter import (
    BaseFormatter,
    BaseTableFormatter,
)


class ConcreteFormatter(BaseFormatter):
    """Concrete implementation of BaseFormatter for testing."""

    def __init__(self) -> None:
        super().__init__()
        self.summary_called = False
        self.structure_called = False
        self.advanced_called = False
        self.table_called = False

    def format_summary(self, analysis_result: dict[str, Any]) -> str:
        self.summary_called = True
        return "Summary"

    def format_structure(self, analysis_result: dict[str, Any]) -> str:
        self.structure_called = True
        return "Structure"

    def format_advanced(
        self, analysis_result: dict[str, Any], output_format: str = "json"
    ) -> str:
        self.advanced_called = True
        return f"Advanced: {output_format}"

    def format_table(
        self, analysis_result: dict[str, Any], table_type: str = "full"
    ) -> str:
        self.table_called = True
        return f"Table: {table_type}"


class ConcreteTableFormatter(BaseTableFormatter):
    """Concrete implementation of BaseTableFormatter for testing."""

    def _format_full_table(self, data: dict[str, Any]) -> str:
        return "Full Table"

    def _format_compact_table(self, data: dict[str, Any]) -> str:
        return "Compact Table"


class TestBaseFormatter:
    """Test BaseFormatter abstract base class."""

    def test_cannot_instantiate_base_formatter_directly(self) -> None:
        """Test that BaseFormatter cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseFormatter()  # type: ignore

    def test_concrete_formatter_initialization(self) -> None:
        """Test concrete formatter can be instantiated."""
        formatter = ConcreteFormatter()
        assert formatter is not None
        assert isinstance(formatter, BaseFormatter)

    def test_format_summary_abstract_method(self) -> None:
        """Test format_summary abstract method."""
        formatter = ConcreteFormatter()
        result = formatter.format_summary({})
        assert result == "Summary"
        assert formatter.summary_called

    def test_format_structure_abstract_method(self) -> None:
        """Test format_structure abstract method."""
        formatter = ConcreteFormatter()
        result = formatter.format_structure({})
        assert result == "Structure"
        assert formatter.structure_called

    def test_format_advanced_abstract_method(self) -> None:
        """Test format_advanced abstract method."""
        formatter = ConcreteFormatter()
        result = formatter.format_advanced({}, "json")
        assert result == "Advanced: json"
        assert formatter.advanced_called

    def test_format_advanced_with_different_formats(self) -> None:
        """Test format_advanced with different output formats."""
        formatter = ConcreteFormatter()
        
        result_json = formatter.format_advanced({}, "json")
        assert "json" in result_json
        
        result_xml = formatter.format_advanced({}, "xml")
        assert "xml" in result_xml

    def test_format_table_abstract_method(self) -> None:
        """Test format_table abstract method."""
        formatter = ConcreteFormatter()
        result = formatter.format_table({}, "full")
        assert result == "Table: full"
        assert formatter.table_called

    def test_format_table_with_different_types(self) -> None:
        """Test format_table with different table types."""
        formatter = ConcreteFormatter()
        
        result_full = formatter.format_table({}, "full")
        assert "full" in result_full
        
        result_compact = formatter.format_table({}, "compact")
        assert "compact" in result_compact

    def test_all_abstract_methods_must_be_implemented(self) -> None:
        """Test that all abstract methods must be implemented."""
        class IncompleteFormatter(BaseFormatter):
            def __init__(self) -> None:
                pass
        
        with pytest.raises(TypeError):
            IncompleteFormatter()  # type: ignore


class TestBaseTableFormatter:
    """Test BaseTableFormatter class."""

    def test_initialization_default_format_type(self) -> None:
        """Test default format_type initialization."""
        formatter = ConcreteTableFormatter()
        assert formatter.format_type == "full"

    def test_initialization_with_format_type(self) -> None:
        """Test initialization with custom format type."""
        formatter = ConcreteTableFormatter(format_type="compact")
        assert formatter.format_type == "compact"
        
        formatter_csv = ConcreteTableFormatter(format_type="csv")
        assert formatter_csv.format_type == "csv"

    @patch("os.name", "nt")
    def test_get_platform_newline_windows(self) -> None:
        """Test platform newline detection on Windows."""
        formatter = ConcreteTableFormatter()
        newline = formatter._get_platform_newline()
        assert newline == "\r\n"

    @patch("os.name", "posix")
    def test_get_platform_newline_unix(self) -> None:
        """Test platform newline detection on Unix."""
        formatter = ConcreteTableFormatter()
        newline = formatter._get_platform_newline()
        assert newline == "\n"

    @patch("os.name", "nt")
    def test_convert_to_platform_newlines_windows(self) -> None:
        """Test newline conversion on Windows."""
        formatter = ConcreteTableFormatter()
        text = "Line 1\nLine 2\nLine 3"
        result = formatter._convert_to_platform_newlines(text)
        assert result == "Line 1\r\nLine 2\r\nLine 3"

    @patch("os.name", "posix")
    def test_convert_to_platform_newlines_unix(self) -> None:
        """Test newline conversion on Unix (no change)."""
        formatter = ConcreteTableFormatter()
        text = "Line 1\nLine 2\nLine 3"
        result = formatter._convert_to_platform_newlines(text)
        assert result == "Line 1\nLine 2\nLine 3"

    def test_format_structure_full_table(self) -> None:
        """Test format_structure with full table format."""
        formatter = ConcreteTableFormatter(format_type="full")
        result = formatter.format_structure({})
        assert "Full Table" in result

    def test_format_structure_compact_table(self) -> None:
        """Test format_structure with compact table format."""
        formatter = ConcreteTableFormatter(format_type="compact")
        result = formatter.format_structure({})
        assert "Compact Table" in result

    def test_format_structure_csv_format(self) -> None:
        """Test format_structure with CSV format."""
        formatter = ConcreteTableFormatter(format_type="csv")
        data = {
            "fields": [],
            "methods": []
        }
        result = formatter.format_structure(data)
        
        # CSV should contain header
        assert "Type,Name,Signature,Visibility,Lines,Complexity,Doc" in result

    def test_format_structure_invalid_format_type(self) -> None:
        """Test format_structure with invalid format type."""
        formatter = ConcreteTableFormatter(format_type="invalid")
        
        with pytest.raises(ValueError, match="Unsupported format type"):
            formatter.format_structure({})

    def test_format_csv_with_empty_data(self) -> None:
        """Test CSV formatting with empty data."""
        formatter = ConcreteTableFormatter(format_type="csv")
        data = {
            "fields": [],
            "methods": []
        }
        result = formatter._format_csv(data)
        
        # Should have header only
        lines = result.split("\n")
        assert len(lines) == 1
        assert lines[0].startswith("Type,Name,Signature")

    def test_format_csv_with_fields(self) -> None:
        """Test CSV formatting with field data."""
        formatter = ConcreteTableFormatter(format_type="csv")
        data = {
            "fields": [
                {
                    "name": "field1",
                    "type": "String",
                    "visibility": "private",
                    "line_range": {"start": 10, "end": 10},
                    "javadoc": "/** Field documentation */"
                }
            ],
            "methods": []
        }
        result = formatter._format_csv(data)
        
        lines = result.split("\n")
        assert len(lines) == 2  # Header + 1 field
        assert "Field,field1" in lines[1]

    def test_format_csv_with_methods(self) -> None:
        """Test CSV formatting with method data."""
        formatter = ConcreteTableFormatter(format_type="csv")
        data = {
            "fields": [],
            "methods": [
                {
                    "name": "testMethod",
                    "parameters": [
                        {"name": "param1", "type": "int"},
                        {"name": "param2", "type": "String"}
                    ],
                    "return_type": "void",
                    "visibility": "public",
                    "is_static": False,
                    "is_constructor": False,
                    "line_range": {"start": 20, "end": 30},
                    "complexity_score": 5,
                    "javadoc": "/** Method documentation */"
                }
            ]
        }
        result = formatter._format_csv(data)
        
        lines = result.split("\n")
        assert len(lines) == 2  # Header + 1 method
        assert "Method,testMethod" in lines[1]
        assert "5" in lines[1]  # complexity

    def test_format_csv_with_constructor(self) -> None:
        """Test CSV formatting with constructor."""
        formatter = ConcreteTableFormatter(format_type="csv")
        data = {
            "fields": [],
            "methods": [
                {
                    "name": "MyClass",
                    "parameters": [],
                    "return_type": "",
                    "visibility": "public",
                    "is_static": False,
                    "is_constructor": True,
                    "line_range": {"start": 5, "end": 10},
                    "complexity_score": 1,
                    "javadoc": ""
                }
            ]
        }
        result = formatter._format_csv(data)
        
        lines = result.split("\n")
        assert "Constructor,MyClass" in lines[1]

    def test_create_full_signature_simple(self) -> None:
        """Test creating full signature for simple method."""
        formatter = ConcreteTableFormatter()
        method = {
            "parameters": [],
            "return_type": "void",
            "is_static": False
        }
        
        signature = formatter._create_full_signature(method)
        assert signature == "():void"

    def test_create_full_signature_with_parameters(self) -> None:
        """Test creating full signature with parameters."""
        formatter = ConcreteTableFormatter()
        method = {
            "parameters": [
                {"name": "x", "type": "int"},
                {"name": "y", "type": "String"}
            ],
            "return_type": "boolean",
            "is_static": False
        }
        
        signature = formatter._create_full_signature(method)
        assert signature == "(x:int, y:String):boolean"

    def test_create_full_signature_static_method(self) -> None:
        """Test creating full signature for static method."""
        formatter = ConcreteTableFormatter()
        method = {
            "parameters": [],
            "return_type": "void",
            "is_static": True
        }
        
        signature = formatter._create_full_signature(method)
        assert "[static]" in signature
        assert "():void" in signature

    def test_create_full_signature_with_default_types(self) -> None:
        """Test creating signature with default types when missing."""
        formatter = ConcreteTableFormatter()
        method = {
            "parameters": [
                {"name": "x"}  # Missing type
            ]
        }
        
        signature = formatter._create_full_signature(method)
        assert "x:Object" in signature  # Should use default type

    def test_create_full_signature_with_string_parameters(self) -> None:
        """Test creating signature with string parameters."""
        formatter = ConcreteTableFormatter()
        method = {
            "parameters": ["param1", "param2"],  # String parameters
            "return_type": "void",
            "is_static": False
        }
        
        signature = formatter._create_full_signature(method)
        assert "(param1, param2):void" in signature

    def test_convert_visibility_public(self) -> None:
        """Test visibility conversion for public."""
        formatter = ConcreteTableFormatter()
        assert formatter._convert_visibility("public") == "+"

    def test_convert_visibility_private(self) -> None:
        """Test visibility conversion for private."""
        formatter = ConcreteTableFormatter()
        assert formatter._convert_visibility("private") == "-"

    def test_convert_visibility_protected(self) -> None:
        """Test visibility conversion for protected."""
        formatter = ConcreteTableFormatter()
        assert formatter._convert_visibility("protected") == "#"

    def test_convert_visibility_package(self) -> None:
        """Test visibility conversion for package."""
        formatter = ConcreteTableFormatter()
        assert formatter._convert_visibility("package") == "~"

    def test_convert_visibility_unknown(self) -> None:
        """Test visibility conversion for unknown visibility."""
        formatter = ConcreteTableFormatter()
        assert formatter._convert_visibility("custom") == "custom"

    def test_extract_doc_summary_empty(self) -> None:
        """Test extracting summary from empty documentation."""
        formatter = ConcreteTableFormatter()
        assert formatter._extract_doc_summary("") == "-"
        assert formatter._extract_doc_summary(None) == "-"  # type: ignore

    def test_extract_doc_summary_simple(self) -> None:
        """Test extracting summary from simple documentation."""
        formatter = ConcreteTableFormatter()
        javadoc = "/** Simple documentation */"
        result = formatter._extract_doc_summary(javadoc)
        assert result == "Simple documentation"

    def test_extract_doc_summary_multiline(self) -> None:
        """Test extracting summary from multiline documentation."""
        formatter = ConcreteTableFormatter()
        javadoc = """/**
         * First line of documentation
         * Second line
         */"""
        result = formatter._extract_doc_summary(javadoc)
        assert result == "First line of documentation"

    def test_extract_doc_summary_long_text(self) -> None:
        """Test extracting summary from long documentation (truncation)."""
        formatter = ConcreteTableFormatter()
        javadoc = "/** " + "x" * 100 + " */"
        result = formatter._extract_doc_summary(javadoc)
        assert len(result) == 50
        assert result.endswith("...")

    def test_extract_doc_summary_with_pipe_chars(self) -> None:
        """Test extracting summary with pipe characters (escaped for tables)."""
        formatter = ConcreteTableFormatter()
        javadoc = "/** Documentation | with | pipes */"
        result = formatter._extract_doc_summary(javadoc)
        assert "\\|" in result
        assert "|" not in result or result.count("|") < 3  # Pipes should be escaped

    def test_extract_doc_summary_with_newlines(self) -> None:
        """Test extracting summary replaces newlines with spaces."""
        formatter = ConcreteTableFormatter()
        javadoc = "/** Line 1\nLine 2 */"
        result = formatter._extract_doc_summary(javadoc)
        assert "\n" not in result
        assert " " in result

    def test_clean_csv_text_empty(self) -> None:
        """Test cleaning empty CSV text."""
        formatter = ConcreteTableFormatter()
        assert formatter._clean_csv_text("") == ""
        assert formatter._clean_csv_text(None) == ""  # type: ignore

    def test_clean_csv_text_simple(self) -> None:
        """Test cleaning simple CSV text."""
        formatter = ConcreteTableFormatter()
        result = formatter._clean_csv_text("Simple text")
        assert result == "Simple text"

    def test_clean_csv_text_with_newlines(self) -> None:
        """Test cleaning CSV text with various newlines."""
        formatter = ConcreteTableFormatter()
        text = "Line 1\r\nLine 2\rLine 3\nLine 4"
        result = formatter._clean_csv_text(text)
        assert "\n" not in result
        assert "\r" not in result
        assert result == "Line 1 Line 2 Line 3 Line 4"

    def test_clean_csv_text_with_quotes(self) -> None:
        """Test cleaning CSV text with quotes (escaping)."""
        formatter = ConcreteTableFormatter()
        text = 'Text with "quotes" inside'
        result = formatter._clean_csv_text(text)
        assert '""' in result  # Quotes should be escaped

    def test_clean_csv_text_with_multiple_spaces(self) -> None:
        """Test cleaning CSV text with multiple spaces."""
        formatter = ConcreteTableFormatter()
        text = "Text    with    multiple    spaces"
        result = formatter._clean_csv_text(text)
        assert result == "Text with multiple spaces"

    def test_csv_format_no_trailing_newline(self) -> None:
        """Test CSV format doesn't have trailing newline."""
        formatter = ConcreteTableFormatter(format_type="csv")
        data = {"fields": [], "methods": []}
        result = formatter._format_csv(data)
        assert not result.endswith("\n")

    def test_csv_format_normalized_newlines(self) -> None:
        """Test CSV format has normalized newlines."""
        formatter = ConcreteTableFormatter(format_type="csv")
        data = {
            "fields": [
                {
                    "name": "field1",
                    "type": "String",
                    "visibility": "private",
                    "line_range": {"start": 1, "end": 1},
                    "javadoc": ""
                }
            ],
            "methods": []
        }
        result = formatter._format_csv(data)
        
        # Should not contain \r\n or \r
        assert "\r\n" not in result
        assert "\r" not in result

    def test_format_structure_applies_platform_newlines_for_non_csv(self) -> None:
        """Test format_structure applies platform newlines for non-CSV formats."""
        formatter = ConcreteTableFormatter(format_type="full")
        
        with patch.object(formatter, "_convert_to_platform_newlines") as mock_convert:
            mock_convert.return_value = "Converted"
            result = formatter.format_structure({})
            
            # Should call conversion for non-CSV
            mock_convert.assert_called_once()

    def test_format_structure_no_platform_newlines_for_csv(self) -> None:
        """Test format_structure doesn't apply platform newlines for CSV."""
        formatter = ConcreteTableFormatter(format_type="csv")
        data = {"fields": [], "methods": []}
        
        result = formatter.format_structure(data)
        
        # CSV format should return as-is without platform newline conversion
        # (CSV has its own newline handling)
        assert "Type,Name,Signature" in result


class TestBaseTableFormatterEdgeCases:
    """Test edge cases for BaseTableFormatter."""

    def test_format_csv_with_missing_fields_in_data(self) -> None:
        """Test CSV formatting with missing fields in data."""
        formatter = ConcreteTableFormatter(format_type="csv")
        data = {
            "fields": [
                {
                    "name": "field1"
                    # Missing type, visibility, etc.
                }
            ],
            "methods": []
        }
        result = formatter._format_csv(data)
        
        # Should not raise, use defaults
        assert "field1" in result

    def test_format_csv_with_missing_method_fields(self) -> None:
        """Test CSV formatting with missing method fields."""
        formatter = ConcreteTableFormatter(format_type="csv")
        data = {
            "fields": [],
            "methods": [
                {
                    "name": "method1"
                    # Missing parameters, return_type, etc.
                }
            ]
        }
        result = formatter._format_csv(data)
        
        # Should not raise, use defaults
        assert "method1" in result

    def test_create_full_signature_empty_parameters(self) -> None:
        """Test creating signature with empty parameters list."""
        formatter = ConcreteTableFormatter()
        method = {
            "parameters": [],
            "return_type": "int"
        }
        signature = formatter._create_full_signature(method)
        assert signature == "():int"

    def test_create_full_signature_missing_return_type(self) -> None:
        """Test creating signature with missing return type."""
        formatter = ConcreteTableFormatter()
        method = {
            "parameters": []
        }
        signature = formatter._create_full_signature(method)
        assert "void" in signature

    def test_format_csv_line_range_missing_keys(self) -> None:
        """Test CSV formatting with incomplete line_range."""
        formatter = ConcreteTableFormatter(format_type="csv")
        data = {
            "fields": [
                {
                    "name": "field1",
                    "type": "int",
                    "visibility": "private",
                    "line_range": {},  # Empty line_range
                    "javadoc": ""
                }
            ],
            "methods": []
        }
        result = formatter._format_csv(data)
        
        # Should handle gracefully with defaults (0-0)
        assert "0-0" in result

    def test_cannot_instantiate_base_table_formatter_without_abstract_methods(
        self,
    ) -> None:
        """Test that BaseTableFormatter requires abstract methods."""
        class IncompleteTableFormatter(BaseTableFormatter):
            pass
        
        with pytest.raises(TypeError):
            IncompleteTableFormatter()  # type: ignore
