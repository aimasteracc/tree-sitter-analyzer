#!/usr/bin/env python3
"""
Formatter Registry

Dynamic formatter registration and management system.
Provides extensible formatter architecture following the Registry pattern.

This is the unified entry point for all formatter operations in the project.
"""

import logging
from typing import Any

from ._builtin_formatters import (
    CompactFormatter,
    CsvFormatter,
    FullFormatter,
    JsonFormatter,
)
from ._formatter_interface import IFormatter, IStructureFormatter  # noqa: F401
from ._language_formatter_registration import (
    ensure_default_language_formatter,
    register_language_formatters,
)

logger = logging.getLogger(__name__)

# Keep the historical public identity after moving implementations behind the facade.
for _formatter_class in (JsonFormatter, CsvFormatter, FullFormatter, CompactFormatter):
    _formatter_class.__module__ = __name__


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
    _language_formatters: dict[str, Any] = {}
    _default_language_formatter: type[Any] | None = None
    _language_registration_complete = False

    @classmethod
    # Format data for output: register_formatter
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
            warn_msg = f"Overriding existing formatter for format: {format_name}"
            logger.warning(warn_msg)

        cls._formatters[format_name] = formatter_class
        logger.debug(f"Registered formatter for format: {format_name}")

    @classmethod
    # Format data for output: get_formatter
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
        formatters = cls._formatters
        if format_name not in formatters:
            available_formats = list(formatters)
            err_msg = f"Unsupported format: {format_name}. Available formats: {available_formats}"
            raise ValueError(err_msg)

        formatter_class = formatters[format_name]
        return formatter_class()

    @classmethod
    # Format data for output: get_available_formats
    def get_available_formats(cls) -> list[str]:
        """
        Get list of all available format names.

        Returns:
            List of available format names
        """
        return list(cls._formatters.keys())

    @classmethod
    # Format data for output: is_format_supported
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
    # Format data for output: unregister_formatter
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
            dbg_msg = f"Unregistered formatter for format: {format_name}"
            logger.debug(dbg_msg)
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
        cls._language_registration_complete = False
        logger.debug("Cleared all registered formatters")

    @classmethod
    # Format data for output: register_language_formatter
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
        cls_name = formatter_class.__name__
        dbg_msg = (
            f"Registered language formatter: {language}/{format_type} -> {cls_name}"
        )
        logger.debug(dbg_msg)

    @classmethod
    # Format data for output: set_default_language_formatter
    def set_default_language_formatter(cls, formatter_class: type[Any]) -> None:
        """
        Set the default formatter class for languages without specific formatters.

        Args:
            formatter_class: Default formatter class
        """
        cls._default_language_formatter = formatter_class
        logger.debug(f"Set default language formatter: {formatter_class.__name__}")

    @classmethod
    # Format data for output: get_formatter_for_language
    def get_formatter_for_language(
        cls,
        language: str,
        format_type: str = "full",
        **kwargs: Any,
    ) -> Any:
        """Return the best language-specific, default, or generic formatter.

        Extra keyword arguments are forwarded to table-style constructors.
        """
        lang_key = language.lower()
        format_key = format_type.lower()

        # Check for language-specific formatter first
        lang_formatters = cls._language_formatters.get(lang_key, {})
        if lang_key in cls._language_formatters and format_key in lang_formatters:
            formatter_class = lang_formatters[format_key]
            return cls._create_formatter_instance(
                formatter_class, format_key, language, **kwargs
            )

        if cls._language_registration_complete:
            ensure_default_language_formatter(cls, logger)

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
    # Format data for output: _create_formatter_instance
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
        # Extract kwargs before try to reduce nesting depth
        include_javadoc = kwargs.get("include_javadoc", False)
        try:
            # Try full signature first (for TableFormatter-style classes)
            return formatter_class(
                format_type=format_type,
                language=language,
                include_javadoc=include_javadoc,
            )
        except TypeError:
            return cls._try_format_type_or_bare(formatter_class, format_type)

    @classmethod
    def _try_format_type_or_bare(
        cls, formatter_class: type[Any], format_type: str
    ) -> Any:
        """Fallback: try format_type-only constructor, then bare constructor."""
        try:
            return formatter_class(format_type=format_type)
        except TypeError:
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


def register_builtin_formatters() -> None:
    """Register generic and language-specific built-in formatters."""
    for formatter_class in (
        JsonFormatter,
        CsvFormatter,
        FullFormatter,
        CompactFormatter,
    ):
        FormatterRegistry.register_formatter(formatter_class)
    register_language_formatters(FormatterRegistry, logger)


# Auto-register built-in formatters when module is imported
register_builtin_formatters()
