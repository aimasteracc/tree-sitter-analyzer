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


class TestYAMLFormatterFullTable:
    """Tests for _format_full covering all element sections."""

    def test_full_table_with_documents(self, yaml_formatter: YAMLFormatter) -> None:
        result = {
            "file_path": "test.yaml",
            "line_count": 20,
            "elements": [
                {
                    "element_type": "document",
                    "document_index": 0,
                    "start_line": 1,
                    "end_line": 10,
                    "child_count": 3,
                }
            ],
        }
        output = yaml_formatter.format_table(result, table_type="full")
        assert "## Documents" in output
        assert "0" in output

    def test_full_table_with_sequences(self, yaml_formatter: YAMLFormatter) -> None:
        result = {
            "file_path": "test.yaml",
            "line_count": 10,
            "elements": [
                {
                    "element_type": "sequence",
                    "child_count": 5,
                    "nesting_level": 1,
                    "start_line": 3,
                }
            ],
        }
        output = yaml_formatter.format_table(result, table_type="full")
        assert "## Sequences" in output

    def test_full_table_with_anchors(self, yaml_formatter: YAMLFormatter) -> None:
        result = {
            "file_path": "test.yaml",
            "line_count": 10,
            "elements": [
                {
                    "element_type": "anchor",
                    "anchor_name": "myanchor",
                    "start_line": 5,
                }
            ],
        }
        output = yaml_formatter.format_table(result, table_type="full")
        assert "## Anchors" in output
        assert "&myanchor" in output

    def test_full_table_with_aliases(self, yaml_formatter: YAMLFormatter) -> None:
        result = {
            "file_path": "test.yaml",
            "line_count": 10,
            "elements": [
                {
                    "element_type": "alias",
                    "alias_target": "myanchor",
                    "start_line": 8,
                }
            ],
        }
        output = yaml_formatter.format_table(result, table_type="full")
        assert "## Aliases" in output
        assert "*myanchor" in output

    def test_full_table_many_mappings_truncation(
        self, yaml_formatter: YAMLFormatter
    ) -> None:
        elements = [
            {
                "element_type": "mapping",
                "key": f"key{i}",
                "value_type": "string",
                "nesting_level": 1,
                "start_line": i,
            }
            for i in range(1, 53)
        ]
        result = {
            "file_path": "test.yaml",
            "line_count": 60,
            "elements": elements,
        }
        output = yaml_formatter.format_table(result, table_type="full")
        assert "more" in output


class TestYAMLFormatterCompact:
    """Tests for _format_compact covering top-level keys and references."""

    def test_compact_top_level_mappings(self, yaml_formatter: YAMLFormatter) -> None:
        result = {
            "file_path": "test.yaml",
            "line_count": 20,
            "elements": [
                {
                    "element_type": "mapping",
                    "key": "server",
                    "value_type": "mapping",
                    "nesting_level": 1,
                    "start_line": 2,
                },
                {
                    "element_type": "mapping",
                    "key": "database",
                    "value_type": "mapping",
                    "nesting_level": 2,
                    "start_line": 5,
                },
            ],
        }
        output = yaml_formatter.format_table(result, table_type="compact")
        assert "## Top-Level Keys" in output
        assert "server" in output

    def test_compact_with_anchors_and_aliases(
        self, yaml_formatter: YAMLFormatter
    ) -> None:
        result = {
            "file_path": "test.yaml",
            "line_count": 20,
            "elements": [
                {
                    "element_type": "anchor",
                    "anchor_name": "defaults",
                    "start_line": 3,
                },
                {
                    "element_type": "alias",
                    "alias_target": "defaults",
                    "start_line": 8,
                },
            ],
        }
        output = yaml_formatter.format_table(result, table_type="compact")
        assert "## References" in output
        assert "&defaults" in output
        assert "*defaults" in output


