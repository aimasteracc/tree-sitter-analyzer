#!/usr/bin/env python3
"""
Formatter Module

Provides unified formatter architecture for code analysis output.

Primary Entry Point:
    FormatterRegistry - Unified registry for all formatters

Usage:
    from tree_sitter_analyzer.formatters import FormatterRegistry

    # Get formatter for a specific language and format type
    formatter = FormatterRegistry.get_formatter_for_language("java", "full")
    output = formatter.format_structure(analysis_data)

    # Get generic format-based formatter
    formatter = FormatterRegistry.get_formatter("json")
    output = formatter.format(elements)

Backward Compatibility:
    The compat module provides deprecated wrappers for old APIs:
    - create_table_formatter() -> FormatterRegistry.get_formatter_for_language()
    - TableFormatterFactory -> FormatterRegistry
    - LanguageFormatterFactory -> FormatterRegistry
    - FormatterSelector -> FormatterRegistry
"""

from .formatter_registry import (
    CompactFormatter,
    CsvFormatter,
    FormatterRegistry,
    FullFormatter,
    IFormatter,
    IStructureFormatter,
    JsonFormatter,
)

__all__ = [
    # Primary API
    "FormatterRegistry",
    "IFormatter",
    "IStructureFormatter",
    # Built-in formatters
    "JsonFormatter",
    "CsvFormatter",
    "FullFormatter",
    "CompactFormatter",
]
