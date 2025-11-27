#!/usr/bin/env python3
"""
Property-based tests for Kotlin support.

Covering:
- Property 3: Kotlin Element Extraction Completeness (Requirements 3.1-3.5)
- Property 9: Kotlin-Specific Terminology (Requirements 3.8)
"""

from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer.formatters.kotlin_formatter import KotlinTableFormatter
from tree_sitter_analyzer.languages.kotlin_plugin import KotlinElementExtractor
from tree_sitter_analyzer.models import AnalysisResult, Class, Function

# --- Strategies ---


@st.composite
def kotlin_visibilities(draw):
    """Generates Kotlin visibility modifiers."""
    return draw(st.sampled_from(["public", "private", "protected", "internal", ""]))


@st.composite
def kotlin_types(draw):
    """Generates simple Kotlin types."""
    return draw(
        st.sampled_from(
            ["Int", "String", "Boolean", "Unit", "List<String>", "Map<K, V>"]
        )
    )


@st.composite
def kotlin_function_nodes(draw):
    """Generates a mock tree-sitter node representing a Kotlin function."""
    name = draw(
        st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"), min_codepoint=65
            ),
        )
    )
    visibility = draw(kotlin_visibilities())
    is_suspend = draw(st.booleans())
    # Simplified return type generation

    # Create mock node
    node = MagicMock()
    node.type = "function_declaration"
    node.start_point = (draw(st.integers(0, 100)), 0)
    node.end_point = (node.start_point[0] + 5, 0)
    node.start_byte = 0
    node.end_byte = 100

    children = []

    # Modifiers
    mods_text = []
    if visibility and visibility != "public":
        mods_text.append(visibility)
    if is_suspend:
        mods_text.append("suspend")

    if mods_text:
        mods_node = MagicMock()
        mods_node.type = "modifiers"
        mods_node.text = " ".join(mods_text).encode("utf-8")
        children.append(mods_node)

    # Identifier (fallback logic mainly used in extractor)
    name_node = MagicMock()
    name_node.text = name.encode("utf-8")
    name_node.type = "simple_identifier"
    # children.append(name_node) # child_by_field_name usually preferred

    # : Return type (extractor logic iterates children)
    # We skip detailed children simulation for return type as it relies on ':' and position

    node.children = children

    def get_child_by_field(field):
        if field == "name":
            return name_node
        if field == "modifiers":
            return mods_node if mods_text else None
        if field == "parameters":
            return MagicMock(children=[])
        return None

    node.child_by_field_name.side_effect = get_child_by_field

    return {
        "node": node,
        "name": name,
        "visibility": visibility if visibility else "public",
        "is_suspend": is_suspend,
    }


@st.composite
def kotlin_class_nodes(draw):
    """Generates a mock tree-sitter node representing a Kotlin class."""
    name = draw(
        st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"), min_codepoint=65
            ),
        )
    )
    visibility = draw(kotlin_visibilities())
    kind = draw(st.sampled_from(["class", "interface", "object"]))

    node = MagicMock()
    node.type = "class_declaration" if kind != "object" else "object_declaration"
    node.start_point = (draw(st.integers(0, 100)), 0)
    node.end_point = (node.start_point[0] + 3, 0)
    node.start_byte = 0
    node.end_byte = 50

    # Name
    name_node = MagicMock()
    name_node.text = name.encode("utf-8")

    # Modifiers
    mods_text = []
    if visibility and visibility != "public":
        mods_text.append(visibility)

    mods_node = None
    if mods_text:
        mods_node = MagicMock()
        mods_node.type = "modifiers"
        mods_node.text = " ".join(mods_text).encode("utf-8")

    node.children = []  # Populate if needed for text-based check

    # Mock text for interface check
    full_text = f"{visibility} {kind} {name}"
    node.text = full_text.encode("utf-8")

    def get_child_by_field(field):
        if field == "name":
            return name_node
        if field == "modifiers":
            return mods_node
        return None

    node.child_by_field_name.side_effect = get_child_by_field

    return {
        "node": node,
        "name": name,
        "visibility": visibility if visibility else "public",
        "kind": kind,
    }


class TestKotlinProperties:
    @given(data=kotlin_function_nodes())
    @settings(max_examples=50)
    def test_property_3_kotlin_function_extraction_completeness(self, data):
        """
        Property 3: Kotlin Element Extraction Completeness (Functions)

        Validates that given a well-formed function node, the extractor correctly
        populates the Function model with Kotlin-specific attributes.
        """
        extractor = KotlinElementExtractor()

        def mock_get_text(n):
            if hasattr(n, "text"):
                return n.text.decode("utf-8")
            return ""

        with patch.object(extractor, "_get_node_text", side_effect=mock_get_text):
            func = extractor._extract_function(data["node"])

            assert func is not None
            assert func.name == data["name"]
            assert func.language == "kotlin"
            assert func.visibility == data["visibility"]

            # Check suspend attribute
            assert getattr(func, "is_suspend", False) == data["is_suspend"]

    @given(data=kotlin_class_nodes())
    @settings(max_examples=50)
    def test_property_3_kotlin_class_extraction_completeness(self, data):
        """
        Property 3: Kotlin Element Extraction Completeness (Classes)

        Validates that given a well-formed class node, the extractor correctly
        populates the Class model.
        """
        extractor = KotlinElementExtractor()

        def mock_get_text(n):
            if hasattr(n, "text"):
                return n.text.decode("utf-8")
            return ""

        with patch.object(extractor, "_get_node_text", side_effect=mock_get_text):
            kind = "object" if data["kind"] == "object" else "class"

            # For interface logic in _extract_class_or_object
            if data["kind"] == "interface":
                # The extractor checks self._get_node_text(node) which we mocked
                pass

            cls = extractor._extract_class_or_object(data["node"], kind)

            assert cls is not None
            assert cls.name == data["name"]
            assert cls.language == "kotlin"
            assert cls.visibility == data["visibility"]

            # Check kind (class, interface, object)
            assert cls.class_type == data["kind"]

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
        classes=st.lists(
            st.builds(
                Class,
                name=st.text(min_size=1),
                start_line=st.integers(1),
                end_line=st.integers(1),
            ),
            max_size=5,
        ),
    )
    @settings(max_examples=20)
    def test_property_9_kotlin_terminology(self, funcs, classes):
        """
        Property 9: Kotlin-Specific Terminology

        Validates that the Kotlin formatter output contains Kotlin-specific terminology.
        """
        # Setup analysis result
        result = AnalysisResult(
            file_path="test.kt",
            language="kotlin",
            elements=funcs + classes,
            line_count=100,
        )

        formatter = KotlinTableFormatter()
        output = formatter.format_table(result.to_dict(), table_type="full")

        if classes:
            assert "## Classes & Objects" in output

        compact_output = formatter.format_summary(result.to_dict())
        # Sanity check
        if funcs:
            assert "Fn" in compact_output
