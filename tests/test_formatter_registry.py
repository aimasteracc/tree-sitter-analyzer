#!/usr/bin/env python3
"""
Tests for Formatter Registry System

Tests for the dynamic formatter registration and management system,
including IFormatter interface, FormatterRegistry, and built-in formatters.
"""

import json

import pytest

from tree_sitter_analyzer.formatters.formatter_registry import (
    CompactFormatter,
    CsvFormatter,
    FormatterRegistry,
    FullFormatter,
    IFormatter,
    JsonFormatter,
)
from tree_sitter_analyzer.formatters.legacy_formatter_adapters import (
    LegacyCompactFormatter,
    LegacyCsvFormatter,
    LegacyFullFormatter,
)
from tree_sitter_analyzer.models import (
    Class,
    CodeElement,
    Function,
    MarkupElement,
    StyleElement,
    Variable,
)


class TestIFormatterInterface:
    """Test IFormatter interface and contract"""

    def test_iformatter_is_abstract(self):
        """Test that IFormatter cannot be instantiated directly"""
        with pytest.raises(TypeError):
            IFormatter()

    def test_iformatter_subclass_requirements(self):
        """Test that IFormatter subclasses must implement required methods"""

        class IncompleteFormatter(IFormatter):
            pass

        with pytest.raises(TypeError):
            IncompleteFormatter()

    def test_valid_iformatter_implementation(self):
        """Test valid IFormatter implementation"""

        class TestFormatter(IFormatter):
            @staticmethod
            def get_format_name() -> str:
                return "test"

            def format(self, elements: list[CodeElement]) -> str:
                return "test output"

        formatter = TestFormatter()
        assert formatter.get_format_name() == "test"
        assert formatter.format([]) == "test output"


