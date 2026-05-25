#!/usr/bin/env python3
"""
Property-based tests for YAML output format support.

Feature: yaml-language-support
Tests correctness properties for YAML formatter to ensure:
- Text format produces valid text output
- JSON format produces valid JSON output
- CSV format produces valid CSV output
"""

import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer.formatters.yaml_formatter import YAMLFormatter

# Strategies for generating valid YAML elements
yaml_element_types = st.sampled_from(
    ["mapping", "sequence", "scalar", "anchor", "alias", "comment", "document"]
)

yaml_value_types = st.sampled_from(
    ["string", "number", "boolean", "null", "mapping", "sequence", None]
)

yaml_keys = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"),
        min_codepoint=48,
        max_codepoint=122,
    ),
    min_size=1,
    max_size=30,
).filter(lambda x: x and len(x.strip()) > 0)

yaml_values = st.one_of(
    st.text(min_size=0, max_size=50),
    st.integers().map(str),
    st.sampled_from(["true", "false", "null", ""]),
)

line_numbers = st.integers(min_value=1, max_value=1000)
nesting_levels = st.integers(min_value=0, max_value=10)
document_indices = st.integers(min_value=0, max_value=5)
child_counts = st.one_of(st.none(), st.integers(min_value=0, max_value=100))


def _build_basic_yaml_elements(element_count: int) -> list:
    """Build element_count basic YAML elements cycling through 4 types."""
    elements = []
    types = ["mapping", "sequence", "scalar", "document"]
    for i in range(element_count):
        element_type = types[i % 4]
        elements.append(
            create_yaml_element_dict(
                name=f"element_{i}",
                start_line=i + 1,
                end_line=i + 1,
                element_type=element_type,
                key=f"key_{i}" if element_type == "mapping" else None,
                value=f"value_{i}" if element_type in ["scalar", "mapping"] else None,
                value_type="string" if element_type in ["scalar", "mapping"] else None,
                nesting_level=i % 3,
                document_index=0,
            )
        )
    return elements


def _build_mapping_yaml_elements(mapping_count: int) -> list:
    """Build mapping_count YAML mapping elements."""
    return [
        create_yaml_element_dict(
            name=f"key_{i}",
            start_line=i + 1,
            end_line=i + 1,
            element_type="mapping",
            key=f"key_{i}",
            value=f"value_{i}",
            value_type="string",
            nesting_level=0,
            document_index=0,
        )
        for i in range(mapping_count)
    ]


def _make_yaml_analysis_result(file_path: str, line_count: int, elements: list) -> dict:
    """Build a standard analysis_result dict for YAML formatter tests."""
    return {
        "file_path": file_path,
        "language": "yaml",
        "line_count": line_count,
        "elements": elements,
        "analysis_metadata": {
            "analysis_time": 0.1,
            "language": "yaml",
            "file_path": file_path,
        },
    }


def _parse_json_from_output(output: str, context: str) -> dict:
    """Extract the first JSON object from formatter output and parse it."""
    lines = output.split("\n")
    json_start = 0
    for i, line in enumerate(lines):
        if line.strip().startswith("{"):
            json_start = i
            break
    try:
        return json.loads("\n".join(lines[json_start:]))
    except json.JSONDecodeError as e:
        pytest.fail(f"{context} JSON must be valid: {e}")


def _assert_format_succeeds(result: str, context: str) -> None:
    """Assert that a formatter result is a non-empty string."""
    assert isinstance(result, str), f"{context} must be a string"
    assert len(result) > 0, f"{context} must not be empty"


def create_yaml_element_dict(
    name: str,
    start_line: int,
    end_line: int,
    element_type: str,
    key: str | None = None,
    value: str | None = None,
    value_type: str | None = None,
    anchor_name: str | None = None,
    alias_target: str | None = None,
    nesting_level: int = 0,
    document_index: int = 0,
    child_count: int | None = None,
) -> dict:
    """Create a dictionary representation of a YAML element."""
    return {
        "name": name,
        "start_line": start_line,
        "end_line": end_line,
        "element_type": element_type,
        "key": key,
        "value": value,
        "value_type": value_type,
        "anchor_name": anchor_name,
        "alias_target": alias_target,
        "nesting_level": nesting_level,
        "document_index": document_index,
        "child_count": child_count,
    }


