#!/usr/bin/env python3
"""
Unit tests for tree_sitter_analyzer.formatters.legacy_formatter_adapters module.

This module tests LegacyFormatterAdapter and its subclasses.
"""

from tree_sitter_analyzer.constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_PACKAGE,
    ELEMENT_TYPE_VARIABLE,
)
from tree_sitter_analyzer.formatters.legacy_formatter_adapters import (
    LegacyCompactFormatter,
    LegacyCsvFormatter,
    LegacyFormatterAdapter,
    LegacyFullFormatter,
)
from tree_sitter_analyzer.models import (
    Class,
    CodeElement,
    Function,
    Import,
    Variable,
)


class TestLegacyFormatterAdapterInit:
    """Tests for LegacyFormatterAdapter initialization."""

    def test_init_default(self) -> None:
        """Test initialization with default parameters."""
        adapter = LegacyFormatterAdapter("full")
        assert adapter.format_type == "full"
        assert adapter.language == "java"
        assert adapter.include_javadoc is False

    def test_init_with_language(self) -> None:
        """Test initialization with custom language."""
        adapter = LegacyFormatterAdapter("full", language="python")
        assert adapter.language == "python"

    def test_init_with_javadoc(self) -> None:
        """Test initialization with javadoc enabled."""
        adapter = LegacyFormatterAdapter("full", include_javadoc=True)
        assert adapter.include_javadoc is True

    def test_init_compact_format(self) -> None:
        """Test initialization with compact format."""
        adapter = LegacyFormatterAdapter("compact")
        assert adapter.format_type == "compact"

    def test_init_csv_format(self) -> None:
        """Test initialization with CSV format."""
        adapter = LegacyFormatterAdapter("csv")
        assert adapter.format_type == "csv"


class TestLegacyFormatterAdapterFormat:
    """Tests for LegacyFormatterAdapter.format method."""

    def test_format_empty_elements(self) -> None:
        """Test formatting empty element list."""
        adapter = LegacyFormatterAdapter("full")
        result = adapter.format([])
        assert isinstance(result, str)
        assert "file_path" in result or "Unknown" in result

    def test_format_single_class(self) -> None:
        """Test formatting single class element."""
        adapter = LegacyFormatterAdapter("full")
        element = Class(
            name="TestClass",
            element_type=ELEMENT_TYPE_CLASS,
            start_line=10,
            end_line=20,
        )
        result = adapter.format([element])
        assert isinstance(result, str)
        assert "TestClass" in result

    def test_format_multiple_elements(self) -> None:
        """Test formatting multiple elements."""
        adapter = LegacyFormatterAdapter("full")
        elements = [
            CodeElement(
                name="Package1",
                element_type=ELEMENT_TYPE_PACKAGE,
                start_line=1,
                end_line=1,
            ),
            Class(
                name="TestClass",
                element_type=ELEMENT_TYPE_CLASS,
                start_line=10,
                end_line=20,
            ),
            Function(
                name="testMethod",
                element_type=ELEMENT_TYPE_FUNCTION,
                start_line=15,
                end_line=18,
            ),
        ]
        result = adapter.format(elements)
        assert isinstance(result, str)
        assert "TestClass" in result
        assert "testMethod" in result

    def test_format_with_file_path(self) -> None:
        """Test formatting with file path."""
        adapter = LegacyFormatterAdapter("full")
        element = Class(
            name="TestClass",
            element_type=ELEMENT_TYPE_CLASS,
            start_line=10,
            end_line=20,
        )
        result = adapter.format([element])
        assert isinstance(result, str)


class TestLegacyFormatterAdapterConvertToLegacy:
    """Tests for LegacyFormatterAdapter._convert_to_legacy_format method."""

    def test_convert_empty_list(self) -> None:
        """Test converting empty element list."""
        adapter = LegacyFormatterAdapter("full")
        result = adapter._convert_to_legacy_format([])
        assert isinstance(result, dict)
        assert "file_path" in result
        assert "classes" in result
        assert "methods" in result
        assert "fields" in result
        assert "imports" in result
        assert "statistics" in result

    def test_convert_with_package(self) -> None:
        """Test converting with package element."""
        adapter = LegacyFormatterAdapter("full")
        element = CodeElement(
            name="com.example",
            element_type=ELEMENT_TYPE_PACKAGE,
            start_line=1,
            end_line=1,
        )
        result = adapter._convert_to_legacy_format([element])
        assert result["package"]["name"] == "com.example"

    def test_convert_statistics(self) -> None:
        """Test that statistics are calculated correctly."""
        adapter = LegacyFormatterAdapter("full")
        elements = [
            Class(
                name="Class1",
                element_type=ELEMENT_TYPE_CLASS,
                start_line=10,
                end_line=20,
            ),
            Function(
                name="method1",
                element_type=ELEMENT_TYPE_FUNCTION,
                start_line=15,
                end_line=18,
            ),
            Variable(
                name="field1",
                element_type=ELEMENT_TYPE_VARIABLE,
                start_line=12,
                end_line=12,
            ),
        ]
        result = adapter._convert_to_legacy_format(elements)
        assert result["statistics"]["class_count"] == 1
        assert result["statistics"]["method_count"] == 1
        assert result["statistics"]["field_count"] == 1