class TestFormatterRegistry:
    """Test FormatterRegistry functionality"""

    def setup_method(self):
        """Setup for each test method"""
        # Clear registry before each test
        FormatterRegistry.clear_registry()

    def teardown_method(self):
        """Cleanup after each test method"""
        # Restore built-in formatters
        from tree_sitter_analyzer.formatters.formatter_registry import (
            register_builtin_formatters,
        )

        FormatterRegistry.clear_registry()
        register_builtin_formatters()

    def test_register_formatter(self):
        """Test formatter registration"""

        class CustomFormatter(IFormatter):
            @staticmethod
            def get_format_name() -> str:
                return "custom"

            def format(self, elements: list[CodeElement]) -> str:
                return "custom format"

        FormatterRegistry.register_formatter(CustomFormatter)

        assert "custom" in FormatterRegistry.get_available_formats()
        assert FormatterRegistry.is_format_supported("custom")

    def test_register_invalid_formatter(self):
        """Test registration of invalid formatter"""

        class NotAFormatter:
            pass

        with pytest.raises(ValueError, match="must implement IFormatter interface"):
            FormatterRegistry.register_formatter(NotAFormatter)

    def test_register_formatter_without_name(self):
        """Test registration of formatter without format name"""

        class NoNameFormatter(IFormatter):
            @staticmethod
            def get_format_name() -> str:
                return ""

            def format(self, elements: list[CodeElement]) -> str:
                return "output"

        with pytest.raises(ValueError, match="must provide a non-empty format name"):
            FormatterRegistry.register_formatter(NoNameFormatter)

    def test_get_formatter(self):
        """Test getting formatter instance"""

        class TestFormatter(IFormatter):
            @staticmethod
            def get_format_name() -> str:
                return "test"

            def format(self, elements: list[CodeElement]) -> str:
                return "test output"

        FormatterRegistry.register_formatter(TestFormatter)

        formatter = FormatterRegistry.get_formatter("test")
        assert isinstance(formatter, TestFormatter)
        assert formatter.format([]) == "test output"

    def test_get_unsupported_formatter(self):
        """Test getting unsupported formatter"""
        with pytest.raises(ValueError, match="Unsupported format: nonexistent"):
            FormatterRegistry.get_formatter("nonexistent")

    def test_get_available_formats(self):
        """Test getting available formats"""

        class Format1(IFormatter):
            @staticmethod
            def get_format_name() -> str:
                return "format1"

            def format(self, elements: list[CodeElement]) -> str:
                return "output1"

        class Format2(IFormatter):
            @staticmethod
            def get_format_name() -> str:
                return "format2"

            def format(self, elements: list[CodeElement]) -> str:
                return "output2"

        FormatterRegistry.register_formatter(Format1)
        FormatterRegistry.register_formatter(Format2)

        formats = FormatterRegistry.get_available_formats()
        assert "format1" in formats
        assert "format2" in formats

    def test_is_format_supported(self):
        """Test format support checking"""

        class SupportedFormatter(IFormatter):
            @staticmethod
            def get_format_name() -> str:
                return "supported"

            def format(self, elements: list[CodeElement]) -> str:
                return "output"

        FormatterRegistry.register_formatter(SupportedFormatter)

        assert FormatterRegistry.is_format_supported("supported") is True
        assert FormatterRegistry.is_format_supported("unsupported") is False

    def test_unregister_formatter(self):
        """Test formatter unregistration"""

        class TempFormatter(IFormatter):
            @staticmethod
            def get_format_name() -> str:
                return "temp"

            def format(self, elements: list[CodeElement]) -> str:
                return "temp output"

        FormatterRegistry.register_formatter(TempFormatter)
        assert FormatterRegistry.is_format_supported("temp")

        result = FormatterRegistry.unregister_formatter("temp")
        assert result is True
        assert not FormatterRegistry.is_format_supported("temp")

    def test_unregister_nonexistent_formatter(self):
        """Test unregistering nonexistent formatter"""
        result = FormatterRegistry.unregister_formatter("nonexistent")
        assert result is False

    def test_clear_registry(self):
        """Test clearing registry"""

        class TestFormatter(IFormatter):
            @staticmethod
            def get_format_name() -> str:
                return "test"

            def format(self, elements: list[CodeElement]) -> str:
                return "output"

        FormatterRegistry.register_formatter(TestFormatter)
        assert len(FormatterRegistry.get_available_formats()) > 0

        FormatterRegistry.clear_registry()
        assert len(FormatterRegistry.get_available_formats()) == 0

    def test_formatter_override_warning(self, caplog):
        """Test warning when overriding existing formatter"""
        import logging

        # Set logging level to capture warnings for the specific logger
        logger = logging.getLogger("tree_sitter_analyzer.formatters.formatter_registry")
        caplog.set_level(logging.WARNING, logger=logger.name)

        class Formatter1(IFormatter):
            @staticmethod
            def get_format_name() -> str:
                return "same"

            def format(self, elements: list[CodeElement]) -> str:
                return "output1"

        class Formatter2(IFormatter):
            @staticmethod
            def get_format_name() -> str:
                return "same"

            def format(self, elements: list[CodeElement]) -> str:
                return "output2"

        FormatterRegistry.register_formatter(Formatter1)

        # Clear any existing logs
        caplog.clear()

        # This should trigger the warning
        FormatterRegistry.register_formatter(Formatter2)

        # Check that warning was logged
        warning_found = any(
            "Overriding existing formatter" in record.message
            for record in caplog.records
            if record.levelno >= logging.WARNING
        )
        assert (
            warning_found
        ), f"Warning not found in logs. Captured records: {[r.message for r in caplog.records]}"


