#!/usr/bin/env python3
"""Markdown formatter tests — table formatting and analysis result."""

from unittest.mock import Mock

from tree_sitter_analyzer.formatters.markdown_formatter import MarkdownFormatter


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

        # Title uses filename without extension
        assert "# test" in result
        assert "## Document Overview" in result
        assert "test.md" in result
        assert "| Total Lines | 50 |" in result
        # Check that header is in document structure
        assert "Test Document" in result

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

        # Title uses filename without extension
        assert "# document" in result

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
