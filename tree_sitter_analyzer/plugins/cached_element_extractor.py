#!/usr/bin/env python3
"""
Cached Element Extractor

Minimal base class providing basic caching and text extraction.
Suitable for all language types as a foundation.
Provides only essential functionality without imposing heavy machinery.
"""

from abc import ABC
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tree_sitter

from ..encoding_utils import extract_text_slice, safe_encode
from ..utils import log_error
from .base import ElementExtractor


class CachedElementExtractor(ElementExtractor, ABC):
    """
    Minimal base class providing basic caching and text extraction.

    Suitable for all language types as a foundation.
    Provides only essential functionality without imposing heavy machinery.
    """

    def __init__(self) -> None:
        """Initialize the cached element extractor."""
        super().__init__()

        # Minimal caching - only node text
        self._node_text_cache: dict[tuple[int, int], str] = {}

        # Source code management
        self.source_code: str = ""
        self.content_lines: list[str] = []
        self._file_encoding: str = "utf-8"

    def _reset_caches(self) -> None:
        """Reset performance caches - call before analyzing new file."""
        self._node_text_cache.clear()

    def _initialize_source(self, source_code: str, encoding: str = "utf-8") -> None:
        """
        Initialize source code for processing.

        Args:
            source_code: Source code content to process
            encoding: File encoding (default: utf-8)
        """
        self.source_code = source_code
        self.content_lines = source_code.split("\n") if source_code else []
        self._file_encoding = encoding
        self._reset_caches()

    def _get_node_text_optimized(
        self,
        node: "tree_sitter.Node",
        use_byte_offsets: bool = True,
    ) -> str:
        """
        Extract text from AST node with caching.

        Uses position-based cache keys (start_byte, end_byte) for deterministic
        behavior across test runs.

        Args:
            node: Tree-sitter AST node
            use_byte_offsets: If True, use byte-based extraction (recommended for UTF-8).
                             If False, fall back to line/column-based extraction.

        Returns:
            Extracted text string, or empty string on error

        Performance:
            - First call: O(n) where n is text length
            - Subsequent calls with same node position: O(1) cache lookup
        """
        cache_key = (node.start_byte, node.end_byte)

        if cache_key in self._node_text_cache:
            return self._node_text_cache[cache_key]

        text = ""
        try:
            if use_byte_offsets:
                text = self._extract_text_by_bytes(node)
            else:
                text = self._extract_text_by_position(node)

            # If byte extraction returns empty, try position-based fallback
            if not text and use_byte_offsets:
                text = self._extract_text_by_position(node)

        except Exception as e:
            log_error(f"Node text extraction failed: {e}")
            # Try fallback on error
            try:
                text = self._extract_text_by_position(node)
            except Exception:
                text = ""

        self._node_text_cache[cache_key] = text
        return text

    def _extract_text_by_bytes(self, node: "tree_sitter.Node") -> str:
        """
        Extract text using byte offsets (UTF-8 optimized).

        Args:
            node: Tree-sitter AST node

        Returns:
            Extracted text string
        """
        content_bytes = safe_encode("\n".join(self.content_lines), self._file_encoding)
        return extract_text_slice(
            content_bytes,
            node.start_byte,
            node.end_byte,
            self._file_encoding,
        )

    def _extract_text_by_position(self, node: "tree_sitter.Node") -> str:
        """
        Extract text using line/column positions (fallback method).

        Args:
            node: Tree-sitter AST node

        Returns:
            Extracted text string
        """
        start_point = node.start_point
        end_point = node.end_point

        # Boundary validation
        if not self.content_lines:
            return ""

        if start_point[0] < 0 or start_point[0] >= len(self.content_lines):
            return ""

        if end_point[0] < 0 or end_point[0] >= len(self.content_lines):
            return ""

        # Single line extraction
        if start_point[0] == end_point[0]:
            line = self.content_lines[start_point[0]]
            start_col = max(0, min(start_point[1], len(line)))
            end_col = max(start_col, min(end_point[1], len(line)))
            return str(line[start_col:end_col])

        # Multi-line extraction
        lines = []
        for i in range(start_point[0], end_point[0] + 1):
            if i >= len(self.content_lines):
                break

            line = self.content_lines[i]
            if i == start_point[0]:
                # First line: from start column to end
                start_col = max(0, min(start_point[1], len(line)))
                lines.append(line[start_col:])
            elif i == end_point[0]:
                # Last line: from beginning to end column
                end_col = max(0, min(end_point[1], len(line)))
                lines.append(line[:end_col])
            else:
                # Middle lines: entire line
                lines.append(line)

        return "\n".join(lines)
