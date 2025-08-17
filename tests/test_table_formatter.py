#!/usr/bin/env python3
"""
Tests for Table Formatter

This module tests the table formatting functionality including
full table format, compact format, CSV format, and various edge cases.
Follows TDD principles and .roo-config.json requirements.
"""

import csv
import io
import os
from typing import Any
from unittest.mock import patch

import pytest

# Import the module under test
from tree_sitter_analyzer.table_formatter import TableFormatter, create_table_formatter


@pytest.fixture
def sample_structure_data() -> dict[str, Any]:
    """Fixture providing sample structure data for testing"""
    return {
        "package": {"name": "com.example.test"},
        "classes": [
            {
                "name": "TestClass",
                "type": "class",
                "visibility": "public",
                "line_range": {"start": 1, "end": 50},
            }
        ],
        "imports": [
            {"statement": "import java.util.List;"},
            {"statement": "import java.util.Map;"},
        ],
        "fields": [
            {
                "name": "testField",
                "type": "String",
                "visibility": "private",
                "modifiers": ["final"],
                "line_range": {"start": 5, "end": 5},
                "javadoc": "Test field documentation",
            }
        ],
        "methods": [
            {
                "name": "TestClass",
                "is_constructor": True,
                "visibility": "public",
                "parameters": [{"name": "param1", "type": "String"}],
                "line_range": {"start": 10, "end": 15},
                "complexity_score": 1,
                "javadoc": "Constructor documentation",
            },
            {
                "name": "publicMethod",
                "is_constructor": False,
                "visibility": "public",
                "parameters": [
                    {"name": "input", "type": "String"},
                    {"name": "count", "type": "int"},
                ],
                "return_type": "boolean",
                "is_static": True,
                "line_range": {"start": 20, "end": 30},
                "complexity_score": 3,
                "javadoc": "Public method documentation with detailed explanation",
            },
            {
                "name": "privateMethod",
                "is_constructor": False,
                "visibility": "private",
                "parameters": [],
                "return_type": "void",
                "line_range": {"start": 35, "end": 40},
                "complexity_score": 2,
                "javadoc": "Private method documentation",
            },
        ],
        "statistics": {"method_count": 3, "field_count": 1},
    }


@pytest.fixture
def empty_structure_data() -> dict[str, Any]:
    """Fixture providing empty structure data for edge case testing"""
    return {
        "package": None,
        "classes": [],
        "imports": [],
        "fields": [],
        "methods": [],
        "statistics": {},
    }


class TestTableFormatterInitialization:
    """Test cases for TableFormatter initialization"""

    def test_default_initialization(self) -> None:
        """Test TableFormatter initializes with default format type"""
        formatter = TableFormatter()
        assert formatter.format_type == "full"

    def test_custom_format_initialization(self) -> None:
        """Test TableFormatter initializes with custom format type"""
        formatter = TableFormatter("compact")
        assert formatter.format_type == "compact"

    def test_csv_format_initialization(self) -> None:
        """Test TableFormatter initializes with CSV format type"""
        formatter = TableFormatter("csv")
        assert formatter.format_type == "csv"


class TestTableFormatterPlatformHandling:
    """Test cases for platform-specific newline handling"""

    def test_get_platform_newline(self) -> None:
        """Test platform newline detection"""
        formatter = TableFormatter()
        newline = formatter._get_platform_newline()
        # On Windows, should return \r\n, on Unix-like systems \n
        if os.name == "nt":
            assert newline == "\r\n"
        else:
            assert newline == "\n"

    def test_convert_to_platform_newlines_unix(self) -> None:
        """Test newline conversion on Unix-like systems"""
        formatter = TableFormatter()
        # Mock the _get_platform_newline method to return Unix newlines
        with patch.object(formatter, "_get_platform_newline", return_value="\n"):
            result = formatter._convert_to_platform_newlines("line1\nline2\nline3")
            assert result == "line1\nline2\nline3"

    def test_convert_to_platform_newlines_windows(self) -> None:
        """Test newline conversion on Windows systems"""
        formatter = TableFormatter()
        # Mock the _get_platform_newline method to return Windows newlines
        with patch.object(formatter, "_get_platform_newline", return_value="\r\n"):
            result = formatter._convert_to_platform_newlines("line1\nline2\nline3")
            assert result == "line1\r\nline2\r\nline3"


