"""Tests for backward compatibility module."""
from __future__ import annotations

import warnings

from tree_sitter_analyzer.formatters.compat import (
    FormatterSelector,
    LanguageFormatterFactory,
    TableFormatterFactory,
    create_table_formatter,
)


class TestCreateTableFormatter:
    def test_emits_deprecation_warning(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = create_table_formatter("full", "java")
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "deprecated" in str(w[0].message).lower()
        assert isinstance(result, (dict, object))

    def test_returns_formatter(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            result = create_table_formatter("compact", "java")
            assert isinstance(result, (dict, object))


class TestTableFormatterFactory:
    def test_create_formatter_emits_warning(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = TableFormatterFactory.create_formatter("java", "full")
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
        assert isinstance(result, (dict, object))

    def test_get_supported_languages(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            languages = TableFormatterFactory.get_supported_languages()
            assert isinstance(languages, list)
            assert len(languages) > 0


class TestLanguageFormatterFactory:
    def test_supports_language(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            assert LanguageFormatterFactory.supports_language("java") is True

    def test_get_supported_languages(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            languages = LanguageFormatterFactory.get_supported_languages()
            assert isinstance(languages, list)
            assert "java" in languages

    def test_create_formatter(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            result = LanguageFormatterFactory.create_formatter("java")
            assert isinstance(result, (dict, object))


class TestFormatterSelector:
    def test_get_formatter(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            result = FormatterSelector.get_formatter("java", "full")
            assert isinstance(result, (dict, object))

    def test_is_legacy_formatter(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            result = FormatterSelector.is_legacy_formatter("java", "full")
            assert result is True

    def test_get_supported_languages(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            languages = FormatterSelector.get_supported_languages()
            assert isinstance(languages, list)
            assert len(languages) > 0
