#!/usr/bin/env python3
"""
Unit tests for MarkupLanguageExtractor.

Tests cover:
- Initialization and cache management
- Position-based tracking (vs object ID tracking)
- Simple recursive traversal
- Node processing helpers
- Lightweight design validation
- Edge cases and error handling
"""

from unittest.mock import MagicMock

import pytest


class TestMarkupLanguageExtractorInit:
    """Tests for MarkupLanguageExtractor initialization."""

    def test_init_creates_position_based_tracking(self):
        """Test that initialization creates position-based tracking."""
        from tree_sitter_analyzer.plugins.markup_language_extractor import (
            MarkupLanguageExtractor,
        )

        class TestExtractor(MarkupLanguageExtractor):
            def extract_functions(self, tree, source_code):
                return []

            def extract_classes(self, tree, source_code):
                return []

            def extract_variables(self, tree, source_code):
                return []

            def extract_imports(self, tree, source_code):
                return []

        extractor = TestExtractor()

        # Check parent class caches
        assert extractor._node_text_cache == {}
        assert extractor.source_code == ""

        # Check markup-specific tracking (position-based)
        assert extractor._processed_nodes == set()
        assert isinstance(extractor._processed_nodes, set)

    def test_init_inherits_from_cached_element_extractor(self):
        """Test that MarkupLanguageExtractor inherits from CachedElementExtractor."""
        from tree_sitter_analyzer.plugins.cached_element_extractor import (
            CachedElementExtractor,
        )
        from tree_sitter_analyzer.plugins.markup_language_extractor import (
            MarkupLanguageExtractor,
        )

        assert issubclass(MarkupLanguageExtractor, CachedElementExtractor)


class TestCacheManagement:
    """Tests for cache management methods."""

    @pytest.fixture
    def extractor(self):
        """Create a test extractor instance."""
        from tree_sitter_analyzer.plugins.markup_language_extractor import (
            MarkupLanguageExtractor,
        )

        class TestExtractor(MarkupLanguageExtractor):
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
        """Test that _reset_caches clears all caches including position tracking."""
        # Populate caches
        extractor._node_text_cache[(0, 10)] = "test"
        extractor._processed_nodes.add((100, 200))

        # Reset
        extractor._reset_caches()

        # Verify all caches are empty
        assert extractor._node_text_cache == {}
        assert extractor._processed_nodes == set()


class TestPositionBasedTracking:
    """Tests for position-based tracking (vs object ID tracking)."""

    @pytest.fixture
    def extractor(self):
        """Create a test extractor instance."""
        from tree_sitter_analyzer.plugins.markup_language_extractor import (
            MarkupLanguageExtractor,
        )

        class TestExtractor(MarkupLanguageExtractor):
            def extract_functions(self, tree, source_code):
                return []

            def extract_classes(self, tree, source_code):
                return []

            def extract_variables(self, tree, source_code):
                return []

            def extract_imports(self, tree, source_code):
                return []

        return TestExtractor()

    def test_is_node_processed_uses_position(self, extractor):
        """Test that _is_node_processed uses position-based tracking."""
        mock_node = MagicMock()
        mock_node.start_byte = 10
        mock_node.end_byte = 20

        # Initially not processed
        assert not extractor._is_node_processed(mock_node)

        # Mark as processed
        extractor._mark_node_processed(mock_node)

        # Now should be processed
        assert extractor._is_node_processed(mock_node)

    def test_mark_node_processed_uses_position(self, extractor):
        """Test that _mark_node_processed uses position-based tracking."""
        mock_node = MagicMock()
        mock_node.start_byte = 10
        mock_node.end_byte = 20

        extractor._mark_node_processed(mock_node)

        # Check that position tuple is in the set
        assert (10, 20) in extractor._processed_nodes

    def test_position_tracking_vs_object_id(self, extractor):
        """Test that position tracking differs from object ID tracking."""
        # Create two different node objects with same position
        node1 = MagicMock()
        node1.start_byte = 10
        node1.end_byte = 20

        node2 = MagicMock()
        node2.start_byte = 10
        node2.end_byte = 20

        # Different object IDs
        assert id(node1) != id(node2)

        # Mark first node as processed
        extractor._mark_node_processed(node1)

        # Second node should also be considered processed (same position)
        assert extractor._is_node_processed(node2)

    def test_different_positions_tracked_separately(self, extractor):
        """Test that different positions are tracked separately."""
        node1 = MagicMock()
        node1.start_byte = 10
        node1.end_byte = 20

        node2 = MagicMock()
        node2.start_byte = 30
        node2.end_byte = 40

        extractor._mark_node_processed(node1)

        assert extractor._is_node_processed(node1)
        assert not extractor._is_node_processed(node2)


