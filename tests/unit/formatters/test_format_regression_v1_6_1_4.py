#!/usr/bin/env python3
"""
Format Regression Tests for v1.6.1.4 Compatibility

This test suite ensures that the analyze_code_structure tool produces
output that exactly matches the v1.6.1.4 specification, preventing
format regression issues like those found in v1.9.4.
"""

import pytest

from tree_sitter_analyzer.formatters.legacy_formatter_adapters import (
    LegacyCompactFormatter,
    LegacyCsvFormatter,
    LegacyFullFormatter,
)
from tree_sitter_analyzer.models import CodeElement


class TestFormatRegressionV1614:
    """Test suite for v1.6.1.4 format regression prevention"""

    @pytest.fixture
    def sample_java_elements(self) -> list[CodeElement]:
        """Create sample Java CodeElements for testing"""
        elements = []

        # Package element
        package_element = CodeElement(
            name="com.example.service", start_line=1, end_line=1, language="java"
        )
        package_element.element_type = "package"
        elements.append(package_element)

        # Import elements
        import1 = CodeElement(
            name="java.util.List", start_line=3, end_line=3, language="java"
        )
        import1.element_type = "import"
        import1.import_statement = "import java.util.List;"
        elements.append(import1)

        import2 = CodeElement(
            name="java.sql.SQLException", start_line=4, end_line=4, language="java"
        )
        import2.element_type = "import"
        import2.import_statement = "import java.sql.SQLException;"
        elements.append(import2)

        # Class element
        class_element = CodeElement(
            name="UserService", start_line=6, end_line=50, language="java"
        )
        class_element.element_type = "class"
        class_element.class_type = "class"
        class_element.visibility = "public"
        elements.append(class_element)

        # Field elements
        field1 = CodeElement(
            name="userRepository", start_line=8, end_line=8, language="java"
        )
        field1.element_type = "field"
        field1.field_type = "UserRepository"
        field1.visibility = "private"
        field1.modifiers = ["private", "final"]
        elements.append(field1)

        field2 = CodeElement(name="logger", start_line=9, end_line=9, language="java")
        field2.element_type = "field"
        field2.field_type = "Logger"
        field2.visibility = "private"
        field2.modifiers = ["private", "static", "final"]
        elements.append(field2)

        # Constructor
        constructor = CodeElement(
            name="UserService", start_line=11, end_line=14, language="java"
        )
        constructor.element_type = "method"
        constructor.is_constructor = True
        constructor.visibility = "public"
        constructor.return_type = "void"
        constructor.parameters = [{"name": "userRepository", "type": "UserRepository"}]
        constructor.complexity_score = 1
        constructor.modifiers = ["public"]
        elements.append(constructor)

        # Regular methods
        method1 = CodeElement(
            name="findUserById", start_line=16, end_line=25, language="java"
        )
        method1.element_type = "method"
        method1.visibility = "public"
        method1.return_type = "User"
        method1.parameters = [{"name": "id", "type": "Long"}]
        method1.complexity_score = 3
        method1.modifiers = ["public"]
        method1.documentation = "Find user by ID"
        elements.append(method1)

        method2 = CodeElement(
            name="createUser", start_line=27, end_line=35, language="java"
        )
        method2.element_type = "method"
        method2.visibility = "public"
        method2.return_type = "User"
        method2.parameters = [
            {"name": "name", "type": "String"},
            {"name": "email", "type": "String"},
        ]
        method2.complexity_score = 2
        method2.modifiers = ["public"]
        method2.documentation = "Create a new user"
        elements.append(method2)

        method3 = CodeElement(
            name="validateUser", start_line=37, end_line=45, language="java"
        )
        method3.element_type = "method"
        method3.visibility = "private"
        method3.return_type = "boolean"
        method3.parameters = [{"name": "user", "type": "User"}]
        method3.complexity_score = 4
        method3.modifiers = ["private"]
        elements.append(method3)

        return elements

    def test_full_format_markdown_table_structure(self, sample_java_elements):
        """Test that full format produces proper Markdown table structure"""
        formatter = LegacyFullFormatter()
        result = formatter.format(sample_java_elements)

        # Verify Markdown structure per format specification
        assert "# com.example.service.UserService" in result
        assert "## Package" in result  # v1.6.1.4 has Package section
        assert "`com.example.service`" in result
        assert "## Class Info" in result
        assert "| Property | Value |" in result
        assert "|----------|-------|" in result
        assert "| Name | UserService |" in result
        assert "| Package | com.example.service |" in result
        assert "| Type | class |" in result
        assert "| Access | public |" in result

        # Verify Methods section per specification
        assert "## Methods" in result
        assert "| Name | Return Type | Parameters | Access | Line |" in result

        # Verify Fields section per specification
        assert "## Fields" in result
        assert "| Name | Type | Access | Static | Final | Line |" in result

        # Verify Imports section (v1.6.1.4 uses code block format, not table)
        assert "## Imports" in result
        assert "```java" in result
        assert "import java.util.List;" in result
        assert "import java.sql.SQLException;" in result

    def test_compact_format_with_complexity(self, sample_java_elements):
        """Test compact format per specification (no complexity scores in spec)"""
        formatter = LegacyCompactFormatter()
        result = formatter.format(sample_java_elements)

        # Verify compact structure per specification
        assert "# UserService" in result  # Compact format: no package in header
        assert "## Info" in result
        assert "| Property | Value |" in result
        assert "| Type | class |" in result
        assert "| Methods |" in result
        assert "| Fields |" in result

        # Verify Methods section per specification (simplified for compact)
        assert "## Methods" in result
        assert "| Name | Return Type | Access | Line |" in result

        # Verify Fields section per specification (simplified for compact)
        assert "## Fields" in result
        assert "| Name | Type | Access | Line |" in result

    def test_csv_format_simple_structure(self, sample_java_elements):
        """Test CSV format simple structure per specification"""
        formatter = LegacyCsvFormatter()
        result = formatter.format(sample_java_elements)

        lines = result.strip().split("\n")

        # Verify header per specification
        header = lines[0]
        expected_header = "Type,Name,ReturnType,Parameters,Access,Static,Final,Line"
        assert header == expected_header

        # Should have at least header + some data rows
        assert len(lines) >= 2

    def test_no_html_formats_supported(self):
        """Test HTML formats not supported (v1.6.1.4 compliance)"""
        from tree_sitter_analyzer.formatters.formatter_registry import FormatterRegistry

        available_formats = FormatterRegistry.get_available_formats()

        # HTML formats should not be available for analyze_code_structure
        html_formats = [f for f in available_formats if "html" in f.lower()]
        assert len(html_formats) == 0, f"HTML formats found: {html_formats}"

        # Only v1.6.1.4 formats should be available
        actual_formats = set(available_formats)

        # Check that core formats are present
        core_formats = {"full", "compact", "csv"}
        assert core_formats.issubset(
            actual_formats
        ), f"Missing core formats: {core_formats - actual_formats}"

    def test_format_consistency_across_formatters(self, sample_java_elements):
        """Test that all formatters handle the same data consistently"""
        full_formatter = LegacyFullFormatter()
        compact_formatter = LegacyCompactFormatter()
        csv_formatter = LegacyCsvFormatter()

        full_result = full_formatter.format(sample_java_elements)
        compact_result = compact_formatter.format(sample_java_elements)
        csv_result = csv_formatter.format(sample_java_elements)

        # All should be non-empty
        assert len(full_result.strip()) > 0
        assert len(compact_result.strip()) > 0
        assert len(csv_result.strip()) > 0

        # All should contain the class name
        assert "UserService" in full_result
        assert "UserService" in compact_result
        assert "UserService" in csv_result

        # All should contain method information
        assert "findUserById" in full_result
        assert "findUserById" in compact_result

    def test_newline_handling_consistency(self, sample_java_elements):
        """Test that newline handling is consistent"""
        full_formatter = LegacyFullFormatter()
        result = full_formatter.format(sample_java_elements)

        # Should not contain Windows-style CRLF
        assert "\r\n" not in result

        # Should use Unix-style LF
        assert "\n" in result

        # Should not end with trailing newlines (CLI compatibility)
        assert not result.endswith("\n\n")

    def test_visibility_symbol_conversion(self, sample_java_elements):
        """Test visibility display per specification (full names, not symbols)"""
        compact_formatter = LegacyCompactFormatter()
        result = compact_formatter.format(sample_java_elements)

        # Per specification, compact format uses full visibility names
        assert "## Methods" in result
        assert "public" in result.lower() or "private" in result.lower()

    def test_parameter_formatting(self, sample_java_elements):
        """Test parameter formatting per specification"""
        full_formatter = LegacyFullFormatter()
        result = full_formatter.format(sample_java_elements)

        # Per specification, full format shows "type param" in Parameters column
        assert "## Methods" in result
        assert "| Parameters |" in result

    def test_empty_elements_handling(self):
        """Test handling of empty element lists"""
        formatters = [
            LegacyFullFormatter(),
            LegacyCompactFormatter(),
            LegacyCsvFormatter(),
        ]

        for formatter in formatters:
            result = formatter.format([])
            assert isinstance(result, str)
            assert (
                len(result.strip()) > 0
            )  # Should produce some output even for empty input


