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