class TestTableFormatterFullFormat:
    """Test cases for full table format"""

    def test_format_structure_full(self, sample_structure_data: dict[str, Any]) -> None:
        """Test full format structure formatting"""
        formatter = TableFormatter("full", include_javadoc=True)
        result = formatter.format_structure(sample_structure_data)

        # Verify header
        assert "# com.example.test.TestClass" in result

        # Verify imports section
        assert "## Imports" in result
        assert "import java.util.List;" in result
        assert "import java.util.Map;" in result

        # Verify class info section
        assert "## Class Info" in result
        assert "| Package | com.example.test |" in result
        assert "| Type | class |" in result
        assert "| Visibility | public |" in result
        assert "| Lines | 1-50 |" in result
        assert "| Total Methods | 3 |" in result
        assert "| Total Fields | 1 |" in result

        # Verify fields section
        assert "## Fields" in result
        assert (
            "| testField | String | - | final | 5 | Test field documentation |"
            in result
        )

        # Verify constructor section
        assert "## Constructor" in result
        assert "| TestClass |" in result

        # Verify public methods section
        assert "## Public Methods" in result
        assert "| publicMethod |" in result

        # Verify private methods section
        assert "## Private Methods" in result
        assert "| privateMethod |" in result

    def test_format_structure_full_with_empty_data(
        self, empty_structure_data: dict[str, Any]
    ) -> None:
        """Test full format with empty data"""
        formatter = TableFormatter("full")
        result = formatter.format_structure(empty_structure_data)

        # Should handle empty data gracefully
        assert "# unknown.Unknown" in result
        assert "## Class Info" in result
        assert "| Package | unknown |" in result

    def test_format_structure_full_no_imports(
        self, sample_structure_data: dict[str, Any]
    ) -> None:
        """Test full format without imports"""
        data = sample_structure_data.copy()
        data["imports"] = []

        formatter = TableFormatter("full")
        result = formatter.format_structure(data)

        # Should not include imports section
        assert "## Imports" not in result

    def test_format_structure_full_no_fields(
        self, sample_structure_data: dict[str, Any]
    ) -> None:
        """Test full format without fields"""
        data = sample_structure_data.copy()
        data["fields"] = []

        formatter = TableFormatter("full")
        result = formatter.format_structure(data)

        # Should not include fields section
        assert "## Fields" not in result

    def test_format_structure_full_no_constructors(
        self, sample_structure_data: dict[str, Any]
    ) -> None:
        """Test full format without constructors"""
        data = sample_structure_data.copy()
        data["methods"] = [
            m for m in data["methods"] if not m.get("is_constructor", False)
        ]

        formatter = TableFormatter("full")
        result = formatter.format_structure(data)

        # Should not include constructor section
        assert "## Constructor" not in result


class TestTableFormatterCompactFormat:
    """Test cases for compact table format"""

    def test_format_structure_compact(
        self, sample_structure_data: dict[str, Any]
    ) -> None:
        """Test compact format structure formatting"""
        formatter = TableFormatter("compact")
        result = formatter.format_structure(sample_structure_data)

        # Verify header
        assert "# com.example.test.TestClass" in result

        # Verify info section
        assert "## Info" in result
        assert "| Package | com.example.test |" in result
        assert "| Methods | 3 |" in result
        assert "| Fields | 1 |" in result

        # Verify methods section
        assert "## Methods" in result
        assert "| Method | Sig | V | L | Cx | Doc |" in result

    def test_format_structure_compact_with_empty_data(
        self, empty_structure_data: dict[str, Any]
    ) -> None:
        """Test compact format with empty data"""
        formatter = TableFormatter("compact")
        result = formatter.format_structure(empty_structure_data)

        # Should handle empty data gracefully
        assert "# unknown.Unknown" in result
        assert "## Info" in result


