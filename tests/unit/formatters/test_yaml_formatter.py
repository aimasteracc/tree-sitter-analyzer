#!/usr/bin/env python3
"""
Unit tests for tree_sitter_analyzer.formatters.yaml_formatter module.

This module tests YAMLFormatter class.
"""

import pytest

from tree_sitter_analyzer.formatters.yaml_formatter import YAMLFormatter


class TestYAMLFormatterInit:
    """Tests for YAMLFormatter initialization."""

    def test_yaml_formatter_init(self) -> None:
        """Test YAMLFormatter initialization."""
        formatter = YAMLFormatter()
        assert formatter.language == "yaml"


class TestYAMLFormatterFormatSummary:
    """Tests for YAMLFormatter.format_summary method."""

    def test_format_summary_empty_elements(self, yaml_formatter: YAMLFormatter) -> None:
        """Test formatting summary with empty elements."""
        result = {
            "file_path": "test.yaml",
            "elements": [],
        }
        output = yaml_formatter.format_summary(result)
        assert "Summary Results" in output
        assert "documents" in output
        assert "mappings" in output
        assert "sequences" in output

    def test_format_summary_with_documents(self, yaml_formatter: YAMLFormatter) -> None:
        """Test formatting summary with documents."""
        result = {
            "file_path": "test.yaml",
            "elements": [
                {
                    "element_type": "document",
                    "document_index": 0,
                    "start_line": 1,
                    "end_line": 10,
                }
            ],
        }
        output = yaml_formatter.format_summary(result)
        assert '"documents": 1' in output

    def test_format_summary_with_mappings(self, yaml_formatter: YAMLFormatter) -> None:
        """Test formatting summary with mappings."""
        result = {
            "file_path": "test.yaml",
            "elements": [
                {
                    "element_type": "mapping",
                    "key": "name",
                    "value_type": "string",
                    "nesting_level": 1,
                    "start_line": 2,
                    "end_line": 3,
                }
            ],
        }
        output = yaml_formatter.format_summary(result)
        assert '"mappings": 1' in output

    def test_format_summary_with_sequences(self, yaml_formatter: YAMLFormatter) -> None:
        """Test formatting summary with sequences."""
        result = {
            "file_path": "test.yaml",
            "elements": [
                {
                    "element_type": "sequence",
                    "child_count": 3,
                    "nesting_level": 1,
                    "start_line": 4,
                    "end_line": 7,
                }
            ],
        }
        output = yaml_formatter.format_summary(result)
        assert '"sequences": 1' in output

    def test_format_summary_with_anchors(self, yaml_formatter: YAMLFormatter) -> None:
        """Test formatting summary with anchors."""
        result = {
            "file_path": "test.yaml",
            "elements": [
                {
                    "element_type": "anchor",
                    "anchor_name": "ref",
                    "start_line": 5,
                    "end_line": 5,
                }
            ],
        }
        output = yaml_formatter.format_summary(result)
        assert '"anchors": [' in output
        assert '"name": "ref"' in output

    def test_format_summary_with_aliases(self, yaml_formatter: YAMLFormatter) -> None:
        """Test formatting summary with aliases."""
        result = {
            "file_path": "test.yaml",
            "elements": [
                {
                    "element_type": "alias",
                    "alias_target": "ref",
                    "start_line": 6,
                    "end_line": 6,
                }
            ],
        }
        output = yaml_formatter.format_summary(result)
        assert '"aliases": [' in output
        assert '"target": "ref"' in output


class TestYAMLFormatterFormatStructure:
    """Tests for YAMLFormatter.format_structure method."""

    def test_format_structure_empty(self, yaml_formatter: YAMLFormatter) -> None:
        """Test formatting structure with empty elements."""
        result = {
            "file_path": "test.yaml",
            "line_count": 10,
            "elements": [],
        }
        output = yaml_formatter.format_structure(result)
        assert "Structure Analysis Results" in output
        assert "documents" in output
        assert "statistics" in output

    def test_format_structure_with_documents(
        self, yaml_formatter: YAMLFormatter
    ) -> None:
        """Test formatting structure with documents."""
        result = {
            "file_path": "test.yaml",
            "line_count": 10,
            "elements": [
                {
                    "element_type": "document",
                    "document_index": 0,
                    "start_line": 1,
                    "end_line": 10,
                    "child_count": 2,
                }
            ],
        }
        output = yaml_formatter.format_structure(result)
        assert '"document_count": 1' in output

    def test_format_structure_with_mappings(
        self, yaml_formatter: YAMLFormatter
    ) -> None:
        """Test formatting structure with mappings."""
        result = {
            "file_path": "test.yaml",
            "line_count": 10,
            "elements": [
                {
                    "element_type": "mapping",
                    "key": "name",
                    "value_type": "string",
                    "nesting_level": 1,
                    "start_line": 2,
                    "end_line": 3,
                }
            ],
        }
        output = yaml_formatter.format_structure(result)
        assert '"mapping_count": 1' in output

    def test_format_structure_with_sequences(
        self, yaml_formatter: YAMLFormatter
    ) -> None:
        """Test formatting structure with sequences."""
        result = {
            "file_path": "test.yaml",
            "line_count": 10,
            "elements": [
                {
                    "element_type": "sequence",
                    "child_count": 3,
                    "nesting_level": 1,
                    "start_line": 4,
                    "end_line": 7,
                }
            ],
        }
        output = yaml_formatter.format_structure(result)
        assert '"sequence_count": 1' in output


