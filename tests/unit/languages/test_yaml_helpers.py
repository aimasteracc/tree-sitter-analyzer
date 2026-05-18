"""Direct tests for YAML helper behavior."""

from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from tree_sitter_analyzer.languages.yaml_helpers import (
    analyze_yaml_file,
    append_mapping_element,
    build_alias_element,
    build_anchor_element,
    build_comment_element,
    build_document_element,
    build_mapping_element,
    build_sequence_element,
    count_document_children,
    count_sequence_children,
    extract_value_info,
)


@dataclass
class FakeNode:
    type: str
    text: str = ""
    children: list["FakeNode"] = field(default_factory=list)
    start_point: tuple[int, int] = (0, 0)
    end_point: tuple[int, int] = (0, 0)
    start_byte: int = 0
    parent: "FakeNode | None" = None
    prev_sibling: "FakeNode | None" = None

    def __post_init__(self) -> None:
        for child in self.children:
            child.parent = self


def _text(node: FakeNode) -> str:
    return node.text


def _document_index(_node: FakeNode) -> int:
    return 2


def _nesting_level(_node: FakeNode) -> int:
    return 3


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


def test_build_yaml_elements() -> None:
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

    assert document.element_type == "document"
    assert mapping_element.key == "key"
    assert mapping_element.value == "value"
    assert sequence_element.child_count == 2
    assert anchor.anchor_name == "defaults"
    assert alias.alias_target == "defaults"
    assert comment.value == "hello"


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
