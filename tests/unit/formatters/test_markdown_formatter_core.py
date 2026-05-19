#!/usr/bin/env python3
"""Core Markdown formatter tests — initialization, summary, structure, advanced."""

import json
from unittest.mock import patch

from tree_sitter_analyzer.formatters.markdown_formatter import MarkdownFormatter


class TestMarkdownFormatterInitialization:
    """Test MarkdownFormatter initialization"""

    def test_init(self):
        """Test basic initialization"""
        formatter = MarkdownFormatter()
        assert formatter.language == "markdown"

    def test_inherits_from_base(self):
        """Test that MarkdownFormatter inherits from BaseFormatter"""
        from tree_sitter_analyzer.formatters.base_formatter import BaseFormatter

        formatter = MarkdownFormatter()
        assert isinstance(formatter, BaseFormatter)


class TestFormatSummary:
    """Test format_summary method"""

    def test_format_summary_basic(self):
        """Test basic summary formatting"""
        formatter = MarkdownFormatter()
        analysis_result = {
            "file_path": "test.md",
            "elements": [
                {"type": "heading", "text": "Test Header", "level": 1},
                {"type": "link", "text": "Link1", "url": "http://example.com"},
                {"type": "code_block", "language": "python", "line_count": 5},
            ],
        }

        result = formatter.format_summary(analysis_result)

        assert "Summary Results" in result
        assert "test.md" in result
        assert "markdown" in result
        # Check JSON structure
        json_start = result.find("{")
        json_data = json.loads(result[json_start:])
        assert json_data["language"] == "markdown"
        assert len(json_data["summary"]["headers"]) == 1
        assert len(json_data["summary"]["links"]) == 1
        assert len(json_data["summary"]["code_blocks"]) == 1

    def test_format_summary_empty_elements(self):
        """Test summary with no elements"""
        formatter = MarkdownFormatter()
        analysis_result = {"file_path": "empty.md", "elements": []}

        result = formatter.format_summary(analysis_result)

        json_start = result.find("{")
        json_data = json.loads(result[json_start:])
        assert json_data["summary"]["headers"] == []
        assert json_data["summary"]["links"] == []
        assert json_data["summary"]["images"] == []

    def test_format_summary_multiple_link_types(self):
        """Test summary with different link types"""
        formatter = MarkdownFormatter()
        analysis_result = {
            "file_path": "links.md",
            "elements": [
                {"type": "link", "text": "Link1", "url": "http://example.com"},
                {"type": "autolink", "text": "Link2", "url": "http://auto.com"},
                {
                    "type": "reference_link",
                    "text": "Link3",
                    "url": "http://ref.com",
                },
            ],
        }

        result = formatter.format_summary(analysis_result)

        json_start = result.find("{")
        json_data = json.loads(result[json_start:])
        assert len(json_data["summary"]["links"]) == 3

    def test_format_summary_with_images(self):
        """Test summary with images"""
        formatter = MarkdownFormatter()
        analysis_result = {
            "file_path": "images.md",
            "elements": [
                {"type": "image", "alt": "Test Image", "url": "image.png"},
                {
                    "type": "reference_image",
                    "alt": "Ref Image",
                    "url": "ref_image.png",
                },
            ],
        }

        result = formatter.format_summary(analysis_result)

        json_start = result.find("{")
        json_data = json.loads(result[json_start:])
        assert len(json_data["summary"]["images"]) == 2

    def test_format_summary_with_lists(self):
        """Test summary with different list types"""
        formatter = MarkdownFormatter()
        analysis_result = {
            "file_path": "lists.md",
            "elements": [
                {"type": "list", "list_type": "ordered", "item_count": 5},
                {"type": "task_list", "list_type": "task", "item_count": 3},
            ],
        }

        result = formatter.format_summary(analysis_result)

        json_start = result.find("{")
        json_data = json.loads(result[json_start:])
        assert len(json_data["summary"]["lists"]) == 2
        assert json_data["summary"]["lists"][0]["items"] == 5

    @patch.object(MarkdownFormatter, "_compute_robust_counts_from_file")
    def test_format_summary_with_robust_counts_links(self, mock_robust):
        """Test summary with robust link count adjustment"""
        formatter = MarkdownFormatter()
        mock_robust.return_value = {"link_count": 5, "image_count": 0}

        analysis_result = {
            "file_path": "test.md",
            "elements": [
                {"type": "link", "text": "Link1", "url": "http://example.com"},
            ],
        }

        result = formatter.format_summary(analysis_result)

        json_start = result.find("{")
        json_data = json.loads(result[json_start:])
        # Should add placeholder links to match robust count
        assert len(json_data["summary"]["links"]) == 5

    @patch.object(MarkdownFormatter, "_compute_robust_counts_from_file")
    def test_format_summary_with_robust_counts_images(self, mock_robust):
        """Test summary with robust image count adjustment"""
        formatter = MarkdownFormatter()
        mock_robust.return_value = {"link_count": 0, "image_count": 3}

        analysis_result = {
            "file_path": "test.md",
            "elements": [{"type": "image", "alt": "Image1", "url": "img.png"}],
        }

        result = formatter.format_summary(analysis_result)

        json_start = result.find("{")
        json_data = json.loads(result[json_start:])
        # Should add placeholder images to match robust count
        assert len(json_data["summary"]["images"]) == 3


