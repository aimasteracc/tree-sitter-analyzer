#!/usr/bin/env python3
"""
Tests for Markdown Formatter with new elements

Tests for the newly added Markdown element formatting functionality:
- blockquotes
- horizontal rules
- HTML elements
- text formatting
- footnotes
"""

import pytest
import json
from tree_sitter_analyzer.formatters.markdown_formatter import MarkdownFormatter


class TestMarkdownFormatterNewElements:
    """Test Markdown formatter with new element types"""

    def setup_method(self):
        """Setup test fixtures"""
        self.formatter = MarkdownFormatter()

    def test_format_table_with_blockquotes(self):
        """Test table formatting with blockquotes"""
        analysis_result = {
            "file_path": "test.md",
            "line_count": 10,
            "elements": [
                {
                    "type": "heading",
                    "text": "Test Document",
                    "level": 1,
                    "line_range": {"start": 1, "end": 1}
                },
                {
                    "type": "blockquote",
                    "text": "This is a blockquote with some content",
                    "line_range": {"start": 3, "end": 3}
                },
                {
                    "type": "blockquote",
                    "text": "Another blockquote with very long content that should be truncated when displayed in the table format",
                    "line_range": {"start": 5, "end": 5}
                }
            ]
        }
        
        result = self.formatter.format_table(analysis_result)
        
        # Check that blockquotes section is included
        assert "## Blockquotes" in result
        assert "| Content | Line |" in result
        assert "This is a blockquote with some content | 3 |" in result
        assert "Another blockquote with very long content that sho..." in result  # Should be truncated

    def test_format_table_with_horizontal_rules(self):
        """Test table formatting with horizontal rules"""
        analysis_result = {
            "file_path": "test.md",
            "line_count": 15,
            "elements": [
                {
                    "type": "heading",
                    "text": "Test Document",
                    "level": 1,
                    "line_range": {"start": 1, "end": 1}
                },
                {
                    "type": "horizontal_rule",
                    "line_range": {"start": 3, "end": 3}
                },
                {
                    "type": "horizontal_rule",
                    "line_range": {"start": 7, "end": 7}
                },
                {
                    "type": "horizontal_rule",
                    "line_range": {"start": 12, "end": 12}
                }
            ]
        }
        
        result = self.formatter.format_table(analysis_result)
        
        # Check that horizontal rules section is included
        assert "## Horizontal Rules" in result
        assert "| Type | Line |" in result
        assert "| Horizontal Rule | 3 |" in result
        assert "| Horizontal Rule | 7 |" in result
        assert "| Horizontal Rule | 12 |" in result

    def test_format_table_with_html_elements(self):
        """Test table formatting with HTML elements"""
        analysis_result = {
            "file_path": "test.md",
            "line_count": 20,
            "elements": [
                {
                    "type": "heading",
                    "text": "Test Document",
                    "level": 1,
                    "line_range": {"start": 1, "end": 1}
                },
                {
                    "type": "html_block",
                    "name": "<div>This is an HTML div element</div>",
                    "line_range": {"start": 3, "end": 3}
                },
                {
                    "type": "html_inline",
                    "name": "<strong>inline HTML</strong>",
                    "line_range": {"start": 5, "end": 5}
                },
                {
                    "type": "html_block",
                    "name": "<p>HTML paragraph with very long content that should be truncated when displayed</p>",
                    "line_range": {"start": 7, "end": 7}
                }
            ]
        }
        
        result = self.formatter.format_table(analysis_result)
        
        # Check that HTML elements section is included
        assert "## HTML Elements" in result
        assert "| Type | Content | Line |" in result
        assert "| html_block | <div>This is an HTML div eleme... | 3 |" in result
        assert "| html_inline | <strong>inline HTML</strong> | 5 |" in result
        assert "| html_block | <p>HTML paragraph with very lo... | 7 |" in result  # Should be truncated

    def test_format_table_with_text_formatting(self):
        """Test table formatting with text formatting elements"""
        analysis_result = {
            "file_path": "test.md",
            "line_count": 25,
            "elements": [
                {
                    "type": "heading",
                    "text": "Test Document",
                    "level": 1,
                    "line_range": {"start": 1, "end": 1}
                },
                {
                    "type": "strong_emphasis",
                    "text": "bold text",
                    "line_range": {"start": 3, "end": 3}
                },
                {
                    "type": "emphasis",
                    "text": "italic text",
                    "line_range": {"start": 3, "end": 3}
                },
                {
                    "type": "inline_code",
                    "text": "code span",
                    "line_range": {"start": 5, "end": 5}
                },
                {
                    "type": "strikethrough",
                    "text": "strikethrough text with very long content that should be truncated",
                    "line_range": {"start": 7, "end": 7}
                }
            ]
        }
        
        result = self.formatter.format_table(analysis_result)
        
        # Check that text formatting section is included
        assert "## Text Formatting" in result
        assert "| Type | Content | Line |" in result
        assert "| strong_emphasis | bold text | 3 |" in result
        assert "| emphasis | italic text | 3 |" in result
        assert "| inline_code | code span | 5 |" in result
        assert "| strikethrough | strikethrough text with very l... | 7 |" in result  # Should be truncated

    def test_format_table_with_footnotes(self):
        """Test table formatting with footnotes"""
        analysis_result = {
            "file_path": "test.md",
            "line_count": 30,
            "elements": [
                {
                    "type": "heading",
                    "text": "Test Document",
                    "level": 1,
                    "line_range": {"start": 1, "end": 1}
                },
                {
                    "type": "footnote_reference",
                    "text": "[^1]",
                    "line_range": {"start": 3, "end": 3}
                },
                {
                    "type": "footnote_reference",
                    "text": "[^note]",
                    "line_range": {"start": 5, "end": 5}
                },
                {
                    "type": "footnote_definition",
                    "text": "[^1]: This is the footnote content.",
                    "line_range": {"start": 10, "end": 10}
                },
                {
                    "type": "footnote_definition",
                    "text": "[^note]: This is another footnote with very long content that should be truncated when displayed in the table",
                    "line_range": {"start": 12, "end": 12}
                }
            ]
        }
        
        result = self.formatter.format_table(analysis_result)
        
        # Check that footnotes section is included
        assert "## Footnotes" in result
        assert "| Type | Content | Line |" in result
        assert "| footnote_reference | [^1] | 3 |" in result
        assert "| footnote_reference | [^note] | 5 |" in result
        assert "| footnote_definition | [^1]: This is the footnote con... | 10 |" in result
        assert "| footnote_definition | [^note]: This is another footn... | 12 |" in result  # Should be truncated

    def test_format_table_with_all_new_elements(self):
        """Test table formatting with all new element types combined"""
        analysis_result = {
            "file_path": "comprehensive.md",
            "line_count": 50,
            "elements": [
                {
                    "type": "heading",
                    "text": "Comprehensive Test Document",
                    "level": 1,
                    "line_range": {"start": 1, "end": 1}
                },
                {
                    "type": "blockquote",
                    "text": "This is a blockquote",
                    "line_range": {"start": 3, "end": 3}
                },
                {
                    "type": "horizontal_rule",
                    "line_range": {"start": 5, "end": 5}
                },
                {
                    "type": "html_block",
                    "name": "<div>HTML content</div>",
                    "line_range": {"start": 7, "end": 7}
                },
                {
                    "type": "strong_emphasis",
                    "text": "bold text",
                    "line_range": {"start": 9, "end": 9}
                },
                {
                    "type": "footnote_reference",
                    "text": "[^1]",
                    "line_range": {"start": 11, "end": 11}
                }
            ]
        }
        
        result = self.formatter.format_table(analysis_result)
        
        # Check that all new sections are included
        assert "## Blockquotes" in result
        assert "## Horizontal Rules" in result
        assert "## HTML Elements" in result
        assert "## Text Formatting" in result
        assert "## Footnotes" in result
        
        # Check document overview
        assert "| Total Elements | 6 |" in result

    def test_format_table_with_no_new_elements(self):
        """Test table formatting when no new elements are present"""
        analysis_result = {
            "file_path": "simple.md",
            "line_count": 10,
            "elements": [
                {
                    "type": "heading",
                    "text": "Simple Document",
                    "level": 1,
                    "line_range": {"start": 1, "end": 1}
                },
                {
                    "type": "link",
                    "text": "Example Link",
                    "url": "https://example.com",
                    "line_range": {"start": 3, "end": 3}
                }
            ]
        }
        
        result = self.formatter.format_table(analysis_result)
        
        # Check that new element sections are not included when no elements exist
        assert "## Blockquotes" not in result
        assert "## Horizontal Rules" not in result
        assert "## HTML Elements" not in result
        assert "## Text Formatting" not in result
        assert "## Footnotes" not in result
        
        # But basic sections should still be there
        assert "## Document Overview" in result
        assert "## Document Structure" in result
        assert "## Links" in result

    def test_format_summary_with_new_elements(self):
        """Test summary formatting includes traditional elements (new elements not in summary)"""
        analysis_result = {
            "file_path": "test.md",
            "elements": [
                {
                    "type": "heading",
                    "text": "Test Header",
                    "level": 1
                },
                {
                    "type": "blockquote",
                    "text": "This is a blockquote"
                },
                {
                    "type": "link",
                    "text": "Test Link",
                    "url": "https://example.com"
                }
            ]
        }
        
        result = self.formatter.format_summary(analysis_result)
        
        # Summary should include traditional elements
        assert "headers" in result
        assert "links" in result
        
        # Parse JSON to verify structure
        lines = result.split('\n')
        json_start = next(i for i, line in enumerate(lines) if line.startswith('{'))
        json_content = '\n'.join(lines[json_start:])
        data = json.loads(json_content)
        
        assert len(data["summary"]["headers"]) == 1
        assert len(data["summary"]["links"]) == 1
        assert data["summary"]["headers"][0]["name"] == "Test Header"
        assert data["summary"]["links"][0]["text"] == "Test Link"

    def test_format_structure_with_new_elements(self):
        """Test structure formatting includes traditional elements (new elements not in structure)"""
        analysis_result = {
            "file_path": "test.md",
            "line_count": 20,
            "elements": [
                {
                    "type": "heading",
                    "text": "Test Header",
                    "level": 1,
                    "line_range": {"start": 1, "end": 1}
                },
                {
                    "type": "blockquote",
                    "text": "This is a blockquote",
                    "line_range": {"start": 3, "end": 3}
                },
                {
                    "type": "code_block",
                    "language": "python",
                    "line_count": 3,
                    "line_range": {"start": 5, "end": 7}
                }
            ]
        }
        
        result = self.formatter.format_structure(analysis_result)
        
        # Parse JSON to verify structure
        lines = result.split('\n')
        json_start = next(i for i, line in enumerate(lines) if line.startswith('{'))
        json_content = '\n'.join(lines[json_start:])
        data = json.loads(json_content)
        
        # Structure should include traditional elements
        assert len(data["headers"]) == 1
        assert len(data["code_blocks"]) == 1
        assert data["statistics"]["header_count"] == 1
        assert data["statistics"]["code_block_count"] == 1

    def test_format_advanced_includes_new_elements_in_count(self):
        """Test advanced formatting includes new elements in total count"""
        analysis_result = {
            "file_path": "test.md",
            "line_count": 30,
            "elements": [
                {
                    "type": "heading",
                    "text": "Test Header",
                    "level": 1
                },
                {
                    "type": "blockquote",
                    "text": "This is a blockquote"
                },
                {
                    "type": "horizontal_rule"
                },
                {
                    "type": "html_block",
                    "name": "<div>HTML content</div>"
                },
                {
                    "type": "strong_emphasis",
                    "text": "bold text"
                },
                {
                    "type": "footnote_reference",
                    "text": "[^1]"
                }
            ]
        }
        
        result = self.formatter.format_advanced(analysis_result)
        
        # Parse JSON to verify structure
        lines = result.split('\n')
        json_start = next(i for i, line in enumerate(lines) if line.startswith('{'))
        json_content = '\n'.join(lines[json_start:])
        data = json.loads(json_content)
        
        # Should include all elements in count
        assert data["element_count"] == 6
        assert len(data["elements"]) == 6

    def test_format_advanced_text_format(self):
        """Test advanced formatting in text format"""
        analysis_result = {
            "file_path": "test.md",
            "line_count": 25,
            "elements": [
                {
                    "type": "heading",
                    "text": "Test Header",
                    "level": 1
                },
                {
                    "type": "link",
                    "text": "External Link",
                    "url": "https://example.com"
                },
                {
                    "type": "code_block",
                    "language": "python",
                    "line_count": 5
                }
            ]
        }
        
        result = self.formatter.format_advanced(analysis_result, output_format="text")
        
        # Check text format structure
        assert "--- Advanced Analysis Results ---" in result
        assert '"File: test.md"' in result
        assert '"Language: markdown"' in result
        assert '"Lines: 25"' in result
        assert '"Elements: 3"' in result
        assert '"Headers: 1"' in result
        assert '"Links: 1"' in result
        assert '"External Links: 1"' in result
        assert '"Code Blocks: 1"' in result

    def test_empty_elements_sections_not_shown(self):
        """Test that empty sections for new elements are not displayed"""
        analysis_result = {
            "file_path": "minimal.md",
            "line_count": 5,
            "elements": [
                {
                    "type": "heading",
                    "text": "Minimal Document",
                    "level": 1,
                    "line_range": {"start": 1, "end": 1}
                }
            ]
        }
        
        result = self.formatter.format_table(analysis_result)
        
        # Verify that sections for new elements are not present when no elements exist
        new_element_sections = [
            "## Blockquotes",
            "## Horizontal Rules", 
            "## HTML Elements",
            "## Text Formatting",
            "## Footnotes"
        ]
        
        for section in new_element_sections:
            assert section not in result, f"Section '{section}' should not be present when no elements exist"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=tree_sitter_analyzer.formatters.markdown_formatter", "--cov-report=term-missing"])