#!/usr/bin/env python3
"""
Unit tests for tree_sitter_analyzer.formatters.formatter_selector module.

This module tests FormatterSelector class.
"""

from unittest.mock import Mock, patch

from tree_sitter_analyzer.formatters.formatter_selector import FormatterSelector


class TestFormatterSelectorGetFormatter:
    """Tests for FormatterSelector.get_formatter method."""

    @patch("tree_sitter_analyzer.formatters.formatter_selector.get_formatter_strategy")
    @patch(
        "tree_sitter_analyzer.formatters.formatter_selector.create_language_formatter"
    )
    def test_get_formatter_new_strategy(
        self, mock_create_lang_formatter, mock_get_strategy
    ) -> None:
        """Test getting formatter with new strategy."""
        mock_get_strategy.return_value = "new"
        mock_formatter = Mock()
        mock_create_lang_formatter.return_value = mock_formatter

        result = FormatterSelector.get_formatter("kotlin", "table")

        assert result == mock_formatter
        mock_get_strategy.assert_called_once_with("kotlin", "table")
        mock_create_lang_formatter.assert_called_once_with("kotlin")

    @patch("tree_sitter_analyzer.formatters.formatter_selector.get_formatter_strategy")
    @patch("tree_sitter_analyzer.formatters.formatter_selector.create_table_formatter")
    def test_get_formatter_legacy_strategy(
        self, mock_create_table_formatter, mock_get_strategy
    ) -> None:
        """Test getting formatter with legacy strategy."""
        mock_get_strategy.return_value = "legacy"
        mock_formatter = Mock()
        mock_create_table_formatter.return_value = mock_formatter

        result = FormatterSelector.get_formatter("java", "table")

        assert result == mock_formatter
        mock_get_strategy.assert_called_once_with("java", "table")
        mock_create_table_formatter.assert_called_once_with("table", "java", False)

    @patch("tree_sitter_analyzer.formatters.formatter_selector.get_formatter_strategy")
    @patch("tree_sitter_analyzer.formatters.formatter_selector.create_table_formatter")
    def test_get_formatter_with_include_javadoc(
        self, mock_create_table_formatter, mock_get_strategy
    ) -> None:
        """Test getting formatter with include_javadoc parameter."""
        mock_get_strategy.return_value = "legacy"
        mock_formatter = Mock()
        mock_create_table_formatter.return_value = mock_formatter

        result = FormatterSelector.get_formatter("java", "table", include_javadoc=True)

        assert result == mock_formatter
        mock_create_table_formatter.assert_called_once_with("table", "java", True)


class TestFormatterSelectorCreateNewFormatter:
    """Tests for FormatterSelector._create_new_formatter method."""

    @patch(
        "tree_sitter_analyzer.formatters.formatter_selector.create_language_formatter"
    )
    def test_create_new_formatter_success(self, mock_create_lang_formatter) -> None:
        """Test creating new formatter successfully."""
        mock_formatter = Mock()
        mock_formatter.format_type = None
        mock_create_lang_formatter.return_value = mock_formatter

        result = FormatterSelector._create_new_formatter("kotlin", "table")

        assert result == mock_formatter
        assert result.format_type == "table"
        mock_create_lang_formatter.assert_called_once_with("kotlin")

    @patch(
        "tree_sitter_analyzer.formatters.formatter_selector.create_language_formatter"
    )
    @patch("tree_sitter_analyzer.formatters.formatter_selector.create_table_formatter")
    def test_create_new_formatter_fallback(
        self, mock_create_table_formatter, mock_create_lang_formatter
    ) -> None:
        """Test creating new formatter falls back to legacy when None."""
        mock_create_lang_formatter.return_value = None
        mock_formatter = Mock()
        mock_create_table_formatter.return_value = mock_formatter

        result = FormatterSelector._create_new_formatter("unknown", "table")

        assert result == mock_formatter
        mock_create_lang_formatter.assert_called_once_with("unknown")
        mock_create_table_formatter.assert_called_once_with("table", "unknown", False)

    @patch(
        "tree_sitter_analyzer.formatters.formatter_selector.create_language_formatter"
    )
    def test_create_new_formatter_sets_format_type(
        self, mock_create_lang_formatter
    ) -> None:
        """Test that format_type is set on formatter."""
        mock_formatter = Mock()
        mock_formatter.format_type = None
        mock_create_lang_formatter.return_value = mock_formatter

        result = FormatterSelector._create_new_formatter("kotlin", "compact")

        assert result.format_type == "compact"

    @patch(
        "tree_sitter_analyzer.formatters.formatter_selector.create_language_formatter"
    )
    def test_create_new_formatter_without_format_type_attr(
        self, mock_create_lang_formatter
    ) -> None:
        """Test creating new formatter when formatter doesn't have format_type attr."""
        mock_formatter = Mock(spec=[])  # Mock without format_type attribute
        mock_create_lang_formatter.return_value = mock_formatter

        result = FormatterSelector._create_new_formatter("kotlin", "table")

        assert result == mock_formatter
        # Should not raise AttributeError


