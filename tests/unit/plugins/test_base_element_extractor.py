#!/usr/bin/env python3
"""
Unit tests for BaseElementExtractor.

Tests cover:
- Cache initialization and reset
- Source code initialization
- Node text extraction (byte-based and position-based)
- Multi-byte character handling
- AST traversal
- Edge cases and error handling
"""

from unittest.mock import MagicMock, patch

import pytest


class TestBaseElementExtractorInit:
    """Tests for BaseElementExtractor initialization."""

    def test_init_creates_empty_caches(self):
        """Test that initialization creates empty caches."""
        from tree_sitter_analyzer.plugins.base_element_extractor import (
            BaseElementExtractor,
        )

        # Create a concrete subclass for testing
        class TestExtractor(BaseElementExtractor):
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
        assert extractor._processed_nodes == set()
        assert extractor._element_cache == {}
        assert extractor.source_code == ""
        assert extractor.content_lines == []
        assert extractor._file_encoding == "utf-8"

    def test_init_inherits_from_element_extractor(self):
        """Test that BaseElementExtractor inherits from ElementExtractor."""
        from tree_sitter_analyzer.plugins.base import ElementExtractor
        from tree_sitter_analyzer.plugins.base_element_extractor import (
            BaseElementExtractor,
        )

        assert issubclass(BaseElementExtractor, ElementExtractor)


class TestCacheManagement:
    """Tests for cache management methods."""

    @pytest.fixture
    def extractor(self):
        """Create a test extractor instance."""
        from tree_sitter_analyzer.plugins.base_element_extractor import (
            BaseElementExtractor,
        )

        class TestExtractor(BaseElementExtractor):
            def extract_functions(self, tree, source_code):
                return []

            def extract_classes(self, tree, source_code):
                return []

            def extract_variables(self, tree, source_code):
                return []

            def extract_imports(self, tree, source_code):
                return []

        return TestExtractor()

    def test_reset_caches_clears_all_caches(self, extractor):
        """Test that _reset_caches clears all caches."""
        # Populate caches
        extractor._node_text_cache[(0, 10)] = "test"
        extractor._processed_nodes.add(123)
        extractor._element_cache[(456, "function")] = {"name": "test"}

        # Reset
        extractor._reset_caches()

        # Verify all caches are empty
        assert extractor._node_text_cache == {}
        assert extractor._processed_nodes == set()
        assert extractor._element_cache == {}

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
        # Populate caches
        extractor._node_text_cache[(0, 10)] = "test"
        extractor._processed_nodes.add(123)

        # Initialize new source
        extractor._initialize_source("new source")

        # Caches should be cleared
        assert extractor._node_text_cache == {}
        assert extractor._processed_nodes == set()

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
        from tree_sitter_analyzer.plugins.base_element_extractor import (
            BaseElementExtractor,
        )

        class TestExtractor(BaseElementExtractor):
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
        from tree_sitter_analyzer.plugins.base_element_extractor import (
            BaseElementExtractor,
        )

        class TestExtractor(BaseElementExtractor):
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


class TestMultibyteCharacterHandling:
    """Tests for multi-byte character handling."""

    @pytest.fixture
    def extractor(self):
        """Create a test extractor instance."""
        from tree_sitter_analyzer.plugins.base_element_extractor import (
            BaseElementExtractor,
        )

        class TestExtractor(BaseElementExtractor):
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


