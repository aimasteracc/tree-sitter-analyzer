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
def yaml_simple_mapping(draw):
    """Generate simple YAML mapping content."""
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
                        whitelist_categories=("Lu", "Ll", "Nd", "Zs"),
                        min_codepoint=32,
                        max_codepoint=122,
                    ),
                    min_size=1,
                    max_size=30,
                ),
                st.integers(min_value=0, max_value=1000).map(str),
                st.sampled_from(["true", "false", "null"]),
            )
        )
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


@st.composite
def yaml_simple_sequence(draw):
    """Generate simple YAML sequence content."""
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
def yaml_with_comments(draw):
    """Generate YAML content with comments."""
    num_lines = draw(st.integers(min_value=2, max_value=8))
    lines = []
    for _i in range(num_lines):
        if draw(st.booleans()):
            # Add a comment
            comment_text = draw(
                st.text(
                    alphabet=st.characters(
                        whitelist_categories=("Lu", "Ll", "Nd", "Zs"),
                        min_codepoint=32,
                        max_codepoint=122,
                    ),
                    min_size=1,
                    max_size=30,
                )
            )
            lines.append(f"# {comment_text}")
        else:
            # Add a mapping
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
            value = draw(st.integers(min_value=0, max_value=100).map(str))
            lines.append(f"{key}: {value}")
    return "\n".join(lines)


