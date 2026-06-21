"""Tests for C# primitive helpers — visibility, parameters, type_name, modifiers, complexity, attributes, using_directive."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tree_sitter_analyzer.languages.csharp_helpers import (
    calculate_complexity,
    determine_visibility,
    extract_attributes,
    extract_modifiers,
    extract_parameters,
    extract_type_name,
    extract_using_directive,
)


@dataclass
class FakeNode:
    type: str
    text: str = ""
    children: list[FakeNode] = field(default_factory=list)
    fields: dict[str, FakeNode] = field(default_factory=dict)
    start_point: tuple[int, int] = (0, 0)
    end_point: tuple[int, int] = (0, 0)
    start_byte: int = 0
    end_byte: int = 0
    _prev_sibling: FakeNode | None = None

    def child_by_field_name(self, name: str) -> FakeNode | None:
        return self.fields.get(name)

    @property
    def prev_sibling(self) -> FakeNode | None:
        return self._prev_sibling


def _get_node_text(node: Any) -> str:
    return node.text


def _make_modifier(text: str) -> FakeNode:
    return FakeNode("modifier", text)


class TestDetermineVisibility:
    def test_public(self) -> None:
        assert determine_visibility(["public"]) == "public"

    def test_private(self) -> None:
        assert determine_visibility(["private"]) == "private"

    def test_protected(self) -> None:
        assert determine_visibility(["protected"]) == "protected"

    def test_internal(self) -> None:
        assert determine_visibility(["internal"]) == "internal"

    def test_default_is_private(self) -> None:
        assert determine_visibility([]) == "private"

    def test_public_priority_over_private(self) -> None:
        assert determine_visibility(["private", "public"]) == "public"

    def test_protected_priority_over_internal(self) -> None:
        assert determine_visibility(["internal", "protected"]) == "protected"

    def test_non_visibility_modifiers_ignored(self) -> None:
        assert determine_visibility(["static", "readonly"]) == "private"


class TestExtractParameters:
    def test_none_node_returns_empty(self) -> None:
        assert extract_parameters(None, _get_node_text) == []

    def test_no_parameter_children(self) -> None:
        node = FakeNode("parameter_list", children=[FakeNode("comma")])
        assert extract_parameters(node, _get_node_text) == []

    def test_single_parameter(self) -> None:
        param = FakeNode("parameter", "int x")
        node = FakeNode("parameter_list", children=[param])
        result = extract_parameters(node, _get_node_text)
        assert result == ["int x"]

    def test_multiple_parameters(self) -> None:
        p1 = FakeNode("parameter", "int x")
        p2 = FakeNode("parameter", "string y")
        node = FakeNode("parameter_list", children=[p1, FakeNode("comma"), p2])
        result = extract_parameters(node, _get_node_text)
        assert result == ["int x", "string y"]

    def test_skips_non_parameter_children(self) -> None:
        p1 = FakeNode("parameter", "int a")
        other = FakeNode("identifier", "not_a_param")
        node = FakeNode("parameter_list", children=[p1, other])
        result = extract_parameters(node, _get_node_text)
        assert result == ["int a"]


class TestExtractTypeName:
    def test_none_returns_void(self) -> None:
        assert extract_type_name(None, _get_node_text) == "void"

    def test_returns_node_text(self) -> None:
        node = FakeNode("type_identifier", "string")
        assert extract_type_name(node, _get_node_text) == "string"

    def test_generic_name(self) -> None:
        node = FakeNode("generic_name", "List<int>")
        assert extract_type_name(node, _get_node_text) == "List<int>"


class TestExtractModifiers:
    def test_no_modifiers(self) -> None:
        node = FakeNode("class_declaration", children=[FakeNode("identifier", "Foo")])
        assert extract_modifiers(node, _get_node_text) == []

    def test_single_modifier(self) -> None:
        node = FakeNode(
            "method_declaration",
            children=[_make_modifier("public"), FakeNode("identifier", "Foo")],
        )
        assert extract_modifiers(node, _get_node_text) == ["public"]

    def test_multiple_modifiers(self) -> None:
        node = FakeNode(
            "method_declaration",
            children=[
                _make_modifier("public"),
                _make_modifier("static"),
                FakeNode("identifier", "Main"),
            ],
        )
        assert extract_modifiers(node, _get_node_text) == ["public", "static"]

    def test_skips_non_modifier_children(self) -> None:
        node = FakeNode(
            "class_declaration",
            children=[FakeNode("identifier", "Foo"), _make_modifier("sealed")],
        )
        assert extract_modifiers(node, _get_node_text) == ["sealed"]


class TestCalculateComplexity:
    def _traverse(self, node: FakeNode) -> list[FakeNode]:
        result: list[FakeNode] = []
        stack = list(reversed(node.children))
        while stack:
            child = stack.pop()
            result.append(child)
            stack.extend(reversed(child.children))
        return result

    def test_base_complexity_is_one(self) -> None:
        node = FakeNode("method_declaration")
        assert calculate_complexity(node, self._traverse) == 1

    def test_single_if_increments(self) -> None:
        node = FakeNode(
            "method_declaration",
            children=[FakeNode("if_statement")],
        )
        assert calculate_complexity(node, self._traverse) == 2

    def test_all_decision_keywords(self) -> None:
        children = [
            FakeNode("if_statement"),
            FakeNode("switch_statement"),
            FakeNode("for_statement"),
            FakeNode("foreach_statement"),
            FakeNode("while_statement"),
            FakeNode("do_statement"),
            FakeNode("catch_clause"),
            FakeNode("conditional_expression"),
        ]
        node = FakeNode("method_declaration", children=children)
        assert calculate_complexity(node, self._traverse) == 9

    def test_nested_decisions(self) -> None:
        inner = FakeNode("if_statement", children=[FakeNode("for_statement")])
        node = FakeNode("method_declaration", children=[inner])
        assert calculate_complexity(node, self._traverse) == 3

    def test_non_decision_nodes_ignored(self) -> None:
        node = FakeNode(
            "method_declaration",
            children=[
                FakeNode("expression_statement"),
                FakeNode("return_statement"),
            ],
        )
        assert calculate_complexity(node, self._traverse) == 1


def _make_attribute_list(name: str, line: int = 0) -> FakeNode:
    """Build a FakeNode tree matching tree-sitter C# attribute_list structure.

    attribute_list → attribute → identifier (the name)
    """
    ident = FakeNode("identifier", name)
    attr = FakeNode("attribute", name, children=[ident])
    return FakeNode(
        "attribute_list", f"[{name}]", children=[attr], start_point=(line, 0)
    )


class TestExtractAttributes:
    """Tests for extract_attributes — reads attribute_list direct children."""

    def test_no_attribute_list_children_returns_empty(self) -> None:
        node = FakeNode("class_declaration", children=[FakeNode("modifier", "public")])
        cache: dict[tuple[int, int], list[dict[str, Any]]] = {}
        result = extract_attributes(node, _get_node_text, cache)
        assert result == []

    def test_single_attribute_child(self) -> None:
        attr_list = _make_attribute_list("Serializable", line=2)
        modifier = FakeNode("modifier", "public")
        node = FakeNode("class_declaration", children=[attr_list, modifier])
        cache: dict[tuple[int, int], list[dict[str, Any]]] = {}
        result = extract_attributes(node, _get_node_text, cache)
        assert len(result) == 1
        assert result[0]["name"] == "Serializable"
        assert result[0]["text"] == "[Serializable]"
        assert result[0]["line"] == 3  # line=2 → start_point=(2,0) → line 3 (1-indexed)

    def test_multiple_attributes(self) -> None:
        attr1 = _make_attribute_list("Serializable", line=1)
        attr2 = _make_attribute_list("Obsolete", line=2)
        modifier = FakeNode("modifier", "public")
        node = FakeNode("class_declaration", children=[attr1, attr2, modifier])
        cache: dict[tuple[int, int], list[dict[str, Any]]] = {}
        result = extract_attributes(node, _get_node_text, cache)
        assert len(result) == 2
        assert result[0]["name"] == "Serializable"
        assert result[1]["name"] == "Obsolete"

    def test_stops_at_first_non_attribute_list_child(self) -> None:
        attr = _make_attribute_list("Serializable", line=0)
        modifier = FakeNode("modifier", "public")
        attr2 = _make_attribute_list("ShouldBeIgnored", line=3)
        # attribute_list, modifier, attribute_list — second attr_list after modifier is ignored
        node = FakeNode("class_declaration", children=[attr, modifier, attr2])
        cache: dict[tuple[int, int], list[dict[str, Any]]] = {}
        result = extract_attributes(node, _get_node_text, cache)
        assert len(result) == 1
        assert result[0]["name"] == "Serializable"

    def test_method_attributes(self) -> None:
        attr = _make_attribute_list("HttpGet", line=5)
        modifier = FakeNode("modifier", "public")
        node = FakeNode("method_declaration", children=[attr, modifier])
        cache: dict[tuple[int, int], list[dict[str, Any]]] = {}
        result = extract_attributes(node, _get_node_text, cache)
        assert len(result) == 1
        assert result[0]["name"] == "HttpGet"

    def test_caches_result(self) -> None:
        attr = _make_attribute_list("Cached", line=0)
        node = FakeNode(
            "class_declaration",
            start_point=(1, 0),
            end_point=(5, 0),
            children=[attr],
        )
        cache: dict[tuple[int, int], list[dict[str, Any]]] = {}
        result1 = extract_attributes(node, _get_node_text, cache)
        result2 = extract_attributes(node, _get_node_text, cache)
        assert result1 is result2
        assert cache


class TestExtractUsingDirective:
    def test_basic_using(self) -> None:
        name_node = FakeNode("identifier", "System")
        node = FakeNode(
            "using_directive",
            "using System;",
            fields={"name": name_node},
            start_point=(0, 0),
            end_point=(0, 12),
        )
        result = extract_using_directive(node, _get_node_text)
        assert result is not None
        assert result.name == "System"
        assert result.language == "csharp"
        assert result.is_static is False

    def test_using_with_qualified_name(self) -> None:
        name_node = FakeNode("qualified_name", "System.Collections")
        node = FakeNode(
            "using_directive",
            "using System.Collections;",
            fields={"name": name_node},
            start_point=(1, 0),
            end_point=(1, 25),
        )
        result = extract_using_directive(node, _get_node_text)
        assert result is not None
        assert result.name == "System.Collections"

    def test_using_static(self) -> None:
        name_node = FakeNode("qualified_name", "System.Math")
        static_kw = FakeNode("static", "static")
        node = FakeNode(
            "using_directive",
            "using static System.Math;",
            fields={"name": name_node},
            children=[static_kw],
            start_point=(2, 0),
            end_point=(2, 25),
        )
        result = extract_using_directive(node, _get_node_text)
        assert result is not None
        assert result.is_static is True

    def test_using_no_name_returns_none(self) -> None:
        node = FakeNode(
            "using_directive",
            "using ;",
            children=[FakeNode("using_keyword", "using")],
            start_point=(0, 0),
            end_point=(0, 7),
        )
        result = extract_using_directive(node, _get_node_text)
        assert result is None

    def test_using_fallback_name_from_children(self) -> None:
        name_child = FakeNode("identifier", "System.Linq")
        node = FakeNode(
            "using_directive",
            "using System.Linq;",
            children=[name_child],
            start_point=(0, 0),
            end_point=(0, 18),
        )
        result = extract_using_directive(node, _get_node_text)
        assert result is not None
        assert result.name == "System.Linq"
