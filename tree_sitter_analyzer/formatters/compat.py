#!/usr/bin/env python3
"""
Backward Compatibility Module for Formatter Architecture

This module provides deprecated wrapper functions and classes for backward
compatibility during the transition to the unified FormatterRegistry architecture.

All functions and classes in this module emit DeprecationWarning when used.
Users should migrate to using FormatterRegistry directly.

Migration Guide:
    Old: create_table_formatter("full", "java")
    New: FormatterRegistry.get_formatter_for_language("java", "full")

    Old: TableFormatterFactory.create_formatter("java", "full")
    New: FormatterRegistry.get_formatter_for_language("java", "full")

    Old: FormatterSelector.get_formatter("java", "full")
    New: FormatterRegistry.get_formatter_for_language("java", "full")
"""

import warnings
from typing import Any

from .formatter_registry import FormatterRegistry


def create_table_formatter(
    format_type: str,
    language: str = "java",
    include_javadoc: bool = False,
) -> Any:
    """
    DEPRECATED: Use FormatterRegistry.get_formatter_for_language() instead.

    Create a table formatter for the specified language and format type.

    Args:
        format_type: Format type (full, compact, csv)
        language: Programming language name
        include_javadoc: Whether to include JavaDoc in output

    Returns:
        Formatter instance

    Example:
        # Old way (deprecated):
        formatter = create_table_formatter("full", "java")

        # New way:
        from tree_sitter_analyzer.formatters.formatter_registry import FormatterRegistry
        formatter = FormatterRegistry.get_formatter_for_language("java", "full")
    """
    warnings.warn(
        "create_table_formatter is deprecated. "
        "Use FormatterRegistry.get_formatter_for_language() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return FormatterRegistry.get_formatter_for_language(
        language, format_type, include_javadoc=include_javadoc
    )


