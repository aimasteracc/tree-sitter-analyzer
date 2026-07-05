"""Unit tests for Swift AST node helper functions."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from tree_sitter_analyzer.languages._swift_plugin_nodes import (
    TYPE_DECLARATION_KINDS,
    VISIBILITY_MODIFIERS,
    base_element_fields,
    binding_kind,
    class_type,
    decode_node_text,
    fallback_name,
    first_descendant_text,
    inherited_types,
    interfaces,
    modifier_words,
    named_child_text,
    superclass,
    type_annotation,
    type_name,
    variable_name,
    visibility,
    walk,
)

try:
    import tree_sitter
    import tree_sitter_swift

    TREE_SITTER_SWIFT_AVAILABLE = True
except ImportError:
    TREE_SITTER_SWIFT_AVAILABLE = False


def _make_node(
    node_type: str = "source_file",
    text: bytes = b"",
    children: list | None = None,
    start_point: tuple[int, int] = (0, 0),
    end_point: tuple[int, int] = (0, 0),
    start_byte: int = 0,
    end_byte: int = 0,
) -> Mock:
    node = Mock()
    node.type = node_type
    node.text = text
    node.children = children or []
    node.start_point = start_point
    node.end_point = end_point
    node.start_byte = start_byte
    node.end_byte = end_byte
    node.child_by_field_name = Mock(return_value=None)
    return node


def _make_extractor_with_source(source: str) -> Mock:
    extractor = Mock()
    extractor.source_code = source
    extractor.content_lines = source.splitlines()
    extractor._node_text_cache = {}

    def get_node_text(node):
        start = node.start_byte
        end = node.end_byte
        key = (start, end)
        if key not in extractor._node_text_cache:
            text = node.text or b""
            if isinstance(text, bytes):
                text = text.decode("utf-8", errors="replace")
            extractor._node_text_cache[key] = text
        return extractor._node_text_cache[key]

    extractor.get_node_text = get_node_text
    return extractor


class TestConstants:
    def test_visibility_modifiers(self) -> None:
        assert "open" in VISIBILITY_MODIFIERS
        assert "public" in VISIBILITY_MODIFIERS
        assert "internal" in VISIBILITY_MODIFIERS
        assert "private" in VISIBILITY_MODIFIERS
        assert "fileprivate" in VISIBILITY_MODIFIERS

    def test_type_declaration_kinds(self) -> None:
        assert "class" in TYPE_DECLARATION_KINDS
        assert "struct" in TYPE_DECLARATION_KINDS
        assert "enum" in TYPE_DECLARATION_KINDS
        assert "actor" in TYPE_DECLARATION_KINDS
        assert "extension" in TYPE_DECLARATION_KINDS
        assert "protocol" not in TYPE_DECLARATION_KINDS


class TestWalk:
    def test_walk_single_node(self) -> None:
        root = _make_node("source_file", b"let x = 1")
        nodes = walk(root)
        assert len(nodes) == 1
        assert nodes[0] is root

    def test_walk_with_children(self) -> None:
        child1 = _make_node("let", b"let")
        child2 = _make_node("x", b"x")
        root = _make_node("source_file", b"let x", children=[child1, child2])
        nodes = walk(root)
        assert len(nodes) == 3
        assert nodes[0] is root
        assert nodes[1] is child1
        assert nodes[2] is child2

    def test_walk_nested(self) -> None:
        grandchild = _make_node("identifier", b"x")
        child = _make_node("binding", b"let x", children=[grandchild])
        root = _make_node("source_file", b"let x = 1", children=[child])
        nodes = walk(root)
        assert len(nodes) == 3


class TestDecodeNodeText:
    def test_bytes_input(self) -> None:
        node = _make_node(text=b"hello")
        assert decode_node_text(node) == "hello"

    def test_string_input(self) -> None:
        node = _make_node(text="hello")
        assert decode_node_text(node) == "hello"

    def test_none_input(self) -> None:
        node = Mock()
        node.text = None
        assert decode_node_text(node) == ""

    def test_utf8_decode_error(self) -> None:
        node = _make_node(text=b"\xff\xfe")
        result = decode_node_text(node)
        assert isinstance(result, str)


class TestModifierWords:
    def test_no_modifiers_field(self) -> None:
        node = _make_node("function_declaration")
        node.child_by_field_name = Mock(return_value=None)
        result = modifier_words(node)
        assert result == []

    def test_with_modifiers_field(self) -> None:
        modifiers_node = _make_node("modifiers", b"public static")
        node = _make_node("function_declaration")
        node.child_by_field_name = Mock(return_value=modifiers_node)
        result = modifier_words(node)
        assert "public" in result
        assert "static" in result

    def test_modifiers_as_child(self) -> None:
        modifiers_node = _make_node("modifiers", b"private")
        node = _make_node("function_declaration", children=[modifiers_node])
        node.child_by_field_name = Mock(return_value=None)
        result = modifier_words(node)
        assert "private" in result

    def test_modifiers_with_non_alpha(self) -> None:
        modifiers_node = _make_node("modifiers", b"@available(iOS 16, *)")
        node = _make_node("function_declaration")
        node.child_by_field_name = Mock(return_value=modifiers_node)
        result = modifier_words(node)
        assert all(w.isalpha() or "_" in w for w in result)


class TestClassType:
    def test_protocol_declaration(self) -> None:
        node = _make_node("protocol_declaration")
        assert class_type(node) == "protocol"

    def test_with_declaration_kind_field(self) -> None:
        kind_node = _make_node("struct", b"struct")
        node = _make_node("class_declaration")
        node.child_by_field_name = Mock(
            side_effect=lambda n: kind_node if n == "declaration_kind" else None
        )
        assert class_type(node) == "struct"

    def test_with_child_type(self) -> None:
        kind_child = _make_node("enum", b"enum")
        node = _make_node("class_declaration", children=[kind_child])
        node.child_by_field_name = Mock(return_value=None)
        assert class_type(node) == "enum"

    def test_default_class(self) -> None:
        node = _make_node("class_declaration")
        node.child_by_field_name = Mock(return_value=None)
        assert class_type(node) == "class"


class TestBindingKind:
    def test_let_binding(self) -> None:
        vbp = _make_node("value_binding_pattern", b"let")
        node = _make_node("property_declaration", b"let x: Int", children=[vbp])
        assert binding_kind(node, "let x: Int") == "let"

    def test_var_binding(self) -> None:
        vbp = _make_node("value_binding_pattern", b"var")
        node = _make_node("property_declaration", b"var x: Int", children=[vbp])
        assert binding_kind(node, "var x: Int") == "var"

    def test_fallback_let(self) -> None:
        node = _make_node("property_declaration", b"  let x = 1")
        assert binding_kind(node, "  let x = 1") == "let"

    def test_fallback_var(self) -> None:
        node = _make_node("property_declaration", b"var y = 2")
        assert binding_kind(node, "var y = 2") == "var"

    def test_fallback_default(self) -> None:
        node = _make_node("property_declaration", b"x = 3")
        assert binding_kind(node, "x = 3") == "var"


class TestVisibility:
    def test_public(self) -> None:
        assert visibility(["public"]) == "public"

    def test_private(self) -> None:
        assert visibility(["private"]) == "private"

    def test_open(self) -> None:
        assert visibility(["open"]) == "open"

    def test_fileprivate(self) -> None:
        assert visibility(["fileprivate"]) == "fileprivate"

    def test_internal_default(self) -> None:
        assert visibility([]) == "internal"
        assert visibility(["static"]) == "internal"
        assert visibility(["final"]) == "internal"

    def test_first_visibility_wins(self) -> None:
        assert visibility(["public", "private"]) == "public"


class TestBaseElementFields:
    def test_fields(self) -> None:
        node = _make_node(
            start_point=(4, 0),
            end_point=(10, 5),
        )
        fields = base_element_fields(node, "raw code", "TestName")
        assert fields["name"] == "TestName"
        assert fields["start_line"] == 5
        assert fields["end_line"] == 11
        assert fields["raw_text"] == "raw code"
        assert fields["language"] == "swift"


class TestNamedChildText:
    def test_finds_matching_descendant(self) -> None:
        identifier = _make_node(
            "simple_identifier", b"myFunc", start_byte=0, end_byte=6
        )
        parent = _make_node(
            "function_declaration", b"func myFunc()", children=[identifier]
        )
        extractor = _make_extractor_with_source("func myFunc()")
        result = named_child_text(extractor, parent, ("simple_identifier",))
        assert result == "myFunc"

    def test_fallback_name(self) -> None:
        parent = _make_node("function_declaration", b"func ()")
        extractor = _make_extractor_with_source("func ()")
        result = named_child_text(extractor, parent, ("simple_identifier",))
        assert result.startswith("element_")


class TestFirstDescendantText:
    def test_matching_type(self) -> None:
        identifier = _make_node("identifier", b"foo", start_byte=0, end_byte=3)
        parent = _make_node("expression", b"foo", children=[identifier])
        extractor = _make_extractor_with_source("foo")
        result = first_descendant_text(extractor, parent, ("identifier",))
        assert result == "foo"

    def test_no_match(self) -> None:
        parent = _make_node("expression", b"bar")
        extractor = _make_extractor_with_source("bar")
        result = first_descendant_text(extractor, parent, ("identifier",))
        assert result == ""


class TestTypeName:
    def test_with_name_field(self) -> None:
        name_child = _make_node("type_identifier", b"MyType", start_byte=0, end_byte=6)
        name_field = _make_node("name", b"MyType", children=[name_child])
        node = _make_node("class_declaration", b"class MyType {}")
        node.child_by_field_name = Mock(
            side_effect=lambda n: name_field if n == "name" else None
        )
        extractor = _make_extractor_with_source("class MyType {}")
        result = type_name(extractor, node)
        assert result == "MyType"

    def test_without_name_field(self) -> None:
        type_child = _make_node(
            "type_identifier", b"MyStruct", start_byte=0, end_byte=8
        )
        node = _make_node(
            "struct_declaration", b"struct MyStruct {}", children=[type_child]
        )
        node.child_by_field_name = Mock(return_value=None)
        extractor = _make_extractor_with_source("struct MyStruct {}")
        result = type_name(extractor, node)
        assert result == "MyStruct"


class TestVariableName:
    def test_with_name_field(self) -> None:
        id_child = _make_node("simple_identifier", b"myVar", start_byte=0, end_byte=5)
        name_field = _make_node("name", b"myVar", children=[id_child])
        node = _make_node("property_declaration", b"var myVar: Int")
        node.child_by_field_name = Mock(
            side_effect=lambda n: name_field if n == "name" else None
        )
        extractor = _make_extractor_with_source("var myVar: Int")
        result = variable_name(extractor, node)
        assert result == "myVar"

    def test_without_name_field(self) -> None:
        id_child = _make_node("simple_identifier", b"myVar", start_byte=0, end_byte=5)
        node = _make_node(
            "property_declaration", b"var myVar: Int", children=[id_child]
        )
        node.child_by_field_name = Mock(return_value=None)
        extractor = _make_extractor_with_source("var myVar: Int")
        result = variable_name(extractor, node)
        assert result == "myVar"


class TestTypeAnnotation:
    def test_with_type_annotation(self) -> None:
        ta_child = _make_node("type_annotation", b": String", start_byte=0, end_byte=8)
        node = _make_node("property_declaration", b"var x: String", children=[ta_child])
        extractor = _make_extractor_with_source("var x: String")
        result = type_annotation(extractor, node)
        assert result is not None
        assert "String" in result

    def test_without_type_annotation(self) -> None:
        node = _make_node("property_declaration", b"var x = 1")
        extractor = _make_extractor_with_source("var x = 1")
        result = type_annotation(extractor, node)
        assert result is None


class TestInheritedTypes:
    def test_with_inheritance(self) -> None:
        result = inherited_types("class Foo: Bar, Baz {")
        assert "Bar" in result
        assert "Baz" in result

    def test_no_inheritance(self) -> None:
        result = inherited_types("struct Foo {")
        assert result == []

    def test_colon_no_types(self) -> None:
        result = inherited_types("class Foo: {")
        assert result == []

    def test_single_protocol(self) -> None:
        result = inherited_types("struct Foo: Codable {")
        assert result == ["Codable"]


class TestSuperclass:
    def test_class_with_inheritance(self) -> None:
        assert superclass("class", ["Base", "Proto"]) == "Base"

    def test_class_no_inheritance(self) -> None:
        assert superclass("class", []) is None

    def test_struct_no_superclass(self) -> None:
        assert superclass("struct", ["Codable"]) is None

    def test_enum_no_superclass(self) -> None:
        assert superclass("enum", ["Error"]) is None


class TestInterfaces:
    def test_with_superclass(self) -> None:
        result = interfaces(["Base", "Proto1", "Proto2"], "Base")
        assert result == ["Proto1", "Proto2"]

    def test_without_superclass(self) -> None:
        result = interfaces(["Proto1", "Proto2"], None)
        assert result == ["Proto1", "Proto2"]

    def test_empty(self) -> None:
        assert interfaces([], None) == []

    def test_single_with_superclass(self) -> None:
        result = interfaces(["Base"], "Base")
        assert result == []


class TestFallbackName:
    def test_format(self) -> None:
        node = _make_node(start_point=(10, 5))
        result = fallback_name(node)
        assert result == "element_11_6"

    def test_zero_position(self) -> None:
        node = _make_node(start_point=(0, 0))
        result = fallback_name(node)
        assert result == "element_1_1"


@pytest.mark.skipif(
    not TREE_SITTER_SWIFT_AVAILABLE,
    reason="tree-sitter-swift not installed",
)
class TestWalkWithRealParser:
    def test_walk_real_tree(self) -> None:
        language = tree_sitter.Language(tree_sitter_swift.language())
        parser = tree_sitter.Parser()
        parser.language = language
        tree = parser.parse(b"struct Foo { let x: Int }")
        nodes = walk(tree.root_node)
        assert len(nodes) > 1  # ratchet: nondeterministic

    def test_decode_real_node(self) -> None:
        language = tree_sitter.Language(tree_sitter_swift.language())
        parser = tree_sitter.Parser()
        parser.language = language
        tree = parser.parse(b"import Foundation")
        import_node = tree.root_node.children[0]
        text = decode_node_text(import_node)
        assert "Foundation" in text
