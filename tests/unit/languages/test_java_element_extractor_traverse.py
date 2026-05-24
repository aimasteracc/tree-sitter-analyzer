"""Java element extractor traverse/process tests — extracted from test_java_element_extractor_optimized."""

from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor
from tree_sitter_analyzer.models import Class, Function, Variable


class TestJavaElementExtractorTraverse:
    """Test Java element extractor traverse and batch processing."""

    @pytest.fixture
    def extractor(self):
        return JavaElementExtractor()

    def test_traverse_and_extract_iterative(self, extractor):
        """Test iterative traversal and extraction"""
        mock_root = Mock()
        mock_child1 = Mock()
        mock_child1.type = "method_declaration"
        mock_child1.children = []

        mock_child2 = Mock()
        mock_child2.type = "class_declaration"
        mock_child2.children = []

        mock_root.children = [mock_child1, mock_child2]

        mock_method_extractor = Mock()
        mock_method_extractor.return_value = Function(
            name="test_method",
            start_line=1,
            end_line=3,
            raw_text="public void test_method() {}",
            language="java",
        )

        mock_class_extractor = Mock()
        mock_class_extractor.return_value = Class(
            name="TestClass",
            start_line=5,
            end_line=10,
            raw_text="public class TestClass {}",
            language="java",
        )

        extractors = {
            "method_declaration": mock_method_extractor,
            "class_declaration": mock_class_extractor,
        }

        results = []
        extractor._traverse_and_extract_iterative(
            mock_root, extractors, results, "mixed"
        )

        assert len(results) == 2
        assert isinstance(results[0], Function)
        assert isinstance(results[1], Class)

    def test_traverse_and_extract_iterative_with_caching(self, extractor):
        """Test iterative traversal with caching"""
        mock_root = Mock()
        mock_child = Mock()
        mock_child.type = "method_declaration"
        mock_child.children = []
        mock_root.children = [mock_child]

        node_id = id(mock_child)
        cache_key = (node_id, "method")
        cached_method = Function(
            name="cached_method",
            start_line=1,
            end_line=2,
            raw_text="public void cached_method() {}",
            language="java",
        )
        extractor._element_cache[cache_key] = cached_method

        extractors = {"method_declaration": Mock()}
        results = []

        extractor._traverse_and_extract_iterative(
            mock_root, extractors, results, "method"
        )

        assert len(results) == 1
        assert results[0] == cached_method
        assert extractors["method_declaration"].call_count == 0

    def test_traverse_and_extract_iterative_field_batching(self, extractor):
        """Test field batching in iterative traversal"""
        mock_root = Mock()

        field_nodes = []
        for _i in range(15):
            field_node = Mock()
            field_node.type = "field_declaration"
            field_node.children = []
            field_nodes.append(field_node)

        mock_root.children = field_nodes

        def mock_field_extractor(node):
            return [
                Variable(
                    name=f"field_{id(node)}",
                    start_line=1,
                    end_line=1,
                    raw_text=f"private String field_{id(node)};",
                    language="java",
                )
            ]

        extractors = {"field_declaration": mock_field_extractor}
        results = []

        extractor._traverse_and_extract_iterative(
            mock_root, extractors, results, "field"
        )

        assert len(results) == 15

    def test_process_field_batch(self, extractor):
        """Test field batch processing"""
        field_nodes = []
        for _i in range(5):
            node = Mock()
            node.type = "field_declaration"
            field_nodes.append(node)

        def mock_field_extractor(node):
            return [
                Variable(
                    name=f"field_{i}",
                    start_line=1,
                    end_line=1,
                    raw_text=f"private String field_{i};",
                    language="java",
                )
                for i in range(2)
            ]

        extractors = {"field_declaration": mock_field_extractor}
        results = []

        extractor._process_field_batch(field_nodes, extractors, results)

        assert len(results) == 10

    def test_process_field_batch_with_caching(self, extractor):
        """Test field batch processing with caching"""
        field_node = Mock()
        field_node.type = "field_declaration"
        field_node.start_byte = 0
        field_node.end_byte = 30

        cache_key = (id(field_node), "field")
        cached_fields = [
            Variable(
                name="cached_field",
                start_line=1,
                end_line=1,
                raw_text="private String cached_field;",
                language="java",
            )
        ]
        extractor._element_cache[cache_key] = cached_fields

        extractors = {"field_declaration": Mock()}
        results = []

        extractor._process_field_batch([field_node], extractors, results)

        assert len(results) == 1
        assert results[0].name == "cached_field"
        assert extractors["field_declaration"].call_count == 0

    def test_traverse_and_extract_iterative_max_depth(self, extractor):
        """Test max depth protection in traversal"""
        root_node = Mock()
        root_node.type = "program"
        root_node.children = []

        current_node = root_node

        for _i in range(60):
            child = Mock()
            child.type = "class_body"
            child.children = []
            current_node.children = [child]
            current_node = child

        target_node = Mock()
        target_node.type = "method_declaration"
        target_node.children = []
        current_node.children = [target_node]

        extractors = {"method_declaration": Mock()}
        results = []

        with patch(
            "tree_sitter_analyzer.languages.java_helpers.log_warning"
        ) as mock_log:
            extractor._traverse_and_extract_iterative(
                root_node, extractors, results, "method"
            )

            mock_log.assert_called()