class TestRecursiveTraversal:
    """Tests for simple recursive traversal."""

    @pytest.fixture
    def extractor(self):
        """Create a test extractor instance."""
        from tree_sitter_analyzer.plugins.markup_language_extractor import (
            MarkupLanguageExtractor,
        )

        class TestExtractor(MarkupLanguageExtractor):
            def extract_functions(self, tree, source_code):
                return []

            def extract_classes(self, tree, source_code):
                return []

            def extract_variables(self, tree, source_code):
                return []

            def extract_imports(self, tree, source_code):
                return []

        return TestExtractor()

    def test_traverse_nodes_yields_root_first(self, extractor):
        """Test that traversal yields root node first (pre-order)."""
        root = MagicMock()
        root.type = "document"
        root.children = []

        nodes = list(extractor._traverse_nodes(root))

        assert len(nodes) == 1
        assert nodes[0] == root

    def test_traverse_nodes_yields_all_descendants(self, extractor):
        """Test that traversal yields all descendant nodes."""
        # Create tree structure
        root = MagicMock()
        root.type = "document"

        child1 = MagicMock()
        child1.type = "element"
        child1.children = []

        child2 = MagicMock()
        child2.type = "element"
        child2.children = []

        root.children = [child1, child2]

        nodes = list(extractor._traverse_nodes(root))

        assert len(nodes) == 3
        assert nodes[0] == root
        assert child1 in nodes
        assert child2 in nodes

    def test_traverse_nodes_handles_nested_structure(self, extractor):
        """Test that traversal handles nested structures."""
        # Create nested tree
        root = MagicMock()
        root.type = "document"

        child = MagicMock()
        child.type = "div"

        grandchild = MagicMock()
        grandchild.type = "span"
        grandchild.children = []

        child.children = [grandchild]
        root.children = [child]

        nodes = list(extractor._traverse_nodes(root))

        assert len(nodes) == 3
        assert nodes[0] == root
        assert nodes[1] == child
        assert nodes[2] == grandchild

    def test_traverse_nodes_handles_no_children(self, extractor):
        """Test that traversal handles nodes without children."""
        root = MagicMock()
        root.type = "text"
        # No children attribute

        nodes = list(extractor._traverse_nodes(root))

        assert len(nodes) == 1
        assert nodes[0] == root

    def test_traverse_nodes_handles_empty_children(self, extractor):
        """Test that traversal handles empty children list."""
        root = MagicMock()
        root.type = "element"
        root.children = []

        nodes = list(extractor._traverse_nodes(root))

        assert len(nodes) == 1
        assert nodes[0] == root

    def test_traverse_nodes_pre_order_traversal(self, extractor):
        """Test that traversal is pre-order (parent before children)."""
        root = MagicMock()
        root.name = "root"

        child = MagicMock()
        child.name = "child"
        child.children = []

        root.children = [child]

        nodes = list(extractor._traverse_nodes(root))

        # Root should come before child
        assert nodes[0].name == "root"
        assert nodes[1].name == "child"


