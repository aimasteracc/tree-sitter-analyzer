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
