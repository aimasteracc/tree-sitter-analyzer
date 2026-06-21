#!/usr/bin/env python3
"""Coverage boost tests for MarkdownFormatter uncovered methods.

Targets:
- format_table with "compact" and "csv" types
- _format_compact
- _format_csv
- _collect_images exception handler
"""

from tree_sitter_analyzer.formatters.markdown_formatter import MarkdownFormatter


class TestFormatTableCompactAndCSV:
    """Tests for format_table with compact and csv table_type."""

    def setup_method(self):
        self.formatter = MarkdownFormatter()

    def test_format_table_csv(self):
        """Test format_table with table_type='csv'."""
        analysis_result = {
            "file_path": "test.md",
            "line_count": 10,
            "elements": [
                {
                    "type": "heading",
                    "text": "Test",
                    "level": 1,
                    "line_range": {"start": 1, "end": 1},
                },
                {
                    "type": "link",
                    "text": "Link",
                    "url": "http://example.com",
                    "line_range": {"start": 3, "end": 3},
                },
            ],
        }

        result = self.formatter.format_table(analysis_result, table_type="csv")
        assert result is not None
        assert isinstance(result, str)
        assert result


class TestFormatCompact:
    """Tests for _format_compact method."""

    def setup_method(self):
        self.formatter = MarkdownFormatter()

    def test_format_compact_empty(self):
        """Test _format_compact with empty elements."""
        analysis_result = {
            "file_path": "empty.md",
            "line_count": 0,
            "elements": [],
        }

        result = self.formatter._format_compact(analysis_result)
        assert "# empty" in result
        assert "## Summary" in result
        assert "| **Total** | **0** |" in result

    def test_format_compact_with_headers(self):
        """Test _format_compact with heading elements."""
        analysis_result = {
            "file_path": "doc.md",
            "line_count": 20,
            "elements": [
                {
                    "type": "heading",
                    "text": "Introduction",
                    "level": 1,
                    "line_range": {"start": 1, "end": 1},
                },
                {
                    "type": "heading",
                    "text": "Details",
                    "level": 2,
                    "line_range": {"start": 5, "end": 5},
                },
            ],
        }

        result = self.formatter._format_compact(analysis_result)
        assert "# doc" in result
        assert "## Summary" in result
        assert "| Headers | 2 |" in result
        assert "## Document Structure" in result
        assert "| # | Introduction |" in result
        assert "| ## | Details |" in result

    def test_format_compact_with_links(self):
        """Test _format_compact with link elements."""
        analysis_result = {
            "file_path": "links.md",
            "line_count": 10,
            "elements": [
                {
                    "type": "link",
                    "text": "Example",
                    "url": "http://example.com",
                    "line_range": {"start": 3, "end": 3},
                },
                {
                    "type": "autolink",
                    "text": "auto",
                    "url": "http://auto.com",
                    "line_range": {"start": 5, "end": 5},
                },
            ],
        }

        result = self.formatter._format_compact(analysis_result)
        assert "## Summary" in result
        assert "| Links |" in result

    def test_format_compact_with_images(self):
        """Test _format_compact with image elements."""
        analysis_result = {
            "file_path": "images.md",
            "line_count": 10,
            "elements": [
                {
                    "type": "image",
                    "alt": "Photo",
                    "url": "photo.png",
                    "line_range": {"start": 1, "end": 1},
                },
            ],
        }

        result = self.formatter._format_compact(analysis_result)
        assert "## Summary" in result
        assert "| Images |" in result

    def test_format_compact_with_code_blocks(self):
        """Test _format_compact with code block elements."""
        analysis_result = {
            "file_path": "code.md",
            "line_count": 30,
            "elements": [
                {
                    "type": "code_block",
                    "language": "python",
                    "line_count": 10,
                    "line_range": {"start": 5, "end": 15},
                },
            ],
        }

        result = self.formatter._format_compact(analysis_result)
        assert "## Summary" in result
        assert "| Code Blocks |" in result

    def test_format_compact_with_lists(self):
        """Test _format_compact with list elements."""
        analysis_result = {
            "file_path": "lists.md",
            "line_count": 15,
            "elements": [
                {
                    "type": "list",
                    "list_type": "unordered",
                    "item_count": 3,
                    "line_range": {"start": 2, "end": 5},
                },
                {
                    "type": "task_list",
                    "list_type": "task",
                    "item_count": 4,
                    "line_range": {"start": 7, "end": 11},
                },
            ],
        }

        result = self.formatter._format_compact(analysis_result)
        assert "## Summary" in result
        assert "| Lists |" in result

    def test_format_compact_with_tables(self):
        """Test _format_compact with table elements."""
        analysis_result = {
            "file_path": "tables.md",
            "line_count": 20,
            "elements": [
                {
                    "type": "table",
                    "column_count": 3,
                    "row_count": 5,
                    "line_range": {"start": 4, "end": 9},
                },
            ],
        }

        result = self.formatter._format_compact(analysis_result)
        assert "## Summary" in result
        assert "| Tables |" in result

    def test_format_compact_filename_without_extension(self):
        """Test _format_compact with filename that has no extension."""
        analysis_result = {
            "file_path": "README",
            "line_count": 5,
            "elements": [
                {
                    "type": "heading",
                    "text": "README",
                    "level": 1,
                    "line_range": {"start": 1, "end": 1},
                },
            ],
        }

        result = self.formatter._format_compact(analysis_result)
        assert "# README" in result

    def test_format_compact_filename_markdown_extension(self):
        """Test _format_compact strips .markdown extension."""
        analysis_result = {
            "file_path": "docs/guide.markdown",
            "line_count": 5,
            "elements": [],
        }

        result = self.formatter._format_compact(analysis_result)
        assert "# guide" in result

    def test_format_compact_windows_path(self):
        """Test _format_compact with Windows-style path."""
        analysis_result = {
            "file_path": "C:\\Users\\docs\\readme.md",
            "line_count": 5,
            "elements": [],
        }

        result = self.formatter._format_compact(analysis_result)
        assert "# readme" in result

    def test_format_compact_many_headers(self):
        """Test _format_compact with more than 20 headers (truncation)."""
        headers = []
        for i in range(25):
            headers.append(
                {
                    "type": "heading",
                    "text": f"Section {i + 1}",
                    "level": (i % 3) + 1,
                    "line_range": {"start": i * 2 + 1, "end": i * 2 + 1},
                }
            )

        analysis_result = {
            "file_path": "long.md",
            "line_count": 50,
            "elements": headers,
        }

        result = self.formatter._format_compact(analysis_result)
        assert "(5 more)" in result

    def test_format_compact_no_headers(self):
        """Test _format_compact without heading elements (no structure section)."""
        analysis_result = {
            "file_path": "nolinks.md",
            "line_count": 10,
            "elements": [
                {
                    "type": "link",
                    "text": "Link1",
                    "url": "http://a.com",
                    "line_range": {"start": 1, "end": 1},
                },
            ],
        }

        result = self.formatter._format_compact(analysis_result)
        assert "## Document Structure" not in result


