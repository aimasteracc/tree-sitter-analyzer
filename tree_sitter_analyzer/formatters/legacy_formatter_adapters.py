#!/usr/bin/env python3
"""
Legacy Formatter Adapters

Adapters to integrate the legacy v1.6.1.4 TableFormatter with the v1.9.4 FormatterRegistry system.
This ensures backward compatibility while maintaining the new architecture.
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from ..constants import (
    ELEMENT_TYPE_CLASS,
    ELEMENT_TYPE_FUNCTION,
    ELEMENT_TYPE_IMPORT,
    ELEMENT_TYPE_PACKAGE,
    ELEMENT_TYPE_VARIABLE,
    get_element_type,
    is_element_of_type,
)
from ..legacy_table_formatter import LegacyTableFormatter
from ..models import CodeElement
from .formatter_registry import IFormatter

logger = logging.getLogger(__name__)


class LegacyFormatterAdapter(IFormatter):
    """
    Base adapter class for legacy table formatters.

    Converts CodeElement lists to the legacy data structure format
    and delegates formatting to LegacyTableFormatter.
    """

    @staticmethod
    def get_format_name() -> str:
        """Return the format name this formatter supports"""
        # This will be overridden in subclasses
        return "legacy"

    def __init__(
        self, format_type: str, language: str = "java", include_javadoc: bool = False
    ):
        """
        Initialize the legacy formatter adapter.

        Args:
            format_type: Format type (full, compact, csv)
            language: Programming language for syntax highlighting
            include_javadoc: Whether to include JavaDoc/documentation
        """
        self.format_type = format_type
        self.language = language
        self.include_javadoc = include_javadoc
        self.formatter = LegacyTableFormatter(
            format_type=format_type, language=language, include_javadoc=include_javadoc
        )

    def format(self, elements: list[CodeElement]) -> str:
        """
        Format CodeElement list using legacy formatter.

        Args:
            elements: List of CodeElement objects to format

        Returns:
            Formatted string in legacy v1.6.1.4 format
        """
        # Convert CodeElement list to legacy data structure
        legacy_data = self._convert_to_legacy_format(elements)

        # Use legacy formatter
        result = self.formatter.format_structure(legacy_data)

        # Ensure Unix-style line endings for consistency
        result = result.replace("\r\n", "\n").replace("\r", "\n")

        return result

    def _convert_to_legacy_format(self, elements: list[CodeElement]) -> dict[str, Any]:
        """
        Convert CodeElement list to legacy data structure format.

        Args:
            elements: List of CodeElement objects

        Returns:
            Dictionary in legacy format expected by LegacyTableFormatter
        """
        # Extract file_path from first element if available
        file_path = "Unknown"
        if elements and hasattr(elements[0], "file_path"):
            file_path = elements[0].file_path or "Unknown"

        # Initialize legacy data structure
        legacy_data: dict[str, Any] = {
            "file_path": file_path,
            "package": {"name": "unknown"},
            "imports": [],
            "classes": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0, "class_count": 0},
        }

        # Process elements by type
        package_name = "unknown"
        for element in elements:
            # Use is_element_of_type helper for accurate type checking
            # Also handle legacy "method" and "field" type names
            element_type = get_element_type(element)

            if is_element_of_type(element, ELEMENT_TYPE_PACKAGE):
                package_name = element.name
                legacy_data["package"]["name"] = package_name
            elif is_element_of_type(element, ELEMENT_TYPE_CLASS):
                legacy_data["classes"].append(self._convert_class_element(element))
            elif (
                is_element_of_type(element, ELEMENT_TYPE_FUNCTION)
                or element_type == "method"
            ):
                legacy_data["methods"].append(self._convert_method_element(element))
            elif (
                is_element_of_type(element, ELEMENT_TYPE_VARIABLE)
                or element_type == "field"
            ):
                legacy_data["fields"].append(self._convert_field_element(element))
            elif is_element_of_type(element, ELEMENT_TYPE_IMPORT):
                legacy_data["imports"].append(self._convert_import_element(element))

        # Update statistics
        legacy_data["statistics"]["method_count"] = len(legacy_data["methods"])
        legacy_data["statistics"]["field_count"] = len(legacy_data["fields"])
        legacy_data["statistics"]["class_count"] = len(legacy_data["classes"])

        # If no classes found, create a default one for proper formatting
        if not legacy_data["classes"] and (
            legacy_data["methods"] or legacy_data["fields"]
        ):
            legacy_data["classes"] = [
                {
                    "name": "Unknown",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 100},
                }
            ]

        return legacy_data

    def _convert_class_element(self, element: CodeElement) -> dict[str, Any]:
        """Convert class CodeElement to legacy format"""
        return {
            "name": element.name,
            "type": getattr(element, "class_type", "class"),
            "visibility": getattr(element, "visibility", "public"),
            "line_range": {"start": element.start_line, "end": element.end_line},
            "modifiers": getattr(element, "modifiers", []),
        }

    def _convert_method_element(self, element: CodeElement) -> dict[str, Any]:
        """Convert method CodeElement to legacy format"""
        return {
            "name": element.name,
            "visibility": getattr(element, "visibility", "public"),
            "return_type": getattr(element, "return_type", "void"),
            "parameters": getattr(element, "parameters", []),
            "line_range": {"start": element.start_line, "end": element.end_line},
            "is_constructor": getattr(element, "is_constructor", False),
            "is_static": getattr(element, "is_static", False),
            "modifiers": getattr(element, "modifiers", []),
            "complexity_score": getattr(element, "complexity_score", 0),
            "javadoc": getattr(element, "documentation", ""),
        }

    def _convert_field_element(self, element: CodeElement) -> dict[str, Any]:
        """Convert field CodeElement to legacy format"""
        return {
            "name": element.name,
            "type": getattr(element, "field_type", "Object"),
            "visibility": getattr(element, "visibility", "private"),
            "line_range": {"start": element.start_line, "end": element.end_line},
            "modifiers": getattr(element, "modifiers", []),
            "javadoc": getattr(element, "documentation", ""),
        }

    def _convert_import_element(self, element: CodeElement) -> dict[str, Any]:
        """Convert import CodeElement to legacy format"""
        return {
            "statement": getattr(element, "import_statement", f"import {element.name}")
        }


class LegacyFullFormatter(LegacyFormatterAdapter):
    """Legacy full formatter producing Markdown tables"""

    def __init__(self, language: str = "java", include_javadoc: bool = False):
        super().__init__("full", language, include_javadoc)

    @staticmethod
    def get_format_name() -> str:
        return "full"


class LegacyCompactFormatter(LegacyFormatterAdapter):
    """Legacy compact formatter with complexity scores"""

    def __init__(self, language: str = "java", include_javadoc: bool = False):
        super().__init__("compact", language, include_javadoc)

    @staticmethod
    def get_format_name() -> str:
        return "compact"


class LegacyCsvFormatter(LegacyFormatterAdapter):
    """Legacy CSV formatter with simple structure"""

    def __init__(self, language: str = "java", include_javadoc: bool = False):
        super().__init__("csv", language, include_javadoc)

    @staticmethod
    def get_format_name() -> str:
        return "csv"
