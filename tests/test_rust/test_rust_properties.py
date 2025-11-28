#!/usr/bin/env python3
"""
Property-based tests for Rust support.

Covering:
- Property 2: Rust Element Extraction Completeness (Requirements 2.1-2.6)
- Property 8: Rust-Specific Terminology (Requirements 2.9)
"""

from unittest.mock import MagicMock, patch

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer.formatters.rust_formatter import RustTableFormatter
from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor
from tree_sitter_analyzer.models import AnalysisResult, Class, Function

# --- Strategies ---


@st.composite
def rust_visibilities(draw):
    """Generates Rust visibility modifiers."""
    return draw(st.sampled_from(["pub", "pub(crate)", "private", ""]))


@st.composite
def rust_types(draw):
    """Generates simple Rust types."""
    return draw(
        st.sampled_from(["i32", "String", "bool", "u64", "Option<T>", "Result<T, E>"])
    )


@st.composite
def rust_function_nodes(draw):
    """Generates a mock tree-sitter node representing a Rust function."""
    name = draw(
        st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"), min_codepoint=65
            ),
        )
    )
    visibility = draw(rust_visibilities())
    is_async = draw(st.booleans())
    return_type = draw(st.one_of(st.none(), rust_types()))

    # Create mock node
    node = MagicMock()
    node.type = "function_item"
    node.start_point = (draw(st.integers(0, 100)), 0)
    node.end_point = (node.start_point[0] + 5, 0)
    node.start_byte = 0
    node.end_byte = 100

    # Name child
    name_node = MagicMock()
    name_node.text = name.encode("utf-8")

    # Visibility child
    children = []
    if visibility and visibility != "private":
        vis_node = MagicMock()
        vis_node.type = "visibility_modifier"
        vis_node.text = visibility.encode("utf-8")
        children.append(vis_node)

    # Async modifier
    if is_async:
        # Either direct async node or function_modifiers -> async
        # Let's simulate function_modifiers -> async for robustness
        mod_node = MagicMock()
        mod_node.type = "function_modifiers"
        async_node = MagicMock()
        async_node.type = "async"
        mod_node.children = [async_node]
        children.append(mod_node)

    node.children = children

    # Return type child
    ret_node = None
    if return_type:
        ret_node = MagicMock()
        ret_node.text = f"-> {return_type}".encode()

    # child_by_field_name side effects
    def get_child_by_field(field):
        if field == "name":
            return name_node
        if field == "return_type":
            return ret_node
        if field == "parameters":
            return MagicMock(children=[])  # Empty params for simplicity
        return None

    node.child_by_field_name.side_effect = get_child_by_field

    return {
        "node": node,
        "name": name,
        "visibility": visibility
        if visibility and visibility != "private"
        else "private",
        "is_async": is_async,
        "return_type": return_type if return_type else "()",
    }


@st.composite
def rust_struct_nodes(draw):
    """Generates a mock tree-sitter node representing a Rust struct."""
    name = draw(
        st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"), min_codepoint=65
            ),
        )
    )
    visibility = draw(rust_visibilities())

    node = MagicMock()
    node.type = "struct_item"
    node.start_point = (draw(st.integers(0, 100)), 0)
    node.end_point = (node.start_point[0] + 3, 0)
    node.start_byte = 0
    node.end_byte = 50

    name_node = MagicMock()
    name_node.text = name.encode("utf-8")

    children = []
    if visibility and visibility != "private":
        vis_node = MagicMock()
        vis_node.type = "visibility_modifier"
        vis_node.text = visibility.encode("utf-8")
        children.append(vis_node)

    node.children = children

    def get_child_by_field(field):
        if field == "name":
            return name_node
        return None

    node.child_by_field_name.side_effect = get_child_by_field

    return {
        "node": node,
        "name": name,
        "visibility": visibility
        if visibility and visibility != "private"
        else "private",
    }


class TestRustProperties:
    @given(data=rust_function_nodes())
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_property_2_rust_function_extraction_completeness(self, data):
        """
        Property 2: Rust Element Extraction Completeness (Functions)

        Validates that given a well-formed function node, the extractor correctly
        populates the Function model with Rust-specific attributes.
        """
        extractor = RustElementExtractor()

        # Mock _get_node_text to return text from mock nodes
        def mock_get_text(n):
            if hasattr(n, "text"):
                return n.text.decode("utf-8")
            return ""

        with patch.object(extractor, "_get_node_text", side_effect=mock_get_text):
            func = extractor._extract_function(data["node"])

            assert func is not None
            assert func.name == data["name"]
            assert func.language == "rust"
            assert func.visibility == data["visibility"]
            assert func.return_type == data["return_type"]

            # Check async attribute (Rust specific)
            assert getattr(func, "is_async", False) == data["is_async"]

    @given(data=rust_struct_nodes())
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_property_2_rust_struct_extraction_completeness(self, data):
        """
        Property 2: Rust Element Extraction Completeness (Structs)

        Validates that given a well-formed struct node, the extractor correctly
        populates the Class model.
        """
        extractor = RustElementExtractor()

        def mock_get_text(n):
            if hasattr(n, "text"):
                return n.text.decode("utf-8")
            return ""

        with patch.object(extractor, "_get_node_text", side_effect=mock_get_text):
            cls = extractor._extract_struct(data["node"])

            assert cls is not None
            assert cls.name == data["name"]
            assert cls.class_type == "struct"
            assert cls.language == "rust"
            assert cls.visibility == data["visibility"]

    @given(
        funcs=st.lists(
            st.builds(
                Function,
                name=st.text(min_size=1),
                start_line=st.integers(1),
                end_line=st.integers(1),
            ),
            max_size=5,
        ),
        structs=st.lists(
            st.builds(
                Class,
                name=st.text(min_size=1),
                start_line=st.integers(1),
                end_line=st.integers(1),
            ),
            max_size=5,
        ),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_property_8_rust_terminology(self, funcs, structs):
        """
        Property 8: Rust-Specific Terminology

        Validates that the Rust formatter output contains Rust-specific terminology
        like 'Fn', 'Struct', 'Trait', 'impl', etc.
        """
        # Setup analysis result
        result = AnalysisResult(
            file_path="test.rs",
            language="rust",
            elements=funcs + structs,
            line_count=100,
        )

        formatter = RustTableFormatter()
        output = formatter.format_table(result.to_dict(), table_type="full")

        # Basic Rust terminology checks
        if funcs:
            assert "## Functions" in output
            assert "| Function | Signature |" in output

        if structs:
            assert "## Structs" in output
            assert "| Name | Type | Visibility |" in output

        # Check for absence of non-Rust terms if possible, e.g. "Method" is generic but "Fn" is preferred in compact?
        compact_output = formatter.format_summary(result.to_dict())
        if funcs:
            assert "Fn" in compact_output or "Function" in compact_output