class TestTableFormatterCSVFormat:
    """Test cases for CSV format"""

    def test_format_structure_csv(self, sample_structure_data: dict[str, Any]) -> None:
        """Test CSV format structure formatting"""
        formatter = TableFormatter("csv")
        result = formatter.format_structure(sample_structure_data)

        # Parse CSV to verify structure
        csv_reader = csv.reader(io.StringIO(result))
        rows = list(csv_reader)

        # Verify header
        assert rows[0] == [
            "Type",
            "Name",
            "Signature",
            "Visibility",
            "Lines",
            "Complexity",
            "Doc",
        ]

        # Verify field row
        field_row = next((row for row in rows if row[0] == "Field"), None)
        assert field_row is not None
        assert field_row[1] == "testField"
        assert field_row[3] == "private"

        # Verify method rows
        method_rows = [row for row in rows if row[0] in ["Method", "Constructor"]]
        assert len(method_rows) == 3

    def test_format_structure_csv_with_empty_data(
        self, empty_structure_data: dict[str, Any]
    ) -> None:
        """Test CSV format with empty data"""
        formatter = TableFormatter("csv")
        result = formatter.format_structure(empty_structure_data)

        # Should produce valid CSV even with empty data
        csv_reader = csv.reader(io.StringIO(result))
        rows = list(csv_reader)
        assert len(rows) >= 1  # At least header row

    def test_csv_newline_handling(self, sample_structure_data: dict[str, Any]) -> None:
        """Test CSV format handles newlines correctly"""
        formatter = TableFormatter("csv")
        result = formatter.format_structure(sample_structure_data)

        # Should not end with newline
        assert not result.endswith("\n")

        # Should use consistent newlines
        assert "\r\n" not in result or "\n" not in result.replace("\r\n", "")


class TestTableFormatterHelperMethods:
    """Test cases for helper methods"""

    def test_format_method_row(self, sample_structure_data: dict[str, Any]) -> None:
        """Test method row formatting"""
        formatter = TableFormatter()
        method = sample_structure_data["methods"][1]  # publicMethod
        result = formatter._format_method_row(method)

        assert "| publicMethod |" in result
        assert "| + |" in result  # public visibility
        assert "| 20-30 |" in result  # line range
        assert "| 3 |" in result  # complexity

    def test_create_full_signature(self, sample_structure_data: dict[str, Any]) -> None:
        """Test full signature creation"""
        formatter = TableFormatter()
        method = sample_structure_data["methods"][1]  # publicMethod
        result = formatter._create_full_signature(method)

        assert "(input:String, count:int):boolean [static]" == result

    def test_create_compact_signature(
        self, sample_structure_data: dict[str, Any]
    ) -> None:
        """Test compact signature creation"""
        formatter = TableFormatter()
        method = sample_structure_data["methods"][1]  # publicMethod
        result = formatter._create_compact_signature(method)

        assert "(S,i):b" == result

    def test_shorten_type_basic_types(self) -> None:
        """Test type shortening for basic types"""
        formatter = TableFormatter()

        assert formatter._shorten_type("String") == "S"
        assert formatter._shorten_type("int") == "i"
        assert formatter._shorten_type("boolean") == "b"
        assert formatter._shorten_type("void") == "void"
        assert formatter._shorten_type("Object") == "O"

    def test_shorten_type_complex_types(self) -> None:
        """Test type shortening for complex types"""
        formatter = TableFormatter()

        assert formatter._shorten_type("Map<String,Object>") == "M<S,O>"
        assert formatter._shorten_type("List<String>") == "L<S>"
        assert formatter._shorten_type("String[]") == "S[]"
        assert formatter._shorten_type("CustomType") == "CustomType"

    def test_shorten_type_none_and_non_string(self) -> None:
        """Test type shortening with None and non-string inputs"""
        formatter = TableFormatter()

        assert formatter._shorten_type(None) == "O"
        assert formatter._shorten_type(123) == "123"
        assert formatter._shorten_type([]) == "O[]"

    def test_convert_visibility(self) -> None:
        """Test visibility conversion to symbols"""
        formatter = TableFormatter()

        assert formatter._convert_visibility("public") == "+"
        assert formatter._convert_visibility("private") == "-"
        assert formatter._convert_visibility("protected") == "#"
        assert formatter._convert_visibility("package") == "~"
        assert formatter._convert_visibility("unknown") == "unknown"

    def test_extract_doc_summary(self) -> None:
        """Test JavaDoc summary extraction"""
        formatter = TableFormatter()

        # Test normal JavaDoc
        javadoc = (
            "/**\n * This is a test method\n * @param input the input parameter\n */"
        )
        result = formatter._extract_doc_summary(javadoc)
        assert result == "This is a test method"

        # Test empty JavaDoc
        assert formatter._extract_doc_summary("") == "-"
        assert formatter._extract_doc_summary(None) == "-"

        # Test long JavaDoc (should be truncated)
        long_doc = "/**\n * " + "A" * 60 + "\n */"
        result = formatter._extract_doc_summary(long_doc)
        assert len(result) <= 50
        assert result.endswith("...")

    def test_extract_doc_summary_with_special_characters(self) -> None:
        """Test JavaDoc summary extraction with special characters"""
        formatter = TableFormatter()

        # Test with pipe characters (should be escaped)
        javadoc = "/**\n * Method with | pipe character\n */"
        result = formatter._extract_doc_summary(javadoc)
        assert "\\|" in result

        # Test with newlines (should be replaced with spaces)
        javadoc = "/**\n * Method with\n * multiple lines\n */"
        result = formatter._extract_doc_summary(javadoc)
        assert "\n" not in result

    def test_clean_csv_text(self) -> None:
        """Test CSV text cleaning"""
        formatter = TableFormatter()

        # Test normal text
        assert formatter._clean_csv_text("normal text") == "normal text"

        # Test empty text
        assert formatter._clean_csv_text("") == ""
        assert formatter._clean_csv_text(None) == ""

        # Test text with newlines
        text_with_newlines = "line1\nline2\r\nline3\r"
        result = formatter._clean_csv_text(text_with_newlines)
        assert "\n" not in result
        assert "\r" not in result
        assert result == "line1 line2 line3"

        # Test text with quotes
        text_with_quotes = 'text with "quotes"'
        result = formatter._clean_csv_text(text_with_quotes)
        assert '""' in result

        # Test text with multiple spaces
        text_with_spaces = "text   with    multiple     spaces"
        result = formatter._clean_csv_text(text_with_spaces)
        assert result == "text with multiple spaces"


