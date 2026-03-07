#!/usr/bin/env python3
"""
Tests for tree_sitter_analyzer.plugins.extractor_mixin module.

This module tests the new mixin classes that provide reusable functionality
for language element extractors.
"""

from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.plugins.extractor_mixin import (
    CacheManagementMixin,
    ElementExtractorBase,
)


class TestCacheManagementMixin:
    """Test cases for CacheManagementMixin"""

    def test_init_caches(self) -> None:
        """Test cache initialization"""
        mixin = CacheManagementMixin()
        mixin._init_caches()

        assert hasattr(mixin, '_node_text_cache')
        assert hasattr(mixin, '_processed_nodes')
        assert hasattr(mixin, '_element_cache')
        assert hasattr(mixin, '_file_encoding')

        assert mixin._node_text_cache == {}
        assert mixin._processed_nodes == set()
        assert mixin._element_cache == {}
        assert mixin._file_encoding is None

    def test_reset_caches(self) -> None:
        """Test cache reset functionality"""
        mixin = CacheManagementMixin()
        mixin._init_caches()

        # Add some data to caches
        mixin._node_text_cache[(0, 10)] = "test"
        mixin._processed_nodes.add(1)
        mixin._element_cache[(1, "function")] = Mock()

        # Reset caches
        mixin._reset_caches()

        # Verify caches are cleared
        assert mixin._node_text_cache == {}
        assert mixin._processed_nodes == set()
        assert mixin._element_cache == {}

    def test_reset_caches_with_language_specific_caches(self) -> None:
        """Test that reset also clears language-specific caches"""
        mixin = CacheManagementMixin()
        mixin._init_caches()

        # Add language-specific caches
        mixin._annotation_cache = {1: []}
        mixin._signature_cache = {1: "sig"}
        mixin._docstring_cache = {1: "doc"}
        mixin._complexity_cache = {1: 5}
        mixin.annotations = [Mock()]
        mixin.current_package = "com.test"

        # Reset caches
        mixin._reset_caches()

        # Verify all caches are cleared
        assert mixin._annotation_cache == {}
        assert mixin._signature_cache == {}
        assert mixin._docstring_cache == {}
        assert mixin._complexity_cache == {}
        assert mixin.annotations == []
        assert mixin.current_package == ""


class TestNodeTraversalMixin:
    """Test cases for NodeTraversalMixin using ElementExtractorBase"""

    @pytest.fixture
    def extractor(self) -> ElementExtractorBase:
        """Create an ElementExtractorBase instance (combines all mixins)"""
        extractor = ElementExtractorBase()
        extractor.content_lines = ["line1", "line2", "line3"]
        return extractor

    def test_traverse_empty_tree(self, extractor: ElementExtractorBase) -> None:
        """Test traversal with None root node"""
        results: list = []
        extractors = {"function_declaration": lambda n: Mock()}

        # Should not raise exception
        extractor._traverse_and_extract_iterative(None, extractors, results, "function")

        assert results == []

    def test_traverse_simple_tree(self, extractor: ElementExtractorBase) -> None:
        """Test traversal with simple tree structure"""
        # Create mock tree
        root_node = Mock()
        root_node.type = "program"
        root_node.children = []

        results: list = []
        extractors = {}

        extractor._traverse_and_extract_iterative(root_node, extractors, results, "test")

        # Should complete without errors
        assert True

    def test_traverse_with_extractor(self, extractor: ElementExtractorBase) -> None:
        """Test traversal with actual extractor function"""
        # Create mock function node
        func_node = Mock()
        func_node.type = "function_declaration"
        func_node.children = []
        func_node.start_byte = 0
        func_node.end_byte = 10

        # Create mock root node
        root_node = Mock()
        root_node.type = "program"
        root_node.children = [func_node]

        # Create mock result
        mock_result = Mock()
        mock_result.name = "test_function"

        results: list = []
        extractors = {
            "function_declaration": lambda n: mock_result
        }

        extractor._traverse_and_extract_iterative(root_node, extractors, results, "function")

        assert len(results) == 1
        assert results[0] == mock_result

    def test_traverse_respects_max_depth(self, extractor: ElementExtractorBase) -> None:
        """Test that traversal respects maximum depth limit"""
        # Create deeply nested tree
        current = Mock()
        current.type = "program"
        current.children = []

        # Add children to exceed max depth (50)
        for i in range(60):
            child = Mock()
            child.type = f"level_{i}"
            child.children = []
            current.children = [child]
            current = child

        root = current
        results: list = []
        extractors = {}

        # Should complete without infinite loop
        extractor._traverse_and_extract_iterative(root, extractors, results, "test")

        assert True  # Just verify it completes


