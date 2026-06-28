"""Focused tests for Go helper extraction functions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tree_sitter_analyzer.languages._go_common import extract_docstring
from tree_sitter_analyzer.languages._go_import import (
    _extract_import_declaration,
    extract_import_spec,
)
from tree_sitter_analyzer.languages._go_type import (
    extract_embedded_types,
    extract_go_type_spec,
)


@dataclass
class FakeNode:
    type: str
    text: str = ""
    children: list[FakeNode] = field(default_factory=list)
    fields: dict[str, FakeNode] = field(default_factory=dict)
    start_point: tuple[int, int] = (0, 0)
    end_point: tuple[int, int] = (0, 0)

    def child_by_field_name(self, name: str) -> FakeNode | None:
        return self.fields.get(name)


def get_node_text(node: Any) -> str:
    return node.text


def test_extract_import_spec_handles_named_alias() -> None:
    alias = FakeNode("package_identifier", "jsoniter")
    path = FakeNode("interpreted_string_literal", '"github.com/json-iterator/go"')
    node = FakeNode(
        "import_spec",
        'jsoniter "github.com/json-iterator/go"',
        [alias, path],
        start_point=(4, 0),
        end_point=(4, 40),
    )

    result = extract_import_spec(node, get_node_text)

    assert result is not None
    assert result.name == "go"
    assert result.module_name == "github.com/json-iterator/go"
    assert result.alias == "jsoniter"
    assert result.start_line == 5
    assert result.end_line == 5


def test_extract_import_declaration_flattens_grouped_imports() -> None:
    fmt_spec = FakeNode(
        "import_spec",
        '"fmt"',
        [FakeNode("interpreted_string_literal", '"fmt"')],
    )
    blank_spec = FakeNode(
        "import_spec",
        '_ "net/http/pprof"',
        [
            FakeNode("blank_identifier", "_"),
            FakeNode("interpreted_string_literal", '"net/http/pprof"'),
        ],
    )
    declaration = FakeNode(
        "import_declaration",
        'import ("fmt"; _ "net/http/pprof")',
        [FakeNode("import_spec_list", children=[fmt_spec, blank_spec])],
    )

    imports = _extract_import_declaration(declaration, get_node_text)

    assert [imp.module_name for imp in imports] == ["fmt", "net/http/pprof"]
    assert [imp.alias for imp in imports] == [None, "_"]


def test_extract_embedded_types_ignores_named_fields() -> None:
    embedded_reader = FakeNode(
        "field_declaration",
        "io.Reader",
        [FakeNode("qualified_type", "io.Reader")],
    )
    named_field = FakeNode(
        "field_declaration",
        "Name string",
        [
            FakeNode("field_identifier", "Name"),
            FakeNode("type_identifier", "string"),
        ],
    )
    struct_node = FakeNode(
        "struct_type",
        children=[
            FakeNode(
                "field_declaration_list",
                children=[embedded_reader, named_field],
            )
        ],
    )

    assert extract_embedded_types(struct_node, get_node_text) == ["io.Reader"]


def test_extract_go_type_spec_includes_embedded_struct_types() -> None:
    name_node = FakeNode("type_identifier", "Service")
    struct_node = FakeNode(
        "struct_type",
        children=[
            FakeNode(
                "field_declaration_list",
                children=[
                    FakeNode(
                        "field_declaration",
                        "BaseService",
                        [FakeNode("type_identifier", "BaseService")],
                    )
                ],
            )
        ],
    )
    type_spec = FakeNode(
        "type_spec",
        "type Service struct { BaseService }",
        fields={"name": name_node, "type": struct_node},
        start_point=(2, 0),
        end_point=(4, 1),
    )

    result = extract_go_type_spec(type_spec, get_node_text, [])

    assert result is not None
    assert result.name == "Service"
    assert result.class_type == "struct"
    assert result.interfaces == ["BaseService"]


def test_extract_docstring_collects_contiguous_go_comments() -> None:
    node = FakeNode("function_declaration", start_point=(4, 0))
    content_lines = [
        "package demo",
        "",
        "// First sentence.",
        "// Second sentence.",
        "func Run() {}",
    ]

    assert extract_docstring(node, content_lines) == "First sentence.\nSecond sentence."
