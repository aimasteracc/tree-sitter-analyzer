"""
Formatter Registry - Central registry for output formatters

This module provides a registry for managing output formatters (TOON, Markdown).

Features:
- Formatter registration
- Formatter retrieval by name
- List available formats
- Singleton default registry
"""

from typing import Any, Protocol


class Formatter(Protocol):
    """Protocol for formatter classes."""

    def format(self, data: Any) -> str:
        """Format data to string."""
        ...


class FormatterRegistry:
    """
    Registry for output formatters.

    Manages registration and retrieval of formatters by name.
    """

    def __init__(self) -> None:
        """Initialize formatter registry."""
        self._formatters: dict[str, Formatter] = {}
        self._register_default_formatters()

    def _register_default_formatters(self) -> None:
        """Register default formatters (TOON, Markdown, and Summary)."""
        from tree_sitter_analyzer_v2.formatters.markdown_formatter import MarkdownFormatter
        from tree_sitter_analyzer_v2.formatters.summary_formatter import SummaryFormatter
        from tree_sitter_analyzer_v2.formatters.toon_formatter import ToonFormatter

        # Register TOON formatter
        self._formatters["toon"] = ToonFormatter()

        # Register Markdown formatter
        self._formatters["markdown"] = MarkdownFormatter()

        # Register Summary formatter
        self._formatters["summary"] = SummaryFormatter()

    def register(self, name: str, formatter: Formatter) -> None:
        """
        Register a formatter.

        Args:
            name: Format name (e.g., "toon", "markdown")
            formatter: Formatter instance

        Raises:
            ValueError: If name is empty or formatter is None
        """
        if not name:
            raise ValueError("Format name cannot be empty")
        if formatter is None:
            raise ValueError("Formatter cannot be None")

        self._formatters[name.lower()] = formatter

    def get(self, format_name: str) -> Formatter:
        """
        Get formatter by name.

        Args:
            format_name: Format name (case-insensitive)

        Returns:
            Formatter instance

        Raises:
            ValueError: If format name is unknown
        """
        if not format_name:
            raise ValueError("Format name cannot be empty")

        format_key = format_name.lower()

        if format_key not in self._formatters:
            available = ", ".join(self.list_formats())
            raise ValueError(f"Unknown format: {format_name}. Available formats: {available}")

        return self._formatters[format_key]

    def list_formats(self) -> list[str]:
        """
        List all available format names.

        Returns:
            List of format names
        """
        return list(self._formatters.keys())


# Singleton default registry
_default_registry: FormatterRegistry | None = None


def get_default_registry() -> FormatterRegistry:
    """
    Get the default formatter registry singleton.

    Returns:
        Default FormatterRegistry instance
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = FormatterRegistry()
    return _default_registry
