#!/usr/bin/env python3
"""
Markdown Language Plugin

Enhanced Markdown-specific parsing and element extraction functionality.
Provides comprehensive support for Markdown elements including headers,
links, code blocks, lists, tables, and other structural elements.
"""

try:
    import tree_sitter

    TREE_SITTER_AVAILABLE = tree_sitter is not None
except ImportError:
    tree_sitter = None
    TREE_SITTER_AVAILABLE = False

from ...plugins.base import ElementExtractor
from ...utils import log_debug
from .private_extraction import MarkdownPrivateExtractionMixin
from .public_extraction import (
    MarkdownBlockExtractionMixin,
    MarkdownInlineExtractionMixin,
    MarkdownModelExtractionMixin,
)

__all__ = [
    "MarkdownElementExtractor",
    "TREE_SITTER_AVAILABLE",
    "log_debug",
    "tree_sitter",
]


class MarkdownElementExtractor(
    MarkdownModelExtractionMixin,
    MarkdownBlockExtractionMixin,
    MarkdownInlineExtractionMixin,
    MarkdownPrivateExtractionMixin,
    ElementExtractor,
):
    """Markdown-specific element extractor with comprehensive feature support."""

    def __init__(self) -> None:
        """Initialize the Markdown element extractor."""
        self.current_file: str = ""
        self.source_code: str = ""
        self.content_lines: list[str] = []

        self._node_text_cache: dict[tuple[int, int], str] = {}
        self._processed_nodes: set[tuple[int, int]] = set()
        self._element_cache: dict[tuple[tuple[int, int], str], object] = {}
        self._file_encoding: str | None = None

        self._extracted_links: set[str] = set()
        self._extracted_images: set[tuple[str, str]] = set()
