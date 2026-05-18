"""Helpers for YAML metadata property tests."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.languages.yaml_plugin import YAMLElementExtractor


def parse_yaml_elements_and_lines(yaml_content: str):
    """Parse YAML content and return elements with their source lines."""
    try:
        import tree_sitter
        import tree_sitter_yaml as ts_yaml
    except ImportError:
        pytest.skip("tree-sitter-yaml not available")

    yaml_language = tree_sitter.Language(ts_yaml.language())
    parser = tree_sitter.Parser()
    parser.language = yaml_language
    tree = parser.parse(yaml_content.encode("utf-8"))

    extractor = YAMLElementExtractor()
    elements = extractor.extract_yaml_elements(tree, yaml_content)
    source_lines = yaml_content.split("\n")
    return elements, source_lines


def assert_element_line_number_properties(elements, source_lines):
    """Assert core line-number invariants for extracted YAML elements."""
    total_lines = len(source_lines)

    for element in elements:
        assert hasattr(element, "start_line"), (
            f"Element '{element.name}' must have start_line attribute"
        )
        assert isinstance(element.start_line, int), (
            f"start_line must be int, got {type(element.start_line)}"
        )

    for element in elements:
        assert hasattr(element, "end_line"), (
            f"Element '{element.name}' must have end_line attribute"
        )
        assert isinstance(element.end_line, int), (
            f"end_line must be int, got {type(element.end_line)}"
        )

    for element in elements:
        assert element.start_line > 0, (
            f"Element '{element.name}' start_line must be positive, "
            f"got {element.start_line}"
        )

    for element in elements:
        assert element.end_line >= element.start_line, (
            f"Element '{element.name}' end_line ({element.end_line}) must be >= "
            f"start_line ({element.start_line})"
        )
        assert element.start_line <= total_lines, (
            f"Element '{element.name}' start_line ({element.start_line}) must be "
            f"<= total lines ({total_lines})"
        )
        assert element.end_line <= total_lines, (
            f"Element '{element.name}' end_line ({element.end_line}) must be <= "
            f"total lines ({total_lines})"
        )

    for element in elements:
        start_idx = element.start_line - 1
        end_idx = element.end_line
        if start_idx < len(source_lines) and end_idx <= len(source_lines):
            element_lines = source_lines[start_idx:end_idx]
            element_text = "\n".join(element_lines)
            assert len(element_text.strip()) > 0, (
                f"Element '{element.name}' at lines {element.start_line}-{element.end_line} "
                "should have non-empty content"
            )


def assert_mixed_structures_complete_metadata(elements):
    """Assert mixed structure elements have complete metadata fields."""
    for element in elements:
        assert element.start_line > 0, (
            f"Element '{element.name}' must have valid start_line"
        )
        assert element.end_line >= element.start_line, (
            f"Element '{element.name}' must have valid end_line"
        )
        assert element.raw_text is not None, (
            f"Element '{element.name}' must have raw_text"
        )
        assert len(element.raw_text) > 0, (
            f"Element '{element.name}' must have non-empty raw_text"
        )


def assert_mixed_structures_mapping_raw_text(mappings, yaml_content):
    """Assert mapping raw_text matches the original YAML source lines."""
    source_lines = yaml_content.split("\n")
    for mapping in mappings:
        start_idx = mapping.start_line - 1
        end_idx = mapping.end_line
        if start_idx < len(source_lines) and end_idx <= len(source_lines):
            expected_text = "\n".join(source_lines[start_idx:end_idx])
            assert mapping.raw_text == expected_text, (
                f"Mapping raw_text mismatch at line {mapping.start_line}"
            )


def assert_mixed_structures_nesting(elements):
    """Assert same-level elements have no partial overlaps."""
    for i, elem1 in enumerate(elements):
        for elem2 in elements[i + 1 :]:
            if elem1.nesting_level != elem2.nesting_level:
                continue
            if (
                elem1.start_line == elem2.start_line
                and elem1.end_line == elem2.end_line
            ):
                continue
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


def assert_raw_text_fields(elements):
    """Assert raw_text presence and string type for extracted elements."""
    for element in elements:
        assert hasattr(element, "raw_text"), (
            f"Element '{element.name}' must have raw_text attribute"
        )
        assert isinstance(element.raw_text, str), (
            f"raw_text must be str, got {type(element.raw_text)}"
        )
        assert element.raw_text is not None, (
            f"Element '{element.name}' raw_text must not be None"
        )


def assert_raw_text_matches_source(elements, source_lines):
    """Assert raw_text matches YAML source text for each element range."""
    for element in elements:
        start_idx = element.start_line - 1
        end_idx = element.end_line

        if start_idx < len(source_lines) and end_idx <= len(source_lines):
            expected_text = "\n".join(source_lines[start_idx:end_idx])
            assert element.raw_text.rstrip() == expected_text.rstrip(), (
                f"Element '{element.name}' raw_text does not match source. "
                f"Expected: '{expected_text}', Got: '{element.raw_text}'"
            )


def assert_mapping_raw_text_contains_key(elements):
    """Assert mapping raw_text includes declared keys."""
    mappings = [e for e in elements if e.element_type == "mapping" and e.key]
    for mapping in mappings:
        assert mapping.key in mapping.raw_text, (
            f"Mapping raw_text should contain key '{mapping.key}'. "
            f"Raw text: '{mapping.raw_text}'"
        )


def assert_scalar_raw_text_non_empty(elements):
    """Assert scalar elements with values have non-empty raw text."""
    scalars = [e for e in elements if e.element_type == "scalar" and e.value]
    for scalar in scalars:
        assert len(scalar.raw_text) > 0, (
            f"Scalar raw_text should not be empty. Value: '{scalar.value}'"
        )


def assert_comment_raw_text(elements, source_lines):
    """Assert comment elements have raw text and source alignment."""
    comments = [e for e in elements if e.element_type == "comment"]
    for comment in comments:
        assert "#" in comment.raw_text, (
            f"Comment raw_text should contain '#'. Got: '{comment.raw_text}'"
        )

        start_idx = comment.start_line - 1
        end_idx = comment.end_line
        if start_idx < len(source_lines) and end_idx <= len(source_lines):
            expected_text = "\n".join(source_lines[start_idx:end_idx])
            assert comment.raw_text == expected_text, (
                f"Comment raw_text mismatch. Expected: '{expected_text}', "
                f"Got: '{comment.raw_text}'"
            )


def assert_comment_elements(elements, source_lines):
    """Assert comment metadata is complete and source aligned."""
    for element in elements:
        assert hasattr(element, "start_line"), (
            f"Element '{element.name}' must have start_line"
        )
        assert hasattr(element, "end_line"), (
            f"Element '{element.name}' must have end_line"
        )
        assert element.start_line > 0, "start_line must be positive"
        assert element.end_line >= element.start_line, "end_line must be >= start_line"
        assert hasattr(element, "raw_text"), (
            f"Element '{element.name}' must have raw_text"
        )
        assert element.raw_text is not None, "raw_text must not be None"
        assert isinstance(element.raw_text, str), "raw_text must be str"

    assert_comment_raw_text(elements, source_lines)


def assert_element_line_metadata(elements):
    """Assert every element has numeric and non-empty metadata."""
    for element in elements:
        assert element.start_line > 0, (
            f"Element '{element.name}' start_line must be positive"
        )
        assert element.end_line >= element.start_line, (
            f"Element '{element.name}' end_line ({element.end_line}) must be >= "
            f"start_line ({element.start_line})"
        )


def assert_consistent_mappings(elements, source_lines, num_keys: int):
    """Assert mappings are complete and aligned for consistency test."""
    mappings = [e for e in elements if e.element_type == "mapping"]
    assert len(mappings) == num_keys, (
        f"Expected {num_keys} mappings, got {len(mappings)}"
    )

    mapping_lines = [m.start_line for m in mappings]
    assert len(mapping_lines) == len(set(mapping_lines)), (
        f"Mappings should be on different lines. Lines: {mapping_lines}"
    )

    sorted_mappings = sorted(mappings, key=lambda m: m.start_line)
    for i, mapping in enumerate(sorted_mappings):
        assert mapping.start_line == i + 1, (
            f"Mapping {i} should be on line {i + 1}, got line {mapping.start_line}"
        )

    for mapping in mappings:
        expected_text = source_lines[mapping.start_line - 1]
        assert mapping.raw_text == expected_text, (
            f"Mapping raw_text mismatch at line {mapping.start_line}. "
            f"Expected: '{expected_text}', Got: '{mapping.raw_text}'"
        )
        if mapping.key:
            assert mapping.key in mapping.raw_text, (
                f"Mapping key '{mapping.key}' should be in raw_text '{mapping.raw_text}'"
            )


def assert_sequence_metadata(sequences):
    """Assert sequence-specific metadata invariants."""
    for sequence in sequences:
        assert sequence.start_line > 0, "Sequence start_line must be positive"
        assert sequence.end_line >= sequence.start_line, (
            "Sequence end_line must be >= start_line"
        )
        assert sequence.raw_text is not None, "Sequence raw_text must not be None"
        assert isinstance(sequence.raw_text, str), "Sequence raw_text must be str"
        assert len(sequence.raw_text) > 0, "Sequence raw_text must not be empty"

    if not sequences or not sequences[0].child_count:
        return

    main_sequence = sequences[0]
    line_count = main_sequence.end_line - main_sequence.start_line + 1
    assert line_count >= 1, (
        f"Sequence with {main_sequence.child_count} items should span at least 1 line"
    )
