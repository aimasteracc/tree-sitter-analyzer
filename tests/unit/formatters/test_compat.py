#!/usr/bin/env python3
"""
Tests for Backward Compatibility Module (compat.py)

Tests that all deprecated wrapper functions and classes emit DeprecationWarning
and correctly delegate to FormatterRegistry.
"""

import pytest

from tree_sitter_analyzer.formatters.compat import (
    FormatterSelector,
    LanguageFormatterFactory,
    TableFormatterFactory,
    create_table_formatter,
)

# ---------------------------------------------------------------------------
# Tests for create_table_formatter
# ---------------------------------------------------------------------------


class TestCreateTableFormatter:
    """Tests for the deprecated create_table_formatter function."""

    def test_emits_deprecation_warning_and_returns_formatter(self):
        """create_table_formatter should emit a DeprecationWarning and return a formatter."""
        with pytest.warns(DeprecationWarning, match="create_table_formatter is deprecated"):
            formatter = create_table_formatter("full", "java")
        assert formatter is not None

    def test_with_include_javadoc(self):
        """create_table_formatter should accept the include_javadoc parameter."""
        with pytest.warns(DeprecationWarning):
            formatter = create_table_formatter("full", "java", include_javadoc=True)
        assert formatter is not None

    def test_default_language_is_java(self):
        """create_table_formatter should default language to java."""
        with pytest.warns(DeprecationWarning):
            formatter = create_table_formatter("full")
        assert formatter is not None


# ---------------------------------------------------------------------------
# Tests for TableFormatterFactory
# ---------------------------------------------------------------------------


class TestTableFormatterFactory:
    """Tests for the deprecated TableFormatterFactory class."""

    def test_create_formatter_emits_warning_and_returns_instance(self):
        """create_formatter should emit DeprecationWarning and return a formatter."""
        with pytest.warns(DeprecationWarning, match="TableFormatterFactory.create_formatter"):
            formatter = TableFormatterFactory.create_formatter("java", "full")
        assert formatter is not None

    def test_register_formatter_emits_warning(self):
        """register_formatter should emit DeprecationWarning."""

        class DummyFormatter:
            pass

        with pytest.warns(DeprecationWarning, match="TableFormatterFactory.register_formatter"):
            TableFormatterFactory.register_formatter("dummy_test_lang", DummyFormatter)

    def test_get_supported_languages_emits_warning_and_returns_list(self):
        """get_supported_languages should emit DeprecationWarning and return languages."""
        with pytest.warns(DeprecationWarning, match="TableFormatterFactory.get_supported_languages"):
            languages = TableFormatterFactory.get_supported_languages()
        assert isinstance(languages, list)
        assert len(languages) > 0
        assert "java" in languages


# ---------------------------------------------------------------------------
# Tests for LanguageFormatterFactory
# ---------------------------------------------------------------------------


class TestLanguageFormatterFactory:
    """Tests for the deprecated LanguageFormatterFactory class."""

    def test_create_formatter_emits_warning_and_returns_instance(self):
        """create_formatter should emit DeprecationWarning and return a formatter."""
        with pytest.warns(DeprecationWarning, match="LanguageFormatterFactory.create_formatter"):
            formatter = LanguageFormatterFactory.create_formatter("python")
        assert formatter is not None

    def test_supports_language_true_for_known(self):
        """supports_language should emit DeprecationWarning and return True for known languages."""
        with pytest.warns(DeprecationWarning, match="LanguageFormatterFactory.supports_language"):
            result = LanguageFormatterFactory.supports_language("java")
        assert result is True

    def test_supports_language_false_for_unknown(self):
        """supports_language should return False for an unregistered language."""
        with pytest.warns(DeprecationWarning):
            result = LanguageFormatterFactory.supports_language("unknown_lang_xyz")
        assert result is False

    def test_get_supported_languages_emits_warning_and_returns_list(self):
        """get_supported_languages should emit DeprecationWarning and return a list."""
        with pytest.warns(DeprecationWarning, match="LanguageFormatterFactory.get_supported_languages"):
            languages = LanguageFormatterFactory.get_supported_languages()
        assert isinstance(languages, list)


# ---------------------------------------------------------------------------
# Tests for FormatterSelector
# ---------------------------------------------------------------------------


class TestFormatterSelector:
    """Tests for the deprecated FormatterSelector class."""

    def test_get_formatter_emits_warning_and_returns_instance(self):
        """get_formatter should emit DeprecationWarning and return a formatter."""
        with pytest.warns(DeprecationWarning, match="FormatterSelector.get_formatter"):
            formatter = FormatterSelector.get_formatter("java", "full")
        assert formatter is not None

    def test_is_legacy_formatter_emits_warning(self):
        """is_legacy_formatter should emit DeprecationWarning."""
        with pytest.warns(DeprecationWarning, match="FormatterSelector.is_legacy_formatter"):
            FormatterSelector.is_legacy_formatter("java", "full")

    def test_is_legacy_formatter_always_returns_true(self):
        """is_legacy_formatter should always return True regardless of arguments."""
        with pytest.warns(DeprecationWarning):
            assert FormatterSelector.is_legacy_formatter("java", "full") is True
        with pytest.warns(DeprecationWarning):
            assert FormatterSelector.is_legacy_formatter("python", "compact") is True
        with pytest.warns(DeprecationWarning):
            assert FormatterSelector.is_legacy_formatter("unknown_lang_xyz", "csv") is True

    def test_get_supported_languages_emits_warning_and_returns_known(self):
        """get_supported_languages should emit DeprecationWarning and include known languages."""
        with pytest.warns(DeprecationWarning, match="FormatterSelector.get_supported_languages"):
            languages = FormatterSelector.get_supported_languages()
        assert isinstance(languages, list)
        assert "java" in languages
        assert "python" in languages