class TestASTTraversal:
    """Tests for AST traversal methods."""

    @pytest.fixture
    def extractor(self):
        """Create a test extractor instance."""
        from tree_sitter_analyzer.plugins.base_element_extractor import (
            BaseElementExtractor,
        )

        class TestExtractor(BaseElementExtractor):
            def extract_functions(self, tree, source_code):
                return []

            def extract_classes(self, tree, source_code):
                return []

            def extract_variables(self, tree, source_code):
                return []

            def extract_imports(self, tree, source_code):
                return []

        ext = TestExtractor()
        ext._initialize_source("test source")
        return ext

    def test_get_container_node_types_returns_set(self, extractor):
        """Test that _get_container_node_types returns a set."""
        result = extractor._get_container_node_types()

        assert isinstance(result, set)
        assert "program" in result
        assert "module" in result
        assert "block" in result

    def test_traverse_with_none_root(self, extractor):
        """Test that traversal handles None root gracefully."""
        results = []
        extractors = {"function_definition": lambda n: {"name": "test"}}

        # Should not raise
        extractor._traverse_and_extract_iterative(None, extractors, results, "function")

        assert results == []

    def test_traverse_extracts_matching_nodes(self, extractor):
        """Test that traversal extracts matching nodes."""
        # Create mock AST
        root = MagicMock()
        root.type = "program"
        root.children = []

        func_node = MagicMock()
        func_node.type = "function_definition"
        func_node.children = []
        root.children.append(func_node)

        results = []
        extractors = {"function_definition": lambda n: {"name": "extracted"}}

        extractor._traverse_and_extract_iterative(root, extractors, results, "function")

        assert len(results) == 1
        assert results[0]["name"] == "extracted"

    def test_traverse_respects_max_depth(self, extractor):
        """Test that traversal respects maximum depth."""
        # Create deeply nested structure
        root = MagicMock()
        root.type = "program"

        current = root
        for _i in range(100):
            child = MagicMock()
            child.type = "block"
            child.children = []
            current.children = [child]
            current = child

        results = []
        extractors = {}

        # Should not raise even with deep nesting
        extractor._traverse_and_extract_iterative(
            root, extractors, results, "test", max_depth=50
        )

    def test_traverse_skips_processed_nodes(self, extractor):
        """Test that traversal skips already processed nodes."""
        root = MagicMock()
        root.type = "program"
        root.children = []

        func_node = MagicMock()
        func_node.type = "function_definition"
        func_node.children = []
        root.children.append(func_node)

        # Pre-mark the node as processed
        extractor._processed_nodes.add(id(func_node))

        results = []
        call_count = [0]

        def counter_extractor(n):
            call_count[0] += 1
            return {"name": "test"}

        extractors = {"function_definition": counter_extractor}

        extractor._traverse_and_extract_iterative(root, extractors, results, "function")

        # Extractor should not have been called
        assert call_count[0] == 0
        assert results == []

    def test_traverse_uses_cache(self, extractor):
        """Test that traversal uses element cache."""
        root = MagicMock()
        root.type = "program"
        root.children = []

        func_node = MagicMock()
        func_node.type = "function_definition"
        func_node.children = []
        root.children.append(func_node)

        # Pre-populate cache
        cached_element = {"name": "cached"}
        extractor._element_cache[(id(func_node), "function")] = cached_element

        results = []
        call_count = [0]

        def counter_extractor(n):
            call_count[0] += 1
            return {"name": "new"}

        extractors = {"function_definition": counter_extractor}

        extractor._traverse_and_extract_iterative(root, extractors, results, "function")

        # Extractor should not have been called (cache hit)
        assert call_count[0] == 0
        assert len(results) == 1
        assert results[0]["name"] == "cached"


class TestAppendElementToResults:
    """Tests for _append_element_to_results helper."""

    @pytest.fixture
    def extractor(self):
        """Create a test extractor instance."""
        from tree_sitter_analyzer.plugins.base_element_extractor import (
            BaseElementExtractor,
        )

        class TestExtractor(BaseElementExtractor):
            def extract_functions(self, tree, source_code):
                return []

            def extract_classes(self, tree, source_code):
                return []

            def extract_variables(self, tree, source_code):
                return []

            def extract_imports(self, tree, source_code):
                return []

        return TestExtractor()

    def test_appends_single_element(self, extractor):
        """Test appending single element."""
        results = []
        extractor._append_element_to_results({"name": "test"}, results)

        assert len(results) == 1
        assert results[0]["name"] == "test"

    def test_extends_list_element(self, extractor):
        """Test extending with list of elements."""
        results = []
        extractor._append_element_to_results([{"name": "a"}, {"name": "b"}], results)

        assert len(results) == 2
        assert results[0]["name"] == "a"
        assert results[1]["name"] == "b"

    def test_ignores_none(self, extractor):
        """Test that None is ignored."""
        results = []
        extractor._append_element_to_results(None, results)

        assert results == []

    def test_ignores_empty_list(self, extractor):
        """Test that empty list is ignored."""
        results = []
        extractor._append_element_to_results([], results)

        assert results == []


class TestComplexityCalculation:
    """Tests for complexity calculation methods."""

    @pytest.fixture
    def extractor(self):
        """Create a test extractor instance."""
        from tree_sitter_analyzer.plugins.base_element_extractor import (
            BaseElementExtractor,
        )

        class TestExtractor(BaseElementExtractor):
            def extract_functions(self, tree, source_code):
                return []

            def extract_classes(self, tree, source_code):
                return []

            def extract_variables(self, tree, source_code):
                return []

            def extract_imports(self, tree, source_code):
                return []

        return TestExtractor()

    def test_get_decision_keywords_returns_set(self, extractor):
        """Test that _get_decision_keywords returns a set."""
        result = extractor._get_decision_keywords()

        assert isinstance(result, set)
        assert "if_statement" in result
        assert "for_statement" in result
        assert "while_statement" in result

    def test_calculate_complexity_base_is_one(self, extractor):
        """Test that base complexity is 1."""
        mock_node = MagicMock()
        mock_node.type = "function_definition"
        mock_node.children = []

        result = extractor._calculate_complexity_optimized(mock_node)

        assert result >= 1

    def test_calculate_complexity_counts_if_statements(self, extractor):
        """Test that complexity increases with if statements."""
        mock_node = MagicMock()
        mock_node.type = "function_definition"

        if_node = MagicMock()
        if_node.type = "if_statement"
        if_node.children = []

        mock_node.children = [if_node]

        result = extractor._calculate_complexity_optimized(mock_node)

        assert result >= 2  # Base 1 + 1 for if

    def test_calculate_complexity_nested_decisions(self, extractor):
        """Test complexity with nested decisions."""
        mock_node = MagicMock()
        mock_node.type = "function_definition"

        if_node = MagicMock()
        if_node.type = "if_statement"

        for_node = MagicMock()
        for_node.type = "for_statement"
        for_node.children = []

        if_node.children = [for_node]
        mock_node.children = [if_node]

        result = extractor._calculate_complexity_optimized(mock_node)

        assert result >= 3  # Base 1 + if + for


