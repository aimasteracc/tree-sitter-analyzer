"""Tests for tree_sitter_analyzer.core._query_service_helpers."""

from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tree_sitter_analyzer.core._query_service_helpers import (
    PluginQueryNode,
    _element_to_capture,
    _node_matches_query,
    _walk_for_plugin_categories,
    fallback_query_captures,
    plugin_category_captures,
    plugin_strategy_captures,
)


@dataclass
class FakeElement:
    element_type: str = "function"
    start_line: int = 1
    end_line: int = 5
    raw_text: str = "def foo(): pass"


class TestPluginQueryNode:
    def test_init_with_full_element(self):
        elem = FakeElement()
        node = PluginQueryNode(elem, "function")
        assert node.type == "function"
        assert node.start_point == (0, 0)
        assert node.end_point == (4, 0)
        assert node.text == b"def foo(): pass"

    def test_init_with_missing_attributes(self):
        elem = SimpleNamespace()
        node = PluginQueryNode(elem, "class")
        assert node.type == "class"
        assert node.start_point == (0, 0)
        assert node.end_point == (0, 0)
        assert node.text == b""

    def test_init_with_none_query_key(self):
        elem = SimpleNamespace()
        node = PluginQueryNode(elem, None)
        assert node.type == "unknown"

    def test_init_element_type_attribute(self):
        elem = SimpleNamespace(element_type="method")
        node = PluginQueryNode(elem, None)
        assert node.type == "method"

    def test_text_encoding(self):
        elem = SimpleNamespace(raw_text="héllo wörld")
        node = PluginQueryNode(elem, None)
        assert node.text == "héllo wörld".encode()


class TestElementToCapture:
    def test_returns_capture_tuple(self):
        elem = FakeElement()
        result = _element_to_capture(elem, "function")
        assert result is not None
        node, key = result
        assert isinstance(node, PluginQueryNode)
        assert key == "function"

    def test_returns_none_without_start_line(self):
        elem = SimpleNamespace(end_line=5)
        assert _element_to_capture(elem, "function") is None

    def test_returns_none_without_end_line(self):
        elem = SimpleNamespace(start_line=1)
        assert _element_to_capture(elem, "function") is None

    def test_returns_none_with_no_line_attrs(self):
        elem = SimpleNamespace()
        assert _element_to_capture(elem, "function") is None

    def test_uses_query_key_as_fallback(self):
        elem = FakeElement()
        result = _element_to_capture(elem, None)
        assert result is not None
        _, key = result
        assert key == "element"

    def test_with_custom_query_key(self):
        elem = FakeElement()
        result = _element_to_capture(elem, "class")
        assert result is not None
        _, key = result
        assert key == "class"


class TestPluginStrategyCaptures:
    def test_returns_captures_from_plugin(self):
        elem = FakeElement()
        plugin = MagicMock()
        plugin.execute_query_strategy.return_value = [elem]
        result = plugin_strategy_captures(plugin, "function", "code")
        assert result is not None
        assert len(result) == 1

    def test_returns_none_on_exception(self):
        plugin = MagicMock()
        plugin.execute_query_strategy.side_effect = RuntimeError("fail")
        result = plugin_strategy_captures(plugin, "function", "code")
        assert result is None

    def test_returns_empty_for_none_elements(self):
        plugin = MagicMock()
        plugin.execute_query_strategy.return_value = None
        result = plugin_strategy_captures(plugin, "function", "code")
        assert result == []

    def test_skips_elements_without_line_attrs(self):
        good = FakeElement()
        bad = SimpleNamespace(name="no_lines")
        plugin = MagicMock()
        plugin.execute_query_strategy.return_value = [good, bad]
        result = plugin_strategy_captures(plugin, "function", "code")
        assert len(result) == 1

    def test_uses_function_as_default_query_key(self):
        plugin = MagicMock()
        plugin.execute_query_strategy.return_value = []
        plugin_strategy_captures(plugin, None, "code")
        plugin.execute_query_strategy.assert_called_once_with("code", "function")

    def test_multiple_valid_elements(self):
        elems = [FakeElement(start_line=i, end_line=i + 1) for i in range(1, 6)]
        plugin = MagicMock()
        plugin.execute_query_strategy.return_value = elems
        result = plugin_strategy_captures(plugin, "function", "code")
        assert len(result) == 5


class TestWalkForPluginCategories:
    def test_appends_matching_node(self):
        node = SimpleNamespace(type="function_declaration", children=[])
        captures = []
        _walk_for_plugin_categories(
            node, ["function_declaration"], "function", captures
        )
        assert len(captures) == 1
        assert captures[0] == (node, "function")

    def test_ignores_non_matching_node(self):
        node = SimpleNamespace(type="class_declaration", children=[])
        captures = []
        _walk_for_plugin_categories(
            node, ["function_declaration"], "function", captures
        )
        assert len(captures) == 0

    def test_walks_children(self):
        child1 = SimpleNamespace(type="function_declaration", children=[])
        child2 = SimpleNamespace(type="class_declaration", children=[])
        root = SimpleNamespace(type="module", children=[child1, child2])
        captures = []
        _walk_for_plugin_categories(
            root, ["function_declaration"], "function", captures
        )
        assert len(captures) == 1
        assert captures[0] == (child1, "function")

    def test_empty_node_types_list(self):
        node = SimpleNamespace(type="function_declaration", children=[])
        captures = []
        _walk_for_plugin_categories(node, [], "function", captures)
        assert len(captures) == 0

    def test_deeply_nested(self):
        leaf = SimpleNamespace(type="method_declaration", children=[])
        mid = SimpleNamespace(type="class_body", children=[leaf])
        root = SimpleNamespace(type="program", children=[mid])
        captures = []
        _walk_for_plugin_categories(root, ["method_declaration"], "method", captures)
        assert len(captures) == 1
        assert captures[0] == (leaf, "method")


