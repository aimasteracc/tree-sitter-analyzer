#!/usr/bin/env python3
"""
Property-based tests for YAMLElement data model.

Feature: yaml-language-support
Tests correctness properties for YAMLElement to ensure:
- All required attributes are present
- Serialization to JSON produces valid output
"""

import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer.models import YAMLElement

# Strategies for generating valid YAML element data
yaml_element_types = st.sampled_from(
    ["mapping", "sequence", "scalar", "anchor", "alias", "comment", "document", "yaml"]
)

yaml_value_types = st.sampled_from(
    ["string", "number", "boolean", "null", "mapping", "sequence", None]
)

# Strategy for valid YAML keys (non-empty strings)
yaml_keys = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"),
        min_codepoint=48,
        max_codepoint=122,
    ),
    min_size=1,
    max_size=50,
).filter(lambda x: x and len(x.strip()) > 0)

# Strategy for YAML scalar values
yaml_scalar_values = st.one_of(
    st.text(min_size=0, max_size=100),
    st.integers().map(str),
    st.sampled_from(["true", "false", "null", "~", ""]),
)

# Strategy for line numbers (positive integers)
line_numbers = st.integers(min_value=1, max_value=10000)

# Strategy for nesting levels
nesting_levels = st.integers(min_value=0, max_value=20)

# Strategy for document indices
document_indices = st.integers(min_value=0, max_value=100)

# Strategy for child counts
child_counts = st.one_of(st.none(), st.integers(min_value=0, max_value=1000))

# Strategy for anchor/alias names
anchor_names = st.one_of(
    st.none(),
    st.text(
        alphabet=st.characters(
            whitelist_categories=("Lu", "Ll", "Nd"),
            min_codepoint=48,
            max_codepoint=122,
        ),
        min_size=1,
        max_size=30,
    ).filter(lambda x: x and len(x.strip()) > 0),
)


def _assert_base_element_attrs(element) -> None:
    """Assert that base CodeElement attributes are present."""
    for attr in (
        "name",
        "start_line",
        "end_line",
        "raw_text",
        "language",
        "element_type",
    ):
        assert hasattr(element, attr), f"YAMLElement must have '{attr}' attribute"


def _assert_yaml_specific_attrs(element) -> None:
    """Assert that YAML-specific attributes are present."""
    for attr in (
        "key",
        "value",
        "value_type",
        "anchor_name",
        "alias_target",
        "nesting_level",
        "document_index",
        "child_count",
    ):
        assert hasattr(element, attr), f"YAMLElement must have '{attr}' attribute"


def _assert_summary_required_fields(summary: dict) -> None:
    """Assert that a to_summary_item() result has required fields."""
    for field in ("name", "type", "lines"):
        assert field in summary, f"Summary must contain '{field}' field"
    assert "start" in summary["lines"], "Lines must contain 'start' field"
    assert "end" in summary["lines"], "Lines must contain 'end' field"
    for field in ("key", "value_type", "nesting_level", "document_index"):
        assert field in summary, f"Summary must contain '{field}' field"


def _assert_json_roundtrip(summary: dict) -> None:
    """Assert that summary is JSON-serializable and round-trips correctly."""
    try:
        json_str = json.dumps(summary)
        assert isinstance(json_str, str) and len(json_str) > 0
    except (TypeError, ValueError) as e:
        pytest.fail(f"Summary must be JSON serializable: {e}")
    try:
        parsed = json.loads(json_str)
        assert parsed == summary, "JSON round-trip must preserve data"
    except json.JSONDecodeError as e:
        pytest.fail(f"JSON must be parseable: {e}")


