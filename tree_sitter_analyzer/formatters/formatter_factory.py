#!/usr/bin/env python3
"""
Factory for creating language-specific table formatters.
"""

from .base_formatter import BaseTableFormatter
from .java_formatter import JavaTableFormatter
from .python_formatter import PythonTableFormatter


class TableFormatterFactory:
    """Factory for creating language-specific table formatters"""

    _formatters: dict[str, type[BaseTableFormatter]] = {
        "java": JavaTableFormatter,
        "python": PythonTableFormatter,
    }

    @classmethod
    def create_formatter(
        cls, language: str, format_type: str = "full"
    ) -> BaseTableFormatter:
        """
        Create table formatter for specified language

        Args:
            language: Programming language name
            format_type: Format type (full, compact, csv)

        Returns:
            Language-specific table formatter
        """
        formatter_class = cls._formatters.get(language.lower())

        if formatter_class is None:
            # Use Java formatter as default
            formatter_class = JavaTableFormatter

        return formatter_class(format_type)

    @classmethod
    def register_formatter(
        cls, language: str, formatter_class: type[BaseTableFormatter]
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


def create_table_formatter(
    format_type: str, language: str = "java"
) -> BaseTableFormatter:
    """
    Create table formatter (function for compatibility)

    Args:
        format_type: Format type
        language: Programming language name

    Returns:
        Table formatter
    """
    return TableFormatterFactory.create_formatter(language, format_type)