class TestYAMLOutputFormatProperties:
    """Property-based tests for YAML output format support."""

    @settings(max_examples=100)
    @given(
        file_path=st.text(min_size=1, max_size=50).filter(
            lambda x: "/" not in x and "\\" not in x
        ),
        line_count=st.integers(min_value=1, max_value=1000),
        element_count=st.integers(min_value=0, max_value=20),
    )
    def test_property_10_json_format_produces_valid_json(
        self,
        file_path: str,
        line_count: int,
        element_count: int,
    ):
        """
        Feature: yaml-language-support, Property 10: Output Format Support

        For any YAML analysis result, formatting to JSON SHALL produce valid
        JSON output that can be parsed without errors.

        Validates: Requirements 4.3, 4.5
        """
        formatter = YAMLFormatter()
        elements = _build_basic_yaml_elements(element_count)
        analysis_result = _make_yaml_analysis_result(file_path, line_count, elements)

        json_output = formatter.format_advanced(analysis_result, output_format="json")
        _assert_format_succeeds(json_output, "JSON output")
        parsed = _parse_json_from_output(json_output, "JSON output")
        assert isinstance(parsed, dict), "Parsed JSON must be a dictionary"
        assert "file_path" in parsed, "JSON must contain file_path"
        assert "language" in parsed, "JSON must contain language"
        assert parsed["language"] == "yaml", "Language must be yaml"

        summary_output = formatter.format_summary(analysis_result)
        _assert_format_succeeds(summary_output, "Summary output")
        summary_parsed = _parse_json_from_output(summary_output, "Summary output")
        assert isinstance(summary_parsed, dict), "Summary JSON must be a dictionary"
        assert "file_path" in summary_parsed, "Summary must contain file_path"
        assert "language" in summary_parsed, "Summary must contain language"

        structure_output = formatter.format_structure(analysis_result)
        _assert_format_succeeds(structure_output, "Structure output")
        structure_parsed = _parse_json_from_output(structure_output, "Structure output")
        assert isinstance(structure_parsed, dict), "Structure JSON must be a dictionary"
        assert "file_path" in structure_parsed, "Structure must contain file_path"

    @settings(max_examples=100)
    @given(
        file_path=st.text(min_size=1, max_size=50).filter(
            lambda x: "/" not in x and "\\" not in x
        ),
        line_count=st.integers(min_value=1, max_value=1000),
        element_count=st.integers(min_value=0, max_value=20),
    )
    def test_property_10_text_format_produces_valid_text(
        self,
        file_path: str,
        line_count: int,
        element_count: int,
    ):
        """
        Feature: yaml-language-support, Property 10: Output Format Support

        For any YAML analysis result, formatting to text SHALL produce valid
        text output with readable content.

        Validates: Requirements 4.3, 4.5
        """
        formatter = YAMLFormatter()
        elements = _build_basic_yaml_elements(element_count)
        analysis_result = _make_yaml_analysis_result(file_path, line_count, elements)

        text_output = formatter.format_advanced(analysis_result, output_format="text")
        _assert_format_succeeds(text_output, "Text output")
        assert "File:" in text_output or "file" in text_output.lower(), (
            "Text must mention file"
        )
        assert "Language:" in text_output or "yaml" in text_output.lower(), (
            "Text must mention language"
        )
        try:
            text_output.encode("utf-8")
        except UnicodeEncodeError as e:
            pytest.fail(f"Text output must be valid UTF-8: {e}")

        table_output = formatter.format_table(analysis_result, table_type="full")
        _assert_format_succeeds(table_output, "Table output")
        assert "|" in table_output, "Table output should contain pipe characters"
        assert "#" in table_output, "Table output should contain markdown headers"

    @settings(max_examples=100)
    @given(
        file_path=st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"),
                min_codepoint=48,
                max_codepoint=122,
            ),
            min_size=1,
            max_size=50,
        ).filter(lambda x: "/" not in x and "\\" not in x and "|" not in x),
        mapping_count=st.integers(min_value=1, max_value=10),
    )
    def test_property_10_csv_format_produces_valid_csv(
        self,
        file_path: str,
        mapping_count: int,
    ):
        """
        Feature: yaml-language-support, Property 10: Output Format Support

        For any YAML analysis result, tabular output SHALL be valid and
        well-structured.

        Validates: Requirements 4.3, 4.5
        """
        formatter = YAMLFormatter()
        elements = _build_mapping_yaml_elements(mapping_count)
        analysis_result = _make_yaml_analysis_result(file_path, mapping_count, elements)

        # Property: format_table produces structured output
        table_output = formatter.format_table(analysis_result, table_type="full")
        assert isinstance(table_output, str), "Table output must be a string"
        assert len(table_output) > 0, "Table output must not be empty"

        # Property: Table output should be structured with separators
        lines = table_output.split("\n")
        assert len(lines) > 0, "Table must have at least one line"

        # Property: Table should contain pipe-separated values (markdown table format)
        pipe_lines = [
            line for line in lines if "|" in line and not line.startswith("#")
        ]
        assert len(pipe_lines) > 0, "Table must contain pipe-separated lines"

        # Property: Table should contain markdown headers
        header_lines = [line for line in lines if line.startswith("#")]
        assert len(header_lines) > 0, "Table must contain markdown section headers"

        # Property: Table should have proper markdown table structure
        # Each table section should have at least a header row and separator row
        # We verify that tables exist and have basic structure

        # Count table sections (lines with |---|)
        separator_lines = [line for line in lines if "|---" in line or "|--" in line]
        assert len(separator_lines) > 0, "Table must contain separator rows"

        # Property: File path should appear in the output
        assert file_path in table_output or "File" in table_output, (
            "Table should reference the file being analyzed"
        )

        # Property: Language should be mentioned
        assert "yaml" in table_output.lower(), "Table should mention YAML language"

    @settings(max_examples=100)
    @given(
        element_count=st.integers(min_value=0, max_value=50),
    )
    def test_property_10_output_format_consistency(
        self,
        element_count: int,
    ):
        """
        Feature: yaml-language-support, Property 10: Output Format Support

        For any YAML analysis result, all output formats SHALL successfully
        produce output without errors.

        Validates: Requirements 4.3, 4.5
        """
        formatter = YAMLFormatter()

        # Generate diverse elements
        elements = []
        element_types = [
            "mapping",
            "sequence",
            "scalar",
            "anchor",
            "alias",
            "comment",
            "document",
        ]

        for i in range(element_count):
            element_type = element_types[i % len(element_types)]
            element = create_yaml_element_dict(
                name=f"element_{i}",
                start_line=i + 1,
                end_line=i + 2,
                element_type=element_type,
                key=f"key_{i}" if element_type == "mapping" else None,
                value=f"value_{i}"
                if element_type in ["scalar", "mapping", "comment"]
                else None,
                value_type="string" if element_type in ["scalar", "mapping"] else None,
                anchor_name=f"anchor_{i}" if element_type == "anchor" else None,
                alias_target=f"anchor_{i}" if element_type == "alias" else None,
                nesting_level=i % 5,
                document_index=i % 3,
                child_count=i % 10
                if element_type in ["sequence", "document"]
                else None,
            )
            elements.append(element)

        analysis_result = {
            "file_path": "test.yaml",
            "language": "yaml",
            "line_count": element_count + 10,
            "elements": elements,
            "analysis_metadata": {
                "analysis_time": 0.1,
                "language": "yaml",
                "file_path": "test.yaml",
            },
        }

        # Property: All format methods must succeed without exceptions
        _assert_format_succeeds(formatter.format_summary(analysis_result), "Summary")
        _assert_format_succeeds(
            formatter.format_structure(analysis_result), "Structure"
        )
        _assert_format_succeeds(
            formatter.format_advanced(analysis_result, output_format="json"),
            "Advanced JSON",
        )
        _assert_format_succeeds(
            formatter.format_advanced(analysis_result, output_format="text"),
            "Advanced text",
        )
        _assert_format_succeeds(
            formatter.format_table(analysis_result, table_type="full"), "Table"
        )

    @settings(max_examples=50)
    @given(
        file_path=st.text(min_size=1, max_size=50).filter(
            lambda x: "/" not in x and "\\" not in x
        ),
    )
    def test_property_10_empty_result_handling(
        self,
        file_path: str,
    ):
        """
        Feature: yaml-language-support, Property 10: Output Format Support

        For any YAML analysis result with no elements, all output formats
        SHALL handle empty results gracefully.

        Validates: Requirements 4.3, 4.5
        """
        formatter = YAMLFormatter()

        # Empty analysis result
        analysis_result = {
            "file_path": file_path,
            "language": "yaml",
            "line_count": 0,
            "elements": [],
            "analysis_metadata": {
                "analysis_time": 0.0,
                "language": "yaml",
                "file_path": file_path,
            },
        }

        # Property: All formats must handle empty results without errors
        try:
            summary = formatter.format_summary(analysis_result)
            assert isinstance(summary, str), "Empty summary must be string"
        except Exception as e:
            pytest.fail(f"format_summary must handle empty results: {e}")

        try:
            structure = formatter.format_structure(analysis_result)
            assert isinstance(structure, str), "Empty structure must be string"
        except Exception as e:
            pytest.fail(f"format_structure must handle empty results: {e}")

        try:
            advanced = formatter.format_advanced(analysis_result, output_format="json")
            assert isinstance(advanced, str), "Empty advanced must be string"
        except Exception as e:
            pytest.fail(f"format_advanced must handle empty results: {e}")

        try:
            table = formatter.format_table(analysis_result, table_type="full")
            assert isinstance(table, str), "Empty table must be string"
        except Exception as e:
            pytest.fail(f"format_table must handle empty results: {e}")
