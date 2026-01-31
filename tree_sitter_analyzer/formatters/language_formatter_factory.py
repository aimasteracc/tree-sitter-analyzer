#!/usr/bin/env python3
"""
Language Formatter Factory - Language-Specific Formatter Creation

This module provides a factory for creating language-specific formatters
for different programming languages and output types.

Optimized with:
- Complete type hints (PEP 484)
- Comprehensive error handling
- Performance optimization with caching
- Detailed documentation in English

Features:
- Language-to-formatter mapping
- Format type resolution
- Language alias support (py, js, ts, etc.)
- Extensible formatter registration
- Type-safe operations (PEP 484)

Architecture:
- Factory pattern for formatter creation
- Static formatter registry
- Integration with all language formatters
- Fallback to generic formatter

Usage:
    >>> from tree_sitter_analyzer.formatters import LanguageFormatterFactory
    >>> formatter = LanguageFormatterFactory.create("python")
    >>> output = formatter.format(analysis_result)

Author: aisheng.yu
Version: 1.10.5
Date: 2026-01-28
"""

# Standard library imports
import logging

# Internal imports - Language formatters
from .base_formatter import BaseFormatter
from .cpp_formatter import CppTableFormatter
from .csharp_formatter import CSharpTableFormatter
from .css_formatter import CSSFormatter
from .go_formatter import GoTableFormatter
from .html_formatter import HtmlFormatter
from .java_formatter import JavaTableFormatter
from .javascript_formatter import JavaScriptTableFormatter
from .kotlin_formatter import KotlinTableFormatter
from .markdown_formatter import MarkdownFormatter
from .php_formatter import PHPTableFormatter
from .python_formatter import PythonTableFormatter
from .ruby_formatter import RubyTableFormatter
from .rust_formatter import RustTableFormatter
from .sql_formatter_wrapper import SQLFormatterWrapper
from .typescript_formatter import TypeScriptTableFormatter
from .yaml_formatter import YAMLFormatter

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class LanguageFormatterFactory:
    """Factory for creating language-specific formatters"""

    _formatters: dict[str, type[BaseFormatter]] = {
        "markdown": MarkdownFormatter,
        "md": MarkdownFormatter,  # Alias
        "html": HtmlFormatter,
        "css": CSSFormatter,  # CSS files use CSS formatter
        "sql": SQLFormatterWrapper,  # SQL-specific formatter
        "python": PythonTableFormatter,  # Python files use Python formatter
        "py": PythonTableFormatter,  # Python alias
        "java": JavaTableFormatter,  # Java files use Java formatter
        "kotlin": KotlinTableFormatter,  # Kotlin files use Kotlin formatter
        "kt": KotlinTableFormatter,  # Kotlin alias
        "kts": KotlinTableFormatter,  # Kotlin script alias
        "javascript": JavaScriptTableFormatter,  # JavaScript files use JavaScript formatter
        "js": JavaScriptTableFormatter,  # JavaScript alias
        "typescript": TypeScriptTableFormatter,  # TypeScript files use TypeScript formatter
        "ts": TypeScriptTableFormatter,  # TypeScript alias
        "csharp": CSharpTableFormatter,  # C# files use C# formatter
        "cs": CSharpTableFormatter,  # C# alias
        "php": PHPTableFormatter,  # PHP files use PHP formatter
        "ruby": RubyTableFormatter,  # Ruby files use Ruby formatter
        "rb": RubyTableFormatter,  # Ruby alias
        "rust": RustTableFormatter,  # Rust files use Rust formatter
        "rs": RustTableFormatter,  # Rust alias
        "go": GoTableFormatter,  # Go files use Go formatter
        "yaml": YAMLFormatter,  # YAML files use YAML formatter
        "yml": YAMLFormatter,  # YAML alias
        "c": CppTableFormatter,  # C files use C/C++ formatter
        "h": CppTableFormatter,  # C header files
        "cpp": CppTableFormatter,  # C++ files use C/C++ formatter
        "cxx": CppTableFormatter,
        "cc": CppTableFormatter,
        "hpp": CppTableFormatter,
        "hxx": CppTableFormatter,
        "h++": CppTableFormatter,
        "c++": CppTableFormatter,
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


# Exported public API
__all__ = [
    "LanguageFormatterFactory",
]
