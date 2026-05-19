"""Tests for C# declaration extractors — class, method, constructor, property, variable helpers, field, event."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tree_sitter_analyzer.languages.csharp_helpers import (
    _extract_declarator_name,
    _find_variable_declaration,
    _iter_variable_declarators,
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
