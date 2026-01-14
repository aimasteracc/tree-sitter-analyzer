#!/usr/bin/env python3
"""
Unit tests for CachedElementExtractor.

Tests cover:
- Cache initialization and reset
- Source code initialization
- Node text extraction (byte-based and position-based)
- Multi-byte character handling
- Fallback mechanisms
- Edge cases and error handling
"""

from unittest.mock import MagicMock, patch

import pytest


class TestCachedElementExtractorInit:
    """Tests for CachedElementExtractor initialization."""

    def test_init_creates_empty_caches(self):
        """Test that initialization creates empty caches."""
        from tree_sitter_analyzer.plugins.cached_element_extractor import (
            CachedElementExtractor,
        )

        # Create a concrete subclass for testing
        class TestExtractor(CachedElementExtractor):
            def extract_functions(self, tree, source_code):
                return []

            def extract_classes(self, tree, source_code):
                return []

            def extract_variables(self, tree, source_code):
                return []

            def extract_imports(self, tree, source_code):
                return []

        extractor = TestExtractor()

        assert extractor._node_text_cache == {}
        assert extractor.source_code == ""
        assert extractor.content_lines == []
        assert extractor._file_encoding == "utf-8"

    def test_init_inherits_from_element_extractor(self):
        """Test that CachedElementExtractor inherits from ElementExtractor."""
        from tree_sitter_analyzer.plugins.base import ElementExtractor
        from tree_sitter_analyzer.plugins.cached_element_extractor import (
            CachedElementExtractor,
        )

        assert issubclass(CachedElementExtractor, ElementExtractor)


class TestCacheManagement:
    """Tests for cache management methods."""

    @pytest.fixture
    def extractor(self):
        """Create a test extractor instance."""
        from tree_sitter_analyzer.plugins.cached_element_extractor import (
            CachedElementExtractor,
        )

        class TestExtractor(CachedElementExtractor):
            def extract_functions(self, tree, source_code):
                return []

            def extract_classes(self, tree, source_code):
                return []

            def extract_variables(self, tree, source_code):
                return []

            def extract_imports(self, tree, source_code):
                return []

        return TestExtractor()

    def test_reset_caches_clears_node_text_cache(self, extractor):
        """Test that _reset_caches clears node text cache."""
        # Populate cache
        extractor._node_text_cache[(0, 10)] = "test"

        # Reset
        extractor._reset_caches()

        # Verify cache is empty
        assert extractor._node_text_cache == {}

    def test_initialize_source_sets_source_code(self, extractor):
        """Test that _initialize_source sets source code correctly."""
        source = "line1\nline2\nline3"
        extractor._initialize_source(source)

        assert extractor.source_code == source
        assert extractor.content_lines == ["line1", "line2", "line3"]
        assert extractor._file_encoding == "utf-8"

    def test_initialize_source_with_custom_encoding(self, extractor):
        """Test that _initialize_source respects custom encoding."""
        source = "test"
        extractor._initialize_source(source, encoding="latin-1")

        assert extractor._file_encoding == "latin-1"

    def test_initialize_source_resets_caches(self, extractor):
        """Test that _initialize_source resets caches."""
        # Populate cache
        extractor._node_text_cache[(0, 10)] = "test"

        # Initialize new source
        extractor._initialize_source("new source")

        # Cache should be cleared
        assert extractor._node_text_cache == {}

    def test_initialize_source_handles_empty_string(self, extractor):
        """Test that _initialize_source handles empty source code."""
        extractor._initialize_source("")

        assert extractor.source_code == ""
        assert extractor.content_lines == []

    def test_initialize_source_handles_single_line(self, extractor):
        """Test that _initialize_source handles single line without newline."""
        extractor._initialize_source("single line")

        assert extractor.content_lines == ["single line"]


