from unittest.mock import Mock, patch

from tree_sitter_analyzer.formatters.markdown_formatter import MarkdownFormatter


class TestFormatTable:
    def test_format_table_basic(self):
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

        assert "# test" in result
        assert "## Document Overview" in result
        assert "test.md" in result
        assert "| Total Lines | 50 |" in result
        assert "Test Document" in result

    def test_format_table_headers_section(self):
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
        formatter = MarkdownFormatter()
        analysis_result = {
            "file_path": "path/to/document.md",
            "line_count": 20,
            "elements": [],
        }

        result = formatter.format_table(analysis_result)

        assert "# document" in result

    def test_format_table_long_content_truncation(self):
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

        assert "..." in result
        assert long_text not in result


class TestFormatAnalysisResult:
    def test_format_analysis_result(self):
        formatter = MarkdownFormatter()

        mock_result = Mock()
        mock_result.file_path = "test.md"
        mock_result.language = "markdown"
        mock_result.line_count = 100

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

        assert "Document Overview" in result
        assert "test.md" in result

    def test_convert_analysis_result_to_format(self):
        formatter = MarkdownFormatter()

        mock_result = Mock()
        mock_result.file_path = "test.md"
        mock_result.language = "markdown"
        mock_result.line_count = 50

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
    def test_collect_images_basic(self):
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

        assert len(images) == 2

    def test_collect_images_fallback_to_ref_defs(self):
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

        assert len(images) == 2

    def test_collect_images_parse_from_name_field(self):
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

        assert len(images) == 1
        assert images[0]["url"] == "company-logo.svg"

    def test_collect_images_various_extensions(self):
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

        assert len(images) == len(extensions)

    def test_collect_images_exception_handling(self):
        formatter = MarkdownFormatter()

        elements = [{"type": "image", "alt": "Test"}]

        images = formatter._collect_images(elements)

        assert len(images) == 1
        assert images[0]["alt"] == "Test"


class TestCalculateDocumentComplexity:
    def test_complexity_simple(self):
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
        formatter = MarkdownFormatter()
        headers = []
        links = [{"url": "http://example.com"}] * 5
        code_blocks = [{"language": "python"}]
        tables = []

        complexity = formatter._calculate_document_complexity(
            headers, links, code_blocks, tables
        )

        assert complexity in ["Simple", "Moderate"]


class TestComputeRobustCounts:
    @patch("tree_sitter_analyzer.encoding_utils.read_file_safe")
    def test_compute_robust_counts_basic(self, mock_read):
        formatter = MarkdownFormatter()
        mock_read.return_value = (
            "[Link](http://example.com)\n![Image](image.png)",
            None,
        )

        counts = formatter._compute_robust_counts_from_file("test.md")

        assert counts["link_count"] == 1
        assert counts["image_count"] == 1

    @patch("tree_sitter_analyzer.encoding_utils.read_file_safe")
    def test_compute_robust_counts_autolinks(self, mock_read):
        formatter = MarkdownFormatter()
        mock_read.return_value = (
            "<http://example.com>\n<mailto:test@example.com>",  # pragma: allowlist secret
            None,
        )

        counts = formatter._compute_robust_counts_from_file("test.md")

        assert counts["link_count"] == 2

    @patch("tree_sitter_analyzer.encoding_utils.read_file_safe")
    def test_compute_robust_counts_reference_links(self, mock_read):
        formatter = MarkdownFormatter()
        mock_read.return_value = (
            "[Link Text][ref]\n[ref]: http://example.com",
            None,
        )

        counts = formatter._compute_robust_counts_from_file("test.md")

        assert counts["link_count"] == 1

    @patch("tree_sitter_analyzer.encoding_utils.read_file_safe")
    def test_compute_robust_counts_image_references(self, mock_read):
        formatter = MarkdownFormatter()
        mock_read.return_value = ("![Alt][imgref]\n[imgref]: image.png", None)

        counts = formatter._compute_robust_counts_from_file("test.md")

        # 2 = the ![Alt][imgref] reference + its used [imgref]: definition
        # (count_markdown_images counts both; exact fact, update if the
        # counting rules change)
        assert counts["image_count"] == 2

    @patch("tree_sitter_analyzer.encoding_utils.read_file_safe")
    def test_compute_robust_counts_mixed_content(self, mock_read):
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

        # links: Link1 inline + Link2 reference + autolink = 3
        # images: Image1 inline + Image2 reference = 2 (indented [imgref]:
        # definition lines do not match the ^-anchored definition pattern)
        assert counts["link_count"] == 3
        assert counts["image_count"] == 2

    @patch("tree_sitter_analyzer.encoding_utils.read_file_safe")
    def test_compute_robust_counts_file_read_error(self, mock_read):
        formatter = MarkdownFormatter()
        mock_read.side_effect = Exception("File not found")

        counts = formatter._compute_robust_counts_from_file("nonexistent.md")

        assert counts["link_count"] == 0
        assert counts["image_count"] == 0

    def test_compute_robust_counts_empty_path(self):
        formatter = MarkdownFormatter()

        counts = formatter._compute_robust_counts_from_file("")

        assert counts["link_count"] == 0
        assert counts["image_count"] == 0

    @patch("tree_sitter_analyzer.encoding_utils.read_file_safe")
    def test_compute_robust_counts_image_extensions(self, mock_read):
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

        assert counts["image_count"] == 4
        assert counts["link_count"] == 1


class TestFormatJsonOutput:
    def test_format_json_output_basic(self):
        formatter = MarkdownFormatter()
        data = {"key": "value", "number": 42}

        result = formatter._format_json_output("Test Title", data)

        assert "--- Test Title ---" in result
        assert '"key": "value"' in result
        assert '"number": 42' in result

    def test_format_json_output_nested(self):
        formatter = MarkdownFormatter()
        data = {"outer": {"inner": {"deep": "value"}}}

        result = formatter._format_json_output("Nested Test", data)

        assert "--- Nested Test ---" in result
        assert "  " in result

    def test_format_json_output_unicode(self):
        formatter = MarkdownFormatter()
        data = {"japanese": "日本語", "emoji": "🎉"}

        result = formatter._format_json_output("Unicode Test", data)

        assert "日本語" in result
        assert "🎉" in result
