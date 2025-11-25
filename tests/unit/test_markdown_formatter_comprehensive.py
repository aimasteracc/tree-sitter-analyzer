"""
Comprehensive tests for MarkdownFormatter

Tests all methods in tree_sitter_analyzer.formatters.markdown_formatter module.
Target: >85% coverage
"""

import json
from unittest.mock import Mock, patch

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


class TestFormatTable:
    """Test format_table method"""

    def test_format_table_basic(self):
        """Test basic table formatting"""
        formatter = MarkdownFormatter()
        analysis_result = {
            "file_path": "test.md",
            "line_count": 50,
            "elements": [
                {
                    "type": "heading",
                    "text": "Test Document",
                    "level": 1,
                    "line_range": {"start": 1, "end": 1},
                }
            ],
        }

        result = formatter.format_table(analysis_result)

        assert "# Test Document" in result
        assert "## Document Overview" in result
        assert "test.md" in result
        assert "| Total Lines | 50 |" in result

    def test_format_table_headers_section(self):
        """Test headers section in table"""
        formatter = MarkdownFormatter()
        analysis_result = {
            "file_path": "test.md",
            "line_count": 50,
            "elements": [
                {
                    "type": "heading",
                    "text": "Header 1",
                    "level": 1,
                    "line_range": {"start": 1, "end": 1},
                },
                {
                    "type": "heading",
                    "text": "Header 2",
                    "level": 2,
                    "line_range": {"start": 5, "end": 5},
                },
            ],
        }

        result = formatter.format_table(analysis_result)

        assert "## Document Structure" in result
        assert "| # | Header 1 | 1 |" in result
        assert "| ## | Header 2 | 5 |" in result

    def test_format_table_links_section(self):
        """Test links section in table"""
        formatter = MarkdownFormatter()
        analysis_result = {
            "file_path": "test.md",
            "line_count": 50,
            "elements": [
                {
                    "type": "heading",
                    "text": "Title",
                    "level": 1,
                    "line_range": {"start": 1, "end": 1},
                },
                {
                    "type": "link",
                    "text": "External",
                    "url": "https://example.com",
                    "line_range": {"start": 10, "end": 10},
                },
                {
                    "type": "link",
                    "text": "Internal",
                    "url": "#section",
                    "line_range": {"start": 15, "end": 15},
                },
            ],
        }

        result = formatter.format_table(analysis_result)

        assert "## Links" in result
        assert "External" in result
        assert "https://example.com" in result
        assert "Internal" in result
        assert "#section" in result

    def test_format_table_images_section(self):
        """Test images section in table"""
        formatter = MarkdownFormatter()
        analysis_result = {
            "file_path": "test.md",
            "line_count": 50,
            "elements": [
                {
                    "type": "heading",
                    "text": "Title",
                    "level": 1,
                    "line_range": {"start": 1, "end": 1},
                },
                {
                    "type": "image",
                    "alt": "Test Image",
                    "url": "image.png",
                    "line_range": {"start": 5, "end": 5},
                },
            ],
        }

        result = formatter.format_table(analysis_result)

        assert "## Images" in result
        assert "Test Image" in result
        assert "image.png" in result

    def test_format_table_code_blocks_section(self):
        """Test code blocks section in table"""
        formatter = MarkdownFormatter()
        analysis_result = {
            "file_path": "test.md",
            "line_count": 50,
            "elements": [
                {
                    "type": "heading",
                    "text": "Title",
                    "level": 1,
                    "line_range": {"start": 1, "end": 1},
                },
                {
                    "type": "code_block",
                    "language": "python",
                    "line_count": 10,
                    "line_range": {"start": 10, "end": 20},
                },
            ],
        }

        result = formatter.format_table(analysis_result)

        assert "## Code Blocks" in result
        assert "python" in result
        assert "| 10 |" in result
        assert "10-20" in result

    def test_format_table_lists_section(self):
        """Test lists section in table"""
        formatter = MarkdownFormatter()
        analysis_result = {
            "file_path": "test.md",
            "line_count": 50,
            "elements": [
                {
                    "type": "heading",
                    "text": "Title",
                    "level": 1,
                    "line_range": {"start": 1, "end": 1},
                },
                {
                    "type": "list",
                    "list_type": "ordered",
                    "item_count": 5,
                    "line_range": {"start": 10, "end": 15},
                },
            ],
        }

        result = formatter.format_table(analysis_result)

        assert "## Lists" in result
        assert "ordered" in result
        assert "| 5 |" in result

    def test_format_table_tables_section(self):
        """Test tables section in table"""
        formatter = MarkdownFormatter()
        analysis_result = {
            "file_path": "test.md",
            "line_count": 50,
            "elements": [
                {
                    "type": "heading",
                    "text": "Title",
                    "level": 1,
                    "line_range": {"start": 1, "end": 1},
                },
                {
                    "type": "table",
                    "column_count": 3,
                    "row_count": 5,
                    "line_range": {"start": 10, "end": 15},
                },
            ],
        }

        result = formatter.format_table(analysis_result)

        assert "## Tables" in result
        assert "| 3 |" in result
        assert "| 5 |" in result

    def test_format_table_blockquotes_section(self):
        """Test blockquotes section in table"""
        formatter = MarkdownFormatter()
        analysis_result = {
            "file_path": "test.md",
            "line_count": 50,
            "elements": [
                {
                    "type": "heading",
                    "text": "Title",
                    "level": 1,
                    "line_range": {"start": 1, "end": 1},
                },
                {
                    "type": "blockquote",
                    "text": "This is a quote from someone famous",
                    "line_range": {"start": 10, "end": 10},
                },
            ],
        }

        result = formatter.format_table(analysis_result)

        assert "## Blockquotes" in result
        assert "This is a quote" in result

    def test_format_table_horizontal_rules_section(self):
        """Test horizontal rules section in table"""
        formatter = MarkdownFormatter()
        analysis_result = {
            "file_path": "test.md",
            "line_count": 50,
            "elements": [
                {
                    "type": "heading",
                    "text": "Title",
                    "level": 1,
                    "line_range": {"start": 1, "end": 1},
                },
                {
                    "type": "horizontal_rule",
                    "line_range": {"start": 10, "end": 10},
                },
            ],
        }

        result = formatter.format_table(analysis_result)

        assert "## Horizontal Rules" in result
        assert "Horizontal Rule" in result

    def test_format_table_html_elements_section(self):
        """Test HTML elements section in table"""
        formatter = MarkdownFormatter()
        analysis_result = {
            "file_path": "test.md",
            "line_count": 50,
            "elements": [
                {
                    "type": "heading",
                    "text": "Title",
                    "level": 1,
                    "line_range": {"start": 1, "end": 1},
                },
                {
                    "type": "html_block",
                    "name": "<div>Content</div>",
                    "line_range": {"start": 10, "end": 10},
                },
                {
                    "type": "html_inline",
                    "name": "<span>Text</span>",
                    "line_range": {"start": 15, "end": 15},
                },
            ],
        }

        result = formatter.format_table(analysis_result)

        assert "## HTML Elements" in result
        assert "html_block" in result
        assert "html_inline" in result

    def test_format_table_text_formatting_section(self):
        """Test text formatting section in table"""
        formatter = MarkdownFormatter()
        analysis_result = {
            "file_path": "test.md",
            "line_count": 50,
            "elements": [
                {
                    "type": "heading",
                    "text": "Title",
                    "level": 1,
                    "line_range": {"start": 1, "end": 1},
                },
                {
                    "type": "strong_emphasis",
                    "text": "Bold text",
                    "line_range": {"start": 10, "end": 10},
                },
                {
                    "type": "emphasis",
                    "text": "Italic text",
                    "line_range": {"start": 11, "end": 11},
                },
                {
                    "type": "inline_code",
                    "text": "code",
                    "line_range": {"start": 12, "end": 12},
                },
                {
                    "type": "strikethrough",
                    "text": "deleted",
                    "line_range": {"start": 13, "end": 13},
                },
            ],
        }

        result = formatter.format_table(analysis_result)

        assert "## Text Formatting" in result
        assert "strong_emphasis" in result
        assert "emphasis" in result
        assert "inline_code" in result
        assert "strikethrough" in result

    def test_format_table_footnotes_section(self):
        """Test footnotes section in table"""
        formatter = MarkdownFormatter()
        analysis_result = {
            "file_path": "test.md",
            "line_count": 50,
            "elements": [
                {
                    "type": "heading",
                    "text": "Title",
                    "level": 1,
                    "line_range": {"start": 1, "end": 1},
                },
                {
                    "type": "footnote_reference",
                    "text": "Note 1",
                    "line_range": {"start": 10, "end": 10},
                },
                {
                    "type": "footnote_definition",
                    "text": "Footnote content",
                    "line_range": {"start": 20, "end": 20},
                },
            ],
        }

        result = formatter.format_table(analysis_result)

        assert "## Footnotes" in result
        assert "footnote_reference" in result
        assert "footnote_definition" in result

    def test_format_table_reference_definitions_section(self):
        """Test reference definitions section in table"""
        formatter = MarkdownFormatter()
        analysis_result = {
            "file_path": "test.md",
            "line_count": 50,
            "elements": [
                {
                    "type": "heading",
                    "text": "Title",
                    "level": 1,
                    "line_range": {"start": 1, "end": 1},
                },
                {
                    "type": "reference_definition",
                    "name": "[link]: http://example.com",
                    "line_range": {"start": 10, "end": 10},
                },
            ],
        }

        result = formatter.format_table(analysis_result)

        assert "## Reference Definitions" in result
        assert "[link]: http://example.com" in result

    def test_format_table_no_headers_uses_filename(self):
        """Test table uses filename as title when no headers"""
        formatter = MarkdownFormatter()
        analysis_result = {
            "file_path": "path/to/document.md",
            "line_count": 20,
            "elements": [],
        }

        result = formatter.format_table(analysis_result)

        assert "# document.md" in result

    def test_format_table_long_content_truncation(self):
        """Test that long content is truncated properly"""
        formatter = MarkdownFormatter()
        long_text = "a" * 100
        analysis_result = {
            "file_path": "test.md",
            "line_count": 50,
            "elements": [
                {
                    "type": "heading",
                    "text": "Title",
                    "level": 1,
                    "line_range": {"start": 1, "end": 1},
                },
                {
                    "type": "blockquote",
                    "text": long_text,
                    "line_range": {"start": 10, "end": 10},
                },
            ],
        }

        result = formatter.format_table(analysis_result)

        # Should truncate to 50 chars + ...
        assert "..." in result
        assert long_text not in result


