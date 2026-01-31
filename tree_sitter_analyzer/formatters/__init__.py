#!/usr/bin/env python3
"""
Formatter Module - Unified Formatter Architecture

This module provides a unified formatter architecture for code analysis output,
serving as the primary entry point for all formatting operations.

Optimized with:
- Complete type hints (PEP 484)
- Clean public API design
- Comprehensive documentation in English

Features:
- Unified FormatterRegistry for all formatters
- Language-specific formatter support
- Multiple output formats (full, compact, CSV, TOON)
- Extensible formatter plugin architecture
- Type-safe operations (PEP 484)

Primary Entry Point:
    FormatterRegistry - Unified registry for all formatters

Usage:
    >>> from tree_sitter_analyzer.formatters import FormatterRegistry
    >>>
    >>> # Get formatter for a specific language and format type
    >>> formatter = FormatterRegistry.get_formatter_for_language("java", "full")
    >>> output = formatter.format_structure(analysis_data)
    >>>
    >>> # Get generic format-based formatter
    >>> formatter = FormatterRegistry.get_formatter("json")
    >>> output = formatter.format(elements)

Backward Compatibility:
    The compat module provides deprecated wrappers for old APIs:
    - create_table_formatter() -> FormatterRegistry.get_formatter_for_language()
    - TableFormatterFactory -> FormatterRegistry
    - LanguageFormatterFactory -> FormatterRegistry
    - FormatterSelector -> FormatterRegistry

Author: aisheng.yu
Version: 1.10.5
Date: 2026-01-28
"""

from .formatter_registry import (
    FormatterRegistry,
    FullFormatter,
    IFormatter,
    IStructureFormatter,
)

__all__ = [
    # Primary API
    "FormatterRegistry",
    "IFormatter",
    "IStructureFormatter",
    # Built-in formatters
    "FullFormatter",
]