class TestFormatCSV:
    """Tests for _format_csv method."""

    def setup_method(self):
        self.formatter = MarkdownFormatter()

    def test_format_csv_empty(self):
        """Test _format_csv with empty elements."""
        analysis_result = {
            "file_path": "empty.md",
            "elements": [],
        }

        result = self.formatter._format_csv(analysis_result)
        assert "Type,Text/URL/Language,Level/Count,Start Line,End Line" in result

    def test_format_csv_heading(self):
        """Test _format_csv with heading element."""
        analysis_result = {
            "file_path": "doc.md",
            "elements": [
                {
                    "type": "heading",
                    "text": "Introduction",
                    "level": 1,
                    "line_range": {"start": 1, "end": 1},
                },
            ],
        }

        result = self.formatter._format_csv(analysis_result)
        assert "heading,Introduction,1,1,1" in result

    def test_format_csv_link(self):
        """Test _format_csv with link element."""
        analysis_result = {
            "file_path": "links.md",
            "elements": [
                {
                    "type": "link",
                    "text": "Example",
                    "url": "http://example.com",
                    "line_range": {"start": 3, "end": 3},
                },
            ],
        }

        result = self.formatter._format_csv(analysis_result)
        assert "link" in result
        assert "Example -> http://example.com" in result

    def test_format_csv_autolink(self):
        """Test _format_csv with autolink element."""
        analysis_result = {
            "file_path": "auto.md",
            "elements": [
                {
                    "type": "autolink",
                    "text": "auto",
                    "url": "http://auto.com",
                    "line_range": {"start": 2, "end": 2},
                },
            ],
        }

        result = self.formatter._format_csv(analysis_result)
        assert "autolink" in result

    def test_format_csv_image(self):
        """Test _format_csv with image element."""
        analysis_result = {
            "file_path": "img.md",
            "elements": [
                {
                    "type": "image",
                    "alt": "Photo",
                    "url": "photo.png",
                    "line_range": {"start": 5, "end": 5},
                },
            ],
        }

        result = self.formatter._format_csv(analysis_result)
        assert "image" in result
        assert "Photo -> photo.png" in result

    def test_format_csv_code_block(self):
        """Test _format_csv with code block element."""
        analysis_result = {
            "file_path": "code.md",
            "elements": [
                {
                    "type": "code_block",
                    "language": "python",
                    "line_count": 15,
                    "line_range": {"start": 10, "end": 25},
                },
            ],
        }

        result = self.formatter._format_csv(analysis_result)
        assert "code_block,python,15,10,25" in result

    def test_format_csv_list(self):
        """Test _format_csv with list element."""
        analysis_result = {
            "file_path": "list.md",
            "elements": [
                {
                    "type": "list",
                    "list_type": "unordered",
                    "item_count": 5,
                    "line_range": {"start": 2, "end": 7},
                },
            ],
        }

        result = self.formatter._format_csv(analysis_result)
        assert "list,unordered,5,2,7" in result

    def test_format_csv_task_list(self):
        """Test _format_csv with task list element."""
        analysis_result = {
            "file_path": "tasks.md",
            "elements": [
                {
                    "type": "task_list",
                    "list_type": "task",
                    "item_count": 3,
                    "line_range": {"start": 4, "end": 7},
                },
            ],
        }

        result = self.formatter._format_csv(analysis_result)
        assert "task_list,task,3,4,7" in result

    def test_format_csv_table(self):
        """Test _format_csv with table element."""
        analysis_result = {
            "file_path": "tbl.md",
            "elements": [
                {
                    "type": "table",
                    "column_count": 3,
                    "row_count": 5,
                    "line_range": {"start": 8, "end": 13},
                },
            ],
        }

        result = self.formatter._format_csv(analysis_result)
        assert "table,3x5,-,8,13" in result

    def test_format_csv_unknown_type(self):
        """Test _format_csv with unknown element type (else branch)."""
        analysis_result = {
            "file_path": "unknown.md",
            "elements": [
                {
                    "type": "custom_type",
                    "name": "CustomElement",
                    "line_range": {"start": 1, "end": 1},
                },
            ],
        }

        result = self.formatter._format_csv(analysis_result)
        assert "custom_type" in result

    def test_format_csv_all_element_types(self):
        """Test _format_csv with all supported element types."""
        analysis_result = {
            "file_path": "all.md",
            "elements": [
                {
                    "type": "heading",
                    "text": "H1",
                    "level": 1,
                    "line_range": {"start": 1, "end": 1},
                },
                {
                    "type": "link",
                    "text": "L1",
                    "url": "http://a.com",
                    "line_range": {"start": 2, "end": 2},
                },
                {
                    "type": "autolink",
                    "text": "A1",
                    "url": "http://b.com",
                    "line_range": {"start": 3, "end": 3},
                },
                {
                    "type": "image",
                    "alt": "I1",
                    "url": "img.png",
                    "line_range": {"start": 4, "end": 4},
                },
                {
                    "type": "code_block",
                    "language": "python",
                    "line_count": 5,
                    "line_range": {"start": 5, "end": 10},
                },
                {
                    "type": "list",
                    "list_type": "unordered",
                    "item_count": 3,
                    "line_range": {"start": 11, "end": 14},
                },
                {
                    "type": "task_list",
                    "list_type": "task",
                    "item_count": 2,
                    "line_range": {"start": 15, "end": 17},
                },
                {
                    "type": "table",
                    "column_count": 2,
                    "row_count": 3,
                    "line_range": {"start": 18, "end": 21},
                },
            ],
        }

        result = self.formatter._format_csv(analysis_result)
        lines = result.strip().split("\n")
        # Header + 8 data rows
        assert len(lines) == 9
        assert lines[0].startswith("Type,")

    def test_format_csv_truncates_long_text(self):
        """Test _format_csv truncates long heading text to 50 chars."""
        long_text = "A" * 100
        analysis_result = {
            "file_path": "long.md",
            "elements": [
                {
                    "type": "heading",
                    "text": long_text,
                    "level": 1,
                    "line_range": {"start": 1, "end": 1},
                },
            ],
        }

        result = self.formatter._format_csv(analysis_result)
        # The full 100-char text should not appear (truncated to 50)
        assert "A" * 100 not in result
        # Truncated to 50 chars
        assert "A" * 50 in result

    def test_format_csv_truncates_link_text(self):
        """Test _format_csv truncates link text to 30 chars."""
        long_text = "B" * 50
        analysis_result = {
            "file_path": "longlink.md",
            "elements": [
                {
                    "type": "link",
                    "text": long_text,
                    "url": "http://x.com",
                    "line_range": {"start": 1, "end": 1},
                },
            ],
        }

        result = self.formatter._format_csv(analysis_result)
        # Link format: "text -> url", text truncated to 30
        assert "B" * 30 in result
        assert "B" * 50 not in result


