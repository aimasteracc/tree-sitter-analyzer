"""
Output formatters for tree-sitter-analyzer v2.

This module provides formatters for converting analysis results to different output formats:
- TOON (Token-Oriented Object Notation): LLM-optimized format with 50-70% token reduction
- Markdown: Human-readable format with headings, lists, and tables
- FormatterRegistry: Central registry for managing formatters
"""

from tree_sitter_analyzer_v2.formatters.markdown_formatter import MarkdownFormatter
from tree_sitter_analyzer_v2.formatters.registry import (
    FormatterRegistry,
    get_default_registry,
)
from tree_sitter_analyzer_v2.formatters.toon_formatter import ToonFormatter

__all__ = [
    "MarkdownFormatter",
    "ToonFormatter",
    "FormatterRegistry",
    "get_default_registry",
]