class TestYAMLElementProperties:
    """Property-based tests for YAMLElement data model."""

    @settings(max_examples=100)
    @given(
        name=yaml_keys,
        start_line=line_numbers,
        end_line_offset=st.integers(min_value=0, max_value=100),
        raw_text=st.text(min_size=0, max_size=200),
        element_type=yaml_element_types,
        key=st.one_of(st.none(), yaml_keys),
        value=st.one_of(st.none(), yaml_scalar_values),
        value_type=yaml_value_types,
        anchor_name=anchor_names,
        alias_target=anchor_names,
        nesting_level=nesting_levels,
        document_index=document_indices,
        child_count=child_counts,
    )
    def test_property_9_output_schema_consistency_attributes(
        self,
        name: str,
        start_line: int,
        end_line_offset: int,
        raw_text: str,
        element_type: str,
        key: str | None,
        value: str | None,
        value_type: str | None,
        anchor_name: str | None,
        alias_target: str | None,
        nesting_level: int,
        document_index: int,
        child_count: int | None,
    ):
        """
        Feature: yaml-language-support, Property 9: Output Schema Consistency

        For any YAMLElement instance, the element SHALL have all required attributes
        present and accessible, conforming to the standard schema.

        Validates: Requirements 4.1, 4.2
        """
        end_line = start_line + end_line_offset

        # Create YAMLElement with all attributes
        element = YAMLElement(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=raw_text,
            element_type=element_type,
            key=key,
            value=value,
            value_type=value_type,
            anchor_name=anchor_name,
            alias_target=alias_target,
            nesting_level=nesting_level,
            document_index=document_index,
            child_count=child_count,
        )

        # Property: All required attributes must be present
        _assert_base_element_attrs(element)
        _assert_yaml_specific_attrs(element)

        # Property: Attribute values must match what was set
        assert element.name == name, f"Expected name '{name}', got '{element.name}'"
        assert element.start_line == start_line, (
            f"Expected start_line {start_line}, got {element.start_line}"
        )
        assert element.end_line == end_line, (
            f"Expected end_line {end_line}, got {element.end_line}"
        )
        assert element.raw_text == raw_text, (
            f"Expected raw_text '{raw_text}', got '{element.raw_text}'"
        )
        assert element.element_type == element_type, (
            f"Expected element_type '{element_type}', got '{element.element_type}'"
        )
        assert element.key == key, f"Expected key '{key}', got '{element.key}'"
        assert element.value == value, (
            f"Expected value '{value}', got '{element.value}'"
        )
        assert element.value_type == value_type, (
            f"Expected value_type '{value_type}', got '{element.value_type}'"
        )
        assert element.anchor_name == anchor_name, (
            f"Expected anchor_name '{anchor_name}', got '{element.anchor_name}'"
        )
        assert element.alias_target == alias_target, (
            f"Expected alias_target '{alias_target}', got '{element.alias_target}'"
        )
        assert element.nesting_level == nesting_level, (
            f"Expected nesting_level {nesting_level}, got {element.nesting_level}"
        )
        assert element.document_index == document_index, (
            f"Expected document_index {document_index}, got {element.document_index}"
        )
        assert element.child_count == child_count, (
            f"Expected child_count {child_count}, got {element.child_count}"
        )

        # Property: Default language should be 'yaml'
        assert element.language == "yaml", (
            f"Expected language 'yaml', got '{element.language}'"
        )

    @settings(max_examples=100)
    @given(
        name=yaml_keys,
        start_line=line_numbers,
        end_line_offset=st.integers(min_value=0, max_value=100),
        raw_text=st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd", "Zs"),
                min_codepoint=32,
                max_codepoint=122,
            ),
            min_size=0,
            max_size=100,
        ),
        element_type=yaml_element_types,
        key=st.one_of(
            st.none(),
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"),
                    min_codepoint=48,
                    max_codepoint=122,
                ),
                min_size=1,
                max_size=30,
            ),
        ),
        value=st.one_of(
            st.none(),
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd", "Zs"),
                    min_codepoint=32,
                    max_codepoint=122,
                ),
                min_size=0,
                max_size=50,
            ),
        ),
        value_type=yaml_value_types,
        nesting_level=nesting_levels,
        document_index=document_indices,
    )
    def test_property_9_output_schema_consistency_json_serialization(
        self,
        name: str,
        start_line: int,
        end_line_offset: int,
        raw_text: str,
        element_type: str,
        key: str | None,
        value: str | None,
        value_type: str | None,
        nesting_level: int,
        document_index: int,
    ):
        """
        Feature: yaml-language-support, Property 9: Output Schema Consistency

        For any YAMLElement instance, serialization to JSON SHALL produce valid
        JSON output with all required fields present.

        Validates: Requirements 4.1, 4.2
        """
        end_line = start_line + end_line_offset

        # Create YAMLElement
        element = YAMLElement(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=raw_text,
            element_type=element_type,
            key=key,
            value=value,
            value_type=value_type,
            nesting_level=nesting_level,
            document_index=document_index,
        )

        # Property: to_summary_item() must return a valid dictionary
        summary = element.to_summary_item()
        assert isinstance(summary, dict), (
            f"to_summary_item() must return dict, got {type(summary)}"
        )
        _assert_summary_required_fields(summary)

        # Property: Summary values must match element values
        assert summary["name"] == name
        assert summary["type"] == element_type
        assert summary["lines"]["start"] == start_line
        assert summary["lines"]["end"] == end_line

        # Property: Summary must be JSON serializable with round-trip
        _assert_json_roundtrip(summary)

    @settings(max_examples=100)
    @given(
        start_line=line_numbers,
        end_line_offset=st.integers(min_value=0, max_value=100),
    )
    def test_property_9_output_schema_consistency_defaults(
        self,
        start_line: int,
        end_line_offset: int,
    ):
        """
        Feature: yaml-language-support, Property 9: Output Schema Consistency

        For any YAMLElement created with minimal required arguments, default values
        SHALL be correctly applied for all optional attributes.

        Validates: Requirements 4.1, 4.2
        """
        end_line = start_line + end_line_offset

        # Create YAMLElement with only required arguments
        element = YAMLElement(
            name="test_element",
            start_line=start_line,
            end_line=end_line,
            raw_text="test: value",
        )

        # Property: Default values must be correctly set
        assert element.language == "yaml", "Default language must be 'yaml'"
        assert element.element_type == "yaml", "Default element_type must be 'yaml'"
        assert element.key is None, "Default key must be None"
        assert element.value is None, "Default value must be None"
        assert element.value_type is None, "Default value_type must be None"
        assert element.anchor_name is None, "Default anchor_name must be None"
        assert element.alias_target is None, "Default alias_target must be None"
        assert element.nesting_level == 0, "Default nesting_level must be 0"
        assert element.document_index == 0, "Default document_index must be 0"
        assert element.child_count is None, "Default child_count must be None"

        # Property: Element with defaults must still be JSON serializable
        summary = element.to_summary_item()
        try:
            json_str = json.dumps(summary)
            assert isinstance(json_str, str), "JSON serialization must produce string"
        except (TypeError, ValueError) as e:
            pytest.fail(f"Element with defaults must be JSON serializable: {e}")

    @settings(max_examples=100)
    @given(
        element_type=yaml_element_types,
        value_type=yaml_value_types,
    )
    def test_property_9_output_schema_consistency_type_values(
        self,
        element_type: str,
        value_type: str | None,
    ):
        """
        Feature: yaml-language-support, Property 9: Output Schema Consistency

        For any valid element_type and value_type combination, the YAMLElement
        SHALL correctly store and return these type values.

        Validates: Requirements 4.1, 4.2
        """
        element = YAMLElement(
            name="type_test",
            start_line=1,
            end_line=1,
            raw_text="test",
            element_type=element_type,
            value_type=value_type,
        )

        # Property: element_type must be stored correctly
        assert element.element_type == element_type, (
            f"element_type must be '{element_type}'"
        )

        # Property: value_type must be stored correctly
        assert element.value_type == value_type, f"value_type must be '{value_type}'"

        # Property: Summary must reflect correct types
        summary = element.to_summary_item()
        assert summary["type"] == element_type, f"Summary type must be '{element_type}'"
        assert summary["value_type"] == value_type, (
            f"Summary value_type must be '{value_type}'"
        )