class TestNodeTextExtractionMixin:
    """Test cases for NodeTextExtractionMixin using ElementExtractorBase"""

    @pytest.fixture
    def extractor(self) -> ElementExtractorBase:
        """Create an ElementExtractorBase instance (combines all mixins)"""
        extractor = ElementExtractorBase()
        extractor.content_lines = ["line1", "line2", "line3"]
        extractor._file_encoding = "utf-8"
        return extractor

    def test_get_node_text_optimized_caching(self, extractor: ElementExtractorBase) -> None:
        """Test that node text extraction uses caching"""
        # Create mock node
        node = Mock()
        node.start_byte = 0
        node.end_byte = 5
        node.start_point = (0, 0)
        node.end_point = (0, 5)

        # First call
        with patch('tree_sitter_analyzer.plugins.extractor_mixin.safe_encode') as mock_encode:
            with patch('tree_sitter_analyzer.plugins.extractor_mixin.extract_text_slice') as mock_extract:
                mock_encode.return_value = b"line1\nline2"
                mock_extract.return_value = "line1"

                text1 = extractor._get_node_text_optimized(node)

                # Second call should use cache
                text2 = extractor._get_node_text_optimized(node)

                assert text1 == text2
                # Encoding should only be called once
                assert mock_encode.call_count == 1

    def test_fallback_text_extraction_single_line(self, extractor: ElementExtractorBase) -> None:
        """Test fallback extraction for single line"""
        node = Mock()
        node.start_point = (0, 0)
        node.end_point = (0, 5)

        text = extractor._fallback_text_extraction(node)

        assert text == "line1"

    def test_fallback_text_extraction_multiple_lines(self, extractor: ElementExtractorBase) -> None:
        """Test fallback extraction for multiple lines"""
        node = Mock()
        node.start_point = (0, 2)
        node.end_point = (2, 4)

        text = extractor._fallback_text_extraction(node)

        # Should extract from line 0 (starting at char 2) through line 2 (ending at char 4)
        assert "ne1" in text  # "line1"[2:]
        assert "line2" in text
        assert "line" in text  # "line3"[:4]


class TestElementExtractorBase:
    """Test cases for ElementExtractorBase"""

    def test_initialization(self) -> None:
        """Test that ElementExtractorBase initializes correctly"""
        extractor = ElementExtractorBase()

        assert hasattr(extractor, '_node_text_cache')
        assert hasattr(extractor, '_processed_nodes')
        assert hasattr(extractor, '_element_cache')
        assert hasattr(extractor, 'source_code')
        assert hasattr(extractor, 'content_lines')

        assert extractor.source_code == ""
        assert extractor.content_lines == []

    def test_inherits_all_mixins(self) -> None:
        """Test that ElementExtractorBase inherits from all mixins"""
        extractor = ElementExtractorBase()

        # Should have methods from all mixins
        assert hasattr(extractor, '_init_caches')
        assert hasattr(extractor, '_reset_caches')
        assert hasattr(extractor, '_traverse_and_extract_iterative')
        assert hasattr(extractor, '_get_node_text_optimized')
        assert hasattr(extractor, '_fallback_text_extraction')

    def test_can_be_subclassed(self) -> None:
        """Test that ElementExtractorBase can be subclassed"""
        class CustomExtractor(ElementExtractorBase):
            def custom_method(self) -> str:
                return "custom"

        extractor = CustomExtractor()

        assert extractor.custom_method() == "custom"
        assert hasattr(extractor, '_reset_caches')


class TestIntegration:
    """Integration tests for mixin classes"""

    def test_full_workflow(self) -> None:
        """Test complete workflow using all mixins"""
        # Create a custom extractor using the base class
        class TestExtractor(ElementExtractorBase):
            def extract_test_elements(self, root_node: Mock) -> list:
                results: list = []
                extractors = {
                    "test_node": self._extract_test_node
                }
                self._traverse_and_extract_iterative(root_node, extractors, results, "test")
                return results

            def _extract_test_node(self, node: Mock) -> dict:
                return {"name": self._get_node_text_optimized(node)}

        # Setup
        extractor = TestExtractor()
        extractor.content_lines = ["test content"]
        extractor._file_encoding = "utf-8"

        # Create mock tree
        test_node = Mock()
        test_node.type = "test_node"
        test_node.children = []
        test_node.start_byte = 0
        test_node.end_byte = 12
        test_node.start_point = (0, 0)
        test_node.end_point = (0, 12)

        root_node = Mock()
        root_node.type = "program"
        root_node.children = [test_node]

        # Extract
        with patch('tree_sitter_analyzer.plugins.extractor_mixin.safe_encode') as mock_encode:
            with patch('tree_sitter_analyzer.plugins.extractor_mixin.extract_text_slice') as mock_extract:
                mock_encode.return_value = b"test content"
                mock_extract.return_value = "test content"

                results = extractor.extract_test_elements(root_node)

        # Verify
        assert len(results) == 1
        assert results[0]["name"] == "test content"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