class TestYAMLFormatterFormatAdvanced:
    """Tests for YAMLFormatter.format_advanced method."""

    def test_format_basic(self, yaml_formatter: YAMLFormatter) -> None:
        """Test basic advanced formatting."""
        result = {
            "file_path": "test.yaml",
            "line_count": 10,
            "elements": [
                {
                    "element_type": "document",
                    "document_index": 0,
                    "start_line": 1,
                    "end_line": 10,
                    "child_count": 2,
                }
            ],
        }
        output = yaml_formatter.format_advanced(result)
        assert "Advanced Analysis Results" in output
        assert '"success": true' in output

    def test_format_with_nesting(self, yaml_formatter: YAMLFormatter) -> None:
        """Test formatting with nested mappings."""
        result = {
            "file_path": "test.yaml",
            "line_count": 20,
            "elements": [
                {
                    "element_type": "mapping",
                    "key": "parent",
                    "value_type": "string",
                    "nesting_level": 2,
                    "start_line": 2,
                    "end_line": 10,
                }
            ],
        }
        output = yaml_formatter.format_advanced(result)
        assert '"max_nesting_level": 2' in output

    def test_format_text_output(self, yaml_formatter: YAMLFormatter) -> None:
        """Test text output format."""
        result = {
            "file_path": "test.yaml",
            "line_count": 10,
            "elements": [],
        }
        output = yaml_formatter.format_advanced(result, output_format="text")
        assert "--- Advanced Analysis Results ---" in output

    def test_format_json_output(self, yaml_formatter: YAMLFormatter) -> None:
        """Test JSON output format."""
        result = {
            "file_path": "test.yaml",
            "line_count": 10,
            "elements": [],
        }
        output = yaml_formatter.format_advanced(result, output_format="json")
        assert '"file_path": "test.yaml"' in output


class TestYAMLFormatterFormatTable:
    """Tests for YAMLFormatter.format_table method."""

    def test_format_table_full(self, yaml_formatter: YAMLFormatter) -> None:
        """Test formatting full table."""
        result = {
            "file_path": "test.yaml",
            "line_count": 10,
            "elements": [
                {
                    "element_type": "mapping",
                    "key": "name",
                    "value_type": "string",
                    "nesting_level": 0,
                    "start_line": 2,
                    "end_line": 3,
                }
            ],
        }
        output = yaml_formatter.format_table(result, table_type="full")
        assert "# test" in output
        assert "## Mappings" in output

    def test_format_table_compact(self, yaml_formatter: YAMLFormatter) -> None:
        """Test formatting compact table."""
        result = {
            "file_path": "test.yaml",
            "line_count": 10,
            "elements": [
                {
                    "element_type": "mapping",
                    "key": "name",
                    "value_type": "string",
                    "nesting_level": 0,
                    "start_line": 2,
                    "end_line": 3,
                }
            ],
        }
        output = yaml_formatter.format_table(result, table_type="compact")
        assert "# test" in output
        assert "## Summary" in output

    def test_format_table_csv(self, yaml_formatter: YAMLFormatter) -> None:
        """Test formatting CSV table."""
        result = {
            "file_path": "test.yaml",
            "line_count": 10,
            "elements": [
                {
                    "element_type": "mapping",
                    "name": "name",
                    "key": "name",
                    "value_type": "string",
                    "nesting_level": 0,
                    "start_line": 2,
                    "end_line": 3,
                }
            ],
        }
        output = yaml_formatter.format_table(result, table_type="csv")
        assert "name,mapping" in output


class TestYAMLFormatterEdgeCases:
    """Tests for edge cases."""

    def test_format_empty_result(self, yaml_formatter: YAMLFormatter) -> None:
        """Test formatting empty result."""
        result = {"file_path": "test.yaml", "line_count": 0, "elements": []}
        output = yaml_formatter.format_table(result)
        assert "# test" in output

    def test_format_with_special_characters(
        self, yaml_formatter: YAMLFormatter
    ) -> None:
        """Test formatting with special characters in keys."""
        result = {
            "file_path": "test.yaml",
            "line_count": 10,
            "elements": [
                {
                    "element_type": "mapping",
                    "key": "name:with,colons",
                    "value_type": "string",
                    "nesting_level": 0,
                    "start_line": 2,
                    "end_line": 3,
                }
            ],
        }
        output = yaml_formatter.format_table(result, table_type="full")
        assert "name:with,colons" in output

    def test_format_with_long_content(self, yaml_formatter: YAMLFormatter) -> None:
        """Test formatting with long content."""
        result = {
            "file_path": "test.yaml",
            "line_count": 10,
            "elements": [
                {
                    "element_type": "comment",
                    "value": "a" * 100,
                    "start_line": 5,
                    "end_line": 5,
                }
            ],
        }
        output = yaml_formatter.format_table(result, table_type="full")
        assert "..." in output


# Pytest fixtures
@pytest.fixture
def yaml_formatter() -> YAMLFormatter:
    """Create a YAMLFormatter instance for testing."""
    return YAMLFormatter()