class TestMCPToolFormatRegression:
    """Test MCP tool format compliance with v1.6.1.4"""

    def test_tool_schema_format_restriction(self):
        """Test that MCP tool schema only allows v1.6.1.4 formats"""
        from tree_sitter_analyzer.mcp.tools.table_format_tool import TableFormatTool

        tool = TableFormatTool()
        schema = tool.get_tool_schema()

        format_enum = schema["properties"]["format_type"]["enum"]

        # Should only contain v1.6.1.4 formats
        expected_formats = ["full", "compact", "csv"]
        assert set(format_enum) == set(expected_formats)

        # Should not contain HTML formats
        html_formats = [f for f in format_enum if "html" in f.lower()]
        assert len(html_formats) == 0

    def test_tool_validation_rejects_html_formats(self):
        """Test that tool validation rejects HTML formats"""
        from tree_sitter_analyzer.mcp.tools.table_format_tool import TableFormatTool

        tool = TableFormatTool()

        # Should reject HTML formats
        html_formats = ["html", "html_compact", "html_json"]
        for html_format in html_formats:
            with pytest.raises(ValueError, match="format_type must be one of"):
                tool.validate_arguments(
                    {"file_path": "test.java", "format_type": html_format}
                )

        # Should accept v1.6.1.4 formats
        valid_formats = ["full", "compact", "csv"]
        for valid_format in valid_formats:
            # Should not raise exception
            assert (
                tool.validate_arguments(
                    {"file_path": "test.java", "format_type": valid_format}
                )
                is True
            )