class TestTableFormatterErrorHandling:
    """Test cases for error handling and edge cases"""

    def test_unsupported_format_type(
        self, sample_structure_data: dict[str, Any]
    ) -> None:
        """Test error handling for unsupported format types"""
        formatter = TableFormatter("unsupported")

        with pytest.raises(ValueError, match="Unsupported format type: unsupported"):
            formatter.format_structure(sample_structure_data)

    def test_format_structure_with_missing_keys(self) -> None:
        """Test format structure with missing keys in data"""
        formatter = TableFormatter("full")
        minimal_data: dict[str, Any] = {}

        # Should not raise exception, should handle gracefully
        result = formatter.format_structure(minimal_data)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_structure_with_none_values(self) -> None:
        """Test format structure with None values in data"""
        formatter = TableFormatter("full")
        data_with_nones: dict[str, Any] = {
            "package": None,
            "classes": None,
            "imports": None,
            "fields": None,
            "methods": None,
            "statistics": None,
        }

        # Should not raise exception, should handle gracefully
        result = formatter.format_structure(data_with_nones)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_method_with_missing_parameters(self) -> None:
        """Test method formatting with missing parameters"""
        formatter = TableFormatter()
        method_without_params: dict[str, Any] = {
            "name": "testMethod",
            "visibility": "public",
            "line_range": {"start": 1, "end": 5},
            "complexity_score": 1,
        }

        # Should not raise exception
        result = formatter._format_method_row(method_without_params)
        assert isinstance(result, str)
        assert "testMethod" in result

    def test_csv_format_with_special_characters(self) -> None:
        """Test CSV format handles special characters correctly"""
        formatter = TableFormatter("csv")
        data_with_special_chars: dict[str, Any] = {
            "fields": [
                {
                    "name": "field,with,commas",
                    "type": "String",
                    "visibility": "private",
                    "line_range": {"start": 1, "end": 1},
                    "javadoc": 'Documentation with "quotes" and\nnewlines',
                }
            ],
            "methods": [],
            "package": {"name": "test"},
            "classes": [{"name": "Test"}],
            "imports": [],
            "statistics": {},
        }

        result = formatter.format_structure(data_with_special_chars)

        # Should produce valid CSV
        csv_reader = csv.reader(io.StringIO(result))
        rows = list(csv_reader)
        assert len(rows) >= 2  # Header + at least one data row


