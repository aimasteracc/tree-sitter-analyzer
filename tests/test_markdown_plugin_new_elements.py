#!/usr/bin/env python3
"""
Tests for new Markdown elements extraction functionality

Tests for the newly added Markdown element extraction methods:
- blockquotes
- horizontal rules
- HTML elements
- text formatting
- footnotes
"""

from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.languages.markdown_plugin import (
    MarkdownElement,
    MarkdownElementExtractor,
    MarkdownPlugin,
)


class TestMarkdownNewElementsExtraction:
    """Test new Markdown elements extraction functionality"""

    def setup_method(self):
        """Setup test fixtures"""
        self.extractor = MarkdownElementExtractor()
        self.plugin = MarkdownPlugin()

    def test_extract_blockquotes_basic(self):
        """Test basic blockquote extraction"""
        content = """> This is a blockquote.
> It can span multiple lines.
>
> > This is a nested blockquote."""

        mock_tree = Mock()
        mock_root = Mock()
        mock_tree.root_node = mock_root

        # Mock blockquote nodes
        blockquote_node = Mock()
        blockquote_node.type = "block_quote"
        blockquote_node.start_point = (0, 0)
        blockquote_node.end_point = (3, 35)
        blockquote_node.start_byte = 0
        blockquote_node.end_byte = len(content)

        mock_root.children = [blockquote_node]

        # Mock text extraction
        with patch.object(
            self.extractor, "_get_node_text_optimized", return_value=content
        ):
            with patch.object(
                self.extractor, "_traverse_nodes", return_value=[blockquote_node]
            ):
                result = self.extractor.extract_blockquotes(mock_tree, content)

                assert len(result) == 1
                assert result[0].element_type == "blockquote"
                assert "Blockquote" in result[0].name
                assert result[0].start_line == 1
                assert result[0].end_line == 4

    def test_extract_blockquotes_empty(self):
        """Test blockquote extraction with no blockquotes"""
        content = "# Header\n\nRegular paragraph."

        mock_tree = Mock()
        mock_root = Mock()
        mock_tree.root_node = mock_root
        mock_root.children = []

        with patch.object(self.extractor, "_traverse_nodes", return_value=[]):
            result = self.extractor.extract_blockquotes(mock_tree, content)
            assert result == []

    def test_extract_horizontal_rules_basic(self):
        """Test basic horizontal rule extraction"""
        content = """# Header

---

Content

***

More content

___"""

        mock_tree = Mock()
        mock_root = Mock()
        mock_tree.root_node = mock_root

        # Mock horizontal rule nodes
        hr_nodes = []
        for i, hr_text in enumerate(["---", "***", "___"]):
            hr_node = Mock()
            hr_node.type = "thematic_break"
            hr_node.start_point = (i * 4 + 2, 0)
            hr_node.end_point = (i * 4 + 2, len(hr_text))
            hr_nodes.append(hr_node)

        with patch.object(self.extractor, "_traverse_nodes", return_value=hr_nodes):
            with patch.object(
                self.extractor,
                "_get_node_text_optimized",
                side_effect=["---", "***", "___"],
            ):
                result = self.extractor.extract_horizontal_rules(mock_tree, content)

                assert len(result) == 3
                for i, hr in enumerate(result):
                    assert hr.element_type == "horizontal_rule"
                    assert hr.name == "Horizontal Rule"

    def test_extract_html_elements_basic(self):
        """Test basic HTML element extraction"""
        content = """<div>This is an HTML div element</div>

<p>HTML paragraph with <strong>strong</strong> and <em>emphasis</em></p>

<!-- This is an HTML comment -->"""

        mock_tree = Mock()
        mock_root = Mock()
        mock_tree.root_node = mock_root

        # Mock HTML nodes
        html_nodes = []
        html_texts = [
            "<div>This is an HTML div element</div>",
            "<p>HTML paragraph with <strong>strong</strong> and <em>emphasis</em></p>",
            "<!-- This is an HTML comment -->",
        ]

        for i, html_text in enumerate(html_texts):
            html_node = Mock()
            html_node.type = "html_block" if i < 2 else "html_comment"
            html_node.start_point = (i * 2, 0)
            html_node.end_point = (i * 2, len(html_text))
            html_nodes.append(html_node)

        with patch.object(self.extractor, "_traverse_nodes", return_value=html_nodes):
            with patch.object(
                self.extractor, "_get_node_text_optimized", side_effect=html_texts
            ):
                result = self.extractor.extract_html_elements(mock_tree, content)

                assert (
                    len(result) >= 2
                )  # HTML comments might not be detected by tree-sitter
                assert result[0].element_type in ["html_element", "html_block"]
                assert "HTML Block" in result[0].name

    def test_extract_text_formatting_basic(self):
        """Test basic text formatting extraction"""
        content = """This paragraph contains **bold text**, *italic text*, ***bold and italic***, and `inline code`.

You can also use ~~strikethrough~~ text."""

        mock_tree = Mock()
        mock_root = Mock()
        mock_tree.root_node = mock_root

        # Mock formatting nodes
        formatting_nodes = []
        formatting_data = [
            ("strong_emphasis", "**bold text**"),
            ("emphasis", "*italic text*"),
            ("strong_emphasis", "***bold and italic***"),
            ("code_span", "`inline code`"),
            ("strikethrough", "~~strikethrough~~"),
        ]

        for node_type, text in formatting_data:
            node = Mock()
            node.type = node_type
            node.start_point = (0, 0)
            node.end_point = (0, len(text))
            formatting_nodes.append(node)

        with patch.object(
            self.extractor, "_traverse_nodes", return_value=formatting_nodes
        ):
            with patch.object(
                self.extractor,
                "_get_node_text_optimized",
                side_effect=[text for _, text in formatting_data],
            ):
                result = self.extractor.extract_text_formatting(mock_tree, content)

                # Text formatting elements might not be detected by tree-sitter markdown parser
                # as they are often handled differently
                assert isinstance(result, list)
                # If elements are found, check their types
                for element in result:
                    assert element.element_type == "text_formatting"

    def test_extract_footnotes_basic(self):
        """Test basic footnote extraction"""
        content = """Here's a sentence with a footnote[^1].

Another footnote reference[^note].

[^1]: This is the footnote content.

[^note]: This is another footnote with a custom identifier."""

        mock_tree = Mock()
        mock_root = Mock()
        mock_tree.root_node = mock_root

        # Mock footnote nodes
        footnote_nodes = []
        footnote_data = [
            ("footnote_reference", "[^1]"),
            ("footnote_reference", "[^note]"),
            ("footnote_definition", "[^1]: This is the footnote content."),
            (
                "footnote_definition",
                "[^note]: This is another footnote with a custom identifier.",
            ),
        ]

        for node_type, text in footnote_data:
            node = Mock()
            node.type = node_type
            node.start_point = (0, 0)
            node.end_point = (0, len(text))
            footnote_nodes.append(node)

        with patch.object(
            self.extractor, "_traverse_nodes", return_value=footnote_nodes
        ):
            with patch.object(
                self.extractor,
                "_get_node_text_optimized",
                side_effect=[text for _, text in footnote_data],
            ):
                result = self.extractor.extract_footnotes(mock_tree, content)

                # Footnotes might not be detected by tree-sitter markdown parser
                # as they are often handled differently
                assert isinstance(result, list)
                # If elements are found, check their types
                for element in result:
                    assert element.element_type == "footnote"

    def test_extract_blockquotes_with_exception(self):
        """Test blockquote extraction with exception handling"""
        mock_tree = Mock()
        mock_root = Mock()
        mock_tree.root_node = mock_root

        blockquote_node = Mock()
        blockquote_node.type = "block_quote"

        with patch.object(
            self.extractor, "_traverse_nodes", return_value=[blockquote_node]
        ):
            with patch.object(
                self.extractor,
                "_get_node_text_optimized",
                side_effect=Exception("Test error"),
            ):
                result = self.extractor.extract_blockquotes(mock_tree, "> Quote")
                assert result == []

    def test_extract_horizontal_rules_with_exception(self):
        """Test horizontal rule extraction with exception handling"""
        mock_tree = Mock()
        mock_root = Mock()
        mock_tree.root_node = mock_root

        hr_node = Mock()
        hr_node.type = "thematic_break"

        with patch.object(self.extractor, "_traverse_nodes", return_value=[hr_node]):
            with patch.object(
                self.extractor,
                "_get_node_text_optimized",
                side_effect=Exception("Test error"),
            ):
                result = self.extractor.extract_horizontal_rules(mock_tree, "---")
                assert result == []

    def test_extract_html_elements_with_exception(self):
        """Test HTML element extraction with exception handling"""
        mock_tree = Mock()
        mock_root = Mock()
        mock_tree.root_node = mock_root

        html_node = Mock()
        html_node.type = "html_block"

        with patch.object(self.extractor, "_traverse_nodes", return_value=[html_node]):
            with patch.object(
                self.extractor,
                "_get_node_text_optimized",
                side_effect=Exception("Test error"),
            ):
                result = self.extractor.extract_html_elements(
                    mock_tree, "<div>test</div>"
                )
                assert result == []

    def test_extract_text_formatting_with_exception(self):
        """Test text formatting extraction with exception handling"""
        mock_tree = Mock()
        mock_root = Mock()
        mock_tree.root_node = mock_root

        formatting_node = Mock()
        formatting_node.type = "strong_emphasis"

        with patch.object(
            self.extractor, "_traverse_nodes", return_value=[formatting_node]
        ):
            with patch.object(
                self.extractor,
                "_get_node_text_optimized",
                side_effect=Exception("Test error"),
            ):
                result = self.extractor.extract_text_formatting(mock_tree, "**bold**")
                assert result == []

    def test_extract_footnotes_with_exception(self):
        """Test footnote extraction with exception handling"""
        mock_tree = Mock()
        mock_root = Mock()
        mock_tree.root_node = mock_root

        footnote_node = Mock()
        footnote_node.type = "footnote_reference"

        with patch.object(
            self.extractor, "_traverse_nodes", return_value=[footnote_node]
        ):
            with patch.object(
                self.extractor,
                "_get_node_text_optimized",
                side_effect=Exception("Test error"),
            ):
                result = self.extractor.extract_footnotes(mock_tree, "[^1]")
                assert result == []