class TestBuiltinFormatters:
    """Test built-in formatter implementations"""

    def setup_method(self):
        """Setup test data"""
        self.test_elements = [
            Function(
                name="test_function",
                start_line=1,
                end_line=5,
                language="python",
                parameters=["arg1", "arg2"],
                return_type="str",
                visibility="public",
            ),
            Class(
                name="TestClass",
                start_line=10,
                end_line=20,
                language="python",
                visibility="public",
            ),
            Variable(
                name="test_var",
                start_line=25,
                end_line=25,
                language="python",
                variable_type="int",
                visibility="private",
            ),
        ]

    def test_json_formatter(self):
        """Test JsonFormatter"""
        formatter = JsonFormatter()
        assert formatter.get_format_name() == "json"

        result = formatter.format(self.test_elements)

        # Parse JSON to verify it's valid
        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert len(parsed) == 3

        # Check first element (function)
        func_data = parsed[0]
        assert func_data["name"] == "test_function"
        assert func_data["type"] == "function"
        assert func_data["parameters"] == ["arg1", "arg2"]
        assert func_data["return_type"] == "str"
        assert func_data["visibility"] == "public"

    def test_json_formatter_empty_list(self):
        """Test JsonFormatter with empty list"""
        formatter = JsonFormatter()
        result = formatter.format([])

        parsed = json.loads(result)
        assert parsed == []

    def test_csv_formatter(self):
        """Test CsvFormatter"""
        formatter = CsvFormatter()
        assert formatter.get_format_name() == "csv"

        result = formatter.format(self.test_elements)
        lines = result.split("\n")

        # Check header
        assert (
            "Type,Name,Start Line,End Line,Language,Visibility,Parameters,Return Type,Modifiers"
            in lines[0]
        )

        # Check data rows
        assert len(lines) == 4  # header + 3 data rows
        assert "function,test_function,1,5,python,public" in lines[1]
        assert "class,TestClass,10,20,python,public" in lines[2]
        assert "variable,test_var,25,25,python,private" in lines[3]

    def test_csv_formatter_empty_list(self):
        """Test CsvFormatter with empty list"""
        formatter = CsvFormatter()
        result = formatter.format([])

        # Should only contain header
        lines = result.split("\n")
        assert len(lines) == 1
        assert "Type,Name,Start Line,End Line" in lines[0]

    def test_full_formatter(self):
        """Test FullFormatter"""
        formatter = FullFormatter()
        assert formatter.get_format_name() == "full"

        result = formatter.format(self.test_elements)

        # Check structure
        assert "CODE STRUCTURE ANALYSIS" in result
        assert "FUNCTIONS (1)" in result
        assert "CLASSS (1)" in result  # Note: plural form adds 'S'
        assert "VARIABLES (1)" in result
        assert "test_function" in result
        assert "TestClass" in result
        assert "test_var" in result
        assert "Lines: 1-5" in result
        assert "Parameters: arg1, arg2" in result

    def test_full_formatter_empty_list(self):
        """Test FullFormatter with empty list"""
        formatter = FullFormatter()
        result = formatter.format([])

        assert result == "No elements found."

    def test_compact_formatter(self):
        """Test CompactFormatter"""
        formatter = CompactFormatter()
        assert formatter.get_format_name() == "compact"

        result = formatter.format(self.test_elements)

        # Check structure
        assert "CODE ELEMENTS" in result
        assert "+ test_function (function) [1-5]" in result
        assert "+ TestClass (class) [10-20]" in result
        assert "- test_var (variable) [25-25]" in result

    def test_compact_formatter_visibility_symbols(self):
        """Test CompactFormatter visibility symbols"""
        formatter = CompactFormatter()

        elements = [
            Function(name="public_func", start_line=1, end_line=1, visibility="public"),
            Function(
                name="private_func", start_line=2, end_line=2, visibility="private"
            ),
            Function(
                name="protected_func", start_line=3, end_line=3, visibility="protected"
            ),
            Function(
                name="package_func", start_line=4, end_line=4, visibility="package"
            ),
            Function(
                name="unknown_func", start_line=5, end_line=5, visibility="unknown"
            ),
        ]

        result = formatter.format(elements)

        assert "+ public_func" in result
        assert "- private_func" in result
        assert "# protected_func" in result
        assert "~ package_func" in result
        assert "? unknown_func" in result

    def test_compact_formatter_empty_list(self):
        """Test CompactFormatter with empty list"""
        formatter = CompactFormatter()
        result = formatter.format([])

        assert result == "No elements found."


class TestFormatterWithHtmlElements:
    """Test formatters with HTML/CSS elements"""

    def setup_method(self):
        """Setup HTML/CSS test data"""
        self.html_elements = [
            MarkupElement(
                name="div",
                start_line=1,
                end_line=5,
                tag_name="div",
                attributes={"class": "container", "id": "main"},
                element_class="structure",
                language="html",
            ),
            StyleElement(
                name=".container",
                start_line=10,
                end_line=15,
                selector=".container",
                properties={"width": "100%", "margin": "0 auto"},
                element_class="layout",
                language="css",
            ),
        ]

    def test_json_formatter_with_html_elements(self):
        """Test JsonFormatter with HTML elements"""
        formatter = JsonFormatter()
        result = formatter.format(self.html_elements)

        parsed = json.loads(result)
        assert len(parsed) == 2

        # Check MarkupElement
        markup_data = parsed[0]
        assert markup_data["name"] == "div"
        assert markup_data["tag_name"] == "div"
        assert markup_data["element_class"] == "structure"

        # Check StyleElement
        style_data = parsed[1]
        assert style_data["name"] == ".container"
        assert style_data["selector"] == ".container"
        assert style_data["element_class"] == "layout"

    def test_csv_formatter_with_html_elements(self):
        """Test CsvFormatter with HTML elements"""
        formatter = CsvFormatter()
        result = formatter.format(self.html_elements)

        lines = result.split("\n")
        assert len(lines) == 3  # header + 2 data rows
        assert "html_element,div,1,5,html" in lines[1]
        assert "css_rule,.container,10,15,css" in lines[2]

    def test_full_formatter_with_html_elements(self):
        """Test FullFormatter with HTML elements"""
        formatter = FullFormatter()
        result = formatter.format(self.html_elements)

        assert "HTML_ELEMENTS (1)" in result
        assert "CSS_RULES (1)" in result
        assert "div" in result
        assert ".container" in result

    def test_compact_formatter_with_html_elements(self):
        """Test CompactFormatter with HTML elements"""
        formatter = CompactFormatter()
        result = formatter.format(self.html_elements)

        assert "? div (html_element) [1-5]" in result
        assert "? .container (css_rule) [10-15]" in result


