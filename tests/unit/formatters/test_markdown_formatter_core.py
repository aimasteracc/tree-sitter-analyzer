import json
from unittest.mock import patch

from tree_sitter_analyzer.formatters.markdown_formatter import MarkdownFormatter


class TestMarkdownFormatterInitialization:
    def test_init(self):
        formatter = MarkdownFormatter()
        assert formatter.language == "markdown"

    def test_inherits_from_base(self):
        from tree_sitter_analyzer.formatters.base_formatter import BaseFormatter

        formatter = MarkdownFormatter()
        assert isinstance(formatter, BaseFormatter)


class TestFormatSummary:
    def test_format_summary_basic(self):
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
        json_start = result.find("{")
        json_data = json.loads(result[json_start:])
        assert json_data["language"] == "markdown"
        assert len(json_data["summary"]["headers"]) == 1
        assert len(json_data["summary"]["links"]) == 1
        assert len(json_data["summary"]["code_blocks"]) == 1

    def test_format_summary_empty_elements(self):
        formatter = MarkdownFormatter()
        analysis_result = {"file_path": "empty.md", "elements": []}

        result = formatter.format_summary(analysis_result)

        json_start = result.find("{")
        json_data = json.loads(result[json_start:])
        assert json_data["summary"]["headers"] == []
        assert json_data["summary"]["links"] == []
        assert json_data["summary"]["images"] == []

    def test_format_summary_multiple_link_types(self):
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
        assert len(json_data["summary"]["links"]) == 5

    @patch.object(MarkdownFormatter, "_compute_robust_counts_from_file")
    def test_format_summary_with_robust_counts_images(self, mock_robust):
        formatter = MarkdownFormatter()
        mock_robust.return_value = {"link_count": 0, "image_count": 3}

        analysis_result = {
            "file_path": "test.md",
            "elements": [{"type": "image", "alt": "Image1", "url": "img.png"}],
        }

        result = formatter.format_summary(analysis_result)

        json_start = result.find("{")
        json_data = json.loads(result[json_start:])
        assert len(json_data["summary"]["images"]) == 3


class TestFormatStructure:
    def test_format_structure_basic(self):
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
        assert json_data["statistics"]["link_count"] == 10
        assert json_data["statistics"]["image_count"] == 5

    @patch.object(MarkdownFormatter, "_compute_robust_counts_from_file")
    def test_format_structure_robust_fallback(self, mock_robust):
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
        assert json_data["statistics"]["link_count"] == 2


class TestFormatAdvanced:
    def test_format_advanced_json(self):
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
        assert json_data["document_metrics"]["link_count"] == 15
        assert json_data["document_metrics"]["image_count"] == 8


# ---------------------------------------------------------------------------
# Tests migrated from test_markdown_formatter_coverage_boost.py
# ---------------------------------------------------------------------------