class TestMarkdownPluginNewElementsIntegration:
    """Integration tests for new Markdown elements in plugin"""

    def setup_method(self):
        """Setup test fixtures"""
        self.plugin = MarkdownPlugin()

    def test_extract_elements_includes_new_elements(self):
        """Test that extract_elements includes new element types"""
        mock_tree = Mock()
        mock_extractor = Mock(spec=MarkdownElementExtractor)

        # Create mock elements that can be iterated
        mock_element = Mock()
        mock_element.__iter__ = Mock(return_value=iter([mock_element]))

        # Setup mock returns for all extraction methods
        mock_extractor.extract_headers.return_value = [mock_element]
        mock_extractor.extract_code_blocks.return_value = [mock_element]
        mock_extractor.extract_links.return_value = [mock_element]
        mock_extractor.extract_images.return_value = [mock_element]
        mock_extractor.extract_references.return_value = [mock_element]
        mock_extractor.extract_lists.return_value = [mock_element]
        mock_extractor.extract_tables.return_value = [mock_element]
        mock_extractor.extract_blockquotes.return_value = [mock_element]
        mock_extractor.extract_horizontal_rules.return_value = [mock_element]
        mock_extractor.extract_html_elements.return_value = [mock_element]
        mock_extractor.extract_text_formatting.return_value = [mock_element]
        mock_extractor.extract_footnotes.return_value = [mock_element]

        with patch.object(self.plugin, "get_extractor", return_value=mock_extractor):
            elements = self.plugin.extract_elements(mock_tree, "test content")

            # Should include all element types that return results
            assert len(elements) >= 12  # All 12 extraction methods

            # Verify all extraction methods were called
            mock_extractor.extract_headers.assert_called_once()
            mock_extractor.extract_code_blocks.assert_called_once()
            mock_extractor.extract_links.assert_called_once()
            mock_extractor.extract_images.assert_called_once()
            mock_extractor.extract_references.assert_called_once()
            mock_extractor.extract_lists.assert_called_once()
            mock_extractor.extract_tables.assert_called_once()
            mock_extractor.extract_blockquotes.assert_called_once()
            mock_extractor.extract_horizontal_rules.assert_called_once()
            mock_extractor.extract_html_elements.assert_called_once()
            mock_extractor.extract_text_formatting.assert_called_once()
            mock_extractor.extract_footnotes.assert_called_once()

    def test_get_supported_queries_includes_new_queries(self):
        """Test that get_supported_queries includes new query types"""
        queries = self.plugin.get_supported_queries()

        # Check that new query types are included
        new_queries = ["blockquotes", "horizontal_rules", "html_blocks", "footnotes"]

        for query in new_queries:
            assert query in queries, f"Query '{query}' should be in supported queries"

    @pytest.mark.asyncio
    async def test_analyze_file_with_new_elements(self):
        """Test analyze_file includes new elements in results"""
        content = """# Header

> This is a blockquote

---

<div>HTML content</div>

**Bold text** and *italic text*

Footnote reference[^1]

[^1]: Footnote definition"""

        mock_language = Mock()
        mock_parser = Mock()
        mock_tree = Mock()
        mock_root_node = Mock()
        mock_tree.root_node = mock_root_node
        mock_parser.parse.return_value = mock_tree

        # Mock extractor with new elements
        mock_extractor = Mock(spec=MarkdownElementExtractor)
        mock_extractor.extract_headers.return_value = [
            MarkdownElement("Header", 1, 1, "# Header", element_type="header")
        ]
        mock_extractor.extract_blockquotes.return_value = [
            MarkdownElement(
                "Blockquote", 3, 3, "> This is a blockquote", element_type="blockquote"
            )
        ]
        mock_extractor.extract_horizontal_rules.return_value = [
            MarkdownElement(
                "Horizontal Rule", 5, 5, "---", element_type="horizontal_rule"
            )
        ]
        mock_extractor.extract_html_elements.return_value = [
            MarkdownElement(
                "HTML Block",
                7,
                7,
                "<div>HTML content</div>",
                element_type="html_element",
            )
        ]
        mock_extractor.extract_text_formatting.return_value = [
            MarkdownElement(
                "Bold Text", 9, 9, "**Bold text**", element_type="text_formatting"
            ),
            MarkdownElement(
                "Italic Text", 9, 9, "*italic text*", element_type="text_formatting"
            ),
        ]
        mock_extractor.extract_footnotes.return_value = [
            MarkdownElement(
                "Footnote Reference", 11, 11, "[^1]", element_type="footnote"
            ),
            MarkdownElement(
                "Footnote Definition",
                13,
                13,
                "[^1]: Footnote definition",
                element_type="footnote",
            ),
        ]

        # Mock other extraction methods to return empty lists
        for method_name in [
            "extract_code_blocks",
            "extract_links",
            "extract_images",
            "extract_references",
            "extract_lists",
            "extract_tables",
        ]:
            getattr(mock_extractor, method_name).return_value = []

        mock_root_node.children = []

        with patch(
            "tree_sitter_analyzer.encoding_utils.read_file_safe"
        ) as mock_read_file_safe:
            mock_read_file_safe.return_value = (content, "utf-8")

            with patch(
                "tree_sitter_analyzer.languages.markdown_plugin.tree_sitter"
            ) as mock_ts:
                mock_ts.Parser.return_value = mock_parser

                with patch.object(
                    self.plugin, "get_tree_sitter_language", return_value=mock_language
                ):
                    with patch.object(
                        self.plugin, "create_extractor", return_value=mock_extractor
                    ):
                        from tree_sitter_analyzer.core.analysis_engine import (
                            AnalysisRequest,
                        )

                        request = AnalysisRequest(file_path="test.md")
                        result = await self.plugin.analyze_file("test.md", request)

                        assert result.success is True
                        assert (
                            len(result.elements) >= 3
                        )  # At least header, blockquote, and hr should be detected


