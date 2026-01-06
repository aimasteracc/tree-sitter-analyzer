#!/usr/bin/env python3
"""
Unit tests for tree_sitter_analyzer.formatters.language_formatter_factory module.

This module tests LanguageFormatterFactory class.
"""

import pytest

from tree_sitter_analyzer.formatters.base_formatter import BaseFormatter
from tree_sitter_analyzer.formatters.language_formatter_factory import (
    LanguageFormatterFactory,
    create_language_formatter,
)


class TestLanguageFormatterFactoryCreateFormatter:
    """Tests for LanguageFormatterFactory.create_formatter method."""

    def test_create_formatter_python(self) -> None:
        """Test creating Python formatter."""
        formatter = LanguageFormatterFactory.create_formatter("python")
        assert isinstance(formatter, BaseFormatter)

    def test_create_formatter_java(self) -> None:
        """Test creating Java formatter."""
        formatter = LanguageFormatterFactory.create_formatter("java")
        assert isinstance(formatter, BaseFormatter)

    def test_create_formatter_kotlin(self) -> None:
        """Test creating Kotlin formatter."""
        formatter = LanguageFormatterFactory.create_formatter("kotlin")
        assert isinstance(formatter, BaseFormatter)

    def test_create_formatter_rust(self) -> None:
        """Test creating Rust formatter."""
        formatter = LanguageFormatterFactory.create_formatter("rust")
        assert isinstance(formatter, BaseFormatter)

    def test_create_formatter_go(self) -> None:
        """Test creating Go formatter."""
        formatter = LanguageFormatterFactory.create_formatter("go")
        assert isinstance(formatter, BaseFormatter)

    def test_create_formatter_case_insensitive(self) -> None:
        """Test that language lookup is case insensitive."""
        formatter_lower = LanguageFormatterFactory.create_formatter("python")
        formatter_upper = LanguageFormatterFactory.create_formatter("PYTHON")
        formatter_mixed = LanguageFormatterFactory.create_formatter("Python")

        assert type(formatter_lower) is type(formatter_upper) and type(
            formatter_upper
        ) is type(formatter_mixed)

    def test_create_formatter_with_alias(self) -> None:
        """Test creating formatter with language alias."""
        formatter = LanguageFormatterFactory.create_formatter("py")
        assert isinstance(formatter, BaseFormatter)

    def test_create_formatter_unsupported(self) -> None:
        """Test creating formatter for unsupported language."""
        with pytest.raises(ValueError, match="Unsupported language"):
            LanguageFormatterFactory.create_formatter("unsupported_lang")


class TestLanguageFormatterFactoryRegisterFormatter:
    """Tests for LanguageFormatterFactory.register_formatter method."""

    def test_register_formatter(self) -> None:
        """Test registering a new formatter."""

        # Create a mock formatter class
        class MockFormatter(BaseFormatter):
            def __init__(self) -> None:
                self.language = "mock"

            def format_summary(self, elements: list, metadata: dict) -> str:
                return "summary"

            def format_structure(self, elements: list, metadata: dict) -> str:
                return "structure"

            def format_advanced(self, elements: list, metadata: dict) -> str:
                return "advanced"

            def format_table(
                self, elements: list, metadata: dict, format_type: str = "full"
            ) -> str:
                return "table"

        # Register formatter
        LanguageFormatterFactory.register_formatter("mock", MockFormatter)

        # Verify it was registered
        assert LanguageFormatterFactory.supports_language("mock")

        # Clean up
        del LanguageFormatterFactory._formatters["mock"]

    def test_register_formatter_overwrite(self) -> None:
        """Test that registering overwrites existing formatter."""

        class MockFormatter(BaseFormatter):
            def __init__(self) -> None:
                self.language = "python_new"

            def format_summary(self, elements: list, metadata: dict) -> str:
                return "summary"

            def format_structure(self, elements: list, metadata: dict) -> str:
                return "structure"

            def format_advanced(self, elements: list, metadata: dict) -> str:
                return "advanced"

            def format_table(
                self, elements: list, metadata: dict, format_type: str = "full"
            ) -> str:
                return "table"

        # Register over Python formatter
        LanguageFormatterFactory.register_formatter("python", MockFormatter)

        # Verify it was registered
        formatter = LanguageFormatterFactory.create_formatter("python")
        assert isinstance(formatter, MockFormatter)

        # Restore original
        from tree_sitter_analyzer.formatters.python_formatter import (
            PythonTableFormatter,
        )

        LanguageFormatterFactory.register_formatter("python", PythonTableFormatter)


class TestLanguageFormatterFactoryGetSupportedLanguages:
    """Tests for LanguageFormatterFactory.get_supported_languages method."""

    def test_get_supported_languages(self) -> None:
        """Test getting list of supported languages."""
        languages = LanguageFormatterFactory.get_supported_languages()

        assert isinstance(languages, list)
        assert len(languages) > 0
        assert all(isinstance(lang, str) for lang in languages)

    def test_get_supported_languages_includes_common(self) -> None:
        """Test that common languages are in supported list."""
        languages = LanguageFormatterFactory.get_supported_languages()

        assert "python" in languages
        assert "java" in languages
        assert "kotlin" in languages
        assert "rust" in languages
        assert "go" in languages
        assert "javascript" in languages
        assert "typescript" in languages

    def test_get_supported_languages_includes_aliases(self) -> None:
        """Test that language aliases are in supported list."""
        languages = LanguageFormatterFactory.get_supported_languages()

        assert "py" in languages
        assert "js" in languages
        assert "ts" in languages
        assert "kt" in languages
        assert "rs" in languages


