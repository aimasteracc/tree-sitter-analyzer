"""Tests for tree_sitter_analyzer.languages.shared.traversal."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from tree_sitter_analyzer.languages.shared.traversal import (
    collect_named_nodes,
    find_first_child,
    iter_children_of_type,
    node_range,
    node_text,
)


def _make_node(type_: str, children=None, text: bytes | None = None) -> SimpleNamespace:
    """Minimal tree-sitter node stand-in."""
    n = SimpleNamespace(
        type=type_,
        children=children or [],
        text=text,
    )
    return n


class TestIterChildrenOfType:
    def test_yields_matching_children(self):
        child_a = _make_node("identifier")
        child_b = _make_node("comment")
        child_c = _make_node("identifier")
        parent = _make_node("function_definition", [child_a, child_b, child_c])

        result = list(iter_children_of_type(parent, "identifier"))
        assert result == [child_a, child_c]

    def test_no_match_yields_empty(self):
        parent = _make_node("module", [_make_node("comment")])
        result = list(iter_children_of_type(parent, "identifier"))
        assert result == []

    def test_no_children_attribute_yields_empty(self):
        node = SimpleNamespace(type="leaf")  # no .children
        result = list(iter_children_of_type(node, "identifier"))
        assert result == []

    def test_multiple_types_in_filter(self):
        a = _make_node("if_statement")
        b = _make_node("for_statement")
        c = _make_node("comment")
        parent = _make_node("module", [a, b, c])
        result = list(iter_children_of_type(parent, "if_statement", "for_statement"))
        assert result == [a, b]


class TestFindFirstChild:
    def test_returns_first_matching_child(self):
        a = _make_node("comment")
        b = _make_node("identifier")
        c = _make_node("identifier")
        parent = _make_node("module", [a, b, c])
        result = find_first_child(parent, "identifier")
        assert result is b

    def test_returns_none_when_no_match(self):
        parent = _make_node("module", [_make_node("comment")])
        assert find_first_child(parent, "identifier") is None

    def test_returns_none_on_empty_children(self):
        parent = _make_node("module", [])
        assert find_first_child(parent, "identifier") is None


class TestCollectNamedNodes:
    def test_collects_from_single_level(self):
        a = _make_node("if_statement")
        b = _make_node("comment")
        c = _make_node("if_statement")
        root = _make_node("module", [a, b, c])
        result = collect_named_nodes(root, "if_statement")
        assert result == [a, c]

    def test_collects_nested(self):
        inner = _make_node("if_statement")
        outer_if = _make_node("if_statement", [inner])
        root = _make_node("module", [outer_if, _make_node("comment")])
        result = collect_named_nodes(root, "if_statement")
        # DFS pre-order: outer first, then inner
        assert result == [outer_if, inner]

    def test_empty_tree_returns_empty(self):
        root = _make_node("module", [])
        assert collect_named_nodes(root, "if_statement") == []

    def test_root_itself_is_collected(self):
        root = _make_node("if_statement", [])
        result = collect_named_nodes(root, "if_statement")
        assert result == [root]


class TestNodeText:
    def test_returns_text_from_bytes_attribute(self):
        node = _make_node("identifier", text=b"hello_func")
        assert node_text(node, b"") == "hello_func"

    def test_returns_text_from_str_attribute(self):
        node = SimpleNamespace(type="identifier", text="my_symbol", children=[])
        assert node_text(node, b"") == "my_symbol"

    def test_falls_back_to_source_bytes_slice(self):
        source = b"def hello():"
        node = SimpleNamespace(
            type="identifier",
            text=None,
            start_byte=4,
            end_byte=9,
            children=[],
        )
        assert node_text(node, source) == "hello"

    def test_returns_empty_for_none_node(self):
        assert node_text(None, b"anything") == ""

    def test_returns_empty_on_bad_bytes_slice(self):
        node = SimpleNamespace(type="x", text=None, start_byte=999, end_byte=1000, children=[])
        assert node_text(node, b"short") == ""

    def test_multibyte_utf8_slice(self):
        # "こんにちは" is 15 bytes in UTF-8; bytes 0–15
        source = "こんにちは".encode("utf-8")
        node = SimpleNamespace(type="x", text=None, start_byte=0, end_byte=15, children=[])
        assert node_text(node, source) == "こんにちは"


class TestNodeRange:
    def test_converts_0indexed_to_1indexed(self):
        node = SimpleNamespace(start_point=(0, 0), end_point=(4, 10), children=[])
        assert node_range(node) == (1, 5)

    def test_single_line_node(self):
        node = SimpleNamespace(start_point=(9, 0), end_point=(9, 20), children=[])
        assert node_range(node) == (10, 10)

    def test_returns_zero_tuple_on_missing_attribute(self):
        node = SimpleNamespace(children=[])  # no start_point / end_point
        assert node_range(node) == (0, 0)
