#!/usr/bin/env python3
"""
Property-based tests for YAML structure extraction.

Feature: yaml-language-support
Tests correctness properties for YAML structure extraction to ensure:
- All mappings are extracted with correct hierarchy
- All sequences are extracted with correct positions
- Nested structures preserve hierarchy information
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer.languages.yaml_plugin import (
    YAML_AVAILABLE,
    YAMLElementExtractor,
)

# Skip all tests if YAML is not available
pytestmark = pytest.mark.skipif(
    not YAML_AVAILABLE, reason="tree-sitter-yaml not installed"
)


# Strategies for generating valid YAML content
@st.composite
def yaml_mapping_content(draw):
    """Generate YAML content with mappings."""
    num_keys = draw(st.integers(min_value=1, max_value=10))
    lines = []
    for _i in range(num_keys):
        key = draw(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"),
                    min_codepoint=97,
                    max_codepoint=122,
                ),
                min_size=1,
                max_size=20,
            )
        )
        value = draw(
            st.one_of(
                st.text(
                    alphabet=st.characters(
                        whitelist_categories=("Lu", "Ll", "Nd"),
                        min_codepoint=97,
                        max_codepoint=122,
                    ),
                    min_size=1,
                    max_size=20,
                ),
                st.integers(min_value=0, max_value=1000).map(str),
                st.sampled_from(["true", "false", "null"]),
            )
        )
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


@st.composite
def yaml_sequence_content(draw):
    """Generate YAML content with sequences."""
    num_items = draw(st.integers(min_value=1, max_value=10))
    lines = []
    for _i in range(num_items):
        item = draw(
            st.one_of(
                st.text(
                    alphabet=st.characters(
                        whitelist_categories=("Lu", "Ll", "Nd"),
                        min_codepoint=97,
                        max_codepoint=122,
                    ),
                    min_size=1,
                    max_size=20,
                ),
                st.integers(min_value=0, max_value=1000).map(str),
            )
        )
        lines.append(f"- {item}")
    return "\n".join(lines)


@st.composite
def yaml_nested_content(draw):
    """Generate YAML content with nested structures."""
    depth = draw(st.integers(min_value=1, max_value=3))

    def generate_nested(current_depth, indent=""):
        if current_depth == 0:
            value = draw(
                st.one_of(
                    st.text(
                        alphabet=st.characters(
                            whitelist_categories=("Lu", "Ll", "Nd"),
                            min_codepoint=97,
                            max_codepoint=122,
                        ),
                        min_size=1,
                        max_size=15,
                    ),
                    st.integers(min_value=0, max_value=100).map(str),
                )
            )
            return value

        key = draw(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"),
                    min_codepoint=97,
                    max_codepoint=122,
                ),
                min_size=1,
                max_size=15,
            )
        )

        # Decide between nested mapping or simple value
        if draw(st.booleans()):
            # Nested mapping
            nested_key = draw(
                st.text(
                    alphabet=st.characters(
                        whitelist_categories=("Lu", "Ll", "Nd"),
                        min_codepoint=97,
                        max_codepoint=122,
                    ),
                    min_size=1,
                    max_size=15,
                )
            )
            nested_value = generate_nested(current_depth - 1, indent + "  ")
            return f"{key}:\n{indent}  {nested_key}: {nested_value}"
        else:
            # Simple value
            value = generate_nested(0, indent)
            return f"{key}: {value}"

    return generate_nested(depth)


def _extract_yaml_elements(yaml_content: str) -> list:
    """Parse YAML and return extracted elements. Skips if library unavailable."""
    try:
        import tree_sitter
        import tree_sitter_yaml as ts_yaml
    except ImportError:
        pytest.skip("tree-sitter-yaml not available")

    lang = tree_sitter.Language(ts_yaml.language())
    parser = tree_sitter.Parser()
    parser.language = lang
    tree = parser.parse(yaml_content.encode("utf-8"))
    extractor = YAMLElementExtractor()
    return extractor.extract_yaml_elements(tree, yaml_content)


def _group_by_level(elements) -> dict:
    """Group elements by nesting_level."""
    from collections import defaultdict

    by_level: dict = defaultdict(list)
    for element in elements:
        by_level[element.nesting_level].append(element)
    return dict(by_level)


def _assert_no_partial_overlap(level: int, level_elements: list) -> None:
    """Assert that elements at a given nesting level do not partially overlap."""
    sorted_elements = sorted(level_elements, key=lambda e: e.start_line)
    for i in range(len(sorted_elements) - 1):
        current = sorted_elements[i]
        next_elem = sorted_elements[i + 1]
        if current.end_line >= next_elem.start_line:
            assert (
                current.start_line <= next_elem.start_line
                and current.end_line >= next_elem.end_line
            ) or (
                next_elem.start_line <= current.start_line
                and next_elem.end_line >= current.end_line
            ), (
                f"Elements at level {level} should not partially overlap. "
                f"Element 1: lines {current.start_line}-{current.end_line}, "
                f"Element 2: lines {next_elem.start_line}-{next_elem.end_line}"
            )


class TestYAMLStructureExtractionProperties:
    """Property-based tests for YAML structure extraction."""

    @settings(max_examples=100)
    @given(yaml_content=yaml_mapping_content())
    def test_property_2_structure_extraction_mappings(self, yaml_content: str):
        """
        Feature: yaml-language-support, Property 2: Structure Extraction Completeness

        For any YAML file containing mappings, the extractor SHALL extract all
        key-value pairs with correct line numbers and hierarchy information.

        Validates: Requirements 1.2
        """
        elements = _extract_yaml_elements(yaml_content)

        # Property: All mappings must be extracted
        mappings = [e for e in elements if e.element_type == "mapping"]

        # Count expected mappings (lines with ':')
        expected_mapping_count = sum(
            1
            for line in yaml_content.split("\n")
            if ":" in line and not line.strip().startswith("#")
        )

        # Property: Number of extracted mappings should match expected count
        assert len(mappings) == expected_mapping_count, (
            f"Expected {expected_mapping_count} mappings, got {len(mappings)}. "
            f"Content:\n{yaml_content}\n"
            f"Extracted mappings: {[m.name for m in mappings]}"
        )

        # Property: Each mapping must have a key
        for mapping in mappings:
            assert mapping.key is not None, (
                f"Mapping at line {mapping.start_line} must have a key. "
                f"Raw text: {mapping.raw_text}"
            )
            assert len(mapping.key) > 0, (
                f"Mapping key at line {mapping.start_line} must not be empty"
            )

        # Property: Each mapping must have valid line numbers
        for mapping in mappings:
            assert mapping.start_line > 0, (
                f"Mapping start_line must be positive, got {mapping.start_line}"
            )
            assert mapping.end_line >= mapping.start_line, (
                f"Mapping end_line ({mapping.end_line}) must be >= start_line ({mapping.start_line})"
            )

        # Property: Mappings must have correct element_type
        for mapping in mappings:
            assert mapping.element_type == "mapping", (
                f"Element at line {mapping.start_line} must have element_type 'mapping', "
                f"got '{mapping.element_type}'"
            )

    @settings(max_examples=100)
    @given(
        mapping_content=yaml_mapping_content(),
        sequence_content=yaml_sequence_content(),
    )
    def test_property_2_structure_extraction_combined(
        self, mapping_content: str, sequence_content: str
    ):
        """
        Feature: yaml-language-support, Property 2: Structure Extraction Completeness

        For any YAML file containing both mappings and sequences, the extractor
        SHALL extract all structural elements correctly.

        Validates: Requirements 1.2, 1.3, 1.4
        """
        yaml_content = f"{mapping_content}\nitems:\n{sequence_content}"
        elements = _extract_yaml_elements(yaml_content)

        # Property: Both mappings and sequences must be extracted
        mappings = [e for e in elements if e.element_type == "mapping"]
        sequences = [e for e in elements if e.element_type == "sequence"]

        assert len(mappings) > 0, (
            f"Expected mappings to be extracted from combined content. "
            f"Content:\n{yaml_content}"
        )
        assert len(sequences) > 0, (
            f"Expected sequences to be extracted from combined content. "
            f"Content:\n{yaml_content}"
        )

        # Property: All elements must have valid line numbers
        for element in elements:
            assert element.start_line > 0, (
                f"Element start_line must be positive, got {element.start_line}"
            )
            assert element.end_line >= element.start_line, (
                "Element end_line must be >= start_line"
            )

        # Property: No overlapping elements at the same nesting level
        for level, level_elements in _group_by_level(elements).items():
            _assert_no_partial_overlap(level, level_elements)

    @settings(max_examples=50)
    @given(
        num_mappings=st.integers(min_value=1, max_value=5),
        num_sequences=st.integers(min_value=1, max_value=5),
    )
    def test_property_2_structure_extraction_completeness_count(
        self, num_mappings: int, num_sequences: int
    ):
        """
        Feature: yaml-language-support, Property 2: Structure Extraction Completeness

        For any YAML file, the number of extracted structural elements SHALL match
        the actual number of structures in the file.

        Validates: Requirements 1.2, 1.3
        """
        lines = [f"key{i}: value{i}" for i in range(num_mappings)]
        lines.append("items:")
        lines.extend(f"  - item{i}" for i in range(num_sequences))
        yaml_content = "\n".join(lines)
        elements = _extract_yaml_elements(yaml_content)

        # Property: Number of mappings should match (including the "items" key)
        mappings = [e for e in elements if e.element_type == "mapping"]
        expected_mappings = num_mappings + 1  # +1 for "items" key
        assert len(mappings) == expected_mappings, (
            f"Expected {expected_mappings} mappings, got {len(mappings)}. "
            f"Content:\n{yaml_content}\n"
            f"Extracted: {[m.name for m in mappings]}"
        )

        # Property: At least one sequence should be found
        sequences = [e for e in elements if e.element_type == "sequence"]
        assert len(sequences) >= 1, (
            f"Expected at least 1 sequence, got {len(sequences)}"
        )

        # Property: Sequence should have correct child count
        if sequences:
            main_sequence = sequences[0]
            assert main_sequence.child_count == num_sequences, (
                f"Sequence child_count ({main_sequence.child_count}) should match "
                f"number of items ({num_sequences})"
            )