class TestLegacyFormatterAdapterConvertClass:
    """Tests for LegacyFormatterAdapter._convert_class_element method."""

    def test_convert_class_basic(self) -> None:
        """Test converting basic class element."""
        adapter = LegacyFormatterAdapter("full")
        element = Class(
            name="TestClass",
            element_type=ELEMENT_TYPE_CLASS,
            start_line=10,
            end_line=20,
        )
        result = adapter._convert_class_element(element)
        assert result["name"] == "TestClass"
        assert result["type"] == "class"
        assert result["visibility"] == "public"
        assert result["line_range"]["start"] == 10
        assert result["line_range"]["end"] == 20

    def test_convert_class_with_attributes(self) -> None:
        """Test converting class with custom attributes."""
        adapter = LegacyFormatterAdapter("full")
        element = Class(
            name="TestClass",
            element_type=ELEMENT_TYPE_CLASS,
            start_line=10,
            end_line=20,
            class_type="interface",
            visibility="private",
            modifiers=["static", "final"],
        )
        result = adapter._convert_class_element(element)
        assert result["name"] == "TestClass"
        assert result["type"] == "interface"
        assert result["visibility"] == "private"
        assert result["modifiers"] == ["static", "final"]


class TestLegacyFormatterAdapterConvertMethod:
    """Tests for LegacyFormatterAdapter._convert_method_element method."""

    def test_convert_method_basic(self) -> None:
        """Test converting basic method element."""
        adapter = LegacyFormatterAdapter("full")
        element = Function(
            name="testMethod",
            element_type=ELEMENT_TYPE_FUNCTION,
            start_line=15,
            end_line=18,
        )
        result = adapter._convert_method_element(element)
        assert result["name"] == "testMethod"
        assert result["visibility"] == "public"
        assert result["return_type"] is None
        assert result["line_range"]["start"] == 15
        assert result["line_range"]["end"] == 18

    def test_convert_method_with_attributes(self) -> None:
        """Test converting method with custom attributes."""
        adapter = LegacyFormatterAdapter("full")
        element = Function(
            name="testMethod",
            element_type=ELEMENT_TYPE_FUNCTION,
            start_line=15,
            end_line=18,
            visibility="private",
            return_type="int",
            parameters=["param1", "param2"],
            is_constructor=True,
            is_static=True,
            modifiers=["synchronized"],
        )
        result = adapter._convert_method_element(element)
        assert result["name"] == "testMethod"
        assert result["visibility"] == "private"
        assert result["return_type"] == "int"
        assert result["parameters"] == ["param1", "param2"]
        assert result["is_constructor"] is True
        assert result["is_static"] is True
        assert result["modifiers"] == ["synchronized"]


class TestLegacyFormatterAdapterConvertField:
    """Tests for LegacyFormatterAdapter._convert_field_element method."""

    def test_convert_field_basic(self) -> None:
        """Test converting basic field element."""
        adapter = LegacyFormatterAdapter("full")
        element = Variable(
            name="testField",
            element_type=ELEMENT_TYPE_VARIABLE,
            start_line=12,
            end_line=12,
        )
        result = adapter._convert_field_element(element)
        assert result["name"] == "testField"
        assert result["type"] is None
        assert result["visibility"] == "private"
        assert result["line_range"]["start"] == 12
        assert result["line_range"]["end"] == 12

    def test_convert_field_with_attributes(self) -> None:
        """Test converting field with custom attributes."""
        adapter = LegacyFormatterAdapter("full")
        element = Variable(
            name="testField",
            element_type=ELEMENT_TYPE_VARIABLE,
            start_line=12,
            end_line=12,
            field_type="String",
            visibility="public",
            modifiers=["static", "final"],
        )
        result = adapter._convert_field_element(element)
        assert result["name"] == "testField"
        assert result["type"] == "String"
        assert result["visibility"] == "public"
        assert result["modifiers"] == ["static", "final"]