class TestFormatStructure:
    """Test format_structure method"""

    def test_format_structure_basic(self):
        """Test basic structure formatting"""
        formatter = MarkdownFormatter()
        analysis_result = {
            "file_path": "test.md",
            "line_count": 100,
            "elements": [
                {
                    "type": "heading",
                    "text": "Header",
                    "level": 1,
                    "line_range": {"start": 1, "end": 1},
                },
                {
                    "type": "link",
                    "text": "Link",
                    "url": "http://example.com",
                    "line_range": {"start": 5, "end": 5},
                },
            ],
            "analysis_metadata": {"version": "2.0.0"},
        }

        result = formatter.format_structure(analysis_result)

        assert "Structure Analysis Results" in result
        json_start = result.find("{")
        json_data = json.loads(result[json_start:])
        assert json_data["language"] == "markdown"
        assert json_data["statistics"]["total_lines"] == 100
        assert len(json_data["headers"]) == 1
        assert json_data["analysis_metadata"]["version"] == "2.0.0"

    def test_format_structure_all_element_types(self):
        """Test structure with all element types"""
        formatter = MarkdownFormatter()
        analysis_result = {
            "file_path": "test.md",
            "line_count": 200,
            "elements": [
                {
                    "type": "heading",
                    "text": "Header",
                    "level": 2,
                    "line_range": {"start": 1, "end": 1},
                },
                {
                    "type": "link",
                    "text": "Link",
                    "url": "http://example.com",
                    "line_range": {"start": 5, "end": 5},
                },
                {
                    "type": "image",
                    "alt": "Image",
                    "url": "image.png",
                    "line_range": {"start": 10, "end": 10},
                },
                {
                    "type": "code_block",
                    "language": "python",
                    "line_count": 10,
                    "line_range": {"start": 15, "end": 25},
                },
                {
                    "type": "list",
                    "list_type": "ordered",
                    "item_count": 5,
                    "line_range": {"start": 30, "end": 35},
                },
                {
                    "type": "table",
                    "column_count": 3,
                    "row_count": 5,
                    "line_range": {"start": 40, "end": 45},
                },
            ],
        }

        result = formatter.format_structure(analysis_result)

        json_start = result.find("{")
        json_data = json.loads(result[json_start:])
        assert json_data["statistics"]["header_count"] == 1
        assert json_data["statistics"]["link_count"] == 1
        assert json_data["statistics"]["image_count"] == 1
        assert json_data["statistics"]["code_block_count"] == 1
        assert json_data["statistics"]["list_count"] == 1
        assert json_data["statistics"]["table_count"] == 1

    @patch.object(MarkdownFormatter, "_compute_robust_counts_from_file")
    def test_format_structure_with_robust_counts(self, mock_robust):
        """Test structure with robust counts"""
        formatter = MarkdownFormatter()
        mock_robust.return_value = {"link_count": 10, "image_count": 5}

        analysis_result = {
            "file_path": "test.md",
            "line_count": 100,
            "elements": [{"type": "link", "text": "Link", "url": "http://example.com"}],
        }

        result = formatter.format_structure(analysis_result)

        json_start = result.find("{")
        json_data = json.loads(result[json_start:])
        # Should use robust counts when non-zero
        assert json_data["statistics"]["link_count"] == 10
        assert json_data["statistics"]["image_count"] == 5

    @patch.object(MarkdownFormatter, "_compute_robust_counts_from_file")
    def test_format_structure_robust_fallback(self, mock_robust):
        """Test structure fallback to element counts when robust is zero"""
        formatter = MarkdownFormatter()
        mock_robust.return_value = {"link_count": 0, "image_count": 0}

        analysis_result = {
            "file_path": "test.md",
            "line_count": 100,
            "elements": [
                {"type": "link", "text": "Link1", "url": "http://example.com"},
                {"type": "link", "text": "Link2", "url": "http://test.com"},
            ],
        }

        result = formatter.format_structure(analysis_result)

        json_start = result.find("{")
        json_data = json.loads(result[json_start:])
        # Should fall back to element count when robust count is 0
        assert json_data["statistics"]["link_count"] == 2