class TestLightweightDesign:
    """Tests validating lightweight design characteristics."""

    def test_no_iterative_traversal_method(self):
        """Test that MarkupLanguageExtractor doesn't have iterative traversal."""
        from tree_sitter_analyzer.plugins.markup_language_extractor import (
            MarkupLanguageExtractor,
        )

        # Should not have the heavy iterative method from ProgrammingLanguageExtractor
        assert not hasattr(MarkupLanguageExtractor, "_traverse_and_extract_iterative")

    def test_no_complexity_calculation(self):
        """Test that MarkupLanguageExtractor doesn't have complexity calculation."""
        from tree_sitter_analyzer.plugins.markup_language_extractor import (
            MarkupLanguageExtractor,
        )

        # Should not have complexity calculation methods
        assert not hasattr(MarkupLanguageExtractor, "_calculate_complexity_optimized")
        assert not hasattr(MarkupLanguageExtractor, "_get_decision_keywords")

    def test_no_element_cache(self):
        """Test that MarkupLanguageExtractor doesn't have element cache."""
        from tree_sitter_analyzer.plugins.markup_language_extractor import (
            MarkupLanguageExtractor,
        )

        class TestExtractor(MarkupLanguageExtractor):
            def extract_functions(self, tree, source_code):
                return []

            def extract_classes(self, tree, source_code):
                return []

            def extract_variables(self, tree, source_code):
                return []

            def extract_imports(self, tree, source_code):
                return []

        extractor = TestExtractor()

        # Should not have element cache (programming language feature)
        assert not hasattr(extractor, "_element_cache")

    def test_no_container_node_types(self):
        """Test that MarkupLanguageExtractor doesn't have container node types."""
        from tree_sitter_analyzer.plugins.markup_language_extractor import (
            MarkupLanguageExtractor,
        )

        # Should not have container node type method
        assert not hasattr(MarkupLanguageExtractor, "_get_container_node_types")


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.fixture
    def extractor(self):
        """Create a test extractor instance."""
        from tree_sitter_analyzer.plugins.markup_language_extractor import (
            MarkupLanguageExtractor,
        )

        class TestExtractor(MarkupLanguageExtractor):
            def extract_functions(self, tree, source_code):
                return []

            def extract_classes(self, tree, source_code):
                return []

            def extract_variables(self, tree, source_code):
                return []

            def extract_imports(self, tree, source_code):
                return []

        return TestExtractor()

    def test_traverse_handles_circular_reference_protection(self, extractor):
        """Test that position-based tracking prevents infinite loops."""
        # Create a mock circular structure
        root = MagicMock()
        root.start_byte = 0
        root.end_byte = 100
        root.type = "document"

        # In real tree-sitter, this wouldn't happen, but test the protection
        child = MagicMock()
        child.start_byte = 10
        child.end_byte = 50
        child.type = "element"
        child.children = []

        root.children = [child]

        # Traverse and collect nodes
        nodes = list(extractor._traverse_nodes(root))

        # Should complete without infinite loop
        assert len(nodes) == 2

    def test_mark_processed_with_same_position_multiple_times(self, extractor):
        """Test marking same position multiple times is idempotent."""
        node = MagicMock()
        node.start_byte = 10
        node.end_byte = 20

        extractor._mark_node_processed(node)
        extractor._mark_node_processed(node)
        extractor._mark_node_processed(node)

        # Should only have one entry
        assert len(extractor._processed_nodes) == 1
        assert (10, 20) in extractor._processed_nodes


class TestComparisonWithProgrammingExtractor:
    """Tests comparing MarkupLanguageExtractor with ProgrammingLanguageExtractor."""

    def test_tracking_mechanism_difference(self):
        """Test that tracking mechanisms differ between markup and programming."""
        from tree_sitter_analyzer.plugins.markup_language_extractor import (
            MarkupLanguageExtractor,
        )
        from tree_sitter_analyzer.plugins.programming_language_extractor import (
            ProgrammingLanguageExtractor,
        )

        class MarkupExtractor(MarkupLanguageExtractor):
            def extract_functions(self, tree, source_code):
                return []

            def extract_classes(self, tree, source_code):
                return []

            def extract_variables(self, tree, source_code):
                return []

            def extract_imports(self, tree, source_code):
                return []

        class ProgrammingExtractor(ProgrammingLanguageExtractor):
            def extract_functions(self, tree, source_code):
                return []

            def extract_classes(self, tree, source_code):
                return []

            def extract_variables(self, tree, source_code):
                return []

            def extract_imports(self, tree, source_code):
                return []

        markup = MarkupExtractor()
        programming = ProgrammingExtractor()

        # Both have _processed_nodes but different types
        assert hasattr(markup, "_processed_nodes")
        assert hasattr(programming, "_processed_nodes")

        # Markup uses position tuples, Programming uses object IDs
        node = MagicMock()
        node.start_byte = 10
        node.end_byte = 20

        markup._mark_node_processed(node)
        programming._processed_nodes.add(id(node))

        # Markup stores tuple, Programming stores int
        markup_key = list(markup._processed_nodes)[0]
        programming_key = list(programming._processed_nodes)[0]

        assert isinstance(markup_key, tuple)
        assert isinstance(programming_key, int)

    def test_feature_set_difference(self):
        """Test that feature sets differ appropriately."""
        from tree_sitter_analyzer.plugins.markup_language_extractor import (
            MarkupLanguageExtractor,
        )
        from tree_sitter_analyzer.plugins.programming_language_extractor import (
            ProgrammingLanguageExtractor,
        )

        # Markup has simple traversal
        assert hasattr(MarkupLanguageExtractor, "_traverse_nodes")

        # Programming has complex traversal
        assert hasattr(ProgrammingLanguageExtractor, "_traverse_and_extract_iterative")

        # Programming has complexity calculation
        assert hasattr(ProgrammingLanguageExtractor, "_calculate_complexity_optimized")

        # Markup doesn't have complexity calculation
        assert not hasattr(MarkupLanguageExtractor, "_calculate_complexity_optimized")
