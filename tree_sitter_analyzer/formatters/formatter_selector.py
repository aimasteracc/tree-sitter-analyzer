#!/usr/bin/env python3
"""
Formatter selector service - chooses appropriate formatter based on configuration.
"""

from typing import Any

from ..table_formatter import create_table_formatter
from .formatter_config import get_formatter_strategy
from .language_formatter_factory import create_language_formatter


class FormatterSelector:
    """
    Service for selecting appropriate formatter based on language and format type.

    This service decouples command layer from formatter layer by using explicit
    configuration instead of implicit "if formatter exists" logic.
    """

    @staticmethod
    def get_formatter(language: str, format_type: str, **kwargs: Any) -> Any:
        """
        Get appropriate formatter for language and format type.

        Args:
            language: Programming language name
            format_type: Output format type (table, compact, full, csv, json)
            **kwargs: Additional arguments for formatter (e.g., include_javadoc)

        Returns:
            Formatter instance (either legacy TableFormatter or new language-specific formatter)

        Example:
            >>> formatter = FormatterSelector.get_formatter("java", "compact")
            >>> output = formatter.format_structure(data)
        """
        strategy = get_formatter_strategy(language, format_type)

        if strategy == "new":
            return FormatterSelector._create_new_formatter(
                language, format_type, **kwargs
            )
        else:
            return FormatterSelector._create_legacy_formatter(
                language, format_type, **kwargs
            )

    @staticmethod
    def _create_new_formatter(language: str, format_type: str, **kwargs: Any) -> Any:
        """Create formatter from new system (LanguageFormatterFactory)."""
        formatter = create_language_formatter(language)
        if formatter is None:
            # Fallback to legacy if new formatter doesn't exist
            return FormatterSelector._create_legacy_formatter(
                language, format_type, **kwargs
            )

        # Set format type on formatter if it supports it
        if hasattr(formatter, "format_type"):
            formatter.format_type = format_type

        return formatter

    @staticmethod
    def _create_legacy_formatter(language: str, format_type: str, **kwargs: Any) -> Any:
        """Create formatter from legacy system (TableFormatter)."""
        include_javadoc = kwargs.get("include_javadoc", False)
        return create_table_formatter(format_type, language, include_javadoc)

    @staticmethod
    def is_legacy_formatter(language: str, format_type: str) -> bool:
        """
        Check if language uses legacy formatter for given format type.

        Args:
            language: Programming language name
            format_type: Output format type

        Returns:
            True if legacy formatter should be used, False otherwise
        """
        strategy = get_formatter_strategy(language, format_type)
        return strategy == "legacy"

    @staticmethod
    def get_supported_languages() -> list[str]:
        """
        Get list of all supported languages.

        Returns:
            List of supported language names
        """
        from .formatter_config import LANGUAGE_FORMATTER_CONFIG

        return list(LANGUAGE_FORMATTER_CONFIG.keys())
