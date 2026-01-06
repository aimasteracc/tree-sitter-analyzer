#!/usr/bin/env python3
"""
Formatter Registry

Dynamic formatter registration and management system.
Provides extensible formatter architecture following the Registry pattern.

This is the unified entry point for all formatter operations in the project.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

from ..models import CodeElement

logger = logging.getLogger(__name__)


class IFormatter(ABC):
    """
    Interface for code element formatters.

    All formatters must implement this interface to be compatible
    with the FormatterRegistry system.
    """

    @staticmethod
    @abstractmethod
    def get_format_name() -> str:
        """
        Return the format name this formatter supports.

        Returns:
            Format name (e.g., "json", "csv", "markdown")
        """
        pass

    @abstractmethod
    def format(self, elements: list[CodeElement]) -> str:
        """
        Format a list of CodeElements into a string representation.

        Args:
            elements: List of CodeElement objects to format

        Returns:
            Formatted string representation
        """
        pass


class IStructureFormatter(ABC):
    """
    Interface for structure-based formatters (legacy compatibility).

    These formatters accept dict-based structure data instead of CodeElement lists.
    Used for backward compatibility with v1.6.1.4 format output.
    """

    @abstractmethod
    def format_structure(self, structure_data: dict[str, Any]) -> str:
        """
        Format structure data dictionary into a string representation.

        Args:
            structure_data: Dictionary containing analysis results

        Returns:
            Formatted string representation
        """
        pass


class FormatterRegistry:
    """
    Unified registry for managing and providing formatter instances.

    Implements the Registry pattern to allow dynamic registration
    and retrieval of formatters by format name and language.

    This is the primary entry point for formatter operations:
    - Use get_formatter() for format-based lookup
    - Use get_formatter_for_language() for language-specific formatting
    """

    _formatters: dict[str, type[IFormatter]] = {}
    _language_formatters: dict[str, dict[str, type[Any]]] = {}
    _default_language_formatter: type[Any] | None = None

    @classmethod
    def register_formatter(cls, formatter_class: type[IFormatter]) -> None:
        """
        Register a formatter class in the registry.

        Args:
            formatter_class: Formatter class implementing IFormatter

        Raises:
            ValueError: If formatter_class doesn't implement IFormatter
        """
        if not issubclass(formatter_class, IFormatter):
            raise ValueError("Formatter class must implement IFormatter interface")

        format_name = formatter_class.get_format_name()
        if not format_name:
            raise ValueError("Formatter must provide a non-empty format name")

        if format_name in cls._formatters:
            logger.warning(f"Overriding existing formatter for format: {format_name}")

        cls._formatters[format_name] = formatter_class
        logger.debug(f"Registered formatter for format: {format_name}")

    @classmethod
    def get_formatter(cls, format_name: str) -> IFormatter:
        """
        Get a formatter instance for the specified format.

        Args:
            format_name: Name of the format to get formatter for

        Returns:
            Formatter instance

        Raises:
            ValueError: If format is not supported
        """
        if format_name not in cls._formatters:
            available_formats = list(cls._formatters.keys())
            raise ValueError(
                f"Unsupported format: {format_name}. "
                f"Available formats: {available_formats}"
            )

        formatter_class = cls._formatters[format_name]
        return formatter_class()

    @classmethod
    def get_available_formats(cls) -> list[str]:
        """
        Get list of all available format names.

        Returns:
            List of available format names
        """
        return list(cls._formatters.keys())

    @classmethod
    def is_format_supported(cls, format_name: str) -> bool:
        """
        Check if a format is supported.

        Args:
            format_name: Format name to check

        Returns:
            True if format is supported
        """
        return format_name in cls._formatters

    @classmethod
    def unregister_formatter(cls, format_name: str) -> bool:
        """
        Unregister a formatter for the specified format.

        Args:
            format_name: Format name to unregister

        Returns:
            True if formatter was unregistered, False if not found
        """
        if format_name in cls._formatters:
            del cls._formatters[format_name]
            logger.debug(f"Unregistered formatter for format: {format_name}")
            return True
        return False

    @classmethod
    def clear_registry(cls) -> None:
        """
        Clear all registered formatters.

        This method is primarily for testing purposes.
        """
        cls._formatters.clear()
        cls._language_formatters.clear()
        cls._default_language_formatter = None
        logger.debug("Cleared all registered formatters")

    @classmethod
    def register_language_formatter(
        cls,
        language: str,
        format_type: str,
        formatter_class: type[Any],
    ) -> None:
        """
        Register a language-specific formatter.

        Args:
            language: Programming language name (e.g., "java", "python")
            format_type: Format type (e.g., "full", "compact", "csv")
            formatter_class: Formatter class to register

        Example:
            >>> FormatterRegistry.register_language_formatter(
            ...     "java", "full", JavaTableFormatter
            ... )
        """
        lang_key = language.lower()
        if lang_key not in cls._language_formatters:
            cls._language_formatters[lang_key] = {}

        cls._language_formatters[lang_key][format_type] = formatter_class
        logger.debug(
            f"Registered language formatter: {language}/{format_type} -> "
            f"{formatter_class.__name__}"
        )

    @classmethod
    def set_default_language_formatter(cls, formatter_class: type[Any]) -> None:
        """
        Set the default formatter class for languages without specific formatters.

        Args:
            formatter_class: Default formatter class
        """
        cls._default_language_formatter = formatter_class
        logger.debug(f"Set default language formatter: {formatter_class.__name__}")

    @classmethod
    def get_formatter_for_language(
        cls,
        language: str,
        format_type: str = "full",
        **kwargs: Any,
    ) -> Any:
        """
        Get a formatter instance for the specified language and format type.

        This is the primary method for obtaining formatters in the unified architecture.
        It handles language-specific formatter lookup with fallback to defaults.

        Args:
            language: Programming language name
            format_type: Format type (full, compact, csv, json, etc.)
            **kwargs: Additional arguments passed to formatter constructor
                - include_javadoc: bool - Include JavaDoc in output

        Returns:
            Formatter instance appropriate for the language and format

        Example:
            >>> formatter = FormatterRegistry.get_formatter_for_language("java", "full")
            >>> output = formatter.format_structure(analysis_data)
        """
        lang_key = language.lower()
        format_key = format_type.lower()

        # Check for language-specific formatter first
        if lang_key in cls._language_formatters:
            lang_formatters = cls._language_formatters[lang_key]
            if format_key in lang_formatters:
                formatter_class = lang_formatters[format_key]
                return cls._create_formatter_instance(
                    formatter_class, format_key, language, **kwargs
                )

        # Fall back to default language formatter if set
        if cls._default_language_formatter is not None:
            return cls._create_formatter_instance(
                cls._default_language_formatter, format_key, language, **kwargs
            )

        # Final fallback to generic format-based formatter
        if format_key in cls._formatters:
            return cls._formatters[format_key]()

        # If nothing found, raise error with helpful message
        available = cls.get_available_formats()
        raise ValueError(
            f"No formatter found for language '{language}' "
            f"with format '{format_type}'. Available formats: {available}"
        )

    @classmethod
    def _create_formatter_instance(
        cls,
        formatter_class: type[Any],
        format_type: str,
        language: str,
        **kwargs: Any,
    ) -> Any:
        """
        Create a formatter instance with appropriate constructor arguments.

        Handles different formatter constructor signatures gracefully.
        """
        try:
            # Try full signature first (for TableFormatter-style classes)
            include_javadoc = kwargs.get("include_javadoc", False)
            return formatter_class(
                format_type=format_type,
                language=language,
                include_javadoc=include_javadoc,
            )
        except TypeError:
            try:
                # Try format_type only
                return formatter_class(format_type=format_type)
            except TypeError:
                # Fall back to no-arg constructor
                return formatter_class()

    @classmethod
    def get_supported_languages(cls) -> list[str]:
        """
        Get list of all languages with registered formatters.

        Returns:
            List of language names
        """
        return list(cls._language_formatters.keys())

    @classmethod
    def is_language_supported(cls, language: str) -> bool:
        """
        Check if a language has specific formatters registered.

        Args:
            language: Language name to check

        Returns:
            True if language has specific formatters
        """
        return language.lower() in cls._language_formatters


# Built-in formatter implementations


class JsonFormatter(IFormatter):
    """JSON formatter for CodeElement lists"""

    @staticmethod
    def get_format_name() -> str:
        return "json"

    def format(self, elements: list[CodeElement]) -> str:
        """Format elements as JSON"""
        import json

        result = []
        for element in elements:
            element_dict = {
                "name": element.name,
                "type": getattr(element, "element_type", "unknown"),
                "start_line": element.start_line,
                "end_line": element.end_line,
                "language": element.language,
            }

            # Add type-specific attributes
            if hasattr(element, "parameters"):
                element_dict["parameters"] = getattr(element, "parameters", [])
            if hasattr(element, "return_type"):
                element_dict["return_type"] = getattr(element, "return_type", None)
            if hasattr(element, "visibility"):
                element_dict["visibility"] = getattr(element, "visibility", "unknown")
            if hasattr(element, "modifiers"):
                element_dict["modifiers"] = getattr(element, "modifiers", [])
            if hasattr(element, "tag_name"):
                element_dict["tag_name"] = getattr(element, "tag_name", "")
            if hasattr(element, "selector"):
                element_dict["selector"] = getattr(element, "selector", "")
            if hasattr(element, "element_class"):
                element_dict["element_class"] = getattr(element, "element_class", "")

            result.append(element_dict)

        return json.dumps(result, indent=2, ensure_ascii=False)


class CsvFormatter(IFormatter):
    """CSV formatter for CodeElement lists"""

    @staticmethod
    def get_format_name() -> str:
        return "csv"

    def format(self, elements: list[CodeElement]) -> str:
        """Format elements as CSV"""
        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")

        # Write header
        writer.writerow(
            [
                "Type",
                "Name",
                "Start Line",
                "End Line",
                "Language",
                "Visibility",
                "Parameters",
                "Return Type",
                "Modifiers",
            ]
        )

        # Write data rows
        for element in elements:
            writer.writerow(
                [
                    getattr(element, "element_type", "unknown"),
                    element.name,
                    element.start_line,
                    element.end_line,
                    element.language,
                    getattr(element, "visibility", ""),
                    str(getattr(element, "parameters", [])),
                    getattr(element, "return_type", ""),
                    str(getattr(element, "modifiers", [])),
                ]
            )

        csv_content = output.getvalue()
        output.close()
        return csv_content.rstrip("\n")


class FullFormatter(IFormatter):
    """Full table formatter for CodeElement lists"""

    @staticmethod
    def get_format_name() -> str:
        return "full"

    def format(self, elements: list[CodeElement]) -> str:
        """Format elements as full table"""
        if not elements:
            return "No elements found."

        lines = []
        lines.append("=" * 80)
        lines.append("CODE STRUCTURE ANALYSIS")
        lines.append("=" * 80)
        lines.append("")

        # Group elements by type
        element_groups: dict[str, list[CodeElement]] = {}
        for element in elements:
            element_type = getattr(element, "element_type", "unknown")
            if element_type not in element_groups:
                element_groups[element_type] = []
            element_groups[element_type].append(element)

        # Format each group
        for element_type, group_elements in element_groups.items():
            lines.append(f"{element_type.upper()}S ({len(group_elements)})")
            lines.append("-" * 40)

            for element in group_elements:
                lines.append(f"  {element.name}")
                lines.append(f"    Lines: {element.start_line}-{element.end_line}")
                lines.append(f"    Language: {element.language}")

                if hasattr(element, "visibility"):
                    lines.append(
                        f"    Visibility: {getattr(element, 'visibility', 'unknown')}"
                    )
                if hasattr(element, "parameters"):
                    params = getattr(element, "parameters", [])
                    if params:
                        lines.append(
                            f"    Parameters: {', '.join(str(p) for p in params)}"
                        )
                if hasattr(element, "return_type"):
                    ret_type = getattr(element, "return_type", None)
                    if ret_type:
                        lines.append(f"    Return Type: {ret_type}")

                lines.append("")

            lines.append("")

        return "\n".join(lines)


class CompactFormatter(IFormatter):
    """Compact formatter for CodeElement lists"""

    @staticmethod
    def get_format_name() -> str:
        return "compact"

    def format(self, elements: list[CodeElement]) -> str:
        """Format elements in compact format"""
        if not elements:
            return "No elements found."

        lines = []
        lines.append("CODE ELEMENTS")
        lines.append("-" * 20)

        for element in elements:
            element_type = getattr(element, "element_type", "unknown")
            visibility = getattr(element, "visibility", "")
            vis_symbol = self._get_visibility_symbol(visibility)

            line = (
                f"{vis_symbol} {element.name} ({element_type}) "
                f"[{element.start_line}-{element.end_line}]"
            )
            lines.append(line)

        return "\n".join(lines)

    def _get_visibility_symbol(self, visibility: str) -> str:
        """Get symbol for visibility"""
        mapping = {"public": "+", "private": "-", "protected": "#", "package": "~"}
        return mapping.get(visibility, "?")


# Register built-in formatters
def register_builtin_formatters() -> None:
    """Register all built-in formatters"""
    FormatterRegistry.register_formatter(JsonFormatter)

    # Fallback to simple formatters first to avoid circular import issues
    FormatterRegistry.register_formatter(CsvFormatter)
    FormatterRegistry.register_formatter(FullFormatter)
    FormatterRegistry.register_formatter(CompactFormatter)

    # Register language-specific formatters
    _register_language_formatters_safe()


def _register_language_formatters_safe() -> None:
    """Register language-specific formatters safely to avoid circular imports"""
    try:
        # Import language-specific formatters
        from ..legacy_table_formatter import LegacyTableFormatter
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

        # Set LegacyTableFormatter as default for unsupported languages
        FormatterRegistry.set_default_language_formatter(LegacyTableFormatter)

        # Language to formatter mapping
        language_formatters = {
            "java": JavaTableFormatter,
            "python": PythonTableFormatter,
            "py": PythonTableFormatter,
            "javascript": JavaScriptTableFormatter,
            "js": JavaScriptTableFormatter,
            "typescript": TypeScriptTableFormatter,
            "ts": TypeScriptTableFormatter,
            "csharp": CSharpTableFormatter,
            "cs": CSharpTableFormatter,
            "php": PHPTableFormatter,
            "ruby": RubyTableFormatter,
            "rb": RubyTableFormatter,
            "kotlin": KotlinTableFormatter,
            "kt": KotlinTableFormatter,
            "kts": KotlinTableFormatter,
            "go": GoTableFormatter,
            "rust": RustTableFormatter,
            "rs": RustTableFormatter,
            "c": CppTableFormatter,
            "cpp": CppTableFormatter,
            "h": CppTableFormatter,
            "hpp": CppTableFormatter,
            "yaml": YAMLFormatter,
            "yml": YAMLFormatter,
            "css": CSSFormatter,
            "html": HtmlFormatter,
            "htm": HtmlFormatter,
            "markdown": MarkdownFormatter,
            "md": MarkdownFormatter,
            "sql": SQLFormatterWrapper,
        }

        # Register each language with all format types
        format_types = ["full", "compact", "csv"]
        for lang, formatter_class in language_formatters.items():
            for fmt in format_types:
                FormatterRegistry.register_language_formatter(
                    lang, fmt, formatter_class
                )

        logger.info("Registered language-specific formatters")
    except ImportError as e:
        logger.warning(f"Failed to register language formatters: {e}")


# NOTE: HTML formatters are intentionally excluded from analyze_code_structure
# as they are not part of the v1.6.1.4 specification and cause format regression.
# HTML formatters can still be registered separately for other tools if needed.


# Auto-register built-in formatters when module is imported
register_builtin_formatters()