class TestFormatterSelectorCreateLegacyFormatter:
    """Tests for FormatterSelector._create_legacy_formatter method."""

    @patch("tree_sitter_analyzer.formatters.formatter_selector.create_table_formatter")
    def test_create_legacy_formatter(self, mock_create_table_formatter) -> None:
        """Test creating legacy formatter."""
        mock_formatter = Mock()
        mock_create_table_formatter.return_value = mock_formatter

        result = FormatterSelector._create_legacy_formatter("java", "table")

        assert result == mock_formatter
        mock_create_table_formatter.assert_called_once_with("table", "java", False)

    @patch("tree_sitter_analyzer.formatters.formatter_selector.create_table_formatter")
    def test_create_legacy_formatter_with_javadoc(
        self, mock_create_table_formatter
    ) -> None:
        """Test creating legacy formatter with include_javadoc."""
        mock_formatter = Mock()
        mock_create_table_formatter.return_value = mock_formatter

        result = FormatterSelector._create_legacy_formatter(
            "java", "table", include_javadoc=True
        )

        assert result == mock_formatter
        mock_create_table_formatter.assert_called_once_with("table", "java", True)


class TestFormatterSelectorIsLegacyFormatter:
    """Tests for FormatterSelector.is_legacy_formatter method."""

    @patch("tree_sitter_analyzer.formatters.formatter_selector.get_formatter_strategy")
    def test_is_legacy_formatter_true(self, mock_get_strategy) -> None:
        """Test is_legacy_formatter returns True for legacy strategy."""
        mock_get_strategy.return_value = "legacy"

        result = FormatterSelector.is_legacy_formatter("java", "table")

        assert result is True
        mock_get_strategy.assert_called_once_with("java", "table")

    @patch("tree_sitter_analyzer.formatters.formatter_selector.get_formatter_strategy")
    def test_is_legacy_formatter_false(self, mock_get_strategy) -> None:
        """Test is_legacy_formatter returns False for new strategy."""
        mock_get_strategy.return_value = "new"

        result = FormatterSelector.is_legacy_formatter("kotlin", "table")

        assert result is False
        mock_get_strategy.assert_called_once_with("kotlin", "table")


class TestFormatterSelectorGetSupportedLanguages:
    """Tests for FormatterSelector.get_supported_languages method."""

    def test_get_supported_languages(self) -> None:
        """Test getting list of supported languages."""
        languages = FormatterSelector.get_supported_languages()

        assert isinstance(languages, list)
        assert len(languages) > 0
        assert all(isinstance(lang, str) for lang in languages)
        # Check for some known languages
        assert "python" in languages
        assert "java" in languages
        assert "kotlin" in languages
        assert "rust" in languages