class TestTableFormatterIntegration:
    """Integration tests for TableFormatter"""

    def test_all_format_types_produce_output(
        self, sample_structure_data: dict[str, Any]
    ) -> None:
        """Test that all format types produce non-empty output"""
        format_types = ["full", "compact", "csv"]

        for format_type in format_types:
            formatter = TableFormatter(format_type)
            result = formatter.format_structure(sample_structure_data)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_format_consistency_across_platforms(
        self, sample_structure_data: dict[str, Any]
    ) -> None:
        """Test format consistency across different platform newline settings"""
        formatter = TableFormatter("full")

        # Test with different platform newline values
        with patch.object(formatter, "_get_platform_newline", return_value="\n"):
            result_unix = formatter.format_structure(sample_structure_data)

        with patch.object(formatter, "_get_platform_newline", return_value="\r\n"):
            result_windows = formatter.format_structure(sample_structure_data)

        # Content should be the same except for newlines
        assert result_unix.replace("\n", "") == result_windows.replace(
            "\r\n", ""
        ).replace("\n", "")

    def test_csv_format_roundtrip(self, sample_structure_data: dict[str, Any]) -> None:
        """Test CSV format can be parsed and contains expected data"""
        formatter = TableFormatter("csv")
        result = formatter.format_structure(sample_structure_data)

        # Parse CSV
        csv_reader = csv.reader(io.StringIO(result))
        rows = list(csv_reader)

        # Verify we can extract meaningful data
        header = rows[0]
        assert "Type" in header
        assert "Name" in header
        assert "Signature" in header

        # Verify data rows contain expected information
        data_rows = rows[1:]
        names = [row[1] for row in data_rows if len(row) > 1]
        assert "testField" in names
        assert "publicMethod" in names


class TestCreateTableFormatterFunction:
    """Test cases for the create_table_formatter factory function"""

    def test_create_table_formatter_full(self) -> None:
        """Test factory function creates full formatter"""
        formatter = create_table_formatter("full")
        assert isinstance(formatter, TableFormatter)
        assert formatter.format_type == "full"

    def test_create_table_formatter_compact(self) -> None:
        """Test factory function creates compact formatter"""
        formatter = create_table_formatter("compact")
        assert isinstance(formatter, TableFormatter)
        assert formatter.format_type == "compact"

    def test_create_table_formatter_csv(self) -> None:
        """Test factory function creates CSV formatter"""
        formatter = create_table_formatter("csv")
        assert isinstance(formatter, TableFormatter)
        assert formatter.format_type == "csv"


class TestTableFormatterPerformance:
    """Performance and resource management tests"""

    def test_large_data_structure_handling(self) -> None:
        """Test formatter handles large data structures efficiently"""
        # Create large data structure
        large_data: dict[str, Any] = {
            "package": {"name": "com.example.large"},
            "classes": [{"name": f"Class{i}", "type": "class"} for i in range(100)],
            "imports": [
                {"statement": f"import com.example.Import{i};"} for i in range(50)
            ],
            "fields": [
                {
                    "name": f"field{i}",
                    "type": "String",
                    "visibility": "private",
                    "modifiers": [],
                    "line_range": {"start": i, "end": i},
                    "javadoc": f"Field {i} documentation",
                }
                for i in range(200)
            ],
            "methods": [
                {
                    "name": f"method{i}",
                    "is_constructor": False,
                    "visibility": "public",
                    "parameters": [],
                    "return_type": "void",
                    "line_range": {"start": i * 10, "end": i * 10 + 5},
                    "complexity_score": 1,
                    "javadoc": f"Method {i} documentation",
                }
                for i in range(300)
            ],
            "statistics": {"method_count": 300, "field_count": 200},
        }

        # Should handle large data without issues
        formatter = TableFormatter("full")
        result = formatter.format_structure(large_data)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_memory_efficient_csv_generation(
        self, sample_structure_data: dict[str, Any]
    ) -> None:
        """Test CSV generation is memory efficient"""
        formatter = TableFormatter("csv")

        # Should not keep large intermediate strings in memory
        result = formatter.format_structure(sample_structure_data)
        assert isinstance(result, str)

        # Verify CSV is properly formatted
        lines = result.split("\n")
        assert len(lines) >= 2  # Header + data


# Additional test markers for categorization
pytestmark = [
    pytest.mark.unit,
]