class TableFormatterFactory:
    """
    DEPRECATED: Use FormatterRegistry instead.

    Factory for creating language-specific table formatters.
    This class is maintained for backward compatibility only.

    Migration:
        # Old way (deprecated):
        formatter = TableFormatterFactory.create_formatter("java", "full")

        # New way:
        from tree_sitter_analyzer.formatters.formatter_registry import FormatterRegistry
        formatter = FormatterRegistry.get_formatter_for_language("java", "full")
    """

    @classmethod
    def create_formatter(
        cls,
        language: str,
        format_type: str = "full",
        **kwargs: Any,
    ) -> Any:
        """
        DEPRECATED: Use FormatterRegistry.get_formatter_for_language() instead.

        Create table formatter for specified language.

        Args:
            language: Programming language name
            format_type: Format type (full, compact, csv)
            **kwargs: Additional arguments for formatter

        Returns:
            Language-specific table formatter
        """
        warnings.warn(
            "TableFormatterFactory.create_formatter is deprecated. "
            "Use FormatterRegistry.get_formatter_for_language() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return FormatterRegistry.get_formatter_for_language(
            language, format_type, **kwargs
        )

    @classmethod
    def register_formatter(cls, language: str, formatter_class: type) -> None:
        """
        DEPRECATED: Use FormatterRegistry.register_language_formatter() instead.

        Register new language formatter.

        Args:
            language: Programming language name
            formatter_class: Formatter class
        """
        warnings.warn(
            "TableFormatterFactory.register_formatter is deprecated. "
            "Use FormatterRegistry.register_language_formatter() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        # Register for all format types
        for format_type in ["full", "compact", "csv"]:
            FormatterRegistry.register_language_formatter(
                language, format_type, formatter_class
            )

    @classmethod
    def get_supported_languages(cls) -> list[str]:
        """
        DEPRECATED: Use FormatterRegistry.get_supported_languages() instead.

        Get list of supported languages.

        Returns:
            List of supported languages
        """
        warnings.warn(
            "TableFormatterFactory.get_supported_languages is deprecated. "
            "Use FormatterRegistry.get_supported_languages() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return FormatterRegistry.get_supported_languages()


class LanguageFormatterFactory:
    """
    DEPRECATED: Use FormatterRegistry instead.

    Factory for creating language-specific formatters.
    This class is maintained for backward compatibility only.

    Migration:
        # Old way (deprecated):
        formatter = LanguageFormatterFactory.create_formatter("python")

        # New way:
        from tree_sitter_analyzer.formatters.formatter_registry import FormatterRegistry
        formatter = FormatterRegistry.get_formatter_for_language("python", "full")
    """

    @classmethod
    def create_formatter(cls, language: str, **kwargs: Any) -> Any:
        """
        DEPRECATED: Use FormatterRegistry.get_formatter_for_language() instead.

        Create formatter for specified language.

        Args:
            language: Programming language name
            **kwargs: Additional arguments for formatter

        Returns:
            Language-specific formatter
        """
        warnings.warn(
            "LanguageFormatterFactory.create_formatter is deprecated. "
            "Use FormatterRegistry.get_formatter_for_language() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return FormatterRegistry.get_formatter_for_language(language, "full", **kwargs)

    @classmethod
    def supports_language(cls, language: str) -> bool:
        """
        DEPRECATED: Use FormatterRegistry.is_language_supported() instead.

        Check if language is supported.

        Args:
            language: Programming language name

        Returns:
            True if language is supported
        """
        warnings.warn(
            "LanguageFormatterFactory.supports_language is deprecated. "
            "Use FormatterRegistry.is_language_supported() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return FormatterRegistry.is_language_supported(language)

    @classmethod
    def get_supported_languages(cls) -> list[str]:
        """
        DEPRECATED: Use FormatterRegistry.get_supported_languages() instead.

        Get list of supported languages.

        Returns:
            List of supported languages
        """
        warnings.warn(
            "LanguageFormatterFactory.get_supported_languages is deprecated. "
            "Use FormatterRegistry.get_supported_languages() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return FormatterRegistry.get_supported_languages()


class FormatterSelector:
    """
    DEPRECATED: Use FormatterRegistry instead.

    Service for selecting appropriate formatter based on language and format type.
    This class is maintained for backward compatibility only.

    Migration:
        # Old way (deprecated):
        formatter = FormatterSelector.get_formatter("java", "full")

        # New way:
        from tree_sitter_analyzer.formatters.formatter_registry import FormatterRegistry
        formatter = FormatterRegistry.get_formatter_for_language("java", "full")
    """

    @staticmethod
    def get_formatter(language: str, format_type: str, **kwargs: Any) -> Any:
        """
        DEPRECATED: Use FormatterRegistry.get_formatter_for_language() instead.

        Get appropriate formatter for language and format type.

        Args:
            language: Programming language name
            format_type: Output format type
            **kwargs: Additional arguments for formatter

        Returns:
            Formatter instance
        """
        warnings.warn(
            "FormatterSelector.get_formatter is deprecated. "
            "Use FormatterRegistry.get_formatter_for_language() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return FormatterRegistry.get_formatter_for_language(
            language, format_type, **kwargs
        )

    @staticmethod
    def is_legacy_formatter(language: str, format_type: str) -> bool:
        """
        DEPRECATED: This method is no longer relevant in the unified architecture.

        Check if language uses legacy formatter.

        Args:
            language: Programming language name
            format_type: Output format type

        Returns:
            Always returns True (all formatters are now unified)
        """
        warnings.warn(
            "FormatterSelector.is_legacy_formatter is deprecated. "
            "The unified architecture no longer distinguishes legacy formatters.",
            DeprecationWarning,
            stacklevel=2,
        )
        return True

    @staticmethod
    def get_supported_languages() -> list[str]:
        """
        DEPRECATED: Use FormatterRegistry.get_supported_languages() instead.

        Get list of all supported languages.

        Returns:
            List of supported language names
        """
        warnings.warn(
            "FormatterSelector.get_supported_languages is deprecated. "
            "Use FormatterRegistry.get_supported_languages() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return FormatterRegistry.get_supported_languages()
