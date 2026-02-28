#!/usr/bin/env python3
"""
Unit tests for tree_sitter_analyzer.languages.yaml_plugin.

All tests here are MOCK-BASED (no real tree-sitter parser, no file I/O).
For real-parser / I/O tests see tests/integration/languages/test_yaml_integration.py.

Coverage map:
  YAMLElement.__init__                    → TestYAMLElement::test_init_defaults, test_language_is_yaml
  YAMLElement.to_summary_item             → TestYAMLElement::test_to_summary_item_schema, test_json_roundtrip
  YAMLElementExtractor.__init__           → TestYAMLElementExtractor::test_init
  YAMLElementExtractor.extract_functions  → test_extract_functions_returns_empty
  YAMLElementExtractor.extract_classes    → test_extract_classes_returns_empty
  YAMLElementExtractor.extract_variables  → test_extract_variables_returns_empty
  YAMLElementExtractor.extract_imports    → test_extract_imports_returns_empty
  YAMLElementExtractor.extract_yaml_elements → test_extract_yaml_elements_none_tree
  YAMLElementExtractor.extract_elements   → test_extract_elements_delegates
  YAMLElementExtractor._get_node_text     → test__get_node_text_valid_mock, test__get_node_text_exception_returns_empty
  YAMLElementExtractor._calculate_nesting_level → test__nesting_level_root_is_zero, test__nesting_level_nested_increments
  YAMLElementExtractor._get_document_index → test__get_document_index_first_doc, test__get_document_index_no_ancestor
  YAMLElementExtractor._traverse_nodes    → test__traverse_nodes_empty_children, test__traverse_nodes_recursive
  YAMLElementExtractor._count_document_children → test__count_document_children_empty, test__count_document_children_with_mappings
  YAMLElementExtractor._is_number         → test__is_number_integer, test__is_number_float, test__is_number_non_numeric
  YAMLElementExtractor._extract_value_info → test__extract_value_info_* (7 cases)
  YAMLPlugin.__init__                     → TestYAMLPlugin::test_init_creates_extractor
  YAMLPlugin.get_language_name            → test_get_language_name
  YAMLPlugin.get_file_extensions          → test_get_file_extensions
  YAMLPlugin.create_extractor             → test_create_extractor_returns_extractor
  YAMLPlugin.get_tree_sitter_language     → test_get_tree_sitter_language_import_error
  YAMLPlugin.get_supported_element_types  → test_get_supported_element_types_all_seven
  YAMLPlugin.get_queries                  → test_get_queries_not_empty, test_get_queries_are_strings
  YAMLPlugin.execute_query_strategy       → test_execute_query_strategy_yaml_with_key,
                                            test_execute_query_strategy_non_yaml_returns_none,
                                            test_execute_query_strategy_no_key_returns_none
  YAMLPlugin.get_element_categories       → test_get_element_categories_returns_dict,
                                            test_get_element_categories_has_expected_keys
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.languages.yaml_plugin import (
    YAML_AVAILABLE,
    YAMLElement,
    YAMLElementExtractor,
    YAMLPlugin,
)


# ─── YAMLElement ─────────────────────────────────────────────────────────────


class TestYAMLElement:
    """Unit tests for YAMLElement data model."""

    def test_init_defaults(self) -> None:
        """Default attribute values are correctly applied."""
        element = YAMLElement(
            name="k",
            start_line=1,
            end_line=1,
            raw_text="k: v",
        )
        assert element.language == "yaml"
        assert element.element_type == "yaml"
        assert element.key is None
        assert element.value is None
        assert element.value_type is None
        assert element.anchor_name is None
        assert element.alias_target is None
        assert element.nesting_level == 0
        assert element.document_index == 0
        assert element.child_count is None

    def test_language_is_yaml(self) -> None:
        """Language attribute is always 'yaml' for a YAMLElement."""
        element = YAMLElement(name="x", start_line=1, end_line=1, raw_text="")
        assert element.language == "yaml"

    def test_init_with_all_attributes(self) -> None:
        """All constructor attributes are stored correctly."""
        element = YAMLElement(
            name="anchor_key",
            start_line=5,
            end_line=7,
            raw_text="anchor_key: &ref value",
            element_type="anchor",
            key="anchor_key",
            value="value",
            value_type="string",
            anchor_name="ref",
            alias_target=None,
            nesting_level=2,
            document_index=1,
            child_count=3,
        )
        assert element.name == "anchor_key"
        assert element.start_line == 5
        assert element.end_line == 7
        assert element.element_type == "anchor"
        assert element.key == "anchor_key"
        assert element.value == "value"
        assert element.value_type == "string"
        assert element.anchor_name == "ref"
        assert element.alias_target is None
        assert element.nesting_level == 2
        assert element.document_index == 1
        assert element.child_count == 3

    def test_to_summary_item_schema(self) -> None:
        """to_summary_item() returns dict with required keys."""
        element = YAMLElement(
            name="host",
            start_line=3,
            end_line=3,
            raw_text="host: localhost",
            element_type="mapping",
            key="host",
            value="localhost",
            value_type="string",
            nesting_level=1,
            document_index=0,
        )
        summary = element.to_summary_item()
        assert isinstance(summary, dict)
        assert "name" in summary
        assert "type" in summary
        assert "lines" in summary
        assert "start" in summary["lines"]
        assert "end" in summary["lines"]
        assert summary["name"] == "host"
        assert summary["type"] == "mapping"
        assert summary["lines"]["start"] == 3
        assert summary["lines"]["end"] == 3

    def test_json_roundtrip(self) -> None:
        """to_summary_item() result is JSON-serializable and round-trips."""
        element = YAMLElement(
            name="port",
            start_line=4,
            end_line=4,
            raw_text="port: 5432",
            element_type="mapping",
            key="port",
            value="5432",
            value_type="number",
        )
        summary = element.to_summary_item()
        json_str = json.dumps(summary)
        parsed = json.loads(json_str)
        assert parsed["name"] == summary["name"]
        assert parsed["type"] == summary["type"]


# ─── YAMLElementExtractor ────────────────────────────────────────────────────


class TestYAMLElementExtractor:
    """Mock-based unit tests for YAMLElementExtractor.

    No real tree-sitter parser is used here.
    """

    @pytest.fixture
    def extractor(self) -> YAMLElementExtractor:
        return YAMLElementExtractor()

    # — Public interface: empty-return methods —

    def test_init(self, extractor: YAMLElementExtractor) -> None:
        """Extractor initializes with empty source and zero document index."""
        assert extractor.source_code == ""
        assert extractor.content_lines == []
        assert extractor._current_document_index == 0

    def test_extract_functions_returns_empty(self, extractor: YAMLElementExtractor) -> None:
        """YAML has no functions; extract_functions always returns empty list."""
        result = extractor.extract_functions(None, "")  # type: ignore[arg-type]
        assert result == []

    def test_extract_classes_returns_empty(self, extractor: YAMLElementExtractor) -> None:
        """YAML has no classes; extract_classes always returns empty list."""
        result = extractor.extract_classes(None, "")  # type: ignore[arg-type]
        assert result == []

    def test_extract_variables_returns_empty(self, extractor: YAMLElementExtractor) -> None:
        """YAML has no variables; extract_variables always returns empty list."""
        result = extractor.extract_variables(None, "")  # type: ignore[arg-type]
        assert result == []

    def test_extract_imports_returns_empty(self, extractor: YAMLElementExtractor) -> None:
        """YAML has no imports; extract_imports always returns empty list."""
        result = extractor.extract_imports(None, "")  # type: ignore[arg-type]
        assert result == []

    def test_extract_yaml_elements_none_tree(self, extractor: YAMLElementExtractor) -> None:
        """extract_yaml_elements returns empty list when tree is None."""
        result = extractor.extract_yaml_elements(None, "key: value")
        assert result == []

    def test_extract_yaml_elements_none_root_node(self, extractor: YAMLElementExtractor) -> None:
        """extract_yaml_elements returns empty list when root_node is None."""
        mock_tree = MagicMock()
        mock_tree.root_node = None
        result = extractor.extract_yaml_elements(mock_tree, "key: value")
        assert result == []

    def test_extract_elements_delegates_to_yaml_elements(self, extractor: YAMLElementExtractor) -> None:
        """extract_elements is an alias for extract_yaml_elements."""
        with patch.object(extractor, "extract_yaml_elements", return_value=[]) as mock_yaml:
            mock_tree = MagicMock()
            mock_tree.root_node = MagicMock()
            mock_tree.root_node.children = []
            result = extractor.extract_elements(mock_tree, "")
            mock_yaml.assert_called_once_with(mock_tree, "")
            assert result == []

    # — _get_node_text —

    def test__get_node_text_valid_mock(self, extractor: YAMLElementExtractor) -> None:
        """_get_node_text extracts the correct substring from source_code."""
        extractor.source_code = "key: value"
        node = MagicMock()
        node.start_byte = 5
        node.end_byte = 10
        result = extractor._get_node_text(node)
        assert result == "value"

    def test__get_node_text_exception_returns_empty(self, extractor: YAMLElementExtractor) -> None:
        """_get_node_text returns empty string on exception."""
        extractor.source_code = "test"
        node = MagicMock()
        # Simulate AttributeError by making start_byte raise
        type(node).start_byte = property(lambda self: (_ for _ in ()).throw(AttributeError()))
        result = extractor._get_node_text(node)
        assert result == ""

    # — _calculate_nesting_level —

    def test__nesting_level_root_is_zero(self, extractor: YAMLElementExtractor) -> None:
        """Root node with no parents has nesting level 0."""
        node = MagicMock()
        node.parent = None
        result = extractor._calculate_nesting_level(node)
        assert result == 0

    def test__nesting_level_nested_increments(self, extractor: YAMLElementExtractor) -> None:
        """Each block_mapping or block_sequence ancestor increments nesting level."""
        # Build chain: node → block_mapping parent → plain parent (root)
        root = MagicMock()
        root.type = "stream"
        root.parent = None

        mapping_parent = MagicMock()
        mapping_parent.type = "block_mapping"
        mapping_parent.parent = root

        node = MagicMock()
        node.parent = mapping_parent

        result = extractor._calculate_nesting_level(node)
        assert result == 1

    def test__nesting_level_double_nesting(self, extractor: YAMLElementExtractor) -> None:
        """Two nested block_sequence parents give level 2."""
        root = MagicMock()
        root.type = "stream"
        root.parent = None

        outer = MagicMock()
        outer.type = "block_sequence"
        outer.parent = root

        inner = MagicMock()
        inner.type = "block_sequence"
        inner.parent = outer

        node = MagicMock()
        node.parent = inner

        result = extractor._calculate_nesting_level(node)
        assert result == 2

    # — _get_document_index —

    def test__get_document_index_first_doc(self, extractor: YAMLElementExtractor) -> None:
        """First document node (no prior document siblings) returns index 0."""
        doc_node = MagicMock()
        doc_node.type = "document"
        doc_node.prev_sibling = None

        node = MagicMock()
        node.type = "block_mapping"
        node.parent = doc_node

        result = extractor._get_document_index(node)
        assert result == 0

    def test__get_document_index_no_ancestor(self, extractor: YAMLElementExtractor) -> None:
        """Node with no document ancestor returns 0."""
        root = MagicMock()
        root.type = "stream"
        root.parent = None

        node = MagicMock()
        node.type = "plain_scalar"
        node.parent = root

        result = extractor._get_document_index(node)
        assert result == 0

    # — _traverse_nodes —

    def test__traverse_nodes_empty_children(self, extractor: YAMLElementExtractor) -> None:
        """_traverse_nodes returns just the node itself when no children."""
        node = MagicMock()
        node.children = []
        result = extractor._traverse_nodes(node)
        assert result == [node]

    def test__traverse_nodes_recursive(self, extractor: YAMLElementExtractor) -> None:
        """_traverse_nodes collects all descendants recursively."""
        child1 = MagicMock()
        child1.children = []
        child2 = MagicMock()
        child2.children = []
        root = MagicMock()
        root.children = [child1, child2]
        result = extractor._traverse_nodes(root)
        assert root in result
        assert child1 in result
        assert child2 in result
        assert len(result) == 3

    # — _count_document_children —

    def test__count_document_children_empty(self, extractor: YAMLElementExtractor) -> None:
        """Document with no meaningful children returns 0."""
        doc_node = MagicMock()
        doc_node.children = []
        result = extractor._count_document_children(doc_node)
        assert result == 0

    def test__count_document_children_skips_markers(self, extractor: YAMLElementExtractor) -> None:
        """Document markers (---) are excluded from count."""
        marker = MagicMock()
        marker.type = "---"
        doc_node = MagicMock()
        doc_node.children = [marker]
        result = extractor._count_document_children(doc_node)
        assert result == 0

    def test__count_document_children_with_block_mapping(self, extractor: YAMLElementExtractor) -> None:
        """block_mapping_pair children of block_mapping are counted."""
        pair1 = MagicMock()
        pair1.type = "block_mapping_pair"
        pair2 = MagicMock()
        pair2.type = "block_mapping_pair"
        irrelevant = MagicMock()
        irrelevant.type = "comment"

        mapping = MagicMock()
        mapping.type = "block_mapping"
        mapping.children = [pair1, pair2, irrelevant]

        doc_node = MagicMock()
        doc_node.children = [mapping]
        result = extractor._count_document_children(doc_node)
        assert result == 2

    # — _is_number —

    def test__is_number_integer(self, extractor: YAMLElementExtractor) -> None:
        """Integer strings are detected as numbers."""
        assert extractor._is_number("42") is True

    def test__is_number_float(self, extractor: YAMLElementExtractor) -> None:
        """Float strings are detected as numbers."""
        assert extractor._is_number("3.14") is True

    def test__is_number_scientific(self, extractor: YAMLElementExtractor) -> None:
        """Scientific notation strings are detected as numbers."""
        assert extractor._is_number("1.23e+10") is True

    def test__is_number_non_numeric(self, extractor: YAMLElementExtractor) -> None:
        """Non-numeric strings return False."""
        assert extractor._is_number("hello") is False

    def test__is_number_empty_string(self, extractor: YAMLElementExtractor) -> None:
        """Empty string returns False."""
        assert extractor._is_number("") is False

    # — _extract_value_info —

    def _make_scalar_node(self, node_type: str, text: str) -> MagicMock:
        node = MagicMock()
        node.type = node_type
        node.start_byte = 0
        node.end_byte = len(text.encode("utf-8"))
        return node

    def test__extract_value_info_none_node(self, extractor: YAMLElementExtractor) -> None:
        """None input returns (None, None, None)."""
        result = extractor._extract_value_info(None)
        assert result == (None, None, None)

    def test__extract_value_info_boolean_true(self, extractor: YAMLElementExtractor) -> None:
        """plain_scalar 'true' → value_type 'boolean'."""
        extractor.source_code = "true"
        node = self._make_scalar_node("plain_scalar", "true")
        value, vtype, count = extractor._extract_value_info(node)
        assert vtype == "boolean"
        assert value == "true"
        assert count is None

    def test__extract_value_info_boolean_false(self, extractor: YAMLElementExtractor) -> None:
        """plain_scalar 'false' → value_type 'boolean'."""
        extractor.source_code = "false"
        node = self._make_scalar_node("plain_scalar", "false")
        _, vtype, _ = extractor._extract_value_info(node)
        assert vtype == "boolean"

    def test__extract_value_info_null(self, extractor: YAMLElementExtractor) -> None:
        """plain_scalar 'null' → value_type 'null'."""
        extractor.source_code = "null"
        node = self._make_scalar_node("plain_scalar", "null")
        _, vtype, _ = extractor._extract_value_info(node)
        assert vtype == "null"

    def test__extract_value_info_number(self, extractor: YAMLElementExtractor) -> None:
        """plain_scalar numeric string → value_type 'number'."""
        extractor.source_code = "42"
        node = self._make_scalar_node("plain_scalar", "42")
        _, vtype, _ = extractor._extract_value_info(node)
        assert vtype == "number"

    def test__extract_value_info_string(self, extractor: YAMLElementExtractor) -> None:
        """plain_scalar non-special string → value_type 'string'."""
        extractor.source_code = "hello"
        node = self._make_scalar_node("plain_scalar", "hello")
        _, vtype, _ = extractor._extract_value_info(node)
        assert vtype == "string"

    def test__extract_value_info_mapping_node(self, extractor: YAMLElementExtractor) -> None:
        """block_mapping node → value_type 'mapping' with child_count."""
        extractor.source_code = ""
        pair1 = MagicMock()
        pair1.type = "block_mapping_pair"
        pair2 = MagicMock()
        pair2.type = "block_mapping_pair"
        other = MagicMock()
        other.type = "comment"
        node = MagicMock()
        node.type = "block_mapping"
        node.children = [pair1, pair2, other]
        node.start_byte = 0
        node.end_byte = 0
        _, vtype, count = extractor._extract_value_info(node)
        assert vtype == "mapping"
        assert count == 2

    def test__extract_value_info_sequence_node(self, extractor: YAMLElementExtractor) -> None:
        """block_sequence node → value_type 'sequence' with child_count."""
        extractor.source_code = ""
        item1 = MagicMock()
        item1.type = "block_sequence_item"
        item2 = MagicMock()
        item2.type = "block_sequence_item"
        node = MagicMock()
        node.type = "block_sequence"
        node.children = [item1, item2]
        node.start_byte = 0
        node.end_byte = 0
        _, vtype, count = extractor._extract_value_info(node)
        assert vtype == "sequence"
        assert count == 2


# ─── YAMLPlugin ──────────────────────────────────────────────────────────────


class TestYAMLPlugin:
    """Unit tests for YAMLPlugin class."""

    @pytest.fixture
    def plugin(self) -> YAMLPlugin:
        return YAMLPlugin()

    def test_init_creates_extractor(self, plugin: YAMLPlugin) -> None:
        """Plugin initializes with a YAMLElementExtractor instance."""
        assert isinstance(plugin.extractor, YAMLElementExtractor)

    def test_get_language_name(self, plugin: YAMLPlugin) -> None:
        """Language name is 'yaml'."""
        assert plugin.get_language_name() == "yaml"

    def test_get_file_extensions(self, plugin: YAMLPlugin) -> None:
        """Supports .yaml and .yml extensions."""
        extensions = plugin.get_file_extensions()
        assert ".yaml" in extensions
        assert ".yml" in extensions

    def test_create_extractor_returns_extractor(self, plugin: YAMLPlugin) -> None:
        """create_extractor() returns a fresh YAMLElementExtractor."""
        extractor = plugin.create_extractor()
        assert isinstance(extractor, YAMLElementExtractor)

    def test_create_extractor_returns_new_instance(self, plugin: YAMLPlugin) -> None:
        """Each call to create_extractor() returns a distinct instance."""
        e1 = plugin.create_extractor()
        e2 = plugin.create_extractor()
        assert e1 is not e2

    def test_get_supported_element_types_all_seven(self, plugin: YAMLPlugin) -> None:
        """All seven YAML element types are listed."""
        types = plugin.get_supported_element_types()
        for expected in ("mapping", "sequence", "scalar", "anchor", "alias", "comment", "document"):
            assert expected in types, f"'{expected}' missing from supported types"

    def test_get_supported_element_types_returns_list(self, plugin: YAMLPlugin) -> None:
        """get_supported_element_types() returns a list."""
        assert isinstance(plugin.get_supported_element_types(), list)

    def test_get_queries_not_empty(self, plugin: YAMLPlugin) -> None:
        """get_queries() returns a non-empty dict."""
        queries = plugin.get_queries()
        assert isinstance(queries, dict)
        assert len(queries) > 0

    def test_get_queries_are_strings(self, plugin: YAMLPlugin) -> None:
        """All query values are non-empty strings."""
        for key, value in plugin.get_queries().items():
            assert isinstance(value, str), f"Query '{key}' value is not a string"
            assert len(value) > 0, f"Query '{key}' value is empty"

    def test_get_queries_has_document_key(self, plugin: YAMLPlugin) -> None:
        """'document' key exists in YAML queries."""
        assert "document" in plugin.get_queries()

    def test_execute_query_strategy_yaml_with_key(self, plugin: YAMLPlugin) -> None:
        """execute_query_strategy returns a query string for a valid key and 'yaml' language."""
        queries = plugin.get_queries()
        first_key = next(iter(queries))
        result = plugin.execute_query_strategy(first_key, "yaml")
        assert result == queries[first_key]

    def test_execute_query_strategy_non_yaml_returns_none(self, plugin: YAMLPlugin) -> None:
        """execute_query_strategy returns None for non-yaml language."""
        result = plugin.execute_query_strategy("document", "python")
        assert result is None

    def test_execute_query_strategy_no_key_returns_none(self, plugin: YAMLPlugin) -> None:
        """execute_query_strategy returns None when query_key is None."""
        result = plugin.execute_query_strategy(None, "yaml")
        assert result is None

    def test_execute_query_strategy_unknown_key_returns_none(self, plugin: YAMLPlugin) -> None:
        """execute_query_strategy returns None for an unknown key."""
        result = plugin.execute_query_strategy("nonexistent_key_xyz", "yaml")
        assert result is None

    def test_get_element_categories_returns_dict(self, plugin: YAMLPlugin) -> None:
        """get_element_categories() returns a dict."""
        categories = plugin.get_element_categories()
        assert isinstance(categories, dict)

    def test_get_element_categories_has_expected_keys(self, plugin: YAMLPlugin) -> None:
        """Element categories include 'structure', 'mappings', 'references'."""
        categories = plugin.get_element_categories()
        for key in ("structure", "mappings", "references"):
            assert key in categories, f"'{key}' missing from element categories"

    def test_get_element_categories_values_are_lists(self, plugin: YAMLPlugin) -> None:
        """Each category value is a list of strings."""
        for key, value in plugin.get_element_categories().items():
            assert isinstance(value, list), f"Category '{key}' is not a list"

    def test_get_tree_sitter_language_import_error(self) -> None:
        """get_tree_sitter_language() raises ImportError when YAML is not available."""
        plugin = YAMLPlugin()
        with patch(
            "tree_sitter_analyzer.languages.yaml_plugin.YAML_AVAILABLE", False
        ):
            with pytest.raises(ImportError):
                plugin.get_tree_sitter_language()