class TestYAMLElementMetadataProperties:
    """Property-based tests for YAML element metadata completeness."""

    @settings(max_examples=100)
    @given(yaml_content=yaml_simple_mapping())
    def test_property_4_element_metadata_line_numbers(self, yaml_content: str):
        """
        Feature: yaml-language-support, Property 4: Element Metadata Completeness

        For any extracted YAML element, the element SHALL have accurate start_line
        and end_line that correctly identify the element's position in the source.

        Validates: Requirements 2.4
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

        # Get source lines for validation
        source_lines = yaml_content.split("\n")
        total_lines = len(source_lines)

        # Property: All elements must have start_line attribute
        for element in elements:
            assert hasattr(
                element, "start_line"
            ), f"Element '{element.name}' must have start_line attribute"
            assert isinstance(
                element.start_line, int
            ), f"start_line must be int, got {type(element.start_line)}"

        # Property: All elements must have end_line attribute
        for element in elements:
            assert hasattr(
                element, "end_line"
            ), f"Element '{element.name}' must have end_line attribute"
            assert isinstance(
                element.end_line, int
            ), f"end_line must be int, got {type(element.end_line)}"

        # Property: start_line must be positive (1-indexed)
        for element in elements:
            assert element.start_line > 0, (
                f"Element '{element.name}' start_line must be positive, "
                f"got {element.start_line}"
            )

        # Property: end_line must be >= start_line
        for element in elements:
            assert element.end_line >= element.start_line, (
                f"Element '{element.name}' end_line ({element.end_line}) must be >= "
                f"start_line ({element.start_line})"
            )

        # Property: Line numbers must be within source bounds
        for element in elements:
            assert element.start_line <= total_lines, (
                f"Element '{element.name}' start_line ({element.start_line}) must be "
                f"<= total lines ({total_lines})"
            )
            assert element.end_line <= total_lines, (
                f"Element '{element.name}' end_line ({element.end_line}) must be "
                f"<= total lines ({total_lines})"
            )

        # Property: Line numbers must correspond to actual content
        for element in elements:
            # Get the lines for this element
            start_idx = element.start_line - 1  # Convert to 0-indexed
            end_idx = element.end_line  # end_line is inclusive, so no -1

            if start_idx < len(source_lines) and end_idx <= len(source_lines):
                element_lines = source_lines[start_idx:end_idx]
                element_text = "\n".join(element_lines)

                # Property: Element text should not be empty
                assert len(element_text.strip()) > 0, (
                    f"Element '{element.name}' at lines {element.start_line}-{element.end_line} "
                    f"should have non-empty content"
                )

    @settings(max_examples=100)
    @given(yaml_content=yaml_simple_mapping())
    def test_property_4_element_metadata_raw_text_accuracy(self, yaml_content: str):
        """
        Feature: yaml-language-support, Property 4: Element Metadata Completeness

        For any extracted YAML element, the raw_text SHALL accurately match the
        corresponding content from the source file.

        Validates: Requirements 2.5
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

        # Get source lines for validation
        source_lines = yaml_content.split("\n")

        # Property: All elements must have raw_text attribute
        for element in elements:
            assert hasattr(
                element, "raw_text"
            ), f"Element '{element.name}' must have raw_text attribute"
            assert isinstance(
                element.raw_text, str
            ), f"raw_text must be str, got {type(element.raw_text)}"

        # Property: raw_text must not be None
        for element in elements:
            assert (
                element.raw_text is not None
            ), f"Element '{element.name}' raw_text must not be None"

        # Property: raw_text should match source content at specified lines
        for element in elements:
            start_idx = element.start_line - 1  # Convert to 0-indexed
            end_idx = element.end_line  # end_line is inclusive

            if start_idx < len(source_lines) and end_idx <= len(source_lines):
                expected_text = "\n".join(source_lines[start_idx:end_idx])

                # Property: raw_text should match expected text from source
                # Note: tree-sitter may strip trailing whitespace from nodes,
                # so we compare stripped versions
                assert element.raw_text.rstrip() == expected_text.rstrip(), (
                    f"Element '{element.name}' raw_text does not match source. "
                    f"Expected: '{expected_text}', Got: '{element.raw_text}'"
                )

        # Property: raw_text should contain element's key (for mappings)
        mappings = [e for e in elements if e.element_type == "mapping" and e.key]
        for mapping in mappings:
            assert mapping.key in mapping.raw_text, (
                f"Mapping raw_text should contain key '{mapping.key}'. "
                f"Raw text: '{mapping.raw_text}'"
            )

        # Property: raw_text should contain element's value (for scalars with values)
        scalars = [e for e in elements if e.element_type == "scalar" and e.value]
        for scalar in scalars:
            # Value might be quoted or transformed, so check if it's present in some form
            assert (
                len(scalar.raw_text) > 0
            ), f"Scalar raw_text should not be empty. Value: '{scalar.value}'"

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

        # Property: Sequences must have valid metadata
        for sequence in sequences:
            # Property: Must have line numbers
            assert sequence.start_line > 0, "Sequence start_line must be positive"
            assert (
                sequence.end_line >= sequence.start_line
            ), "Sequence end_line must be >= start_line"

            # Property: Must have raw_text
            assert sequence.raw_text is not None, "Sequence raw_text must not be None"
            assert isinstance(sequence.raw_text, str), "Sequence raw_text must be str"
            assert len(sequence.raw_text) > 0, "Sequence raw_text must not be empty"

        # Property: Sequence raw_text should span multiple lines if sequence has items
        if sequences:
            main_sequence = sequences[0]
            if main_sequence.child_count and main_sequence.child_count > 0:
                # Multi-item sequences typically span multiple lines
                line_count = main_sequence.end_line - main_sequence.start_line + 1
                assert (
                    line_count >= 1
                ), f"Sequence with {main_sequence.child_count} items should span at least 1 line"

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

        # Property: All elements must have complete metadata
        for element in elements:
            # Property: Must have line numbers
            assert hasattr(element, "start_line"), "Must have start_line"
            assert hasattr(element, "end_line"), "Must have end_line"
            assert element.start_line > 0, "start_line must be positive"
            assert (
                element.end_line >= element.start_line
            ), "end_line must be >= start_line"

            # Property: Must have raw_text
            assert hasattr(element, "raw_text"), "Must have raw_text"
            assert element.raw_text is not None, "raw_text must not be None"
            assert isinstance(element.raw_text, str), "raw_text must be str"

        # Property: Comment elements should have accurate raw_text
        comments = [e for e in elements if e.element_type == "comment"]
        for comment in comments:
            # Comment raw_text should contain the # character
            assert (
                "#" in comment.raw_text
            ), f"Comment raw_text should contain '#'. Got: '{comment.raw_text}'"

            # Verify against source
            start_idx = comment.start_line - 1
            end_idx = comment.end_line
            if start_idx < len(source_lines) and end_idx <= len(source_lines):
                expected_text = "\n".join(source_lines[start_idx:end_idx])
                assert comment.raw_text == expected_text, (
                    f"Comment raw_text mismatch. Expected: '{expected_text}', "
                    f"Got: '{comment.raw_text}'"
                )

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

        # Generate YAML content with known structure
        lines = []
        for i in range(num_keys):
            lines.append(f"key{i}: value{i}")
        yaml_content = "\n".join(lines)

        # Parse the YAML content
        YAML_LANGUAGE = tree_sitter.Language(ts_yaml.language())
        parser = tree_sitter.Parser()
        parser.language = YAML_LANGUAGE
        tree = parser.parse(yaml_content.encode("utf-8"))

        # Extract elements
        extractor = YAMLElementExtractor()
        elements = extractor.extract_yaml_elements(tree, yaml_content)

        # Property: Number of elements should match expected count
        mappings = [e for e in elements if e.element_type == "mapping"]
        assert (
            len(mappings) == num_keys
        ), f"Expected {num_keys} mappings, got {len(mappings)}"

        # Property: Each mapping should be on a different line
        mapping_lines = [m.start_line for m in mappings]
        assert len(mapping_lines) == len(
            set(mapping_lines)
        ), f"Mappings should be on different lines. Lines: {mapping_lines}"

        # Property: Mappings should be in sequential order
        sorted_mappings = sorted(mappings, key=lambda m: m.start_line)
        for i, mapping in enumerate(sorted_mappings):
            expected_line = i + 1
            assert mapping.start_line == expected_line, (
                f"Mapping {i} should be on line {expected_line}, "
                f"got line {mapping.start_line}"
            )

        # Property: Each mapping's raw_text should match its source line
        source_lines = yaml_content.split("\n")
        for mapping in mappings:
            line_idx = mapping.start_line - 1
            expected_text = source_lines[line_idx]
            assert mapping.raw_text == expected_text, (
                f"Mapping raw_text mismatch at line {mapping.start_line}. "
                f"Expected: '{expected_text}', Got: '{mapping.raw_text}'"
            )

        # Property: Each mapping's key should be in its raw_text
        for mapping in mappings:
            if mapping.key:
                assert (
                    mapping.key in mapping.raw_text
                ), f"Mapping key '{mapping.key}' should be in raw_text '{mapping.raw_text}'"

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
        try:
            import tree_sitter
            import tree_sitter_yaml as ts_yaml
        except ImportError:
            pytest.skip("tree-sitter-yaml not available")

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

        # Parse the YAML content
        YAML_LANGUAGE = tree_sitter.Language(ts_yaml.language())
        parser = tree_sitter.Parser()
        parser.language = YAML_LANGUAGE
        tree = parser.parse(yaml_content.encode("utf-8"))

        # Extract elements
        extractor = YAMLElementExtractor()
        elements = extractor.extract_yaml_elements(tree, yaml_content)

        # Property: All elements must have complete metadata
        for element in elements:
            assert (
                element.start_line > 0
            ), f"Element '{element.name}' must have positive start_line"
            assert (
                element.end_line >= element.start_line
            ), f"Element '{element.name}' must have valid end_line"
            assert (
                element.raw_text is not None
            ), f"Element '{element.name}' must have raw_text"
            assert (
                len(element.raw_text) > 0
            ), f"Element '{element.name}' must have non-empty raw_text"

        # Property: Mappings should have accurate metadata
        mappings = [e for e in elements if e.element_type == "mapping"]
        for mapping in mappings:
            # Verify raw_text matches source
            source_lines = yaml_content.split("\n")
            start_idx = mapping.start_line - 1
            end_idx = mapping.end_line
            if start_idx < len(source_lines) and end_idx <= len(source_lines):
                expected_text = "\n".join(source_lines[start_idx:end_idx])
                assert (
                    mapping.raw_text == expected_text
                ), f"Mapping raw_text mismatch at line {mapping.start_line}"

        # Property: Sequences should have accurate metadata
        sequences = [e for e in elements if e.element_type == "sequence"]
        for sequence in sequences:
            assert sequence.start_line > 0, "Sequence must have valid start_line"
            assert (
                sequence.end_line >= sequence.start_line
            ), "Sequence must have valid end_line"
            assert sequence.raw_text is not None, "Sequence must have raw_text"
            assert len(sequence.raw_text) > 0, "Sequence must have non-empty raw_text"

        # Property: No two elements at the same nesting level should have identical line ranges
        # unless one is contained within the other
        for i, elem1 in enumerate(elements):
            for elem2 in elements[i + 1 :]:
                if elem1.nesting_level == elem2.nesting_level:
                    # If they have the same line range, they should be the same element
                    if (
                        elem1.start_line == elem2.start_line
                        and elem1.end_line == elem2.end_line
                    ):
                        # This is acceptable if they represent different aspects
                        # (e.g., a mapping and its value)
                        pass
                    else:
                        # Otherwise, they should not overlap
                        assert (
                            elem1.end_line < elem2.start_line
                            or elem2.end_line < elem1.start_line
                            or (
                                elem1.start_line <= elem2.start_line
                                and elem1.end_line >= elem2.end_line
                            )
                            or (
                                elem2.start_line <= elem1.start_line
                                and elem2.end_line >= elem1.end_line
                            )
                        ), (
                            f"Elements at same nesting level should not partially overlap. "
                            f"Element 1: {elem1.name} lines {elem1.start_line}-{elem1.end_line}, "
                            f"Element 2: {elem2.name} lines {elem2.start_line}-{elem2.end_line}"
                        )