class TestMarkdownFormatterCompact:
    """Behavioral tests for MarkdownFormatter._format_compact."""

    def setup_method(self):
        self.formatter = MarkdownFormatter()

    def test_format_compact_empty_elements(self):
        result = self.formatter._format_compact(
            {"file_path": "empty.md", "line_count": 0, "elements": []}
        )
        assert "# empty" in result
        assert "## Summary" in result
        assert "| **Total** | **0** |" in result

    def test_format_compact_with_headers_section(self):
        result = self.formatter._format_compact(
            {
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
        )
        assert "# doc" in result
        assert "| Headers | 2 |" in result
        assert "## Document Structure" in result
        assert "| # | Introduction |" in result
        assert "| ## | Details |" in result

    def test_format_compact_with_links(self):
        result = self.formatter._format_compact(
            {
                "file_path": "links.md",
                "line_count": 10,
                "elements": [
                    {
                        "type": "link",
                        "text": "Example",
                        "url": "http://example.com",
                        "line_range": {"start": 3, "end": 3},
                    },
                ],
            }
        )
        assert "| Links |" in result

    def test_format_compact_no_headers_omits_structure_section(self):
        result = self.formatter._format_compact(
            {
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
        )
        assert "## Document Structure" not in result

    def test_format_compact_many_headers_truncation(self):
        headers = [
            {
                "type": "heading",
                "text": f"Section {i + 1}",
                "level": (i % 3) + 1,
                "line_range": {"start": i * 2 + 1, "end": i * 2 + 1},
            }
            for i in range(25)
        ]
        result = self.formatter._format_compact(
            {"file_path": "long.md", "line_count": 50, "elements": headers}
        )
        assert "(5 more)" in result

    def test_format_compact_strips_markdown_extension(self):
        result = self.formatter._format_compact(
            {"file_path": "docs/guide.markdown", "line_count": 5, "elements": []}
        )
        assert "# guide" in result

    def test_format_compact_windows_path(self):
        result = self.formatter._format_compact(
            {"file_path": "C:\\Users\\docs\\readme.md", "line_count": 5, "elements": []}
        )
        assert "# readme" in result


class TestMarkdownFormatterCSV:
    """Behavioral tests for MarkdownFormatter._format_csv."""

    def setup_method(self):
        self.formatter = MarkdownFormatter()

    def test_format_csv_empty_has_header(self):
        result = self.formatter._format_csv({"file_path": "empty.md", "elements": []})
        assert "Type,Text/URL/Language,Level/Count,Start Line,End Line" in result

    def test_format_csv_heading_row(self):
        result = self.formatter._format_csv(
            {
                "file_path": "doc.md",
                "elements": [
                    {
                        "type": "heading",
                        "text": "Introduction",
                        "level": 1,
                        "line_range": {"start": 1, "end": 1},
                    }
                ],
            }
        )
        assert "heading,Introduction,1,1,1" in result

    def test_format_csv_link_row(self):
        result = self.formatter._format_csv(
            {
                "file_path": "links.md",
                "elements": [
                    {
                        "type": "link",
                        "text": "Example",
                        "url": "http://example.com",
                        "line_range": {"start": 3, "end": 3},
                    }
                ],
            }
        )
        assert "link" in result
        assert "Example -> http://example.com" in result

    def test_format_csv_image_row(self):
        result = self.formatter._format_csv(
            {
                "file_path": "img.md",
                "elements": [
                    {
                        "type": "image",
                        "alt": "Photo",
                        "url": "photo.png",
                        "line_range": {"start": 5, "end": 5},
                    }
                ],
            }
        )
        assert "image" in result
        assert "Photo -> photo.png" in result

    def test_format_csv_code_block_row(self):
        result = self.formatter._format_csv(
            {
                "file_path": "code.md",
                "elements": [
                    {
                        "type": "code_block",
                        "language": "python",
                        "line_count": 15,
                        "line_range": {"start": 10, "end": 25},
                    }
                ],
            }
        )
        assert "code_block,python,15,10,25" in result

    def test_format_csv_list_row(self):
        result = self.formatter._format_csv(
            {
                "file_path": "list.md",
                "elements": [
                    {
                        "type": "list",
                        "list_type": "unordered",
                        "item_count": 5,
                        "line_range": {"start": 2, "end": 7},
                    }
                ],
            }
        )
        assert "list,unordered,5,2,7" in result

    def test_format_csv_table_row(self):
        result = self.formatter._format_csv(
            {
                "file_path": "tbl.md",
                "elements": [
                    {
                        "type": "table",
                        "column_count": 3,
                        "row_count": 5,
                        "line_range": {"start": 8, "end": 13},
                    }
                ],
            }
        )
        assert "table,3x5,-,8,13" in result

    def test_format_csv_all_element_types_row_count(self):
        elements = [
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
        ]
        result = self.formatter._format_csv(
            {"file_path": "all.md", "elements": elements}
        )
        lines = result.strip().split("\n")
        assert len(lines) == 9
        assert lines[0].startswith("Type,")

    def test_format_csv_truncates_heading_to_50_chars(self):
        long_text = "A" * 100
        result = self.formatter._format_csv(
            {
                "file_path": "long.md",
                "elements": [
                    {
                        "type": "heading",
                        "text": long_text,
                        "level": 1,
                        "line_range": {"start": 1, "end": 1},
                    }
                ],
            }
        )
        assert "A" * 100 not in result
        assert "A" * 50 in result

    def test_format_csv_truncates_link_text_to_30_chars(self):
        long_text = "B" * 50
        result = self.formatter._format_csv(
            {
                "file_path": "longlink.md",
                "elements": [
                    {
                        "type": "link",
                        "text": long_text,
                        "url": "http://x.com",
                        "line_range": {"start": 1, "end": 1},
                    }
                ],
            }
        )
        assert "B" * 30 in result
        assert "B" * 50 not in result


class TestMarkdownCollectImagesException:
    """Behavioral tests for MarkdownFormatter._collect_images exception handling."""

    def setup_method(self):
        self.formatter = MarkdownFormatter()

    def test_collect_images_exception_in_element_returns_initial_only(self):
        """_collect_images catches exception in fallback loop (lines 589-591)."""

        class BadElement(dict):
            def get(self, key, default=None):
                if key == "alt":
                    raise RuntimeError("Cannot get alt")
                return super().get(key, default)

        elements = [
            {"type": "image", "alt": "Good", "url": "good.png"},
            BadElement({"type": "reference_definition", "url": "photo.png"}),
        ]
        result = self.formatter._collect_images(elements)
        assert len(result) == 1

    def test_collect_images_empty_list(self):
        result = self.formatter._collect_images([])
        assert result == []