class TestFormatterRegistryIntegration:
    """Test FormatterRegistry integration with built-in formatters"""

    def test_builtin_formatters_registered(self):
        """Test that built-in formatters are automatically registered"""
        available_formats = FormatterRegistry.get_available_formats()

        assert "json" in available_formats
        assert "csv" in available_formats
        assert "full" in available_formats
        assert "compact" in available_formats

    def test_get_builtin_formatters(self):
        """Test getting built-in formatter instances"""
        json_formatter = FormatterRegistry.get_formatter("json")
        csv_formatter = FormatterRegistry.get_formatter("csv")
        full_formatter = FormatterRegistry.get_formatter("full")
        compact_formatter = FormatterRegistry.get_formatter("compact")

        assert isinstance(json_formatter, JsonFormatter)
        # CSV, Full, and Compact formatters are now legacy adapters for v1.6.1.4 compatibility
        assert isinstance(csv_formatter, LegacyCsvFormatter)
        assert isinstance(full_formatter, LegacyFullFormatter)
        assert isinstance(compact_formatter, LegacyCompactFormatter)

    def test_formatter_instances_are_new(self):
        """Test that each get_formatter call returns a new instance"""
        formatter1 = FormatterRegistry.get_formatter("json")
        formatter2 = FormatterRegistry.get_formatter("json")

        assert formatter1 is not formatter2
        assert isinstance(formatter1, type(formatter2))


class TestFormatterErrorHandling:
    """Test error handling in formatters"""

    def test_formatter_with_malformed_elements(self):
        """Test formatters with malformed elements"""

        # Create element with missing attributes
        class MalformedElement(CodeElement):
            def __init__(self):
                super().__init__(name="malformed", start_line=1, end_line=1)
                # Don't set some expected attributes

        malformed = MalformedElement()

        # Test that formatters handle missing attributes gracefully
        json_formatter = JsonFormatter()
        result = json_formatter.format([malformed])
        parsed = json.loads(result)
        assert len(parsed) == 1

        csv_formatter = CsvFormatter()
        result = csv_formatter.format([malformed])
        assert "malformed" in result

        full_formatter = FullFormatter()
        result = full_formatter.format([malformed])
        assert "malformed" in result

        compact_formatter = CompactFormatter()
        result = compact_formatter.format([malformed])
        assert "malformed" in result

    def test_formatter_with_none_values(self):
        """Test formatters with None values in elements"""
        element = Function(
            name="test_func",
            start_line=1,
            end_line=1,
            return_type=None,  # Explicitly None
            parameters=None,  # Explicitly None
        )

        json_formatter = JsonFormatter()
        result = json_formatter.format([element])
        parsed = json.loads(result)

        # Should handle None values gracefully
        assert parsed[0]["return_type"] is None

    def test_formatter_with_unicode_content(self):
        """Test formatters with Unicode content"""
        element = Function(
            name="テスト関数",  # Japanese
            start_line=1,
            end_line=1,
            language="python",
        )

        json_formatter = JsonFormatter()
        result = json_formatter.format([element])
        parsed = json.loads(result)
        assert parsed[0]["name"] == "テスト関数"

        csv_formatter = CsvFormatter()
        result = csv_formatter.format([element])
        assert "テスト関数" in result
