"""Focused tests for C# helper extraction functions — csharp_helpers.py."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tree_sitter_analyzer.languages.csharp_helpers import (
    _extract_declarator_name,
    _find_variable_declaration,
    _iter_variable_declarators,
    calculate_complexity,
    determine_visibility,
    extract_attributes,
    extract_class_declaration,
    extract_constructor_declaration,
    extract_event_declaration,
    extract_field_declaration,
    extract_method_declaration,
    extract_modifiers,
    extract_parameters,
    extract_property_declaration,
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


# ---------------------------------------------------------------------------
# determine_visibility
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# extract_parameters
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# extract_type_name
# ---------------------------------------------------------------------------


class TestExtractTypeName:
    def test_none_returns_void(self) -> None:
        assert extract_type_name(None, _get_node_text) == "void"

    def test_returns_node_text(self) -> None:
        node = FakeNode("type_identifier", "string")
        assert extract_type_name(node, _get_node_text) == "string"

    def test_generic_name(self) -> None:
        node = FakeNode("generic_name", "List<int>")
        assert extract_type_name(node, _get_node_text) == "List<int>"


# ---------------------------------------------------------------------------
# extract_modifiers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# calculate_complexity
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# extract_attributes
# ---------------------------------------------------------------------------


class TestExtractAttributes:
    def test_no_prev_sibling_returns_empty(self) -> None:
        node = FakeNode("class_declaration")
        cache: dict[tuple[int, int], list[dict[str, Any]]] = {}
        result = extract_attributes(node, _get_node_text, cache)
        assert result == []

    def test_single_attribute_before_node(self) -> None:
        attr_node = FakeNode(
            "attribute_list",
            "[Serializable]",
            start_point=(2, 0),
        )
        node = FakeNode("class_declaration", _prev_sibling=attr_node)
        cache: dict[tuple[int, int], list[dict[str, Any]]] = {}
        result = extract_attributes(node, _get_node_text, cache)
        assert len(result) == 1
        assert result[0]["name"] == "Serializable"
        assert result[0]["text"] == "[Serializable]"
        assert result[0]["line"] == 3

    def test_multiple_attributes(self) -> None:
        attr2 = FakeNode("attribute_list", "[Obsolete]", start_point=(1, 0))
        attr1 = FakeNode("attribute_list", "[Serializable]", start_point=(2, 0))
        node = FakeNode("class_declaration", _prev_sibling=attr1)
        attr1._prev_sibling = attr2
        cache: dict[tuple[int, int], list[dict[str, Any]]] = {}
        result = extract_attributes(node, _get_node_text, cache)
        assert len(result) == 2
        assert result[0]["name"] == "Obsolete"
        assert result[1]["name"] == "Serializable"

    def test_stops_at_non_comment_non_attribute(self) -> None:
        other = FakeNode("namespace_declaration", "namespace Foo")
        attr = FakeNode("attribute_list", "[Serializable]", start_point=(0, 0))
        node = FakeNode("class_declaration", _prev_sibling=attr)
        attr._prev_sibling = other
        cache: dict[tuple[int, int], list[dict[str, Any]]] = {}
        result = extract_attributes(node, _get_node_text, cache)
        assert len(result) == 1

    def test_line_comment_does_not_block_attribute(self) -> None:
        comment = FakeNode("line_comment", "// comment")
        attr = FakeNode("attribute_list", "[Test]", start_point=(5, 0))
        node = FakeNode("method_declaration", _prev_sibling=attr)
        attr._prev_sibling = comment
        cache: dict[tuple[int, int], list[dict[str, Any]]] = {}
        result = extract_attributes(node, _get_node_text, cache)
        assert len(result) == 1

    def test_block_comment_does_not_block_attribute(self) -> None:
        comment = FakeNode("block_comment", "/* comment */")
        attr = FakeNode("attribute_list", "[Test]", start_point=(3, 0))
        node = FakeNode("method_declaration", _prev_sibling=attr)
        attr._prev_sibling = comment
        cache: dict[tuple[int, int], list[dict[str, Any]]] = {}
        result = extract_attributes(node, _get_node_text, cache)
        assert len(result) == 1

    def test_caches_result(self) -> None:
        attr = FakeNode("attribute_list", "[Cached]", start_point=(0, 0))
        node = FakeNode("class_declaration", start_point=(1, 0), end_point=(5, 0), _prev_sibling=attr)
        cache: dict[tuple[int, int], list[dict[str, Any]]] = {}
        result1 = extract_attributes(node, _get_node_text, cache)
        result2 = extract_attributes(node, _get_node_text, cache)
        assert result1 is result2
        assert len(cache) > 0


# ---------------------------------------------------------------------------
# extract_using_directive
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# extract_class_declaration
# ---------------------------------------------------------------------------


class TestExtractClassDeclaration:
    def _extract_mods(self, node: Any) -> list[str]:
        return extract_modifiers(node, _get_node_text)

    def _extract_attrs(self, node: Any) -> list[dict[str, Any]]:
        return extract_attributes(node, _get_node_text, {})

    def test_simple_class(self) -> None:
        node = FakeNode(
            "class_declaration",
            "public class Foo { }",
            fields={"name": FakeNode("identifier", "Foo")},
            start_point=(0, 0),
            end_point=(0, 20),
            children=[_make_modifier("public")],
        )
        result = extract_class_declaration(
            node, "", _get_node_text, self._extract_mods, self._extract_attrs
        )
        assert result is not None
        assert result.name == "Foo"
        assert result.visibility == "public"
        assert result.class_type == "class"

    def test_class_with_namespace(self) -> None:
        node = FakeNode(
            "class_declaration",
            "class Bar { }",
            fields={"name": FakeNode("identifier", "Bar")},
            start_point=(3, 4),
            end_point=(5, 5),
        )
        result = extract_class_declaration(
            node, "MyApp.Models", _get_node_text, self._extract_mods, self._extract_attrs
        )
        assert result is not None
        assert result.full_qualified_name == "MyApp.Models.Bar"

    def test_class_with_superclass(self) -> None:
        bases = FakeNode(
            "base_list",
            children=[FakeNode("type_identifier", "BaseClass")],
        )
        node = FakeNode(
            "class_declaration",
            "class Derived : BaseClass { }",
            fields={"name": FakeNode("identifier", "Derived"), "bases": bases},
            start_point=(0, 0),
            end_point=(0, 28),
        )
        result = extract_class_declaration(
            node, "", _get_node_text, self._extract_mods, self._extract_attrs
        )
        assert result is not None
        assert result.superclass == "BaseClass"
        assert result.interfaces == []

    def test_class_with_interfaces(self) -> None:
        bases = FakeNode(
            "base_list",
            children=[
                FakeNode("type_identifier", "BaseClass"),
                FakeNode("type_identifier", "IFoo"),
                FakeNode("type_identifier", "IBar"),
            ],
        )
        node = FakeNode(
            "class_declaration",
            "class D : BaseClass, IFoo, IBar { }",
            fields={"name": FakeNode("identifier", "D"), "bases": bases},
            start_point=(0, 0),
            end_point=(0, 32),
        )
        result = extract_class_declaration(
            node, "", _get_node_text, self._extract_mods, self._extract_attrs
        )
        assert result is not None
        assert result.superclass == "BaseClass"
        assert result.interfaces == ["IFoo", "IBar"]

    def test_interface_all_bases_are_interfaces(self) -> None:
        bases = FakeNode(
            "base_list",
            children=[
                FakeNode("type_identifier", "IDisposable"),
                FakeNode("type_identifier", "IEnumerable"),
            ],
        )
        node = FakeNode(
            "interface_declaration",
            "interface IFoo : IDisposable, IEnumerable { }",
            fields={"name": FakeNode("identifier", "IFoo"), "bases": bases},
            start_point=(0, 0),
            end_point=(0, 45),
        )
        result = extract_class_declaration(
            node, "", _get_node_text, self._extract_mods, self._extract_attrs
        )
        assert result is not None
        assert result.class_type == "interface"
        assert result.superclass is None
        assert result.interfaces == ["IDisposable", "IEnumerable"]

    def test_record_type(self) -> None:
        node = FakeNode(
            "record_declaration",
            "public record Point(int X, int Y);",
            fields={"name": FakeNode("identifier", "Point")},
            start_point=(0, 0),
            end_point=(0, 32),
            children=[_make_modifier("public")],
        )
        result = extract_class_declaration(
            node, "", _get_node_text, self._extract_mods, self._extract_attrs
        )
        assert result is not None
        assert result.class_type == "record"

    def test_struct_type(self) -> None:
        node = FakeNode(
            "struct_declaration",
            "struct Point { }",
            fields={"name": FakeNode("identifier", "Point")},
            start_point=(0, 0),
            end_point=(0, 16),
        )
        result = extract_class_declaration(
            node, "", _get_node_text, self._extract_mods, self._extract_attrs
        )
        assert result is not None
        assert result.class_type == "struct"

    def test_enum_type(self) -> None:
        node = FakeNode(
            "enum_declaration",
            "enum Color { Red, Green, Blue }",
            fields={"name": FakeNode("identifier", "Color")},
            start_point=(0, 0),
            end_point=(0, 30),
        )
        result = extract_class_declaration(
            node, "", _get_node_text, self._extract_mods, self._extract_attrs
        )
        assert result is not None
        assert result.class_type == "enum"

    def test_no_name_returns_none(self) -> None:
        node = FakeNode("class_declaration", "class { }")
        result = extract_class_declaration(
            node, "", _get_node_text, self._extract_mods, self._extract_attrs
        )
        assert result is None


# ---------------------------------------------------------------------------
# extract_method_declaration
# ---------------------------------------------------------------------------


class TestExtractMethodDeclaration:
    def _mods(self, node: Any) -> list[str]:
        return extract_modifiers(node, _get_node_text)

    def _attrs(self, node: Any) -> list[dict[str, Any]]:
        return extract_attributes(node, _get_node_text, {})

    def _type(self, node: Any) -> str:
        return extract_type_name(node, _get_node_text)

    def _params(self, node: Any) -> list[str]:
        return extract_parameters(node, _get_node_text)

    def _complexity(self, node: Any) -> int:
        return 1

    def test_simple_method(self) -> None:
        node = FakeNode(
            "method_declaration",
            "public void DoWork() { }",
            fields={
                "name": FakeNode("identifier", "DoWork"),
                "type": FakeNode("type_identifier", "void"),
                "parameters": FakeNode("parameter_list", children=[]),
            },
            start_point=(5, 4),
            end_point=(5, 28),
            children=[_make_modifier("public")],
        )
        result = extract_method_declaration(
            node, _get_node_text, self._mods, self._attrs, self._type, self._params, self._complexity
        )
        assert result is not None
        assert result.name == "DoWork"
        assert result.visibility == "public"
        assert result.return_type == "void"
        assert result.parameters == []

    def test_async_method(self) -> None:
        node = FakeNode(
            "method_declaration",
            "public async Task<string> Fetch() { }",
            fields={
                "name": FakeNode("identifier", "Fetch"),
                "type": FakeNode("generic_name", "Task<string>"),
                "parameters": FakeNode("parameter_list", children=[]),
            },
            start_point=(0, 0),
            end_point=(0, 36),
            children=[_make_modifier("public"), _make_modifier("async")],
        )
        result = extract_method_declaration(
            node, _get_node_text, self._mods, self._attrs, self._type, self._params, self._complexity
        )
        assert result is not None
        assert result.is_async is True
        assert result.return_type == "Task<string>"

    def test_method_with_parameters(self) -> None:
        params_node = FakeNode(
            "parameter_list",
            children=[
                FakeNode("parameter", "int x"),
                FakeNode("parameter", "string y"),
            ],
        )
        node = FakeNode(
            "method_declaration",
            "void Foo(int x, string y) { }",
            fields={
                "name": FakeNode("identifier", "Foo"),
                "type": FakeNode("type_identifier", "void"),
                "parameters": params_node,
            },
            start_point=(0, 0),
            end_point=(0, 29),
        )
        result = extract_method_declaration(
            node, _get_node_text, self._mods, self._attrs, self._type, self._params, self._complexity
        )
        assert result is not None
        assert result.parameters == ["int x", "string y"]

    def test_no_name_returns_none(self) -> None:
        node = FakeNode("method_declaration", "void () { }")
        result = extract_method_declaration(
            node, _get_node_text, self._mods, self._attrs, self._type, self._params, self._complexity
        )
        assert result is None

    def test_complexity_passed_through(self) -> None:
        node = FakeNode(
            "method_declaration",
            "void Complex() { }",
            fields={
                "name": FakeNode("identifier", "Complex"),
                "type": FakeNode("type_identifier", "void"),
                "parameters": FakeNode("parameter_list", children=[]),
            },
            start_point=(0, 0),
            end_point=(0, 19),
        )

        def calc_complex(_n: Any) -> int:
            return 7

        result = extract_method_declaration(
            node, _get_node_text, self._mods, self._attrs, self._type, self._params, calc_complex
        )
        assert result is not None
        assert result.complexity_score == 7


# ---------------------------------------------------------------------------
# extract_constructor_declaration
# ---------------------------------------------------------------------------


class TestExtractConstructorDeclaration:
    def _mods(self, node: Any) -> list[str]:
        return extract_modifiers(node, _get_node_text)

    def _attrs(self, node: Any) -> list[dict[str, Any]]:
        return extract_attributes(node, _get_node_text, {})

    def _params(self, node: Any) -> list[str]:
        return extract_parameters(node, _get_node_text)

    def test_simple_constructor(self) -> None:
        node = FakeNode(
            "constructor_declaration",
            "public MyClass() { }",
            fields={
                "name": FakeNode("identifier", "MyClass"),
                "parameters": FakeNode("parameter_list", children=[]),
            },
            start_point=(3, 4),
            end_point=(3, 23),
            children=[_make_modifier("public")],
        )
        result = extract_constructor_declaration(
            node, _get_node_text, self._mods, self._attrs, self._params
        )
        assert result is not None
        assert result.name == "MyClass"
        assert result.is_constructor is True
        assert result.return_type == "void"
        assert result.visibility == "public"

    def test_constructor_with_params(self) -> None:
        params_node = FakeNode(
            "parameter_list",
            children=[FakeNode("parameter", "string name")],
        )
        node = FakeNode(
            "constructor_declaration",
            "MyClass(string name) { }",
            fields={
                "name": FakeNode("identifier", "MyClass"),
                "parameters": params_node,
            },
            start_point=(0, 0),
            end_point=(0, 25),
        )
        result = extract_constructor_declaration(
            node, _get_node_text, self._mods, self._attrs, self._params
        )
        assert result is not None
        assert result.parameters == ["string name"]

    def test_no_name_returns_none(self) -> None:
        node = FakeNode("constructor_declaration", "() { }")
        result = extract_constructor_declaration(
            node, _get_node_text, self._mods, self._attrs, self._params
        )
        assert result is None


# ---------------------------------------------------------------------------
# extract_property_declaration
# ---------------------------------------------------------------------------


class TestExtractPropertyDeclaration:
    def _mods(self, node: Any) -> list[str]:
        return extract_modifiers(node, _get_node_text)

    def _attrs(self, node: Any) -> list[dict[str, Any]]:
        return extract_attributes(node, _get_node_text, {})

    def _type(self, node: Any) -> str:
        return extract_type_name(node, _get_node_text)

    def test_simple_property(self) -> None:
        node = FakeNode(
            "property_declaration",
            "public string Name { get; set; }",
            fields={
                "name": FakeNode("identifier", "Name"),
                "type": FakeNode("type_identifier", "string"),
            },
            start_point=(2, 4),
            end_point=(2, 34),
            children=[_make_modifier("public")],
        )
        result = extract_property_declaration(
            node, _get_node_text, self._mods, self._attrs, self._type
        )
        assert result is not None
        assert result.name == "Name"
        assert result.return_type == "string"
        assert result.is_property is True
        assert result.visibility == "public"
        assert result.parameters == []

    def test_auto_property_no_type(self) -> None:
        node = FakeNode(
            "property_declaration",
            "int Count { get; }",
            fields={
                "name": FakeNode("identifier", "Count"),
            },
            start_point=(0, 0),
            end_point=(0, 18),
        )
        result = extract_property_declaration(
            node, _get_node_text, self._mods, self._attrs, self._type
        )
        assert result is not None
        assert result.return_type == "void"

    def test_no_name_returns_none(self) -> None:
        node = FakeNode("property_declaration", "{ get; set; }")
        result = extract_property_declaration(
            node, _get_node_text, self._mods, self._attrs, self._type
        )
        assert result is None


# ---------------------------------------------------------------------------
# _find_variable_declaration, _iter_variable_declarators, _extract_declarator_name
# ---------------------------------------------------------------------------


class TestVariableHelpers:
    def test_find_variable_declaration_found(self) -> None:
        var_decl = FakeNode("variable_declaration")
        node = FakeNode("field_declaration", children=[FakeNode("modifier"), var_decl])
        assert _find_variable_declaration(node) is var_decl

    def test_find_variable_declaration_not_found(self) -> None:
        node = FakeNode("field_declaration", children=[FakeNode("modifier")])
        assert _find_variable_declaration(node) is None

    def test_find_variable_declaration_empty_children(self) -> None:
        node = FakeNode("field_declaration", children=[])
        assert _find_variable_declaration(node) is None

    def test_iter_variable_declarators_yields_matching(self) -> None:
        d1 = FakeNode("variable_declarator")
        d2 = FakeNode("variable_declarator")
        var_decl = FakeNode("variable_declaration", children=[d1, FakeNode("comma"), d2])
        result = list(_iter_variable_declarators(var_decl))
        assert result == [d1, d2]

    def test_iter_variable_declarators_none_returns_empty(self) -> None:
        result = list(_iter_variable_declarators(None))
        assert result == []

    def test_iter_variable_declarators_no_matching(self) -> None:
        var_decl = FakeNode("variable_declaration", children=[FakeNode("type_identifier")])
        result = list(_iter_variable_declarators(var_decl))
        assert result == []

    def test_extract_declarator_name(self) -> None:
        declarator = FakeNode(
            "variable_declarator",
            "x",
            fields={"name": FakeNode("identifier", "x")},
        )
        assert _extract_declarator_name(declarator, _get_node_text) == "x"

    def test_extract_declarator_name_no_name_field(self) -> None:
        declarator = FakeNode("variable_declarator", "x")
        assert _extract_declarator_name(declarator, _get_node_text) is None


# ---------------------------------------------------------------------------
# extract_field_declaration
# ---------------------------------------------------------------------------


class TestExtractFieldDeclaration:
    def _mods(self, node: Any) -> list[str]:
        return extract_modifiers(node, _get_node_text)

    def _attrs(self, node: Any) -> list[dict[str, Any]]:
        return extract_attributes(node, _get_node_text, {})

    def _type(self, node: Any) -> str:
        return extract_type_name(node, _get_node_text)

    def test_single_field(self) -> None:
        var_decl = FakeNode(
            "variable_declaration",
            "int x",
            fields={"type": FakeNode("type_identifier", "int")},
            children=[
                FakeNode(
                    "variable_declarator",
                    "x",
                    fields={"name": FakeNode("identifier", "x")},
                ),
            ],
        )
        node = FakeNode(
            "field_declaration",
            "private int x;",
            children=[_make_modifier("private"), var_decl],
            start_point=(1, 4),
            end_point=(1, 18),
        )
        result = extract_field_declaration(
            node, _get_node_text, self._mods, self._attrs, self._type
        )
        assert len(result) == 1
        assert result[0].name == "x"
        assert result[0].variable_type == "int"
        assert result[0].visibility == "private"
        assert result[0].is_constant is False

    def test_multiple_fields_same_declaration(self) -> None:
        d1 = FakeNode("variable_declarator", "x", fields={"name": FakeNode("identifier", "x")})
        d2 = FakeNode("variable_declarator", "y", fields={"name": FakeNode("identifier", "y")})
        var_decl = FakeNode(
            "variable_declaration",
            "int x, y",
            fields={"type": FakeNode("type_identifier", "int")},
            children=[d1, FakeNode("comma"), d2],
        )
        node = FakeNode(
            "field_declaration",
            "int x, y;",
            children=[var_decl],
            start_point=(0, 0),
            end_point=(0, 10),
        )
        result = extract_field_declaration(
            node, _get_node_text, self._mods, self._attrs, self._type
        )
        assert len(result) == 2
        assert result[0].name == "x"
        assert result[1].name == "y"

    def test_const_field(self) -> None:
        var_decl = FakeNode(
            "variable_declaration",
            "int MaxValue",
            fields={"type": FakeNode("type_identifier", "int")},
            children=[
                FakeNode("variable_declarator", "MaxValue", fields={"name": FakeNode("identifier", "MaxValue")}),
            ],
        )
        node = FakeNode(
            "field_declaration",
            "public const int MaxValue = 100;",
            children=[_make_modifier("public"), _make_modifier("const"), var_decl],
            start_point=(0, 0),
            end_point=(0, 31),
        )
        result = extract_field_declaration(
            node, _get_node_text, self._mods, self._attrs, self._type
        )
        assert len(result) == 1
        assert result[0].is_constant is True
        assert result[0].visibility == "public"

    def test_no_variable_declaration_returns_empty(self) -> None:
        node = FakeNode(
            "field_declaration",
            "private;",
            children=[_make_modifier("private")],
            start_point=(0, 0),
            end_point=(0, 8),
        )
        result = extract_field_declaration(
            node, _get_node_text, self._mods, self._attrs, self._type
        )
        assert result == []

    def test_declarator_without_name_skipped(self) -> None:
        var_decl = FakeNode(
            "variable_declaration",
            "int",
            fields={"type": FakeNode("type_identifier", "int")},
            children=[FakeNode("variable_declarator", "")],
        )
        node = FakeNode(
            "field_declaration",
            "int;",
            children=[var_decl],
            start_point=(0, 0),
            end_point=(0, 4),
        )
        result = extract_field_declaration(
            node, _get_node_text, self._mods, self._attrs, self._type
        )
        assert result == []


# ---------------------------------------------------------------------------
# extract_event_declaration
# ---------------------------------------------------------------------------


class TestExtractEventDeclaration:
    def _mods(self, node: Any) -> list[str]:
        return extract_modifiers(node, _get_node_text)

    def _attrs(self, node: Any) -> list[dict[str, Any]]:
        return extract_attributes(node, _get_node_text, {})

    def _type(self, node: Any) -> str:
        return extract_type_name(node, _get_node_text)

    def test_single_event(self) -> None:
        var_decl = FakeNode(
            "variable_declaration",
            "EventHandler Click",
            fields={"type": FakeNode("type_identifier", "EventHandler")},
            children=[
                FakeNode("variable_declarator", "Click", fields={"name": FakeNode("identifier", "Click")}),
            ],
        )
        node = FakeNode(
            "event_field_declaration",
            "public event EventHandler Click;",
            children=[_make_modifier("public"), var_decl],
            start_point=(0, 0),
            end_point=(0, 34),
        )
        result = extract_event_declaration(
            node, _get_node_text, self._mods, self._attrs, self._type
        )
        assert len(result) == 1
        assert result[0].name == "Click"
        assert result[0].variable_type == "EventHandler"
        assert "event" in result[0].modifiers
        assert result[0].visibility == "public"

    def test_multiple_events(self) -> None:
        d1 = FakeNode("variable_declarator", "OnClick", fields={"name": FakeNode("identifier", "OnClick")})
        d2 = FakeNode("variable_declarator", "OnLoad", fields={"name": FakeNode("identifier", "OnLoad")})
        var_decl = FakeNode(
            "variable_declaration",
            "EventHandler OnClick, OnLoad",
            fields={"type": FakeNode("type_identifier", "EventHandler")},
            children=[d1, FakeNode("comma"), d2],
        )
        node = FakeNode(
            "event_field_declaration",
            "event EventHandler OnClick, OnLoad;",
            children=[var_decl],
            start_point=(0, 0),
            end_point=(0, 37),
        )
        result = extract_event_declaration(
            node, _get_node_text, self._mods, self._attrs, self._type
        )
        assert len(result) == 2
        assert result[0].name == "OnClick"
        assert result[1].name == "OnLoad"
        assert all("event" in v.modifiers for v in result)

    def test_no_variable_declaration_returns_empty(self) -> None:
        node = FakeNode(
            "event_field_declaration",
            "event EventHandler;",
            children=[_make_modifier("public")],
            start_point=(0, 0),
            end_point=(0, 21),
        )
        result = extract_event_declaration(
            node, _get_node_text, self._mods, self._attrs, self._type
        )
        assert result == []