class TestLegacyFormatterAdapterConvertImport:
    """Tests for LegacyFormatterAdapter._convert_import_element method."""

    def test_convert_import_basic(self) -> None:
        """Test converting basic import element."""
        adapter = LegacyFormatterAdapter("full")
        element = Import(
            name="List",
            element_type=ELEMENT_TYPE_IMPORT,
            start_line=5,
            end_line=5,
            module_name="java.util",
            import_statement="import java.util.List",
        )
        result = adapter._convert_import_element(element)
        assert "import" in result["statement"]

    def test_convert_import_with_statement(self) -> None:
        """Test converting import with custom statement."""
        adapter = LegacyFormatterAdapter("full")
        element = Import(
            name="List",
            element_type=ELEMENT_TYPE_IMPORT,
            start_line=5,
            end_line=5,
            import_statement="from java.util import List",
        )
        result = adapter._convert_import_element(element)
        assert result["statement"] == "from java.util import List"


class TestLegacyFullFormatter:
    """Tests for LegacyFullFormatter class."""

    def test_init_default(self) -> None:
        """Test initialization with default parameters."""
        formatter = LegacyFullFormatter()
        assert formatter.format_type == "full"
        assert formatter.language == "java"

    def test_init_with_language(self) -> None:
        """Test initialization with custom language."""
        formatter = LegacyFullFormatter(language="python")
        assert formatter.language == "python"

    def test_get_format_name(self) -> None:
        """Test get_format_name method."""
        formatter = LegacyFullFormatter()
        assert formatter.get_format_name() == "full"


class TestLegacyCompactFormatter:
    """Tests for LegacyCompactFormatter class."""

    def test_init_default(self) -> None:
        """Test initialization with default parameters."""
        formatter = LegacyCompactFormatter()
        assert formatter.format_type == "compact"
        assert formatter.language == "java"

    def test_init_with_language(self) -> None:
        """Test initialization with custom language."""
        formatter = LegacyCompactFormatter(language="python")
        assert formatter.language == "python"

    def test_get_format_name(self) -> None:
        """Test get_format_name method."""
        formatter = LegacyCompactFormatter()
        assert formatter.get_format_name() == "compact"


class TestLegacyCsvFormatter:
    """Tests for LegacyCsvFormatter class."""

    def test_init_default(self) -> None:
        """Test initialization with default parameters."""
        formatter = LegacyCsvFormatter()
        assert formatter.format_type == "csv"
        assert formatter.language == "java"

    def test_init_with_language(self) -> None:
        """Test initialization with custom language."""
        formatter = LegacyCsvFormatter(language="python")
        assert formatter.language == "python"

    def test_get_format_name(self) -> None:
        """Test get_format_name method."""
        formatter = LegacyCsvFormatter()
        assert formatter.get_format_name() == "csv"


class TestLegacyFormatterAdapterEdgeCases:
    """Tests for edge cases in LegacyFormatterAdapter."""

    def test_format_with_no_classes_creates_default(self) -> None:
        """Test that default class is created when no classes present."""
        adapter = LegacyFormatterAdapter("full")
        elements = [
            Function(
                name="method1",
                element_type=ELEMENT_TYPE_FUNCTION,
                start_line=15,
                end_line=18,
            ),
        ]
        legacy_data = adapter._convert_to_legacy_format(elements)
        assert len(legacy_data["classes"]) > 0
        assert legacy_data["classes"][0]["name"] == "Unknown"

    def test_format_with_only_classes(self) -> None:
        """Test formatting with only class elements."""
        adapter = LegacyFormatterAdapter("full")
        elements = [
            Class(
                name="Class1",
                element_type=ELEMENT_TYPE_CLASS,
                start_line=10,
                end_line=20,
            ),
            Class(
                name="Class2",
                element_type=ELEMENT_TYPE_CLASS,
                start_line=25,
                end_line=35,
            ),
        ]
        result = adapter.format(elements)
        assert isinstance(result, str)

    def test_format_preserves_unix_line_endings(self) -> None:
        """Test that Unix line endings are preserved."""
        adapter = LegacyFormatterAdapter("full")
        element = Class(
            name="TestClass",
            element_type=ELEMENT_TYPE_CLASS,
            start_line=10,
            end_line=20,
        )
        result = adapter.format([element])
        # Check that Windows line endings are converted to Unix
        assert "\r\n" not in result
        assert "\r" not in result
