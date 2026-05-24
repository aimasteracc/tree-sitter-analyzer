"""Tests for C field/variable declaration extraction helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tree_sitter_analyzer.languages._c_declaration_helpers import (
    _append_array_fields,
    _append_child_names,
    _append_initializer_fields,
    _append_modifier,
    _append_pointer_fields,
    _append_pointer_variables,
    _field_parts,
    _node_line_range,
    _variable_parts,
    extract_field_declaration,
    extract_variable_declaration,
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
    parent: FakeNode | None = None

    def child_by_field_name(self, name: str) -> FakeNode | None:
        return self.fields.get(name)


def _get_node_text(node: Any) -> str:
    return node.text


class TestNodeLineRange:
    def test_basic_range(self) -> None:
        node = FakeNode("field_declaration", start_point=(2, 0), end_point=(2, 20))
        start, end = _node_line_range(node)
        assert start == 3
        assert end == 3

    def test_multiline_range(self) -> None:
        node = FakeNode("declaration", start_point=(4, 0), end_point=(7, 10))
        start, end = _node_line_range(node)
        assert start == 5
        assert end == 8


class TestAppendModifier:
    def test_appends_non_empty(self) -> None:
        modifiers: list[str] = []
        node = FakeNode("type_qualifier", text="const")
        _append_modifier(modifiers, node, _get_node_text)
        assert modifiers == ["const"]

    def test_skips_empty(self) -> None:
        modifiers: list[str] = []
        node = FakeNode("type_qualifier", text="")
        _append_modifier(modifiers, node, _get_node_text)
        assert modifiers == []


class TestAppendChildNames:
    def test_finds_matching_children(self) -> None:
        parent = FakeNode("ptr", children=[
            FakeNode("identifier", text="x"),
            FakeNode("other"),
            FakeNode("identifier", text="y"),
        ])
        names: list[str] = []
        result = _append_child_names(parent, names, "identifier", _get_node_text)
        assert result is True
        assert names == ["x", "y"]

    def test_no_matching_children(self) -> None:
        parent = FakeNode("ptr", children=[FakeNode("other")])
        names: list[str] = []
        result = _append_child_names(parent, names, "identifier", _get_node_text)
        assert result is False
        assert names == []


class TestAppendArrayFields:
    def test_appends_field_identifier(self) -> None:
        node = FakeNode("array_declarator", children=[
            FakeNode("field_identifier", text="arr"),
        ])
        names: list[str] = []
        result = _append_array_fields(node, names, "int", _get_node_text)
        assert "arr" in names
        assert result == "int[]"

    def test_no_type(self) -> None:
        node = FakeNode("array_declarator", children=[
            FakeNode("field_identifier", text="arr"),
        ])
        names: list[str] = []
        result = _append_array_fields(node, names, None, _get_node_text)
        assert result == "[]"


class TestAppendInitializerFields:
    def test_finds_field_identifier(self) -> None:
        node = FakeNode("init_declarator", children=[
            FakeNode("field_identifier", text="x"),
        ])
        names: list[str] = []
        _append_initializer_fields(node, names, _get_node_text)
        assert names == ["x"]

    def test_finds_plain_identifier(self) -> None:
        node = FakeNode("init_declarator", children=[
            FakeNode("identifier", text="y"),
        ])
        names: list[str] = []
        _append_initializer_fields(node, names, _get_node_text)
        assert names == ["y"]


class TestAppendPointerFields:
    def test_appends_and_adds_star(self) -> None:
        node = FakeNode("pointer_declarator", children=[
            FakeNode("field_identifier", text="ptr"),
        ])
        names: list[str] = []
        result = _append_pointer_fields(node, names, "int", _get_node_text)
        assert "ptr" in names
        assert result == "int*"

    def test_no_field_identifier(self) -> None:
        node = FakeNode("pointer_declarator", children=[FakeNode("other")])
        names: list[str] = []
        result = _append_pointer_fields(node, names, "int", _get_node_text)
        assert result == "int"


class TestAppendPointerVariables:
    def test_appends_and_adds_star(self) -> None:
        node = FakeNode("pointer_declarator", children=[
            FakeNode("identifier", text="ptr"),
        ])
        names: list[str] = []
        result = _append_pointer_variables(node, names, "char", _get_node_text)
        assert "ptr" in names
        assert result == "char*"

    def test_no_identifier(self) -> None:
        node = FakeNode("pointer_declarator", children=[FakeNode("other")])
        names: list[str] = []
        result = _append_pointer_variables(node, names, "char", _get_node_text)
        assert result == "char"


class TestFieldParts:
    def test_primitive_type_with_field(self) -> None:
        node = FakeNode("field_declaration", children=[
            FakeNode("primitive_type", text="int"),
            FakeNode("field_identifier", text="x"),
        ])
        ftype, names, mods = _field_parts(node, _get_node_text)
        assert ftype == "int"
        assert names == ["x"]
        assert mods == []

    def test_with_type_qualifier(self) -> None:
        node = FakeNode("field_declaration", children=[
            FakeNode("type_qualifier", text="const"),
            FakeNode("primitive_type", text="int"),
            FakeNode("field_identifier", text="x"),
        ])
        ftype, names, mods = _field_parts(node, _get_node_text)
        assert ftype == "int"
        assert mods == ["const"]

    def test_empty_children(self) -> None:
        node = FakeNode("field_declaration", children=[])
        ftype, names, mods = _field_parts(node, _get_node_text)
        assert ftype is None
        assert names == []


class TestVariableParts:
    def test_primitive_type_with_identifier(self) -> None:
        node = FakeNode("declaration", children=[
            FakeNode("primitive_type", text="int"),
            FakeNode("identifier", text="count"),
        ])
        vtype, names, mods = _variable_parts(node, _get_node_text)
        assert vtype == "int"
        assert names == ["count"]

    def test_storage_class_specifier(self) -> None:
        node = FakeNode("declaration", children=[
            FakeNode("storage_class_specifier", text="static"),
            FakeNode("primitive_type", text="int"),
            FakeNode("identifier", text="s_count"),
        ])
        vtype, names, mods = _variable_parts(node, _get_node_text)
        assert mods == ["static"]

    def test_init_declarator(self) -> None:
        node = FakeNode("declaration", children=[
            FakeNode("primitive_type", text="int"),
            FakeNode("init_declarator", children=[
                FakeNode("identifier", text="x"),
            ]),
        ])
        vtype, names, mods = _variable_parts(node, _get_node_text)
        assert names == ["x"]


class TestExtractFieldDeclaration:
    def test_simple_int_field(self) -> None:
        node = FakeNode(
            "field_declaration",
            text="int x;",
            start_point=(0, 0),
            end_point=(0, 5),
            children=[
                FakeNode("primitive_type", text="int"),
                FakeNode("field_identifier", text="x"),
            ],
        )
        result = extract_field_declaration(node, _get_node_text)
        assert len(result) == 1
        assert result[0].name == "x"
        assert result[0].variable_type == "int"
        assert result[0].language == "c"

    def test_const_field(self) -> None:
        node = FakeNode(
            "field_declaration",
            text="const int size;",
            start_point=(0, 0),
            end_point=(0, 13),
            children=[
                FakeNode("type_qualifier", text="const"),
                FakeNode("primitive_type", text="int"),
                FakeNode("field_identifier", text="size"),
            ],
        )
        result = extract_field_declaration(node, _get_node_text)
        assert len(result) == 1
        assert result[0].is_constant is True
        assert "const" in result[0].modifiers

    def test_pointer_field(self) -> None:
        node = FakeNode(
            "field_declaration",
            text="int *ptr;",
            start_point=(0, 0),
            end_point=(0, 7),
            children=[
                FakeNode("primitive_type", text="int"),
                FakeNode("pointer_declarator", children=[
                    FakeNode("field_identifier", text="ptr"),
                ]),
            ],
        )
        result = extract_field_declaration(node, _get_node_text)
        assert len(result) == 1
        assert result[0].variable_type == "int*"

    def test_no_type_returns_empty(self) -> None:
        node = FakeNode(
            "field_declaration",
            text="x;",
            start_point=(0, 0),
            end_point=(0, 2),
            children=[FakeNode("field_identifier", text="x")],
        )
        result = extract_field_declaration(node, _get_node_text)
        assert result == []

    def test_no_names_returns_empty(self) -> None:
        node = FakeNode(
            "field_declaration",
            text="int;",
            start_point=(0, 0),
            end_point=(0, 3),
            children=[FakeNode("primitive_type", text="int")],
        )
        result = extract_field_declaration(node, _get_node_text)
        assert result == []

    def test_array_field(self) -> None:
        node = FakeNode(
            "field_declaration",
            text="int arr[10];",
            start_point=(0, 0),
            end_point=(0, 11),
            children=[
                FakeNode("primitive_type", text="int"),
                FakeNode("array_declarator", children=[
                    FakeNode("field_identifier", text="arr"),
                ]),
            ],
        )
        result = extract_field_declaration(node, _get_node_text)
        assert len(result) == 1
        assert result[0].variable_type == "int[]"

    def test_exception_returns_empty(self) -> None:
        node = FakeNode("field_declaration")
        node.start_point = None
        result = extract_field_declaration(node, _get_node_text)
        assert result == []


class TestExtractVariableDeclaration:
    def test_simple_int_variable(self) -> None:
        node = FakeNode(
            "declaration",
            text="int x;",
            start_point=(0, 0),
            end_point=(0, 5),
            children=[
                FakeNode("primitive_type", text="int"),
                FakeNode("identifier", text="x"),
            ],
        )
        result = extract_variable_declaration(node, _get_node_text)
        assert len(result) == 1
        assert result[0].name == "x"
        assert result[0].variable_type == "int"
        assert result[0].visibility == "public"

    def test_static_variable(self) -> None:
        node = FakeNode(
            "declaration",
            text="static int count;",
            start_point=(0, 0),
            end_point=(0, 16),
            children=[
                FakeNode("storage_class_specifier", text="static"),
                FakeNode("primitive_type", text="int"),
                FakeNode("identifier", text="count"),
            ],
        )
        result = extract_variable_declaration(node, _get_node_text)
        assert len(result) == 1
        assert result[0].is_static is True
        assert result[0].visibility == "private"

    def test_struct_member_skipped(self) -> None:
        parent = FakeNode("field_declaration_list")
        node = FakeNode(
            "declaration",
            text="int x;",
            start_point=(0, 0),
            end_point=(0, 5),
            parent=parent,
            children=[
                FakeNode("primitive_type", text="int"),
                FakeNode("identifier", text="x"),
            ],
        )
        result = extract_variable_declaration(node, _get_node_text)
        assert result == []

    def test_pointer_variable(self) -> None:
        node = FakeNode(
            "declaration",
            text="char *str;",
            start_point=(0, 0),
            end_point=(0, 9),
            children=[
                FakeNode("primitive_type", text="char"),
                FakeNode("pointer_declarator", children=[
                    FakeNode("identifier", text="str"),
                ]),
            ],
        )
        result = extract_variable_declaration(node, _get_node_text)
        assert len(result) == 1
        assert result[0].variable_type == "char*"

    def test_const_variable(self) -> None:
        node = FakeNode(
            "declaration",
            text="const int MAX = 100;",
            start_point=(0, 0),
            end_point=(0, 19),
            children=[
                FakeNode("type_qualifier", text="const"),
                FakeNode("primitive_type", text="int"),
                FakeNode("init_declarator", children=[
                    FakeNode("identifier", text="MAX"),
                ]),
            ],
        )
        result = extract_variable_declaration(node, _get_node_text)
        assert len(result) == 1
        assert result[0].is_constant is True

    def test_no_type_returns_empty(self) -> None:
        node = FakeNode(
            "declaration",
            text="x;",
            start_point=(0, 0),
            end_point=(0, 2),
            children=[FakeNode("identifier", text="x")],
        )
        result = extract_variable_declaration(node, _get_node_text)
        assert result == []

    def test_exception_returns_empty(self) -> None:
        node = FakeNode("declaration")
        node.start_point = None
        result = extract_variable_declaration(node, _get_node_text)
        assert result == []