class TestFormatAnalysisResult:
    """Test format_analysis_result method"""

    def test_format_analysis_result(self):
        """Test formatting AnalysisResult object"""
        formatter = MarkdownFormatter()

        # Create mock AnalysisResult
        mock_result = Mock()
        mock_result.file_path = "test.md"
        mock_result.language = "markdown"
        mock_result.line_count = 100

        # Create mock element
        mock_element = Mock()
        mock_element.name = "Test Element"
        mock_element.type = "heading"
        mock_element.text = "Header"
        mock_element.level = 1
        mock_element.url = ""
        mock_element.alt = ""
        mock_element.language = ""
        mock_element.line_count = 0
        mock_element.list_type = ""
        mock_element.item_count = 0
        mock_element.column_count = 0
        mock_element.row_count = 0
        mock_element.start_line = 1
        mock_element.end_line = 1

        mock_result.elements = [mock_element]
        mock_result.analysis_time = 0.5

        result = formatter.format_analysis_result(mock_result)

        # Should produce markdown table output
        assert "Document Overview" in result
        assert "test.md" in result

    def test_convert_analysis_result_to_format(self):
        """Test _convert_analysis_result_to_format helper"""
        formatter = MarkdownFormatter()

        # Create mock AnalysisResult
        mock_result = Mock()
        mock_result.file_path = "test.md"
        mock_result.language = "markdown"
        mock_result.line_count = 50

        # Create mock element with all attributes
        mock_element = Mock()
        mock_element.name = "Element"
        mock_element.type = "heading"
        mock_element.text = "Header"
        mock_element.level = 2
        mock_element.url = "http://example.com"
        mock_element.alt = "Alt text"
        mock_element.language = "python"
        mock_element.line_count = 10
        mock_element.list_type = "ordered"
        mock_element.item_count = 5
        mock_element.column_count = 3
        mock_element.row_count = 4
        mock_element.start_line = 10
        mock_element.end_line = 20

        mock_result.elements = [mock_element]
        mock_result.analysis_time = 1.5

        data = formatter._convert_analysis_result_to_format(mock_result)

        assert data["file_path"] == "test.md"
        assert data["language"] == "markdown"
        assert data["line_count"] == 50
        assert len(data["elements"]) == 1
        assert data["elements"][0]["name"] == "Element"
        assert data["elements"][0]["type"] == "heading"
        assert data["elements"][0]["line_range"]["start"] == 10
        assert data["elements"][0]["line_range"]["end"] == 20
        assert data["analysis_metadata"]["analysis_time"] == 1.5