class TestNodeTextExtraction:
    """Tests for node text extraction methods."""

    @pytest.fixture
    def extractor(self):
        """Create a test extractor instance with source code."""
        from tree_sitter_analyzer.plugins.cached_element_extractor import (
            CachedElementExtractor,
        )

        class TestExtractor(CachedElementExtractor):
            def extract_functions(self, tree, source_code):
                return []

            def extract_classes(self, tree, source_code):
                return []

            def extract_variables(self, tree, source_code):
                return []

            def extract_imports(self, tree, source_code):
                return []

        ext = TestExtractor()
        ext._initialize_source("line one\nline two\nline three")
        return ext

    def test_get_node_text_caches_result(self, extractor):
        """Test that _get_node_text_optimized caches results."""
        mock_node = MagicMock()
        mock_node.start_byte = 0
        mock_node.end_byte = 8
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 8)

        # First call
        result1 = extractor._get_node_text_optimized(mock_node, use_byte_offsets=False)

        # Second call should use cache
        result2 = extractor._get_node_text_optimized(mock_node, use_byte_offsets=False)

        assert result1 == result2
        assert (0, 8) in extractor._node_text_cache

    def test_extract_text_by_position_single_line(self, extractor):
        """Test position-based extraction for single line."""
        mock_node = MagicMock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 4)

        result = extractor._extract_text_by_position(mock_node)
        assert result == "line"

    def test_extract_text_by_position_multi_line(self, extractor):
        """Test position-based extraction for multiple lines."""
        mock_node = MagicMock()
        mock_node.start_point = (0, 5)  # "one"
        mock_node.end_point = (1, 4)  # "line"

        result = extractor._extract_text_by_position(mock_node)
        assert result == "one\nline"

    def test_extract_text_by_position_full_line(self, extractor):
        """Test position-based extraction for full line."""
        mock_node = MagicMock()
        mock_node.start_point = (1, 0)
        mock_node.end_point = (1, 8)

        result = extractor._extract_text_by_position(mock_node)
        assert result == "line two"

    def test_extract_text_by_position_boundary_check(self, extractor):
        """Test that out-of-bounds positions return empty string."""
        mock_node = MagicMock()
        mock_node.start_point = (100, 0)  # Out of bounds
        mock_node.end_point = (100, 5)

        result = extractor._extract_text_by_position(mock_node)
        assert result == ""

    def test_extract_text_by_position_negative_start(self, extractor):
        """Test that negative start positions return empty string."""
        mock_node = MagicMock()
        mock_node.start_point = (-1, 0)
        mock_node.end_point = (0, 5)

        result = extractor._extract_text_by_position(mock_node)
        assert result == ""

    def test_extract_text_by_position_empty_content(self):
        """Test extraction with empty content."""
        from tree_sitter_analyzer.plugins.cached_element_extractor import (
            CachedElementExtractor,
        )

        class TestExtractor(CachedElementExtractor):
            def extract_functions(self, tree, source_code):
                return []

            def extract_classes(self, tree, source_code):
                return []

            def extract_variables(self, tree, source_code):
                return []

            def extract_imports(self, tree, source_code):
                return []

        ext = TestExtractor()
        ext._initialize_source("")

        mock_node = MagicMock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 5)

        result = ext._extract_text_by_position(mock_node)
        assert result == ""

    def test_get_node_text_falls_back_to_position(self, extractor):
        """Test that byte extraction falls back to position on failure."""
        mock_node = MagicMock()
        mock_node.start_byte = 0
        mock_node.end_byte = 4
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 4)

        # Mock byte extraction to fail
        with patch.object(
            extractor, "_extract_text_by_bytes", side_effect=Exception("fail")
        ):
            result = extractor._get_node_text_optimized(
                mock_node, use_byte_offsets=True
            )
            assert result == "line"

    def test_column_bounds_validation(self, extractor):
        """Test that column indices are validated."""
        extractor._initialize_source("short")

        mock_node = MagicMock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 1000)  # Beyond line length

        result = extractor._extract_text_by_position(mock_node)

        # Should extract up to actual line length
        assert result == "short"


