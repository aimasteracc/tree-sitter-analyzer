#!/usr/bin/env python3
"""
Property-based tests for YAML element metadata completeness.

Feature: yaml-language-support
Tests correctness properties for YAML element metadata to ensure:
- All elements have accurate start_line
- All elements have accurate end_line
- All elements have accurate raw_text that matches source content
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.unit.languages._test_yaml_element_metadata_properties_helpers import (
    assert_comment_elements,
    assert_consistent_mappings,
    assert_element_line_number_properties,
    assert_mapping_raw_text_contains_key,
    assert_mixed_structures_complete_metadata,
    assert_mixed_structures_mapping_raw_text,
    assert_mixed_structures_nesting,
    assert_raw_text_fields,
    assert_raw_text_matches_source,
    assert_scalar_raw_text_non_empty,
    assert_sequence_metadata,
    parse_yaml_elements_and_lines,
)
from tree_sitter_analyzer.languages.yaml_plugin import (
    YAML_AVAILABLE,
    YAMLElementExtractor,
)

# Skip all tests if YAML is not available
pytestmark = pytest.mark.skipif(
    not YAML_AVAILABLE, reason="tree-sitter-yaml not installed"
)

_YAML_TEXT_CHARS = st.characters(
    whitelist_categories=("Lu", "Ll", "Nd"), min_codepoint=97, max_codepoint=122
)
_YAML_COMMENT_CHARS = st.characters(
    whitelist_categories=("Lu", "Ll", "Nd", "Zs"),
    min_codepoint=32,
    max_codepoint=122,
)


def _yaml_word() -> st.SearchStrategy[str]:
    return st.text(alphabet=_YAML_TEXT_CHARS, min_size=1, max_size=20)


def _yaml_comment() -> st.SearchStrategy[str]:
    return st.text(alphabet=_YAML_COMMENT_CHARS, min_size=1, max_size=30)


def _yaml_scalar_value() -> st.SearchStrategy[str]:
    """Generate YAML scalar values used in property strategies."""
    return st.one_of(
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=20),
        st.integers(min_value=0, max_value=100).map(str),
        st.sampled_from(["true", "false", "null"]),
    )


# Strategies for generating valid YAML content
@st.composite
def yaml_simple_mapping(draw):
    """Generate simple YAML mapping content."""
    num_keys = draw(st.integers(min_value=1, max_value=8))
    lines = []
    for _i in range(num_keys):
        # Simplified key generation - use simple ASCII letters only
        key = draw(
            st.text(
                alphabet="abcdefghijklmnopqrstuvwxyz",
                min_size=1,
                max_size=15,
            )
        )
        # Simplified value generation
        value = draw(_yaml_scalar_value())
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


@st.composite
def yaml_simple_sequence(draw):
    """Generate simple YAML sequence content."""
    num_items = draw(st.integers(min_value=1, max_value=10))
    lines = []
    for _i in range(num_items):
        item = draw(
            st.one_of(_yaml_word(), st.integers(min_value=0, max_value=1000).map(str))
        )
        lines.append(f"- {item}")
    return "\n".join(lines)


@st.composite
def yaml_with_comments(draw):
    """Generate YAML content with comments."""
    num_lines = draw(st.integers(min_value=2, max_value=8))
    lines = []
    for _i in range(num_lines):
        if draw(st.booleans()):
            # Add a comment
            comment_text = draw(_yaml_comment())
            lines.append(f"# {comment_text}")
        else:
            # Add a mapping
            key = draw(_yaml_word())
            value = draw(st.integers(min_value=0, max_value=100).map(str))
            lines.append(f"{key}: {value}")
    return "\n".join(lines)


class TestYAMLElementMetadataProperties:
    """Property-based tests for YAML element metadata completeness."""

    @settings(max_examples=50, deadline=500)
    @given(yaml_content=yaml_simple_mapping())
    def test_property_4_element_metadata_line_numbers(self, yaml_content: str):
        """
        Feature: yaml-language-support, Property 4: Element Metadata Completeness

        For any extracted YAML element, the element SHALL have accurate start_line
        and end_line that correctly identify the element's position in the source.

        Validates: Requirements 2.4
        """
        elements, source_lines = parse_yaml_elements_and_lines(yaml_content)
        assert_element_line_number_properties(elements, source_lines)
        assert len(elements) > 0
        for elem in elements:
            assert elem.start_line >= 1
            assert elem.end_line >= elem.start_line

    @settings(max_examples=100)
    @given(yaml_content=yaml_simple_mapping())
    def test_property_4_element_metadata_raw_text_accuracy(self, yaml_content: str):
        """
        Feature: yaml-language-support, Property 4: Element Metadata Completeness

        For any extracted YAML element, the raw_text SHALL accurately match the
        corresponding content from the source file.

        Validates: Requirements 2.5
        """
        elements, source_lines = parse_yaml_elements_and_lines(yaml_content)
        assert_raw_text_fields(elements)
        assert_raw_text_matches_source(elements, source_lines)
        assert_mapping_raw_text_contains_key(elements)
        assert_scalar_raw_text_non_empty(elements)
        for elem in elements:
            assert elem.raw_text is not None
            assert len(elem.raw_text) > 0

    @settings(max_examples=100)
    @given(yaml_content=yaml_simple_sequence())
    def test_property_4_element_metadata_sequence_accuracy(self, yaml_content: str):
        """
        Feature: yaml-language-support, Property 4: Element Metadata Completeness

        For any YAML sequence element, the metadata SHALL accurately reflect the
        sequence's position and content in the source.

        Validates: Requirements 2.4, 2.5
        """
        try:
            import tree_sitter
            import tree_sitter_yaml as ts_yaml
        except ImportError:
            pytest.skip("tree-sitter-yaml not available")

        # Parse the YAML content
        YAML_LANGUAGE = tree_sitter.Language(ts_yaml.language())
        parser = tree_sitter.Parser()
        parser.language = YAML_LANGUAGE
        tree = parser.parse(yaml_content.encode("utf-8"))

        # Extract elements
        extractor = YAMLElementExtractor()
        elements = extractor.extract_yaml_elements(tree, yaml_content)

        # Get sequences
        sequences = [e for e in elements if e.element_type == "sequence"]

        assert_sequence_metadata(sequences)
        for seq in sequences:
            assert seq.start_line >= 1
            assert seq.end_line >= seq.start_line

    @settings(max_examples=50)
    @given(yaml_content=yaml_with_comments())
    def test_property_4_element_metadata_with_comments(self, yaml_content: str):
        """
        Feature: yaml-language-support, Property 4: Element Metadata Completeness

        For any YAML file with comments, all elements (including comments) SHALL
        have accurate metadata.

        Validates: Requirements 2.4, 2.5
        """
        try:
            import tree_sitter
            import tree_sitter_yaml as ts_yaml
        except ImportError:
            pytest.skip("tree-sitter-yaml not available")

        # Parse the YAML content
        YAML_LANGUAGE = tree_sitter.Language(ts_yaml.language())
        parser = tree_sitter.Parser()
        parser.language = YAML_LANGUAGE
        tree = parser.parse(yaml_content.encode("utf-8"))

        # Extract elements
        extractor = YAMLElementExtractor()
        elements = extractor.extract_yaml_elements(tree, yaml_content)

        # Get source lines
        source_lines = yaml_content.split("\n")

        assert_comment_elements(elements, source_lines)
        comments = [e for e in elements if e.element_type == "comment"]
        for c in comments:
            assert c.start_line >= 1
            assert c.raw_text is not None

    @settings(max_examples=100)
    @given(
        num_keys=st.integers(min_value=1, max_value=15),
    )
    def test_property_4_element_metadata_consistency(self, num_keys: int):
        """
        Feature: yaml-language-support, Property 4: Element Metadata Completeness

        For any YAML file, all extracted elements SHALL have consistent and
        non-overlapping metadata that accurately represents the source structure.

        Validates: Requirements 2.4, 2.5
        """
        try:
            import tree_sitter
            import tree_sitter_yaml as ts_yaml
        except ImportError:
            pytest.skip("tree-sitter-yaml not available")

        lines = [f"key{i}: value{i}" for i in range(num_keys)]
        yaml_content = "\n".join(lines)

        # Parse the YAML content
        YAML_LANGUAGE = tree_sitter.Language(ts_yaml.language())
        parser = tree_sitter.Parser()
        parser.language = YAML_LANGUAGE
        tree = parser.parse(yaml_content.encode("utf-8"))

        # Extract elements
        extractor = YAMLElementExtractor()
        elements = extractor.extract_yaml_elements(tree, yaml_content)

        source_lines = yaml_content.split("\n")
        assert_consistent_mappings(elements, source_lines, num_keys)
        assert len(elements) > 0
        for elem in elements:
            assert elem.start_line >= 1

    @settings(max_examples=50)
    @given(
        mapping_count=st.integers(min_value=1, max_value=5),
        sequence_count=st.integers(min_value=1, max_value=5),
    )
    def test_property_4_element_metadata_mixed_structures(
        self, mapping_count: int, sequence_count: int
    ):
        """
        Feature: yaml-language-support, Property 4: Element Metadata Completeness

        For any YAML file with mixed structures (mappings and sequences), all
        elements SHALL have accurate and complete metadata.

        Validates: Requirements 2.4, 2.5
        """
        # Generate mixed YAML content
        lines = []

        # Add mappings
        for i in range(mapping_count):
            lines.append(f"key{i}: value{i}")

        # Add sequence
        lines.append("items:")
        for i in range(sequence_count):
            lines.append(f"  - item{i}")

        yaml_content = "\n".join(lines)
        elements, _ = parse_yaml_elements_and_lines(yaml_content)
        mappings = [e for e in elements if e.element_type == "mapping"]

        assert_mixed_structures_complete_metadata(elements)
        assert_mixed_structures_mapping_raw_text(mappings, yaml_content)
        assert_mixed_structures_nesting(elements)
        assert len(elements) > 0
        for m in mappings:
            assert m.raw_text is not None
            assert m.start_line >= 1
