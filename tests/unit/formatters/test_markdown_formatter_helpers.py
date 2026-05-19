#!/usr/bin/env python3
"""Markdown formatter tests — images, complexity, robust counts, JSON output."""


from unittest.mock import patch

from tree_sitter_analyzer.formatters.markdown_formatter import MarkdownFormatter


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
