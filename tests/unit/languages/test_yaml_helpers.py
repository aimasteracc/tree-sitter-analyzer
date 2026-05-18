"""Direct tests for YAML helper behavior."""

from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from tree_sitter_analyzer.languages.yaml_helpers import (
    analyze_yaml_file,
    append_alias_element,
    append_anchor_element,
    append_comment_element,
    append_document_element,
    append_mapping_element,
    append_sequence_element,
    build_alias_element,
    build_anchor_element,
    build_comment_element,
    build_document_element,
    build_mapping_element,
    build_sequence_element,
    calculate_nesting_level,
    count_document_children,
    count_sequence_children,
    extract_mapping_key_and_value,
    extract_node_text,
    extract_value_info,
    get_document_index,
    iter_document_nodes,
    iter_mapping_nodes,
    iter_nodes_by_type,
    iter_sequence_nodes,
    traverse_nodes,
)


@dataclass
class FakeNode:
    type: str
    text: str = ""
    children: list["FakeNode"] = field(default_factory=list)
    start_point: tuple[int, int] = (0, 0)
    end_point: tuple[int, int] = (0, 0)
    start_byte: int = 0
    end_byte: int = 0
    parent: "FakeNode | None" = None
    prev_sibling: "FakeNode | None" = None

    def __post_init__(self) -> None:
        for child in self.children:
            child.parent = self


class FakeParser:
    def parse(self, content: bytes) -> object:
        return {"content": content}


class FakeExtractor:
    def __init__(self, elements: list[Any]) -> None:
        self.elements = elements

    def extract_yaml_elements(self, tree: object, content: str) -> list[Any]:
        assert tree == {"content": content.encode("utf-8")}
        return self.elements


def _text(node: FakeNode) -> str:
    return node.text


def _document_index(_node: FakeNode) -> int:
    return 2


def _nesting_level(_node: FakeNode) -> int:
    return 3


def test_extract_node_text_uses_byte_offsets() -> None:
    source = "first: 1\nsecond: 2\n"
    node = FakeNode("plain_scalar", start_byte=9, end_byte=15)

    assert extract_node_text(node, source) == "second"


def test_tree_navigation_helpers() -> None:
    first_document = FakeNode("document")
    second_document = FakeNode("document", prev_sibling=first_document)
    nested_scalar = FakeNode("plain_scalar", "value")
    sequence = FakeNode("block_sequence", children=[nested_scalar])
    mapping = FakeNode("block_mapping", children=[sequence])
    second_document.children.append(mapping)
    mapping.parent = second_document

    traversed = traverse_nodes(second_document)

    assert calculate_nesting_level(nested_scalar) == 2
    assert get_document_index(nested_scalar) == 1
    assert iter_document_nodes([first_document, mapping, second_document]) == [
        first_document,
        second_document,
    ]
    assert iter_mapping_nodes([mapping, FakeNode("flow_pair")]) == [
        FakeNode("flow_pair")
    ]
    assert iter_sequence_nodes(traversed) == [sequence]
    assert iter_nodes_by_type(traversed, "plain_scalar") == [nested_scalar]


def test_extract_value_info_scalar_types() -> None:
    assert extract_value_info(FakeNode("plain_scalar", "true"), _text) == (
        "true",
        "boolean",
        None,
    )
    assert extract_value_info(FakeNode("plain_scalar", "42"), _text) == (
        "42",
        "number",
        None,
    )
    assert extract_value_info(FakeNode("plain_scalar", "~"), _text) == (
        "~",
        "null",
        None,
    )
    assert extract_value_info(FakeNode("alias", "*defaults"), _text) == (
        "*defaults",
        "alias",
        None,
    )


