#!/usr/bin/env python3
"""
Factory for creating language-specific formatters for different output types.
"""

from .base_formatter import BaseFormatter
from .html_formatter import HtmlFormatter
from .markdown_formatter import MarkdownFormatter


class LanguageFormatterFactory:
    """Factory for creating language-specific formatters"""

    _formatters: dict[str, type[BaseFormatter]] = {
        "markdown": MarkdownFormatter,
        "md": MarkdownFormatter,  # Alias
        "html": HtmlFormatter,
        "css": HtmlFormatter,  # CSS files also use HTML formatter
    }

    @classmethod
    def create_formatter(cls, language: str) -> BaseFormatter:
        """
        Create formatter for specified language

        Args:
            language: Programming language name

        Returns:
            Language-specific formatter
        """
        formatter_class = cls._formatters.get(language.lower())

        if formatter_class is None:
            # Return None for unsupported languages
            return None

        return formatter_class()

    @classmethod
    def register_formatter(
        cls, language: str, formatter_class: type[BaseFormatter]
    ) -> None:
        """
        Register new language formatter

        Args:
            language: Programming language name
            formatter_class: Formatter class
        """
        cls._formatters[language.lower()] = formatter_class

    @classmethod
    def get_supported_languages(cls) -> list[str]:
        """
        Get list of supported languages

        Returns:
            List of supported languages
        """
        return list(cls._formatters.keys())

    @classmethod
    def supports_language(cls, language: str) -> bool:
        """
        Check if language is supported

        Args:
            language: Programming language name

        Returns:
            True if language is supported
        """
        return language.lower() in cls._formatters


def create_language_formatter(language: str) -> BaseFormatter:
    """
    Create language formatter (function for compatibility)

    Args:
        language: Programming language name

    Returns:
        Language formatter or None if not supported
    """
    return LanguageFormatterFactory.create_formatter(language)
