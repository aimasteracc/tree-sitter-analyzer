#!/usr/bin/env python3
"""
Unit tests for tree_sitter_analyzer.formatters.formatter_config module.

This module tests formatter configuration and strategy selection.
"""

from tree_sitter_analyzer.formatters.formatter_config import (
    DEFAULT_STRATEGY,
    LANGUAGE_FORMATTER_CONFIG,
    get_formatter_strategy,
)


class TestFormatterConfigTypes:
    """Tests for type definitions."""

    def test_format_type_literal(self) -> None:
        """Test FormatType literal values."""
        expected_values = ["table", "compact", "full", "csv", "json"]
        # FormatType is a Literal, so we can't directly test its values
        # but we can test that the function accepts these values
        for fmt in expected_values:
            result = get_formatter_strategy("python", fmt)
            assert result in ["legacy", "new"]

    def test_formatter_strategy_literal(self) -> None:
        """Test FormatterStrategy literal values."""
        expected_values = ["legacy", "new"]
        # FormatterStrategy is a Literal, so we can't directly test its values
        # but we can test that the function returns these values
        for lang in ["python", "kotlin"]:
            result = get_formatter_strategy(lang, "table")
            assert result in expected_values


class TestLanguageFormatterConfig:
    """Tests for LANGUAGE_FORMATTER_CONFIG dictionary."""

    def test_config_structure(self) -> None:
        """Test that config has correct structure."""
        assert isinstance(LANGUAGE_FORMATTER_CONFIG, dict)
        for lang, formats in LANGUAGE_FORMATTER_CONFIG.items():
            assert isinstance(lang, str)
            assert isinstance(formats, dict)
            for fmt, strategy in formats.items():
                assert isinstance(fmt, str)
                assert strategy in ["legacy", "new"]

    def test_java_config(self) -> None:
        """Test Java configuration."""
        assert "java" in LANGUAGE_FORMATTER_CONFIG
        java_config = LANGUAGE_FORMATTER_CONFIG["java"]
        assert java_config["table"] == "legacy"
        assert java_config["compact"] == "legacy"
        assert java_config["full"] == "legacy"
        assert java_config["csv"] == "legacy"
        assert java_config["json"] == "legacy"

    def test_kotlin_config(self) -> None:
        """Test Kotlin configuration."""
        assert "kotlin" in LANGUAGE_FORMATTER_CONFIG
        kotlin_config = LANGUAGE_FORMATTER_CONFIG["kotlin"]
        assert kotlin_config["table"] == "new"
        assert kotlin_config["compact"] == "new"
        assert kotlin_config["full"] == "new"
        assert kotlin_config["csv"] == "new"
        assert kotlin_config["json"] == "new"

    def test_python_config(self) -> None:
        """Test Python configuration."""
        assert "python" in LANGUAGE_FORMATTER_CONFIG
        python_config = LANGUAGE_FORMATTER_CONFIG["python"]
        assert python_config["table"] == "legacy"
        assert python_config["compact"] == "legacy"
        assert python_config["full"] == "legacy"
        assert python_config["csv"] == "legacy"
        assert python_config["json"] == "legacy"

    def test_sql_config(self) -> None:
        """Test SQL configuration."""
        assert "sql" in LANGUAGE_FORMATTER_CONFIG
        sql_config = LANGUAGE_FORMATTER_CONFIG["sql"]
        assert sql_config["table"] == "new"
        assert sql_config["compact"] == "new"
        assert sql_config["full"] == "new"
        assert sql_config["csv"] == "new"
        assert sql_config["json"] == "new"


class TestLanguageAliases:
    """Tests for language aliases in config."""

    def test_kotlin_aliases(self) -> None:
        """Test Kotlin aliases."""
        kt_config = LANGUAGE_FORMATTER_CONFIG["kt"]
        kts_config = LANGUAGE_FORMATTER_CONFIG["kts"]
        assert kt_config["table"] == "new"
        assert kts_config["table"] == "new"

    def test_python_aliases(self) -> None:
        """Test Python aliases."""
        py_config = LANGUAGE_FORMATTER_CONFIG["py"]
        assert py_config["table"] == "legacy"

    def test_javascript_aliases(self) -> None:
        """Test JavaScript aliases."""
        js_config = LANGUAGE_FORMATTER_CONFIG["js"]
        assert js_config["table"] == "legacy"

    def test_typescript_aliases(self) -> None:
        """Test TypeScript aliases."""
        ts_config = LANGUAGE_FORMATTER_CONFIG["ts"]
        assert ts_config["table"] == "legacy"

    def test_markdown_aliases(self) -> None:
        """Test Markdown aliases."""
        md_config = LANGUAGE_FORMATTER_CONFIG["md"]
        assert md_config["table"] == "new"

    def test_yaml_aliases(self) -> None:
        """Test YAML aliases."""
        yml_config = LANGUAGE_FORMATTER_CONFIG["yml"]
        assert yml_config["table"] == "new"


class TestDefaultStrategy:
    """Tests for DEFAULT_STRATEGY."""

    def test_default_strategy_value(self) -> None:
        """Test DEFAULT_STRATEGY value."""
        assert DEFAULT_STRATEGY == "legacy"


class TestGetFormatterStrategy:
    """Tests for get_formatter_strategy function."""

    def test_get_strategy_legacy_language(self) -> None:
        """Test getting strategy for legacy language."""
        result = get_formatter_strategy("java", "table")
        assert result == "legacy"

    def test_get_strategy_new_language(self) -> None:
        """Test getting strategy for new language."""
        result = get_formatter_strategy("kotlin", "table")
        assert result == "new"

    def test_get_strategy_all_formats(self) -> None:
        """Test getting strategy for all format types."""
        formats = ["table", "compact", "full", "csv", "json"]
        for fmt in formats:
            result = get_formatter_strategy("python", fmt)
            assert result == "legacy"

    def test_get_strategy_case_insensitive(self) -> None:
        """Test that language lookup is case insensitive."""
        result_lower = get_formatter_strategy("python", "table")
        result_upper = get_formatter_strategy("PYTHON", "table")
        result_mixed = get_formatter_strategy("Python", "table")
        assert result_lower == result_upper == result_mixed

    def test_get_strategy_unknown_language(self) -> None:
        """Test getting strategy for unknown language."""
        result = get_formatter_strategy("unknown_language", "table")
        assert result == DEFAULT_STRATEGY

    def test_get_strategy_unknown_format(self) -> None:
        """Test getting strategy for unknown format type."""
        result = get_formatter_strategy("python", "unknown_format")
        assert result == DEFAULT_STRATEGY

    def test_get_strategy_c_family(self) -> None:
        """Test C family languages."""
        c_result = get_formatter_strategy("c", "table")
        cpp_result = get_formatter_strategy("cpp", "table")
        assert c_result == "new"
        assert cpp_result == "new"

    def test_get_strategy_rust(self) -> None:
        """Test Rust language."""
        result = get_formatter_strategy("rust", "table")
        assert result == "new"

    def test_get_strategy_go(self) -> None:
        """Test Go language."""
        result = get_formatter_strategy("go", "table")
        assert result == "new"

    def test_get_strategy_html_css(self) -> None:
        """Test HTML and CSS languages."""
        html_result = get_formatter_strategy("html", "table")
        css_result = get_formatter_strategy("css", "table")
        assert html_result == "new"
        assert css_result == "new"
