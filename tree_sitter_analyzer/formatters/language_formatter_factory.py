#!/usr/bin/env python3
"""
Factory for creating language-specific formatters for different output types.
"""

from .base_formatter import BaseFormatter
from .csharp_formatter import CSharpTableFormatter
from .html_formatter import HtmlFormatter
from .java_formatter import JavaTableFormatter
from .javascript_formatter import JavaScriptTableFormatter
from .markdown_formatter import MarkdownFormatter
from .php_formatter import PHPTableFormatter
from .python_formatter import PythonTableFormatter
from .ruby_formatter import RubyTableFormatter
from .sql_formatter_wrapper import SQLFormatterWrapper
from .typescript_formatter import TypeScriptTableFormatter


class LanguageFormatterFactory:
    """Factory for creating language-specific formatters"""

    _formatters: dict[str, type[BaseFormatter]] = {
        "markdown": MarkdownFormatter,
        "md": MarkdownFormatter,  # Alias
        "html": HtmlFormatter,
        "css": HtmlFormatter,  # CSS files also use HTML formatter
        "sql": SQLFormatterWrapper,  # SQL-specific formatter
        "python": PythonTableFormatter,  # Python files use Python formatter
        "py": PythonTableFormatter,  # Python alias
        "java": JavaTableFormatter,  # Java files use Java formatter
        "javascript": JavaScriptTableFormatter,  # JavaScript files use JavaScript formatter
        "js": JavaScriptTableFormatter,  # JavaScript alias
        "typescript": TypeScriptTableFormatter,  # TypeScript files use TypeScript formatter
        "ts": TypeScriptTableFormatter,  # TypeScript alias
        "csharp": CSharpTableFormatter,  # C# files use C# formatter
        "cs": CSharpTableFormatter,  # C# alias
        "php": PHPTableFormatter,  # PHP files use PHP formatter
        "ruby": RubyTableFormatter,  # Ruby files use Ruby formatter
        "rb": RubyTableFormatter,  # Ruby alias
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
            raise ValueError(f"Unsupported language: {language}")

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


def create_language_formatter(language: str) -> BaseFormatter | None:
    """
    Create language formatter (function for compatibility)

    Args:
        language: Programming language name

    Returns:
        Language formatter or None if not supported
    """
    try:
        return LanguageFormatterFactory.create_formatter(language)
    except ValueError:
        # Return None for unsupported languages instead of raising exception
        return None