class TestMultibyteCharacterHandling:
    """Tests for multi-byte character handling."""

    @pytest.fixture
    def extractor(self):
        """Create a test extractor instance."""
        from tree_sitter_analyzer.plugins.cached_element_extractor import (
            CachedElementExtractor,
        )

        class TestExtractor(CachedElementExtractor):
            def extract_functions(self, tree, source_code):
                return []

            def extract_classes(self, tree, source_code):
                return []

            def extract_variables(self, tree, source_code):
                return []

            def extract_imports(self, tree, source_code):
                return []

        return TestExtractor()

    def test_japanese_text_extraction(self, extractor):
        """Test extraction of Japanese text."""
        source = "こんにちは\n世界"
        extractor._initialize_source(source)

        mock_node = MagicMock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 5)

        result = extractor._extract_text_by_position(mock_node)
        assert result == "こんにちは"

    def test_mixed_language_text(self, extractor):
        """Test extraction of mixed language text."""
        source = "Hello 世界 World"
        extractor._initialize_source(source)

        mock_node = MagicMock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 14)

        result = extractor._extract_text_by_position(mock_node)
        assert "Hello" in result
        assert "世界" in result


class TestFallbackMechanisms:
    """Tests for fallback mechanisms."""

    @pytest.fixture
    def extractor(self):
        """Create a test extractor instance."""
        from tree_sitter_analyzer.plugins.cached_element_extractor import (
            CachedElementExtractor,
        )

        class TestExtractor(CachedElementExtractor):
            def extract_functions(self, tree, source_code):
                return []

            def extract_classes(self, tree, source_code):
                return []

            def extract_variables(self, tree, source_code):
                return []

            def extract_imports(self, tree, source_code):
                return []

        ext = TestExtractor()
        ext._initialize_source("test content")
        return ext

    def test_byte_extraction_empty_fallback(self, extractor):
        """Test fallback when byte extraction returns empty."""
        mock_node = MagicMock()
        mock_node.start_byte = 0
        mock_node.end_byte = 4
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 4)

        # Mock byte extraction to return empty
        with patch.object(extractor, "_extract_text_by_bytes", return_value=""):
            result = extractor._get_node_text_optimized(
                mock_node, use_byte_offsets=True
            )
            assert result == "test"

    def test_double_fallback_on_exception(self, extractor):
        """Test double fallback when both methods fail."""
        mock_node = MagicMock()
        mock_node.start_byte = 0
        mock_node.end_byte = 4
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 4)

        # Mock both methods to fail
        with patch.object(
            extractor, "_extract_text_by_bytes", side_effect=Exception("fail")
        ):
            with patch.object(
                extractor, "_extract_text_by_position", side_effect=Exception("fail")
            ):
                result = extractor._get_node_text_optimized(
                    mock_node, use_byte_offsets=True
                )
                assert result == ""


class TestSubclassExtension:
    """Tests for subclass extension patterns."""

    def test_subclass_can_add_custom_cache(self):
        """Test that subclass can add custom caches."""
        from tree_sitter_analyzer.plugins.cached_element_extractor import (
            CachedElementExtractor,
        )

        class CustomExtractor(CachedElementExtractor):
            def __init__(self):
                super().__init__()
                self._custom_cache = {}

            def _reset_caches(self):
                super()._reset_caches()
                self._custom_cache.clear()

            def extract_functions(self, tree, source_code):
                return []

            def extract_classes(self, tree, source_code):
                return []

            def extract_variables(self, tree, source_code):
                return []

            def extract_imports(self, tree, source_code):
                return []

        ext = CustomExtractor()
        ext._custom_cache["key"] = "value"
        ext._node_text_cache[(0, 1)] = "text"

        ext._reset_caches()

        assert ext._custom_cache == {}
        assert ext._node_text_cache == {}
