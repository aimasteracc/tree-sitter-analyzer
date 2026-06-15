"""Tests for C AST traversal and type definition extraction helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tree_sitter_analyzer.languages._c_traversal_helpers import (
    _append_extracted_element,
    _depth_exceeded,
    _process_target_node,
    _push_children,
    _should_visit_node,
    c_traverse_and_extract,
)
from tree_sitter_analyzer.languages._c_type_definition_helpers import (
    _direct_type_name,
    _node_line_range,
    _raw_text,
    _type_name_and_range,
    _typedef_type_name,
    extract_enum_definition,
    extract_struct_definition,
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


class TestDepthExceeded:
    def test_within_limit(self) -> None:
        assert _depth_exceeded(5, 50) is False

    def test_at_limit(self) -> None:
        assert _depth_exceeded(50, 50) is False

    def test_over_limit(self) -> None:
        assert _depth_exceeded(51, 50) is True

    def test_zero_depth(self) -> None:
        assert _depth_exceeded(0, 50) is False


class TestShouldVisitNode:
    def test_root_depth_always_true(self) -> None:
        node = FakeNode("anything")
        assert _should_visit_node(node, 0, {"target"}) is True

    def test_target_node_type(self) -> None:
        node = FakeNode("target_type")
        assert _should_visit_node(node, 1, {"target_type"}) is True

    def test_container_node_type(self) -> None:
        node = FakeNode("translation_unit")
        assert _should_visit_node(node, 1, set()) is True

    def test_irrelevant_node_type(self) -> None:
        node = FakeNode("something_else")
        assert _should_visit_node(node, 1, {"target"}) is False


class TestAppendExtractedElement:
    def test_single_element(self) -> None:
        results: list[Any] = []
        _append_extracted_element(results, "element")
        assert results == ["element"]

    def test_list_element(self) -> None:
        results: list[Any] = []
        _append_extracted_element(results, ["a", "b"])
        assert results == ["a", "b"]

    def test_none_element(self) -> None:
        results: list[Any] = []
        _append_extracted_element(results, None)
        assert results == []

    def test_empty_list(self) -> None:
        results: list[Any] = []
        _append_extracted_element(results, [])
        assert results == []


class TestProcessTargetNode:
    def test_new_node_processed(self) -> None:
        node = FakeNode("function_definition", start_point=(0, 0), end_point=(5, 1))
        extractors = {"function_definition": lambda n: "func_result"}
        results: list[Any] = []
        processed: set[int] = set()
        cache: dict[tuple[int, str], Any] = {}
        should_continue = _process_target_node(
            node, extractors, results, "function", processed, cache
        )
        assert should_continue is True
        assert "func_result" in results
        assert id(node) in processed

    def test_already_processed_skipped(self) -> None:
        node = FakeNode("function_definition")
        extractors = {"function_definition": lambda n: "result"}
        results: list[Any] = []
        processed = {id(node)}
        cache: dict[tuple[int, str], Any] = {}
        should_continue = _process_target_node(
            node, extractors, results, "function", processed, cache
        )
        assert should_continue is False
        assert results == []

    def test_cached_element_reused(self) -> None:
        node = FakeNode("function_definition")
        extractors = {"function_definition": lambda n: "new_result"}
        results: list[Any] = []
        processed: set[int] = set()
        cache: dict[tuple[int, str], Any] = {(id(node), "function"): "cached"}
        _process_target_node(node, extractors, results, "function", processed, cache)
        assert results == ["cached"]

    def test_list_extractor_result(self) -> None:
        node = FakeNode("declaration")
        extractors = {"declaration": lambda n: ["var1", "var2"]}
        results: list[Any] = []
        processed: set[int] = set()
        cache: dict[tuple[int, str], Any] = {}
        _process_target_node(node, extractors, results, "variable", processed, cache)
        assert results == ["var1", "var2"]


class TestPushChildren:
    def test_pushes_children(self) -> None:
        child1 = FakeNode("child1")
        child2 = FakeNode("child2")
        parent = FakeNode("parent", children=[child1, child2])
        stack: list[tuple[Any, int]] = []
        _push_children(stack, parent, 2)
        assert len(stack) == 2
        assert stack[0] == (child2, 3)
        assert stack[1] == (child1, 3)

    def test_no_children(self) -> None:
        parent = FakeNode("parent", children=[])
        stack: list[tuple[Any, int]] = []
        _push_children(stack, parent, 0)
        assert stack == []


class TestCTraverseAndExtract:
    def test_none_root(self) -> None:
        results: list[Any] = []
        c_traverse_and_extract(None, {}, results, "test", set(), {})
        assert results == []

    def test_single_target_node(self) -> None:
        target = FakeNode("function_definition")
        root = FakeNode("translation_unit", children=[target])
        extractors = {"function_definition": lambda n: "found"}
        results: list[Any] = []
        c_traverse_and_extract(root, extractors, results, "function", set(), {})
        assert "found" in results

    def test_nested_in_container(self) -> None:
        target = FakeNode("declaration")
        compound = FakeNode("compound_statement", children=[target])
        root = FakeNode("function_definition", children=[compound])
        extractors = {"declaration": lambda n: "var"}
        results: list[Any] = []
        c_traverse_and_extract(root, extractors, results, "variable", set(), {})
        assert "var" in results

    def test_multiple_targets(self) -> None:
        t1 = FakeNode("function_definition")
        t2 = FakeNode("declaration")
        root = FakeNode("translation_unit", children=[t1, t2])
        extractors = {
            "function_definition": lambda n: "func",
            "declaration": lambda n: "var",
        }
        results: list[Any] = []
        c_traverse_and_extract(root, extractors, results, "element", set(), {})
        assert "func" in results
        assert "var" in results

    def test_empty_extractors(self) -> None:
        root = FakeNode("translation_unit", children=[FakeNode("anything")])
        results: list[Any] = []
        c_traverse_and_extract(root, {}, results, "test", set(), {})
        assert results == []

    def test_depth_limit_respected(self) -> None:
        deep_node = FakeNode("target")
        current = deep_node
        for _ in range(60):
            parent = FakeNode("translation_unit", children=[current])
            current = parent
        root = current
        extractors = {"target": lambda n: "deep"}
        results: list[Any] = []
        c_traverse_and_extract(root, extractors, results, "test", set(), {})
        assert results == []


class TestDirectTypeName:
    def test_finds_type_identifier(self) -> None:
        node = FakeNode(
            "struct_specifier",
            children=[
                FakeNode("type_identifier", text="Point"),
            ],
        )
        result = _direct_type_name(node, _get_node_text)
        assert result == "Point"

    def test_no_type_identifier(self) -> None:
        node = FakeNode(
            "struct_specifier",
            children=[
                FakeNode("field_declaration_list"),
            ],
        )
        result = _direct_type_name(node, _get_node_text)
        assert result is None


class TestTypedefTypeName:
    def test_typedef_parent(self) -> None:
        typedef_parent = FakeNode(
            "type_definition",
            children=[
                FakeNode("struct_specifier"),
                FakeNode("type_identifier", text="MyStruct"),
            ],
        )
        node = typedef_parent.children[0]
        node.parent = typedef_parent
        result = _typedef_type_name(node, _get_node_text)
        assert result == "MyStruct"

    def test_non_typedef_parent(self) -> None:
        parent = FakeNode("declaration")
        node = FakeNode("struct_specifier", parent=parent)
        result = _typedef_type_name(node, _get_node_text)
        assert result is None

    def test_no_parent(self) -> None:
        node = FakeNode("struct_specifier")
        result = _typedef_type_name(node, _get_node_text)
        assert result is None


class TestRawText:
    def test_basic(self) -> None:
        lines = ["struct Point {", "    int x;", "};"]
        result = _raw_text(lines, 1, 3)
        assert "struct Point {" in result
        assert "};" in result

    def test_empty(self) -> None:
        assert _raw_text([], 1, 1) == ""


class TestNodeLineRange:
    def test_basic(self) -> None:
        node = FakeNode("struct", start_point=(2, 0), end_point=(5, 1))
        start, end = _node_line_range(node)
        assert start == 3
        assert end == 6


class TestTypeNameAndRange:
    def test_direct_name(self) -> None:
        node = FakeNode(
            "struct_specifier",
            children=[
                FakeNode("type_identifier", text="Point"),
            ],
        )
        name, start, end = _type_name_and_range(node, _get_node_text, 1, 5, "anon")
        assert name == "Point"
        assert start == 1
        assert end == 5

    def test_typedef_name(self) -> None:
        typedef_parent = FakeNode(
            "type_definition",
            start_point=(0, 0),
            end_point=(3, 1),
            children=[
                FakeNode("struct_specifier"),
                FakeNode("type_identifier", text="Handle"),
            ],
        )
        node = typedef_parent.children[0]
        node.parent = typedef_parent
        name, start, end = _type_name_and_range(node, _get_node_text, 1, 3, "anon")
        assert name == "Handle"

    def test_anonymous(self) -> None:
        node = FakeNode(
            "struct_specifier",
            children=[
                FakeNode("field_declaration_list"),
            ],
        )
        name, start, end = _type_name_and_range(
            node, _get_node_text, 7, 10, "anonymous_struct"
        )
        assert name == "anonymous_struct_7"


class TestExtractStructDefinition:
    def test_named_struct(self) -> None:
        node = FakeNode(
            "struct_specifier",
            text="struct Point { int x; int y; };",
            start_point=(0, 0),
            end_point=(2, 1),
            children=[
                FakeNode("type_identifier", text="Point"),
                FakeNode("field_declaration_list"),
            ],
        )
        result = extract_struct_definition(
            node,
            _get_node_text,
            [
                "struct Point {",
                "    int x;",
                "    int y;",
                "};",
            ],
        )
        assert result is not None
        assert result.name == "Point"
        assert result.class_type == "struct"
        assert result.language == "c"

    def test_anonymous_struct(self) -> None:
        node = FakeNode(
            "struct_specifier",
            text="struct { int x; };",
            start_point=(4, 0),
            end_point=(5, 1),
            children=[FakeNode("field_declaration_list")],
        )
        result = extract_struct_definition(
            node,
            _get_node_text,
            [
                "struct {",
                "    int x;",
                "};",
            ],
        )
        assert result is not None
        assert "anonymous_struct" in result.name

    def test_exception_returns_none(self) -> None:
        node = FakeNode("struct_specifier")
        node.start_point = None
        result = extract_struct_definition(node, _get_node_text, [])
        assert result is None


class TestExtractEnumDefinition:
    def test_named_enum(self) -> None:
        node = FakeNode(
            "enum_specifier",
            text="enum Color { RED, GREEN, BLUE };",
            start_point=(0, 0),
            end_point=(0, 29),
            children=[
                FakeNode("type_identifier", text="Color"),
                FakeNode("enumerator_list"),
            ],
        )
        result = extract_enum_definition(
            node,
            _get_node_text,
            [
                "enum Color { RED, GREEN, BLUE };",
            ],
        )
        assert result is not None
        assert result.name == "Color"
        assert result.class_type == "enum"

    def test_anonymous_enum(self) -> None:
        node = FakeNode(
            "enum_specifier",
            text="enum { A, B };",
            start_point=(2, 0),
            end_point=(2, 13),
            children=[FakeNode("enumerator_list")],
        )
        result = extract_enum_definition(
            node,
            _get_node_text,
            [
                "enum { A, B };",
            ],
        )
        assert result is not None
        assert "anonymous_enum" in result.name

    def test_exception_returns_none(self) -> None:
        node = FakeNode("enum_specifier")
        node.start_point = None
        result = extract_enum_definition(node, _get_node_text, [])
        assert result is None

    def test_typedef_enum(self) -> None:
        typedef_parent = FakeNode(
            "type_definition",
            start_point=(0, 0),
            end_point=(2, 2),
            children=[
                FakeNode("enum_specifier", children=[]),
                FakeNode("type_identifier", text="StatusCode"),
            ],
        )
        node = typedef_parent.children[0]
        node.parent = typedef_parent
        result = extract_enum_definition(
            node,
            _get_node_text,
            [
                "typedef enum { OK, ERR } StatusCode;",
            ],
        )
        assert result is not None
        assert result.name == "StatusCode"
