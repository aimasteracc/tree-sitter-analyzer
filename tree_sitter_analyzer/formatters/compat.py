#!/usr/bin/env python3
"""
Backward Compatibility Module for Formatter Architecture

This module provides deprecated wrapper classes for backward compatibility
during the transition to the unified FormatterRegistry architecture.

All classes in this module emit DeprecationWarning when used.
Users should migrate to using FormatterRegistry directly.

Migration Guide:
    Old: LanguageFormatterFactory.create_formatter("python")
    New: FormatterRegistry.get_formatter_for_language("python", "full")

    Old: FormatterSelector.get_formatter("java", "full")
    New: FormatterRegistry.get_formatter_for_language("java", "full")
"""

import warnings
from typing import Any

from .formatter_registry import FormatterRegistry


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


# FormatterSelector was removed in v3 (dead code — never imported or used).
# Use FormatterRegistry directly instead.