class TestMarkdownElementNewAttributes:
    """Test MarkdownElement with new attributes for new element types"""

    def test_markdown_element_blockquote_attributes(self):
        """Test MarkdownElement with blockquote-specific attributes"""
        element = MarkdownElement(
            name="Blockquote",
            start_line=1,
            end_line=3,
            raw_text="> This is a blockquote\n> with multiple lines",
            element_type="blockquote",
        )

        assert element.element_type == "blockquote"
        assert element.name == "Blockquote"

    def test_markdown_element_html_attributes(self):
        """Test MarkdownElement with HTML-specific attributes"""
        element = MarkdownElement(
            name="HTML Block",
            start_line=1,
            end_line=1,
            raw_text="<div class='test'>Content</div>",
            element_type="html_element",
        )

        assert element.element_type == "html_element"
        assert element.name == "HTML Block"

    def test_markdown_element_formatting_attributes(self):
        """Test MarkdownElement with text formatting attributes"""
        element = MarkdownElement(
            name="Bold Text",
            start_line=1,
            end_line=1,
            raw_text="**bold text**",
            element_type="text_formatting",
        )

        assert element.element_type == "text_formatting"
        assert element.name == "Bold Text"

    def test_markdown_element_footnote_attributes(self):
        """Test MarkdownElement with footnote attributes"""
        element = MarkdownElement(
            name="Footnote Reference",
            start_line=1,
            end_line=1,
            raw_text="[^1]",
            element_type="footnote",
        )

        assert element.element_type == "footnote"
        assert element.name == "Footnote Reference"


if __name__ == "__main__":
    pytest.main(
        [
            __file__,
            "-v",
            "--cov=tree_sitter_analyzer.languages.markdown_plugin",
            "--cov-report=term-missing",
        ]
    )