def test_extract_value_info_collection_types() -> None:
    mapping = FakeNode(
        "flow_mapping",
        children=[FakeNode("flow_pair"), FakeNode("comment")],
    )
    sequence = FakeNode(
        "flow_sequence",
        children=[FakeNode("plain_scalar", "one"), FakeNode("plain_scalar", "two")],
    )

    assert extract_value_info(None, _text) == (None, None, None)
    assert extract_value_info(FakeNode("block_scalar", "line\n"), _text) == (
        "line",
        "string",
        None,
    )
    assert extract_value_info(mapping, _text) == (None, "mapping", 1)
    assert extract_value_info(sequence, _text) == (None, "sequence", 2)
    assert extract_value_info(FakeNode("tag", "!Ref"), _text) == (
        "!Ref",
        "unknown",
        None,
    )


def test_count_children_helpers_ignore_syntax_nodes() -> None:
    mapping = FakeNode(
        "block_mapping",
        children=[
            FakeNode("block_mapping_pair"),
            FakeNode("comment"),
            FakeNode("block_mapping_pair"),
        ],
    )
    document = FakeNode(
        "document",
        children=[
            FakeNode("---"),
            FakeNode("block_node", children=[mapping]),
            FakeNode("..."),
        ],
    )
    sequence = FakeNode(
        "block_sequence",
        children=[
            FakeNode("block_sequence_item"),
            FakeNode("comment"),
            FakeNode("block_sequence_item"),
        ],
    )

    assert count_document_children(document) == 2
    assert count_sequence_children(sequence) == 2


def test_build_document_mapping_and_sequence_elements() -> None:
    mapping = FakeNode(
        "block_mapping_pair",
        "key: value",
        children=[
            FakeNode("key", children=[FakeNode("plain_scalar", "key")]),
            FakeNode(":"),
            FakeNode("value", children=[FakeNode("plain_scalar", "value")]),
        ],
        start_point=(1, 0),
        end_point=(1, 10),
    )
    sequence = FakeNode(
        "block_sequence",
        "- one\n- two",
        children=[FakeNode("block_sequence_item"), FakeNode("block_sequence_item")],
        start_point=(2, 0),
        end_point=(3, 5),
    )

    document = build_document_element(
        FakeNode("document", "doc", children=[FakeNode("block_node")]),
        _text,
        _document_index,
    )
    mapping_element = build_mapping_element(
        mapping, _text, _document_index, _nesting_level
    )
    sequence_element = build_sequence_element(
        sequence, _text, _document_index, _nesting_level
    )

    assert document.element_type == "document"
    assert mapping_element.key == "key"
    assert mapping_element.value == "value"
    assert sequence_element.child_count == 2


def test_build_anchor_alias_and_comment_elements() -> None:
    anchor = build_anchor_element(
        FakeNode("anchor", "&defaults", start_point=(4, 0), end_point=(4, 9)),
        _text,
        _document_index,
        _nesting_level,
    )
    alias = build_alias_element(
        FakeNode("alias", "*defaults", start_point=(5, 0), end_point=(5, 9)),
        _text,
        _document_index,
        _nesting_level,
    )
    comment = build_comment_element(
        FakeNode("comment", "# hello", start_point=(6, 0), end_point=(6, 7)),
        _text,
        _document_index,
    )

    assert anchor.anchor_name == "defaults"
    assert alias.alias_target == "defaults"
    assert comment.value == "hello"


def test_mapping_extraction_handles_flow_nodes_and_anchors() -> None:
    mapping = FakeNode(
        "block_mapping_pair",
        children=[
            FakeNode(
                "flow_node",
                children=[FakeNode("plain_scalar", "settings")],
                start_byte=0,
            ),
            FakeNode(":", start_byte=8),
            FakeNode(
                "block_node",
                children=[
                    FakeNode("plain_scalar", "enabled"),
                    FakeNode("anchor", "&defaults"),
                ],
                start_byte=10,
            ),
        ],
    )

    assert extract_mapping_key_and_value(mapping, _text) == (
        "settings",
        "enabled",
        "string",
        None,
        "defaults",
    )


