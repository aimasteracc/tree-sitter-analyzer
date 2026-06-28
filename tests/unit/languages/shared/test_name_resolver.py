"""Tests for tree_sitter_analyzer.languages.shared.name_resolver."""

from __future__ import annotations

from tree_sitter_analyzer.languages.shared.name_resolver import (
    QualifiedNameBuilder,
    resolve_self_reference,
    strip_type_params,
)


class TestQualifiedNameBuilder:
    def test_empty_builder_returns_empty_string(self):
        builder = QualifiedNameBuilder()
        assert builder.build() == ""

    def test_single_push(self):
        builder = QualifiedNameBuilder()
        builder.push("MyClass")
        assert builder.build() == "MyClass"

    def test_two_parts_dot_separated(self):
        builder = QualifiedNameBuilder()
        builder.push("com.example")
        builder.push("MyClass")
        assert builder.build() == "com.example.MyClass"

    def test_custom_separator(self):
        builder = QualifiedNameBuilder(separator="::")
        builder.push("std")
        builder.push("collections")
        assert builder.build() == "std::collections"

    def test_pop_removes_last_part(self):
        builder = QualifiedNameBuilder()
        builder.push("A")
        builder.push("B")
        popped = builder.pop()
        assert popped == "B"
        assert builder.build() == "A"

    def test_pop_on_empty_returns_none(self):
        builder = QualifiedNameBuilder()
        assert builder.pop() is None

    def test_is_empty_tracks_state(self):
        builder = QualifiedNameBuilder()
        assert builder.is_empty() is True
        builder.push("X")
        assert builder.is_empty() is False

    def test_depth_tracks_pushes(self):
        builder = QualifiedNameBuilder()
        assert builder.depth() == 0
        builder.push("A")
        assert builder.depth() == 1
        builder.push("B")
        assert builder.depth() == 2

    def test_empty_string_push_is_ignored(self):
        builder = QualifiedNameBuilder()
        builder.push("")
        assert builder.build() == ""
        assert builder.is_empty() is True

    def test_three_levels(self):
        builder = QualifiedNameBuilder()
        builder.push("pkg")
        builder.push("Sub")
        builder.push("method")
        assert builder.build() == "pkg.Sub.method"


class TestResolveSelfReference:
    def test_self_is_self_reference(self):
        assert resolve_self_reference("self") is True

    def test_this_is_self_reference(self):
        assert resolve_self_reference("this") is True

    def test_me_is_self_reference(self):
        assert resolve_self_reference("me") is True

    def test_other_name_is_not_self_reference(self):
        assert resolve_self_reference("obj") is False

    def test_uppercase_self_is_not_self_reference(self):
        # Self-references are case-sensitive (tree-sitter output is lowercase)
        assert resolve_self_reference("Self") is False

    def test_empty_string_is_not_self_reference(self):
        assert resolve_self_reference("") is False


class TestStripTypeParams:
    def test_generic_angle_bracket(self):
        assert strip_type_params("Container<T>") == "Container"

    def test_generic_square_bracket(self):
        assert strip_type_params("List[String]") == "List"

    def test_multiple_type_params(self):
        assert strip_type_params("Map<K, V>") == "Map"

    def test_no_params(self):
        assert strip_type_params("Optional") == "Optional"

    def test_empty_string(self):
        assert strip_type_params("") == ""

    def test_strips_leading_whitespace(self):
        assert strip_type_params("  MyClass<T>") == "MyClass"

    def test_nested_generics(self):
        # Only strips at the outermost level
        assert strip_type_params("Outer<Inner<T>>") == "Outer"

    def test_paren_type_params(self):
        # Less common but handles e.g. function types
        assert strip_type_params("Func(int)") == "Func"

    def test_rust_path_style(self):
        # Rust has no generic syntax stripped here; bare names survive
        assert strip_type_params("HashMap") == "HashMap"
