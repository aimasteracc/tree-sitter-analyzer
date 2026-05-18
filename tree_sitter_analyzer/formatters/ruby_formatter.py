#!/usr/bin/env python3
"""
Ruby-specific table formatter.
Follows Java golden master format for consistency.
"""

from typing import Any

from ._ruby_formatter_helpers import (
    format_compact_signature,
    format_compact_table,
    format_csv,
    format_full_table,
    format_signature,
    get_visibility_symbol,
)
from .base_formatter import BaseTableFormatter


class RubyTableFormatter(BaseTableFormatter):
    """Table formatter specialized for Ruby, following Java golden master format."""

    def _get_visibility_symbol(self, visibility: str) -> str:
        """Convert visibility to symbol."""
        return get_visibility_symbol(visibility)

    def _format_signature(self, method: dict[str, Any]) -> str:
        """Format method signature like Java: (param:type):returnType."""
        return format_signature(method)

    def _format_compact_signature(self, method: dict[str, Any]) -> str:
        """Format compact method signature."""
        return format_compact_signature(method)

    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format for Ruby, following Java golden master format."""
        return format_full_table(data)

    def _format_compact_table(self, data: dict[str, Any]) -> str:
        """Compact table format for Ruby, following Java golden master format."""
        return format_compact_table(data)

    def _format_csv(self, data: dict[str, Any]) -> str:
        """CSV format for Ruby, following Java golden master format."""
        return format_csv(data)


class RubyFullFormatter(RubyTableFormatter):
    """Full table formatter for Ruby"""

    def format(self, data: dict[str, Any]) -> str:
        """Format data as full table"""
        return self._format_full_table(data)


class RubyCompactFormatter(RubyTableFormatter):
    """Compact table formatter for Ruby"""

    def format(self, data: dict[str, Any]) -> str:
        """Format data as compact table"""
        return self._format_compact_table(data)


class RubyCSVFormatter(RubyTableFormatter):
    """CSV formatter for Ruby"""

    def format(self, data: dict[str, Any]) -> str:
        """Format data as CSV"""
        return self._format_csv(data)