def test_sequence_element_extracts_parent_mapping_key() -> None:
    sequence = FakeNode(
        "block_sequence",
        "- one",
        children=[FakeNode("block_sequence_item")],
        start_point=(2, 0),
        end_point=(2, 5),
        start_byte=10,
    )
    mapping = FakeNode(
        "block_mapping_pair",
        children=[
            FakeNode(
                "flow_node",
                children=[FakeNode("plain_scalar", "items")],
                start_byte=0,
            ),
            FakeNode(":", start_byte=5),
            FakeNode("block_node", children=[sequence], start_byte=7),
        ],
    )

    element = build_sequence_element(
        mapping.children[2].children[0], _text, _document_index, _nesting_level
    )

    assert element.key == "items"
    assert element.child_count == 1


def test_append_element_wrappers_add_successful_builds() -> None:
    elements: list[Any] = []
    document = FakeNode("document", children=[FakeNode("block_node")])
    mapping = FakeNode(
        "block_mapping_pair",
        children=[
            FakeNode("key", children=[FakeNode("plain_scalar", "key")]),
            FakeNode(":"),
            FakeNode("value", children=[FakeNode("plain_scalar", "value")]),
        ],
    )
    sequence = FakeNode("block_sequence", children=[FakeNode("block_sequence_item")])

    append_document_element(elements, document, _text, _document_index)
    append_mapping_element(elements, mapping, _text, _document_index, _nesting_level)
    append_sequence_element(elements, sequence, _text, _document_index, _nesting_level)
    append_anchor_element(
        elements,
        FakeNode("anchor", "&defaults"),
        _text,
        _document_index,
        _nesting_level,
    )
    append_alias_element(
        elements,
        FakeNode("alias", "*defaults"),
        _text,
        _document_index,
        _nesting_level,
    )
    append_comment_element(
        elements, FakeNode("comment", "# hello"), _text, _document_index
    )

    assert [element.element_type for element in elements] == [
        "document",
        "mapping",
        "sequence",
        "anchor",
        "alias",
        "comment",
    ]


def test_append_mapping_element_swallows_helper_failures() -> None:
    elements: list[Any] = []

    append_mapping_element(
        elements,
        FakeNode("block_mapping_pair"),
        lambda _node: (_ for _ in ()).throw(RuntimeError("boom")),
        _document_index,
        _nesting_level,
    )

    assert elements == []


def test_analyze_yaml_file_success_path(tmp_path) -> None:  # type: ignore[no-untyped-def]
    yaml_file = tmp_path / "sample.yaml"
    yaml_file.write_text("name: demo\n", encoding="utf-8")
    elements = [
        build_comment_element(FakeNode("comment", "# hello"), _text, _document_index)
    ]

    result = analyze_yaml_file(
        file_path=str(yaml_file),
        create_extractor=lambda: FakeExtractor(elements),
        yaml_available=True,
        parser=FakeParser(),
        parser_lock=Lock(),
    )

    assert result.success is True
    assert result.line_count == 1
    assert result.node_count == 1
    assert result.elements == elements
    assert result.source_code == "name: demo\n"


def test_analyze_yaml_file_failure_paths(tmp_path) -> None:  # type: ignore[no-untyped-def]
    yaml_file = tmp_path / "sample.yaml"
    yaml_file.write_text("name: demo\n", encoding="utf-8")

    unavailable = analyze_yaml_file(
        file_path=str(yaml_file),
        create_extractor=lambda: object(),
        yaml_available=False,
        parser=None,
        parser_lock=None,
    )
    uninitialized = analyze_yaml_file(
        file_path=str(yaml_file),
        create_extractor=lambda: object(),
        yaml_available=True,
        parser=None,
        parser_lock=Lock(),
    )

    assert unavailable.success is False
    assert "not available" in (unavailable.error_message or "")
    assert uninitialized.success is False
    assert "not initialized" in (uninitialized.error_message or "")
