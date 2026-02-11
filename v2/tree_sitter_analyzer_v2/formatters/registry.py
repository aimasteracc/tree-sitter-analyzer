"""
Formatter Registry - Central registry for output formatters

This module provides a registry for managing output formatters (TOON, Markdown).

Features:
- Formatter registration
- Formatter retrieval by name
- List available formats
- Thread-safe singleton default registry
"""

import threading
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
    Thread-safe for concurrent access.
    """

    def __init__(self) -> None:
        """Initialize formatter registry."""
        self._lock = threading.Lock()
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

        with self._lock:
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

        with self._lock:
            if format_key not in self._formatters:
                available = ", ".join(sorted(self._formatters.keys()))
                raise ValueError(f"Unknown format: {format_name}. Available formats: {available}")
            return self._formatters[format_key]

    def list_formats(self) -> list[str]:
        """
        List all available format names.

        Returns:
            List of format names
        """
        with self._lock:
            return list(self._formatters.keys())


# Thread-safe singleton default registry
_default_registry: FormatterRegistry | None = None
_singleton_lock = threading.Lock()


def get_default_registry() -> FormatterRegistry:
    """
    Get the default formatter registry singleton (thread-safe).

    Returns:
        Default FormatterRegistry instance
    """
    global _default_registry
    if _default_registry is None:
        with _singleton_lock:
            # Double-checked locking
            if _default_registry is None:
                _default_registry = FormatterRegistry()
    return _default_registry
