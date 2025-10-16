#!/usr/bin/env python3
"""
Formatter Registry

Dynamic formatter registration and management system.
Provides extensible formatter architecture following the Registry pattern.
"""

import logging
from abc import ABC, abstractmethod

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


class FormatterRegistry:
    """
    Registry for managing and providing formatter instances.

    Implements the Registry pattern to allow dynamic registration
    and retrieval of formatters by format name.
    """

    _formatters: dict[str, type[IFormatter]] = {}

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
        logger.debug("Cleared all registered formatters")


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

            line = f"{vis_symbol} {element.name} ({element_type}) [{element.start_line}-{element.end_line}]"
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
    FormatterRegistry.register_formatter(CsvFormatter)
    FormatterRegistry.register_formatter(FullFormatter)
    FormatterRegistry.register_formatter(CompactFormatter)

    # Register HTML formatters if available
    try:
        from .html_formatter import (
            HtmlCompactFormatter,
            HtmlFormatter,
            HtmlJsonFormatter,
        )

        FormatterRegistry.register_formatter(HtmlFormatter)
        FormatterRegistry.register_formatter(HtmlJsonFormatter)
        FormatterRegistry.register_formatter(HtmlCompactFormatter)
    except ImportError:
        # HTML formatters not available, skip registration
        pass


# Auto-register built-in formatters when module is imported
register_builtin_formatters()