class TestLanguageFormatterFactorySupportsLanguage:
    """Tests for LanguageFormatterFactory.supports_language method."""

    def test_supports_language_true(self) -> None:
        """Test supports_language returns True for supported language."""
        assert LanguageFormatterFactory.supports_language("python") is True

    def test_supports_language_false(self) -> None:
        """Test supports_language returns False for unsupported language."""
        assert LanguageFormatterFactory.supports_language("unsupported") is False

    def test_supports_language_case_insensitive(self) -> None:
        """Test that supports_language is case insensitive."""
        assert LanguageFormatterFactory.supports_language("PYTHON") is True
        assert LanguageFormatterFactory.supports_language("Python") is True

    def test_supports_language_with_alias(self) -> None:
        """Test supports_language with language alias."""
        assert LanguageFormatterFactory.supports_language("py") is True


class TestCreateLanguageFormatter:
    """Tests for create_language_formatter function."""

    def test_create_language_formatter_supported(self) -> None:
        """Test creating formatter for supported language."""
        formatter = create_language_formatter("python")
        assert formatter is not None
        assert isinstance(formatter, BaseFormatter)

    def test_create_language_formatter_unsupported(self) -> None:
        """Test creating formatter for unsupported language."""
        formatter = create_language_formatter("unsupported_lang")
        assert formatter is None

    def test_create_language_formatter_with_alias(self) -> None:
        """Test creating formatter with language alias."""
        formatter = create_language_formatter("py")
        assert formatter is not None
        assert isinstance(formatter, BaseFormatter)


class TestLanguageFormatterFactoryCFamily:
    """Tests for C family languages."""

    def test_create_formatter_c(self) -> None:
        """Test creating C formatter."""
        formatter = LanguageFormatterFactory.create_formatter("c")
        assert isinstance(formatter, BaseFormatter)

    def test_create_formatter_h(self) -> None:
        """Test creating C header formatter."""
        formatter = LanguageFormatterFactory.create_formatter("h")
        assert isinstance(formatter, BaseFormatter)

    def test_create_formatter_cpp(self) -> None:
        """Test creating C++ formatter."""
        formatter = LanguageFormatterFactory.create_formatter("cpp")
        assert isinstance(formatter, BaseFormatter)

    def test_create_formatter_cpp_variants(self) -> None:
        """Test creating C++ formatter with various extensions."""
        for ext in ["cxx", "cc", "hpp", "hxx", "h++", "c++"]:
            formatter = LanguageFormatterFactory.create_formatter(ext)
            assert isinstance(formatter, BaseFormatter)


class TestLanguageFormatterFactoryWebLanguages:
    """Tests for web languages."""

    def test_create_formatter_html(self) -> None:
        """Test creating HTML formatter."""
        formatter = LanguageFormatterFactory.create_formatter("html")
        assert isinstance(formatter, BaseFormatter)

    def test_create_formatter_css(self) -> None:
        """Test creating CSS formatter."""
        formatter = LanguageFormatterFactory.create_formatter("css")
        assert isinstance(formatter, BaseFormatter)

    def test_create_formatter_markdown(self) -> None:
        """Test creating Markdown formatter."""
        formatter = LanguageFormatterFactory.create_formatter("markdown")
        assert isinstance(formatter, BaseFormatter)

    def test_create_formatter_markdown_alias(self) -> None:
        """Test creating Markdown formatter with alias."""
        formatter = LanguageFormatterFactory.create_formatter("md")
        assert isinstance(formatter, BaseFormatter)


class TestLanguageFormatterFactoryOtherLanguages:
    """Tests for other languages."""

    def test_create_formatter_sql(self) -> None:
        """Test creating SQL formatter."""
        formatter = LanguageFormatterFactory.create_formatter("sql")
        assert isinstance(formatter, BaseFormatter)

    def test_create_formatter_csharp(self) -> None:
        """Test creating C# formatter."""
        formatter = LanguageFormatterFactory.create_formatter("csharp")
        assert isinstance(formatter, BaseFormatter)

    def test_create_formatter_csharp_alias(self) -> None:
        """Test creating C# formatter with alias."""
        formatter = LanguageFormatterFactory.create_formatter("cs")
        assert isinstance(formatter, BaseFormatter)

    def test_create_formatter_php(self) -> None:
        """Test creating PHP formatter."""
        formatter = LanguageFormatterFactory.create_formatter("php")
        assert isinstance(formatter, BaseFormatter)

    def test_create_formatter_ruby(self) -> None:
        """Test creating Ruby formatter."""
        formatter = LanguageFormatterFactory.create_formatter("ruby")
        assert isinstance(formatter, BaseFormatter)

    def test_create_formatter_ruby_alias(self) -> None:
        """Test creating Ruby formatter with alias."""
        formatter = LanguageFormatterFactory.create_formatter("rb")
        assert isinstance(formatter, BaseFormatter)

    def test_create_formatter_yaml(self) -> None:
        """Test creating YAML formatter."""
        formatter = LanguageFormatterFactory.create_formatter("yaml")
        assert isinstance(formatter, BaseFormatter)

    def test_create_formatter_yaml_alias(self) -> None:
        """Test creating YAML formatter with alias."""
        formatter = LanguageFormatterFactory.create_formatter("yml")
        assert isinstance(formatter, BaseFormatter)