class TestYAMLFormatterComplexity:
    """Tests for _calculate_complexity covering all branches."""

    def test_complexity_simple(self, yaml_formatter: YAMLFormatter) -> None:
        result = {
            "file_path": "test.yaml",
            "line_count": 10,
            "elements": [
                {
                    "element_type": "mapping",
                    "key": "a",
                    "value_type": "string",
                    "nesting_level": 0,
                    "start_line": 1,
                },
            ],
        }
        output = yaml_formatter.format_advanced(result, output_format="text")
        assert "Simple" in output

    def test_complexity_moderate(self, yaml_formatter: YAMLFormatter) -> None:
        elements = [
            {
                "element_type": "mapping",
                "key": f"k{i}",
                "value_type": "string",
                "nesting_level": 2,
                "start_line": i,
            }
            for i in range(15)
        ]
        result = {"file_path": "test.yaml", "line_count": 30, "elements": elements}
        output = yaml_formatter.format_advanced(result, output_format="text")
        assert "Moderate" in output

    def test_complexity_complex(self, yaml_formatter: YAMLFormatter) -> None:
        elements = [
            {
                "element_type": "mapping",
                "key": f"k{i}",
                "value_type": "string",
                "nesting_level": 3,
                "start_line": i,
            }
            for i in range(35)
        ]
        result = {"file_path": "test.yaml", "line_count": 50, "elements": elements}
        output = yaml_formatter.format_advanced(result, output_format="text")
        assert "Complex" in output or "Very Complex" in output

    def test_complexity_very_complex(self, yaml_formatter: YAMLFormatter) -> None:
        elements = [
            {
                "element_type": "mapping",
                "key": f"k{i}",
                "value_type": "string",
                "nesting_level": 5,
                "start_line": i,
            }
            for i in range(80)
        ]
        result = {"file_path": "test.yaml", "line_count": 100, "elements": elements}
        output = yaml_formatter.format_advanced(result, output_format="text")
        assert "Very Complex" in output


class TestYAMLFormatterFormatAnalysisResult:
    """Tests for format_analysis_result / _convert_analysis_result_to_format."""

    def test_format_analysis_result(self, yaml_formatter: YAMLFormatter) -> None:
        from types import SimpleNamespace

        element = SimpleNamespace(
            name="server",
            element_type="mapping",
            key="server",
            value="localhost",
            value_type="string",
            anchor_name="",
            alias_target="",
            nesting_level=1,
            document_index=0,
            child_count=None,
            start_line=2,
            end_line=3,
        )
        analysis_result = SimpleNamespace(
            file_path="test.yaml",
            language="yaml",
            line_count=10,
            elements=[element],
            analysis_time=0.1,
        )
        output = yaml_formatter.format_analysis_result(analysis_result)
        assert "server" in output


class TestYAMLFormatterValueTypes:
    """Test advanced formatting with various value types."""

    def test_advanced_value_type_distribution(
        self, yaml_formatter: YAMLFormatter
    ) -> None:
        result = {
            "file_path": "test.yaml",
            "line_count": 10,
            "elements": [
                {
                    "element_type": "mapping",
                    "key": "a",
                    "value_type": "string",
                    "nesting_level": 1,
                    "start_line": 1,
                },
                {
                    "element_type": "mapping",
                    "key": "b",
                    "value_type": "integer",
                    "nesting_level": 1,
                    "start_line": 2,
                },
                {
                    "element_type": "mapping",
                    "key": "c",
                    "value_type": "string",
                    "nesting_level": 2,
                    "start_line": 3,
                },
            ],
        }
        output = yaml_formatter.format_advanced(result)
        assert '"string": 2' in output
        assert '"integer": 1' in output

    def test_advanced_multi_document(self, yaml_formatter: YAMLFormatter) -> None:
        result = {
            "file_path": "test.yaml",
            "line_count": 30,
            "elements": [
                {
                    "element_type": "document",
                    "document_index": 0,
                    "start_line": 1,
                    "end_line": 10,
                    "child_count": 2,
                },
                {
                    "element_type": "document",
                    "document_index": 1,
                    "start_line": 12,
                    "end_line": 20,
                    "child_count": 1,
                },
            ],
        }
        output = yaml_formatter.format_advanced(result)
        assert '"is_multi_document": true' in output

    def test_advanced_content_analysis_flags(
        self, yaml_formatter: YAMLFormatter
    ) -> None:
        result = {
            "file_path": "test.yaml",
            "line_count": 20,
            "elements": [
                {"element_type": "anchor", "anchor_name": "ref", "start_line": 1},
                {"element_type": "alias", "alias_target": "ref", "start_line": 5},
                {"element_type": "comment", "value": "# note", "start_line": 8},
            ],
        }
        output = yaml_formatter.format_advanced(result)
        assert '"has_anchors": true' in output
        assert '"has_aliases": true' in output
        assert '"has_comments": true' in output


# Pytest fixtures
@pytest.fixture
def yaml_formatter() -> YAMLFormatter:
    """Create a YAMLFormatter instance for testing."""
    return YAMLFormatter()