class TestPushChildrenToStack:
    """Tests for _push_children_to_stack helper."""

    @pytest.fixture
    def extractor(self):
        """Create a test extractor instance."""
        from tree_sitter_analyzer.plugins.base_element_extractor import (
            BaseElementExtractor,
        )

        class TestExtractor(BaseElementExtractor):
            def extract_functions(self, tree, source_code):
                return []

            def extract_classes(self, tree, source_code):
                return []

            def extract_variables(self, tree, source_code):
                return []

            def extract_imports(self, tree, source_code):
                return []

        return TestExtractor()

    def test_pushes_children_in_reverse_order(self, extractor):
        """Test that children are pushed in reverse order for correct DFS."""
        parent = MagicMock()
        child1 = MagicMock()
        child1.name = "first"
        child2 = MagicMock()
        child2.name = "second"
        parent.children = [child1, child2]

        stack = []
        extractor._push_children_to_stack(parent, 0, stack)

        # Stack should have second child at bottom, first at top (for DFS order)
        assert len(stack) == 2
        # When popping, first child should come out first
        assert stack[-1][0].name == "first"

    def test_handles_empty_children(self, extractor):
        """Test handling of node with no children."""
        parent = MagicMock()
        parent.children = []

        stack = []
        extractor._push_children_to_stack(parent, 0, stack)

        assert stack == []

    def test_handles_none_children(self, extractor):
        """Test handling of node with None children."""
        parent = MagicMock()
        parent.children = None

        stack = []
        # Should not raise
        extractor._push_children_to_stack(parent, 0, stack)

        assert stack == []

    def test_handles_mock_children_without_reversed(self, extractor):
        """Test fallback when reversed() fails on mock."""
        parent = MagicMock()

        # Create a mock that fails on reversed but works with list()
        class NonReversibleList:
            def __init__(self, items):
                self.items = items

            def __iter__(self):
                return iter(self.items)

            def __reversed__(self):
                raise TypeError("Cannot reverse")

        child = MagicMock()
        parent.children = NonReversibleList([child])

        stack = []
        # Should not raise, should fallback
        extractor._push_children_to_stack(parent, 0, stack)

        assert len(stack) == 1


class TestSubclassExtension:
    """Tests for subclass extension patterns."""

    def test_subclass_can_add_custom_cache(self):
        """Test that subclass can add custom caches."""
        from tree_sitter_analyzer.plugins.base_element_extractor import (
            BaseElementExtractor,
        )

        class CustomExtractor(BaseElementExtractor):
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

    def test_subclass_can_override_container_types(self):
        """Test that subclass can extend container types."""
        from tree_sitter_analyzer.plugins.base_element_extractor import (
            BaseElementExtractor,
        )

        class JavaExtractor(BaseElementExtractor):
            def _get_container_node_types(self):
                return super()._get_container_node_types() | {
                    "class_body",
                    "interface_body",
                }

            def extract_functions(self, tree, source_code):
                return []

            def extract_classes(self, tree, source_code):
                return []

            def extract_variables(self, tree, source_code):
                return []

            def extract_imports(self, tree, source_code):
                return []

        ext = JavaExtractor()
        containers = ext._get_container_node_types()

        assert "class_body" in containers
        assert "interface_body" in containers
        assert "program" in containers  # From parent


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.fixture
    def extractor(self):
        """Create a test extractor instance."""
        from tree_sitter_analyzer.plugins.base_element_extractor import (
            BaseElementExtractor,
        )

        class TestExtractor(BaseElementExtractor):
            def extract_functions(self, tree, source_code):
                return []

            def extract_classes(self, tree, source_code):
                return []

            def extract_variables(self, tree, source_code):
                return []

            def extract_imports(self, tree, source_code):
                return []

        return TestExtractor()

    def test_extract_handles_extractor_exception(self, extractor):
        """Test that traversal handles extractor exceptions gracefully."""
        root = MagicMock()
        root.type = "program"
        root.children = []

        func_node = MagicMock()
        func_node.type = "function_definition"
        func_node.children = []
        root.children.append(func_node)

        results = []

        def failing_extractor(n):
            raise ValueError("Extraction failed")

        extractors = {"function_definition": failing_extractor}

        # Should not raise
        extractor._traverse_and_extract_iterative(root, extractors, results, "function")

        # Node should be marked as processed even after failure
        assert id(func_node) in extractor._processed_nodes

    def test_column_bounds_validation(self, extractor):
        """Test that column indices are validated."""
        extractor._initialize_source("short")

        mock_node = MagicMock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 1000)  # Beyond line length

        result = extractor._extract_text_by_position(mock_node)

        # Should extract up to actual line length
        assert result == "short"
