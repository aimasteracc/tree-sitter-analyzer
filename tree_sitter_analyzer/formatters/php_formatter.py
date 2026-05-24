#!/usr/bin/env python3
"""
PHP-specific table formatter.
Follows Java golden master format for consistency.
"""

from typing import Any

from ._php_formatter_helpers import (
    extract_namespace,
    format_compact_signature,
    format_compact_table,
    format_full_table,
    format_signature,
    get_visibility_symbol,
)
from .base_formatter import BaseTableFormatter


class PHPTableFormatter(BaseTableFormatter):
    """Table formatter specialized for PHP, following Java golden master format."""

    def _get_visibility_symbol(self, visibility: str) -> str:
        """Convert visibility to symbol."""
        return get_visibility_symbol(visibility)

    # Format data for output: _format_signature
    def _format_signature(self, method: dict[str, Any]) -> str:
        """Format method signature like Java: ($param:type):returnType."""
        return format_signature(method)

    # Format data for output: _format_compact_signature
    def _format_compact_signature(self, method: dict[str, Any]) -> str:
        """Format compact method signature."""
        return format_compact_signature(method)

    # Extract elements from AST: _extract_namespace
    def _extract_namespace(self, data: dict[str, Any]) -> str:
        """Extract namespace from data."""
        return extract_namespace(data)

    # Format data for output: _format_full_table
    def _format_full_table(self, data: dict[str, Any]) -> str:
        """Full table format for PHP, following Java golden master format."""
        return format_full_table(data)

    # Format data for output: _format_compact_table
    def _format_compact_table(self, data: dict[str, Any]) -> str:
        """Compact table format for PHP, following Java golden master format."""
        return format_compact_table(data)

    # Format data for output: _format_csv
    def _format_csv(self, data: dict[str, Any]) -> str:
        """CSV format for PHP, following Java golden master format."""
        lines = []

        # Header - matching Java format
        lines.append("Type,Name,Signature,Visibility,Lines,Complexity,Doc")

        # Fields
        for field in data.get("fields", []):
            fname = str(field.get("name", "Unknown"))
            parent = field.get("parent_class", "")
            full_name = f"{parent}::{fname}" if parent else fname
            ftype = str(field.get("variable_type", field.get("type", "mixed")))
            sig = f"{full_name}:{ftype}"
            vis = str(field.get("visibility", "public"))
            frange = field.get("line_range", {})
            flines = f"{frange.get('start', 0)}-{frange.get('end', 0)}"
            fdoc = field.get("documentation", "-") or "-"
            lines.append(f"Field,{full_name},{sig},{vis},{flines},,{fdoc}")

        # Methods
        for method in data.get("methods", []):
            mname = str(method.get("name", "Unknown"))
            parent = method.get("parent_class", "")
            full_name = f"{parent}::{mname}" if parent else mname

            sig = self._format_signature(method)
            if method.get("is_static"):
                sig += " [static]"

            vis = str(method.get("visibility", "public"))
            mrange = method.get("line_range", {})
            mlines = f"{mrange.get('start', 0)}-{mrange.get('end', 0)}"
            mcx = method.get("complexity_score", method.get("complexity", 1))
            mdoc = method.get("documentation", "-") or "-"

            entry_type = (
                "Constructor"
                if method.get("is_constructor") or mname.startswith("__construct")
                else "Method"
            )
            lines.append(f"{entry_type},{full_name},{sig},{vis},{mlines},{mcx},{mdoc}")

        return "\n".join(lines)


class PHPFullFormatter(PHPTableFormatter):
    """Full table formatter for PHP"""

    def format(self, data: dict[str, Any]) -> str:
        """Format data as full table"""
        return self._format_full_table(data)


class PHPCompactFormatter(PHPTableFormatter):
    """Compact table formatter for PHP"""

    def format(self, data: dict[str, Any]) -> str:
        """Format data as compact table"""
        return self._format_compact_table(data)


class PHPCSVFormatter(PHPTableFormatter):
    """CSV formatter for PHP"""

    def format(self, data: dict[str, Any]) -> str:
        """Format data as CSV"""
        return self._format_csv(data)