class TestFormatAdvanced:
    """Test format_advanced method"""

    def test_format_advanced_json(self):
        """Test advanced formatting in JSON format"""
        formatter = MarkdownFormatter()
        analysis_result = {
            "file_path": "test.md",
            "line_count": 100,
            "elements": [
                {"type": "heading", "text": "Header 1", "level": 1},
                {"type": "heading", "text": "Header 2", "level": 2},
                {"type": "link", "text": "Link", "url": "http://example.com"},
                {"type": "code_block", "language": "python", "line_count": 10},
            ],
        }

        result = formatter.format_advanced(analysis_result, output_format="json")

        assert "Advanced Analysis Results" in result
        json_start = result.find("{")
        json_data = json.loads(result[json_start:])
        assert json_data["success"] is True
        assert json_data["element_count"] == 4
        assert "document_metrics" in json_data
        assert "content_analysis" in json_data

    def test_format_advanced_text(self):
        """Test advanced formatting in text format"""
        formatter = MarkdownFormatter()
        analysis_result = {
            "file_path": "test.md",
            "line_count": 50,
            "elements": [
                {"type": "heading", "text": "Header", "level": 1},
                {"type": "link", "text": "Link", "url": "http://example.com"},
            ],
        }

        result = formatter.format_advanced(analysis_result, output_format="text")

        assert "Advanced Analysis Results" in result
        assert '"File: test.md"' in result
        assert '"Language: markdown"' in result
        assert '"Lines: 50"' in result

    def test_format_advanced_document_metrics(self):
        """Test document metrics calculation"""
        formatter = MarkdownFormatter()
        analysis_result = {
            "file_path": "test.md",
            "line_count": 100,
            "elements": [
                {"type": "heading", "text": "H1", "level": 1},
                {"type": "heading", "text": "H2", "level": 2},
                {"type": "heading", "text": "H3", "level": 3},
                {"type": "link", "text": "Ext", "url": "http://example.com"},
                {"type": "link", "text": "Int", "url": "#section"},
                {"type": "image", "alt": "Image", "url": "img.png"},
                {"type": "code_block", "language": "python", "line_count": 15},
                {"type": "code_block", "language": "javascript", "line_count": 10},
                {"type": "list", "list_type": "ordered", "item_count": 5},
                {"type": "list", "list_type": "unordered", "item_count": 3},
                {"type": "table", "column_count": 3, "row_count": 5},
            ],
        }

        result = formatter.format_advanced(analysis_result)

        json_start = result.find("{")
        json_data = json.loads(result[json_start:])
        metrics = json_data["document_metrics"]

        assert metrics["header_count"] == 3
        assert metrics["max_header_level"] == 3
        assert metrics["avg_header_level"] == 2.0
        assert metrics["link_count"] == 2
        assert metrics["external_link_count"] == 1
        assert metrics["internal_link_count"] == 1
        assert metrics["image_count"] == 1
        assert metrics["code_block_count"] == 2
        assert metrics["total_code_lines"] == 25
        assert metrics["list_count"] == 2
        assert metrics["total_list_items"] == 8
        assert metrics["table_count"] == 1

    def test_format_advanced_content_analysis(self):
        """Test content analysis features"""
        formatter = MarkdownFormatter()
        analysis_result = {
            "file_path": "test.md",
            "line_count": 100,
            "elements": [
                {"type": "heading", "text": "Table of Contents", "level": 1},
                {"type": "code_block", "language": "python", "line_count": 5},
                {"type": "image", "alt": "Diagram", "url": "diagram.png"},
                {"type": "link", "text": "External", "url": "https://example.com"},
            ],
        }

        result = formatter.format_advanced(analysis_result)

        json_start = result.find("{")
        json_data = json.loads(result[json_start:])
        content = json_data["content_analysis"]

        assert content["has_toc"] is True
        assert content["has_code_examples"] is True
        assert content["has_images"] is True
        assert content["has_external_links"] is True
        assert content["document_complexity"] in [
            "Simple",
            "Moderate",
            "Complex",
            "Very Complex",
        ]

    def test_format_advanced_no_headers(self):
        """Test advanced with no headers"""
        formatter = MarkdownFormatter()
        analysis_result = {"file_path": "test.md", "line_count": 10, "elements": []}

        result = formatter.format_advanced(analysis_result)

        json_start = result.find("{")
        json_data = json.loads(result[json_start:])
        metrics = json_data["document_metrics"]

        assert metrics["max_header_level"] == 0
        assert metrics["avg_header_level"] == 0

    @patch.object(MarkdownFormatter, "_compute_robust_counts_from_file")
    def test_format_advanced_with_robust_counts(self, mock_robust):
        """Test advanced with robust counts"""
        formatter = MarkdownFormatter()
        mock_robust.return_value = {"link_count": 15, "image_count": 8}

        analysis_result = {
            "file_path": "test.md",
            "line_count": 100,
            "elements": [{"type": "link", "text": "Link", "url": "http://example.com"}],
        }

        result = formatter.format_advanced(analysis_result)

        json_start = result.find("{")
        json_data = json.loads(result[json_start:])
        # Should use robust counts when available
        assert json_data["document_metrics"]["link_count"] == 15
        assert json_data["document_metrics"]["image_count"] == 8