class TestCollectImagesException:
    """Tests for _collect_images exception handling."""

    def setup_method(self):
        self.formatter = MarkdownFormatter()

    def test_collect_images_with_malformed_element(self):
        """Test _collect_images handles malformed elements gracefully."""
        elements = [
            {"type": "image", "alt": "Good", "url": "good.png"},
            {"type": "image"},  # Missing both alt and url
            {"type": "reference_image", "alt": None, "url": None},
        ]

        result = self.formatter._collect_images(elements)
        assert len(result) == 3

    def test_collect_images_exception_in_element(self):
        """Test _collect_images catches exception in fallback loop (lines 589-591)."""

        class BadElement(dict):
            def get(self, key, default=None):
                if key == "alt":
                    raise RuntimeError("Cannot get alt")
                return super().get(key, default)

        # Use reference_definition so it's NOT in initial image list;
        # fallback loop tries to promote it but hits the exception
        elements = [
            {"type": "image", "alt": "Good", "url": "good.png"},
            BadElement({"type": "reference_definition", "url": "photo.png"}),
        ]

        result = self.formatter._collect_images(elements)
        # Exception in fallback returns initial images only
        assert len(result) == 1  # Only the explicit "image" type

    def test_collect_images_empty_list(self):
        """Test _collect_images with empty list."""
        result = self.formatter._collect_images([])
        assert result == []