class TestPluginCategoryCaptures:
    def test_returns_captures(self):
        plugin = MagicMock()
        plugin.get_element_categories.return_value = {
            "function": ["function_declaration"]
        }
        root = SimpleNamespace(
            type="module",
            children=[SimpleNamespace(type="function_declaration", children=[])],
        )
        result = plugin_category_captures(plugin, root, "function")
        assert result is not None
        assert len(result) == 1

    def test_returns_none_on_exception(self):
        plugin = MagicMock()
        plugin.get_element_categories.side_effect = RuntimeError("fail")
        result = plugin_category_captures(plugin, None, "function")
        assert result is None

    def test_returns_none_for_empty_categories(self):
        plugin = MagicMock()
        plugin.get_element_categories.return_value = {}
        result = plugin_category_captures(plugin, None, "function")
        assert result is None

    def test_returns_none_for_missing_key(self):
        plugin = MagicMock()
        plugin.get_element_categories.return_value = {"class": ["class_decl"]}
        result = plugin_category_captures(plugin, None, "function")
        assert result is None

    def test_returns_none_for_none_query_key(self):
        plugin = MagicMock()
        plugin.get_element_categories.return_value = {"function": ["fn"]}
        result = plugin_category_captures(plugin, None, None)
        assert result is None

    def test_no_matching_nodes(self):
        plugin = MagicMock()
        plugin.get_element_categories.return_value = {
            "function": ["function_declaration"]
        }
        root = SimpleNamespace(
            type="module",
            children=[SimpleNamespace(type="class_declaration", children=[])],
        )
        result = plugin_category_captures(plugin, root, "function")
        assert result == []


class TestNodeMatchesQuery:
    @pytest.mark.parametrize(
        "node_type,query_key,expected",
        [
            ("function_declaration", "function", True),
            ("function_declaration", "functions", True),
            ("member_function", "function", True),
            ("class_declaration", "class", True),
            ("class_definition", "classes", True),
            ("method_declaration", "method", True),
            ("method_expression", "methods", True),
            ("variable_declaration", "variable", True),
            ("variable_assignment", "variables", True),
            ("import_statement", "import", True),
            ("import_from", "imports", True),
            ("heading_element", "header", True),
            ("heading", "header", True),
            ("class_declaration", "function", False),
            ("function_declaration", "class", False),
            ("random_node", "function", False),
            ("function_declaration", None, False),
            ("something", "unknown", False),
        ],
    )
    def test_matching(self, node_type, query_key, expected):
        assert _node_matches_query(node_type, query_key) is expected


class TestFallbackQueryCaptures:
    def test_captures_matching_nodes(self):
        func_node = SimpleNamespace(type="function_declaration", children=[])
        root = SimpleNamespace(type="module", children=[func_node])
        result = fallback_query_captures(root, "function")
        assert len(result) == 1
        assert result[0] == (func_node, "function")

    def test_empty_tree(self):
        root = SimpleNamespace(type="module", children=[])
        result = fallback_query_captures(root, "function")
        assert result == []

    def test_nested_matches(self):
        inner = SimpleNamespace(type="function_declaration", children=[])
        outer = SimpleNamespace(type="class_declaration", children=[inner])
        root = SimpleNamespace(type="module", children=[outer])
        result = fallback_query_captures(root, "class")
        assert len(result) == 1
        assert result[0] == (outer, "class")

    def test_multiple_matches(self):
        nodes = [
            SimpleNamespace(type="function_declaration", children=[]),
            SimpleNamespace(type="function_expression", children=[]),
        ]
        root = SimpleNamespace(type="module", children=nodes)
        result = fallback_query_captures(root, "function")
        assert len(result) == 2

    def test_none_query_key(self):
        func_node = SimpleNamespace(type="function_declaration", children=[])
        root = SimpleNamespace(type="module", children=[func_node])
        result = fallback_query_captures(root, None)
        assert len(result) == 0

    def test_non_string_node_type(self):
        node = SimpleNamespace(type=42, children=[])
        root = SimpleNamespace(type="module", children=[node])
        result = fallback_query_captures(root, "function")
        assert result == []

    def test_deeply_nested_match(self):
        leaf = SimpleNamespace(type="variable_declaration", children=[])
        mid = SimpleNamespace(type="block", children=[leaf])
        root = SimpleNamespace(type="module", children=[mid])
        result = fallback_query_captures(root, "variable")
        assert len(result) == 1
        assert result[0] == (leaf, "variable")

    def test_mixed_matches_different_types(self):
        func = SimpleNamespace(type="function_declaration", children=[])
        cls = SimpleNamespace(type="class_declaration", children=[])
        var = SimpleNamespace(type="variable_declaration", children=[])
        root = SimpleNamespace(type="module", children=[func, cls, var])
        result = fallback_query_captures(root, "class")
        assert len(result) == 1
        assert result[0][1] == "class"

    def test_import_match(self):
        imp = SimpleNamespace(type="import_statement", children=[])
        root = SimpleNamespace(type="module", children=[imp])
        result = fallback_query_captures(root, "import")
        assert len(result) == 1

    def test_element_key_for_none_query(self):
        assert (
            fallback_query_captures(SimpleNamespace(type="x", children=[]), None) == []
        )