class TestCollectImages:
    """Test _collect_images method"""

    def test_collect_images_basic(self):
        """Test collecting basic image types"""
        formatter = MarkdownFormatter()
        elements = [
            {"type": "image", "alt": "Image1", "url": "img1.png"},
            {"type": "reference_image", "alt": "Image2", "url": "img2.png"},
            {
                "type": "image_reference_definition",
                "alt": "Image3",
                "url": "img3.png",
            },
        ]

        images = formatter._collect_images(elements)

        assert len(images) == 3

    def test_collect_images_with_ref_defs(self):
        """Test that reference definitions with images are included"""
        formatter = MarkdownFormatter()
        elements = [
            {"type": "image", "alt": "Image1", "url": "img1.png"},
            {
                "type": "image_reference_definition",
                "alt": "Image2",
                "url": "img2.png",
            },
        ]

        images = formatter._collect_images(elements)

        # Should not add more images when image_reference_definition exists
        assert len(images) == 2

    def test_collect_images_fallback_to_ref_defs(self):
        """Test fallback to reference definitions with image-like URLs"""
        formatter = MarkdownFormatter()
        elements = [
            {"type": "image", "alt": "Image1", "url": "img1.png"},
            {
                "type": "reference_definition",
                "name": "[img]: diagram.png",
                "url": "diagram.png",
                "alt": "diagram",
            },
            {
                "type": "reference_definition",
                "name": "[link]: http://example.com",
                "url": "http://example.com",
                "alt": "",
            },
        ]

        images = formatter._collect_images(elements)

        # Should add reference_definition with .png URL as image
        assert len(images) == 2

    def test_collect_images_parse_from_name_field(self):
        """Test parsing URL from name field when url is empty"""
        formatter = MarkdownFormatter()
        elements = [
            {
                "type": "reference_definition",
                "name": "[logo]: company-logo.svg",
                "url": "",
                "alt": "",
            }
        ]

        images = formatter._collect_images(elements)

        # Should parse and add as image
        assert len(images) == 1
        assert images[0]["url"] == "company-logo.svg"

    def test_collect_images_various_extensions(self):
        """Test recognition of various image extensions"""
        formatter = MarkdownFormatter()
        extensions = [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp"]
        elements = [
            {
                "type": "reference_definition",
                "name": f"[img{i}]: image{ext}",
                "url": f"image{ext}",
                "alt": "",
            }
            for i, ext in enumerate(extensions)
        ]

        images = formatter._collect_images(elements)

        # Should recognize all image extensions
        assert len(images) == len(extensions)

    def test_collect_images_exception_handling(self):
        """Test graceful handling of exceptions"""
        formatter = MarkdownFormatter()

        # Malformed elements should not crash
        elements = [{"type": "image", "alt": "Test"}]  # Missing url

        images = formatter._collect_images(elements)

        # Should return at least the basic image
        assert len(images) >= 1


class TestCalculateDocumentComplexity:
    """Test _calculate_document_complexity method"""

    def test_complexity_simple(self):
        """Test simple document complexity"""
        formatter = MarkdownFormatter()
        headers = [{"level": 1}]
        links = []
        code_blocks = []
        tables = []

        complexity = formatter._calculate_document_complexity(
            headers, links, code_blocks, tables
        )

        assert complexity == "Simple"

    def test_complexity_moderate(self):
        """Test moderate document complexity"""
        formatter = MarkdownFormatter()
        headers = [{"level": 1}, {"level": 2}, {"level": 2}]
        links = [{"url": "http://example.com"}] * 10
        code_blocks = [{"language": "python"}]
        tables = []

        complexity = formatter._calculate_document_complexity(
            headers, links, code_blocks, tables
        )

        assert complexity == "Moderate"

    def test_complexity_complex(self):
        """Test complex document complexity"""
        formatter = MarkdownFormatter()
        headers = [{"level": i} for i in range(1, 4)] * 3
        links = [{"url": "http://example.com"}] * 10
        code_blocks = [{"language": "python"}] * 3
        tables = [{"columns": 3}] * 2

        complexity = formatter._calculate_document_complexity(
            headers, links, code_blocks, tables
        )

        assert complexity in ["Complex", "Very Complex"]

    def test_complexity_very_complex(self):
        """Test very complex document complexity"""
        formatter = MarkdownFormatter()
        headers = [{"level": i % 6 + 1} for i in range(20)]
        links = [{"url": "http://example.com"}] * 20
        code_blocks = [{"language": "python"}] * 10
        tables = [{"columns": 3}] * 5

        complexity = formatter._calculate_document_complexity(
            headers, links, code_blocks, tables
        )

        assert complexity == "Very Complex"

    def test_complexity_no_headers(self):
        """Test complexity with no headers"""
        formatter = MarkdownFormatter()
        headers = []
        links = [{"url": "http://example.com"}] * 5
        code_blocks = [{"language": "python"}]
        tables = []

        complexity = formatter._calculate_document_complexity(
            headers, links, code_blocks, tables
        )

        # Should still calculate based on other elements
        assert complexity in ["Simple", "Moderate"]


class TestComputeRobustCounts:
    """Test _compute_robust_counts_from_file method"""

    @patch("tree_sitter_analyzer.encoding_utils.read_file_safe")
    def test_compute_robust_counts_basic(self, mock_read):
        """Test basic robust count computation"""
        formatter = MarkdownFormatter()
        mock_read.return_value = (
            "[Link](http://example.com)\n![Image](image.png)",
            None,
        )

        counts = formatter._compute_robust_counts_from_file("test.md")

        assert counts["link_count"] >= 1
        assert counts["image_count"] >= 1

    @patch("tree_sitter_analyzer.encoding_utils.read_file_safe")
    def test_compute_robust_counts_autolinks(self, mock_read):
        """Test autolink detection"""
        formatter = MarkdownFormatter()
        mock_read.return_value = (
            "<http://example.com>\n<mailto:test@example.com>",
            None,
        )

        counts = formatter._compute_robust_counts_from_file("test.md")

        assert counts["link_count"] >= 2

    @patch("tree_sitter_analyzer.encoding_utils.read_file_safe")
    def test_compute_robust_counts_reference_links(self, mock_read):
        """Test reference link detection"""
        formatter = MarkdownFormatter()
        mock_read.return_value = (
            "[Link Text][ref]\n[ref]: http://example.com",
            None,
        )

        counts = formatter._compute_robust_counts_from_file("test.md")

        assert counts["link_count"] >= 1

    @patch("tree_sitter_analyzer.encoding_utils.read_file_safe")
    def test_compute_robust_counts_image_references(self, mock_read):
        """Test reference image detection"""
        formatter = MarkdownFormatter()
        mock_read.return_value = ("![Alt][imgref]\n[imgref]: image.png", None)

        counts = formatter._compute_robust_counts_from_file("test.md")

        assert counts["image_count"] >= 1

    @patch("tree_sitter_analyzer.encoding_utils.read_file_safe")
    def test_compute_robust_counts_mixed_content(self, mock_read):
        """Test mixed links and images"""
        formatter = MarkdownFormatter()
        content = """
        [Link1](http://example.com)
        ![Image1](img1.png)
        [Link2][ref]
        ![Image2][imgref]
        <http://autolink.com>
        [ref]: http://ref.com
        [imgref]: img2.png
        """
        mock_read.return_value = (content, None)

        counts = formatter._compute_robust_counts_from_file("test.md")

        assert counts["link_count"] > 0
        assert counts["image_count"] > 0

    @patch("tree_sitter_analyzer.encoding_utils.read_file_safe")
    def test_compute_robust_counts_file_read_error(self, mock_read):
        """Test handling of file read errors"""
        formatter = MarkdownFormatter()
        mock_read.side_effect = Exception("File not found")

        counts = formatter._compute_robust_counts_from_file("nonexistent.md")

        # Should return zero counts on error
        assert counts["link_count"] == 0
        assert counts["image_count"] == 0

    def test_compute_robust_counts_empty_path(self):
        """Test with empty file path"""
        formatter = MarkdownFormatter()

        counts = formatter._compute_robust_counts_from_file("")

        assert counts["link_count"] == 0
        assert counts["image_count"] == 0

    @patch("tree_sitter_analyzer.encoding_utils.read_file_safe")
    def test_compute_robust_counts_image_extensions(self, mock_read):
        """Test various image extension detection"""
        formatter = MarkdownFormatter()
        content = """
![img1](image.png)
![img2](photo.jpg)
![img3](diagram.svg)
![img4](animation.gif)
[link](http://example.com)
        """
        mock_read.return_value = (content, None)

        counts = formatter._compute_robust_counts_from_file("test.md")

        # Should count inline images
        assert counts["image_count"] >= 4


class TestFormatJsonOutput:
    """Test _format_json_output method"""

    def test_format_json_output_basic(self):
        """Test basic JSON output formatting"""
        formatter = MarkdownFormatter()
        data = {"key": "value", "number": 42}

        result = formatter._format_json_output("Test Title", data)

        assert "--- Test Title ---" in result
        assert '"key": "value"' in result
        assert '"number": 42' in result

    def test_format_json_output_nested(self):
        """Test JSON output with nested structures"""
        formatter = MarkdownFormatter()
        data = {"outer": {"inner": {"deep": "value"}}}

        result = formatter._format_json_output("Nested Test", data)

        assert "--- Nested Test ---" in result
        # Should be pretty-printed with indentation
        assert "  " in result  # Indentation present

    def test_format_json_output_unicode(self):
        """Test JSON output with Unicode characters"""
        formatter = MarkdownFormatter()
        data = {"japanese": "日本語", "emoji": "🎉"}

        result = formatter._format_json_output("Unicode Test", data)

        # Should preserve Unicode with ensure_ascii=False
        assert "日本語" in result
        assert "🎉" in result
