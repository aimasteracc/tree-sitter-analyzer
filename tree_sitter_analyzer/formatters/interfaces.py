#!/usr/bin/env python3
"""
Formatter Interfaces

Abstract base classes for the formatter system. Extracted to a dedicated module
to break circular dependencies between formatter_registry and html_formatter.
"""

from abc import ABC, abstractmethod

from ..models import CodeElement


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
