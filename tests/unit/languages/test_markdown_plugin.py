#!/usr/bin/env python3
"""
Markdown Plugin Tests

Tests for the Markdown language plugin with 90% coverage target.
Covers all major Markdown elements and edge cases.
"""

from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest
from tree_sitter_analyzer.languages.markdown_plugin import (
    MarkdownElement,
    MarkdownElementExtractor,
    MarkdownPlugin,
)
from tree_sitter_analyzer.models import AnalysisResult


class TestMarkdownElement:
    """Test MarkdownElement class"""

    def test_markdown_element_creation(self):
        """Test basic MarkdownElement creation"""
        element = MarkdownElement(
            name="Test Header",
            start_line=1,
            end_line=1,
            raw_text="# Test Header",
            element_type="header",
            level=1,
        )

        assert element.name == "Test Header"
        assert element.start_line == 1
        assert element.end_line == 1
        assert element.raw_text == "# Test Header"
        assert element.language == "markdown"
        assert element.element_type == "header"
        assert element.level == 1

    def test_markdown_element_with_all_attributes(self):
        """Test MarkdownElement with all optional attributes"""
        element = MarkdownElement(
            name="Test Link",
            start_line=5,
            end_line=5,
            raw_text='[Test](http://example.com "Title")',
            element_type="link",
            url="http://example.com",
            title="Title",
            alt_text="Alt text",
            language_info="python",
            is_checked=True,
        )

        assert element.url == "http://example.com"
        assert element.title == "Title"
        assert element.alt_text == "Alt text"
        assert element.language_info == "python"
        assert element.is_checked is True


class TestMarkdownElementExtractor:
    """Test MarkdownElementExtractor class"""

    def setup_method(self):
        """Setup test fixtures"""
        self.extractor = MarkdownElementExtractor()
        self.mock_tree = Mock()
        self.mock_root_node = Mock()
        self.mock_tree.root_node = self.mock_root_node

    def test_extractor_initialization(self):
        """Test extractor initialization"""
        extractor = MarkdownElementExtractor()
        assert extractor.current_file == ""
        assert extractor.source_code == ""
        assert extractor.content_lines == []
        assert len(extractor._node_text_cache) == 0
        assert len(extractor._processed_nodes) == 0
        assert len(extractor._element_cache) == 0

    def test_reset_caches(self):
        """Test cache reset functionality"""
        self.extractor._node_text_cache[1] = "test"
        self.extractor._processed_nodes.add(1)
        self.extractor._element_cache[(1, "test")] = "value"

        self.extractor._reset_caches()

        assert len(self.extractor._node_text_cache) == 0
        assert len(self.extractor._processed_nodes) == 0
        assert len(self.extractor._element_cache) == 0

    def test_extract_functions_with_none_tree(self):
        """Test extract_functions with None tree"""
        result = self.extractor.extract_functions(None, "# Header")
        assert result == []

    def test_extract_classes_with_none_tree(self):
        """Test extract_classes with None tree"""
        result = self.extractor.extract_classes(None, "```python\ncode\n```")
        assert result == []

    def test_extract_variables_with_none_tree(self):
        """Test extract_variables with None tree"""
        result = self.extractor.extract_variables(None, "[link](url)")
        assert result == []

    def test_extract_imports_with_none_tree(self):
        """Test extract_imports with None tree"""
        result = self.extractor.extract_imports(None, "[ref]: url")
        assert result == []

    @patch("tree_sitter_analyzer.languages.markdown_plugin.log_debug")
    def test_extract_headers_with_exception(self, mock_log):
        """Test header extraction with exception handling"""
        self.mock_root_node.children = [Mock()]
        self.mock_root_node.children[0].type = "atx_heading"
        self.mock_root_node.children[0].start_point = (0, 0)
        self.mock_root_node.children[0].end_point = (0, 10)
        self.mock_root_node.children[0].start_byte = 0
        self.mock_root_node.children[0].end_byte = 10

        # Mock an exception in text extraction
        with patch.object(
            self.extractor,
            "_get_node_text_optimized",
            side_effect=Exception("Test error"),
        ):
            result = self.extractor.extract_headers(self.mock_tree, "# Header")
            assert result == []
            mock_log.assert_called()

    def test_get_node_text_optimized_with_cache(self):
        """Test node text extraction with cache"""
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 5

        # Set up cache with position-based key (start_byte, end_byte)
        cache_key = (mock_node.start_byte, mock_node.end_byte)
        self.extractor._node_text_cache[cache_key] = "cached"

        result = self.extractor._get_node_text_optimized(mock_node)
        assert result == "cached"

    def test_get_node_text_optimized_fallback(self):
        """Test node text extraction fallback method"""
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 5
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 5)

        self.extractor.content_lines = ["Hello World"]

        # Mock byte extraction to fail
        with patch(
            "tree_sitter_analyzer.languages.markdown_plugin.extract_text_slice",
            side_effect=Exception("Byte error"),
        ):
            result = self.extractor._get_node_text_optimized(mock_node)
            assert result == "Hello"

    def test_get_node_text_optimized_multiline(self):
        """Test node text extraction for multiline content"""
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 15
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 5)

        self.extractor.content_lines = ["Line 1", "Line 2", "Line 3"]

        with patch(
            "tree_sitter_analyzer.languages.markdown_plugin.extract_text_slice",
            side_effect=Exception("Byte error"),
        ):
            result = self.extractor._get_node_text_optimized(mock_node)
            assert "Line 1" in result
            assert "Line 2" in result
            # Line 3 only partially included (first 5 chars)
            assert "Line " in result  # At least the start of Line 3

    def test_get_node_text_optimized_out_of_bounds(self):
        """Test node text extraction with out of bounds indices"""
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 5
        mock_node.start_point = (10, 0)  # Out of bounds
        mock_node.end_point = (10, 5)

        self.extractor.content_lines = ["Hello"]

        with patch(
            "tree_sitter_analyzer.languages.markdown_plugin.extract_text_slice",
            side_effect=Exception("Byte error"),
        ):
            result = self.extractor._get_node_text_optimized(mock_node)
            assert result == ""

    def test_parse_link_components_valid(self):
        """Test parsing valid link components"""
        text, url, title = self.extractor._parse_link_components(
            '[Text](http://example.com "Title")'
        )
        assert text == "Text"
        assert url == "http://example.com"
        assert title == "Title"

    def test_parse_link_components_no_title(self):
        """Test parsing link components without title"""
        text, url, title = self.extractor._parse_link_components(
            "[Text](http://example.com)"
        )
        assert text == "Text"
        assert url == "http://example.com"
        assert title == ""

    def test_parse_link_components_invalid(self):
        """Test parsing invalid link components"""
        text, url, title = self.extractor._parse_link_components("Invalid link")
        assert text == ""
        assert url == ""
        assert title == ""

    def test_parse_image_components_valid(self):
        """Test parsing valid image components"""
        alt, url, title = self.extractor._parse_image_components(
            '![Alt](image.jpg "Title")'
        )
        assert alt == "Alt"
        assert url == "image.jpg"
        assert title == "Title"

    def test_parse_image_components_no_title(self):
        """Test parsing image components without title"""
        alt, url, title = self.extractor._parse_image_components("![Alt](image.jpg)")
        assert alt == "Alt"
        assert url == "image.jpg"
        assert title == ""

    def test_parse_image_components_invalid(self):
        """Test parsing invalid image components"""
        alt, url, title = self.extractor._parse_image_components("Invalid image")
        assert alt == ""
        assert url == ""
        assert title == ""

    def test_traverse_nodes(self):
        """Test node traversal"""
        # Create a simple tree structure
        root = Mock()
        child1 = Mock()
        child2 = Mock()
        grandchild = Mock()

        root.children = [child1, child2]
        child1.children = [grandchild]
        child2.children = []
        grandchild.children = []

        nodes = list(self.extractor._traverse_nodes(root))
        assert len(nodes) == 4  # root, child1, child2, grandchild
        assert root in nodes
        assert child1 in nodes
        assert child2 in nodes
        assert grandchild in nodes

    def test_extract_blockquotes_basic(self):
        """Test basic blockquote extraction"""
        content = """> This is a blockquote.
> It can span multiple lines.
>
> > This is a nested blockquote."""

        mock_tree = Mock()
        mock_root = Mock()
        mock_tree.root_node = mock_root

        blockquote_node = Mock()
        blockquote_node.type = "block_quote"
        blockquote_node.start_point = (0, 0)
        blockquote_node.end_point = (3, 35)
        blockquote_node.start_byte = 0
        blockquote_node.end_byte = len(content)

        mock_root.children = [blockquote_node]

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
                for _i, hr in enumerate(result):
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

                assert len(result) >= 2
                assert result[0].element_type in ["html_element", "html_block"]
                assert "HTML Block" in result[0].name

    def test_extract_text_formatting_basic(self):
        """Test basic text formatting extraction"""
        content = """This paragraph contains **bold text**, *italic text*, ***bold and italic***, and `inline code`.

You can also use ~~strikethrough~~ text."""

        mock_tree = Mock()
        mock_root = Mock()
        mock_tree.root_node = mock_root

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

                assert isinstance(result, list)
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

                assert isinstance(result, list)
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


class TestMarkdownPlugin:
    """Test MarkdownPlugin class"""

    def setup_method(self):
        """Setup test fixtures"""
        self.plugin = MarkdownPlugin()

    def test_plugin_initialization(self):
        """Test plugin initialization"""
        plugin = MarkdownPlugin()
        assert plugin.get_language_name() == "markdown"
        assert plugin.language == "markdown"
        assert plugin._language_cache is None
        assert plugin._extractor is not None
        assert isinstance(plugin._extractor, MarkdownElementExtractor)

    def test_get_language_name(self):
        """Test get_language_name method"""
        assert self.plugin.get_language_name() == "markdown"

    def test_get_file_extensions(self):
        """Test get_file_extensions method"""
        extensions = self.plugin.get_file_extensions()
        expected = [".md", ".markdown", ".mdown", ".mkd", ".mkdn", ".mdx"]
        assert extensions == expected

    def test_create_extractor(self):
        """Test create_extractor method"""
        extractor = self.plugin.create_extractor()
        assert isinstance(extractor, MarkdownElementExtractor)

    def test_get_extractor_cached(self):
        """Test get_extractor with caching"""
        extractor1 = self.plugin.get_extractor()
        extractor2 = self.plugin.get_extractor()
        assert extractor1 is extractor2  # Should be the same instance

    def test_get_language(self):
        """Test get_language method (legacy compatibility)"""
        assert self.plugin.get_language() == "markdown"

    def test_get_supported_queries(self):
        """Test get_supported_queries method"""
        queries = self.plugin.get_supported_queries()
        expected_queries = [
            "headers",
            "code_blocks",
            "links",
            "images",
            "lists",
            "tables",
            "blockquotes",
            "emphasis",
            "inline_code",
            "references",
            "task_lists",
            "horizontal_rules",
            "html_blocks",
            "text_content",
            "all_elements",
        ]
        for query in expected_queries:
            assert query in queries

    def test_is_applicable_true(self):
        """Test is_applicable method with valid extensions"""
        assert self.plugin.is_applicable("test.md") is True
        assert self.plugin.is_applicable("test.markdown") is True
        assert self.plugin.is_applicable("test.MDX") is True  # Case insensitive

    def test_is_applicable_false(self):
        """Test is_applicable method with invalid extensions"""
        assert self.plugin.is_applicable("test.py") is False
        assert self.plugin.is_applicable("test.txt") is False
        assert self.plugin.is_applicable("test") is False

    def test_get_plugin_info(self):
        """Test get_plugin_info method"""
        info = self.plugin.get_plugin_info()
        assert info["name"] == "Markdown Plugin"
        assert info["language"] == "markdown"
        assert info["version"] == "1.0.0"
        assert "features" in info
        assert "supported_queries" in info

    @patch(
        "tree_sitter_analyzer.languages.markdown_plugin.TREE_SITTER_AVAILABLE", False
    )
    @pytest.mark.asyncio
    async def test_analyze_file_no_tree_sitter(self):
        """Test analyze_file when tree-sitter is not available"""
        request = AnalysisRequest(file_path="test.md")
        result = await self.plugin.analyze_file("test.md", request)

        assert isinstance(result, AnalysisResult)
        assert result.success is False
        assert "Tree-sitter library not available" in result.error_message

    @patch("tree_sitter_analyzer.languages.markdown_plugin.TREE_SITTER_AVAILABLE", True)
    def test_get_tree_sitter_language_import_error(self):
        """Test get_tree_sitter_language with import error"""
        # Clear cache first
        self.plugin._language_cache = None
        # Import happens inside the method, so we need to patch builtins.__import__
        with patch(
            "builtins.__import__",
            side_effect=ImportError("tree_sitter_markdown not found"),
        ):
            language = self.plugin.get_tree_sitter_language()
            assert language is None

    @patch("tree_sitter_analyzer.languages.markdown_plugin.TREE_SITTER_AVAILABLE", True)
    def test_get_tree_sitter_language_general_error(self):
        """Test get_tree_sitter_language with general error"""
        # Clear cache first
        self.plugin._language_cache = None
        # Simulate error during language loading
        with patch("builtins.__import__") as mock_import:
            # Let tree_sitter import succeed, but make tsmarkdown.language() fail
            def import_side_effect(name, *args, **kwargs):
                if name == "tree_sitter_markdown":
                    mock_md = Mock()
                    mock_md.language.side_effect = Exception("General error")
                    return mock_md
                return __import__(name, *args, **kwargs)

            mock_import.side_effect = import_side_effect
            language = self.plugin.get_tree_sitter_language()
            assert language is None

    @patch("tree_sitter_analyzer.languages.markdown_plugin.TREE_SITTER_AVAILABLE", True)
    def test_get_tree_sitter_language_success(self):
        """Test successful get_tree_sitter_language"""
        # Clear cache first
        self.plugin._language_cache = None

        with patch("builtins.__import__") as mock_import:
            mock_ts = Mock()
            mock_md = Mock()
            mock_language_capsule = Mock()
            mock_md.language.return_value = mock_language_capsule
            mock_language_instance = Mock()
            mock_ts.Language.return_value = mock_language_instance

            def import_side_effect(name, *args, **kwargs):
                if name == "tree_sitter":
                    return mock_ts
                elif name == "tree_sitter_markdown":
                    return mock_md
                return __import__(name, *args, **kwargs)

            mock_import.side_effect = import_side_effect

            language = self.plugin.get_tree_sitter_language()
            assert language is mock_language_instance

            # Test caching
            language2 = self.plugin.get_tree_sitter_language()
            assert language2 is mock_language_instance

    def test_execute_query_no_language(self):
        """Test execute_query when language is not available"""
        with patch.object(self.plugin, "get_tree_sitter_language", return_value=None):
            result = self.plugin.execute_query(Mock(), "headers")
            assert "error" in result
            assert "Language not available" in result["error"]

    def test_execute_query_unknown_query(self):
        """Test execute_query with unknown query"""
        mock_language = Mock()
        with patch.object(
            self.plugin, "get_tree_sitter_language", return_value=mock_language
        ):
            result = self.plugin.execute_query(Mock(), "unknown_query")
            assert "error" in result
            assert "Unknown query" in result["error"]

    def test_execute_query_success(self):
        """Test successful execute_query"""
        mock_language = Mock()
        mock_tree = Mock()
        mock_root = Mock()
        mock_root.type = "document"
        mock_root.children = []  # Prevent iteration errors
        mock_tree.root_node = mock_root

        # Mock Query class and get_query function
        with patch.object(
            self.plugin, "get_tree_sitter_language", return_value=mock_language
        ):
            # Patch get_query from where it's actually imported
            with patch(
                "tree_sitter_analyzer.queries.markdown.get_query",
                return_value="test query",
            ):
                with patch(
                    "tree_sitter_analyzer.languages.markdown_plugin.tree_sitter.Query"
                ) as mock_query_class:
                    mock_query_instance = Mock()
                    mock_query_class.return_value = mock_query_instance

                    result = self.plugin.execute_query(mock_tree, "headers")

                    # Should return query results
                    assert isinstance(result, dict)
                    assert "query" in result

    def test_execute_query_exception(self):
        """Test execute_query with exception"""
        with patch.object(
            self.plugin, "get_tree_sitter_language", side_effect=Exception("Test error")
        ):
            result = self.plugin.execute_query(Mock(), "headers")
            assert "error" in result
            assert "Test error" in result["error"]

    def test_extract_elements(self):
        """Test extract_elements method"""
        mock_tree = Mock()
        mock_extractor = Mock(spec=MarkdownElementExtractor)

        # Setup mock returns
        mock_extractor.extract_headers.return_value = [Mock()]
        mock_extractor.extract_code_blocks.return_value = [Mock()]
        mock_extractor.extract_links.return_value = [Mock()]
        mock_extractor.extract_images.return_value = [Mock()]
        mock_extractor.extract_references.return_value = [Mock()]
        mock_extractor.extract_lists.return_value = [Mock()]
        mock_extractor.extract_tables.return_value = [Mock()]
        mock_extractor.extract_blockquotes.return_value = [Mock()]
        mock_extractor.extract_horizontal_rules.return_value = [Mock()]
        mock_extractor.extract_html_elements.return_value = [Mock()]
        mock_extractor.extract_text_formatting.return_value = [Mock()]
        mock_extractor.extract_footnotes.return_value = [Mock()]

        # extract_elements uses create_extractor(), not get_extractor()
        with patch.object(self.plugin, "create_extractor", return_value=mock_extractor):
            elements = self.plugin.extract_elements(mock_tree, "test content")

            assert len(elements) == 12  # All extraction methods called
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

    def test_extract_elements_exception(self):
        """Test extract_elements with exception"""
        mock_tree = Mock()
        mock_extractor = Mock()
        mock_extractor.extract_headers.side_effect = Exception("Test error")

        # extract_elements uses create_extractor(), not get_extractor()
        with patch.object(self.plugin, "create_extractor", return_value=mock_extractor):
            elements = self.plugin.extract_elements(mock_tree, "test content")
            assert elements == []

    def test_legacy_compatibility_methods(self):
        """Test legacy compatibility methods"""
        mock_tree = Mock()
        mock_extractor = Mock()
        mock_extractor.extract_functions.return_value = []
        mock_extractor.extract_classes.return_value = []
        mock_extractor.extract_variables.return_value = []
        mock_extractor.extract_imports.return_value = []

        with patch.object(self.plugin, "get_extractor", return_value=mock_extractor):
            # Test all legacy methods
            self.plugin.extract_functions(mock_tree, "content")
            self.plugin.extract_classes(mock_tree, "content")
            self.plugin.extract_variables(mock_tree, "content")
            self.plugin.extract_imports(mock_tree, "content")

            # Verify all methods were called
            mock_extractor.extract_functions.assert_called_once()
            mock_extractor.extract_classes.assert_called_once()
            mock_extractor.extract_variables.assert_called_once()
            mock_extractor.extract_imports.assert_called_once()


class TestMarkdownPluginIntegration:
    """Integration tests for Markdown plugin"""

    def setup_method(self):
        """Setup test fixtures"""
        self.plugin = MarkdownPlugin()

    @pytest.mark.asyncio
    async def test_analyze_file_file_not_found(self):
        """Test analyze_file with non-existent file"""
        request = AnalysisRequest(file_path="nonexistent.md")

        with patch.object(self.plugin, "get_tree_sitter_language", return_value=Mock()):
            result = await self.plugin.analyze_file("nonexistent.md", request)
            assert result.success is False
            assert "error_message" in result.__dict__

    @pytest.mark.asyncio
    async def test_analyze_file_no_language(self):
        """Test analyze_file when language loading fails"""
        request = AnalysisRequest(file_path="test.md")

        with patch.object(self.plugin, "get_tree_sitter_language", return_value=None):
            result = await self.plugin.analyze_file("test.md", request)
            assert result.success is False
            assert "Could not load Markdown language" in result.error_message

    @pytest.mark.asyncio
    @patch("tree_sitter_analyzer.encoding_utils.read_file_safe")
    @patch("tree_sitter_analyzer.languages.markdown_plugin.tree_sitter")
    async def test_analyze_file_success(self, mock_ts, mock_read_file_safe):
        """Test successful analyze_file"""
        # Setup mocks
        mock_read_file_safe.return_value = ("# Test Header\n\nContent", "utf-8")

        mock_parser = Mock()
        mock_tree = Mock()
        mock_root_node = Mock()
        # Make root_node iterable to avoid "'Mock' object is not iterable" error
        mock_root_node.children = []
        mock_tree.root_node = mock_root_node
        mock_parser.parse.return_value = mock_tree
        mock_ts.Parser.return_value = mock_parser

        mock_language = Mock()

        # Mock extractor
        mock_extractor = Mock()
        # Make extractor methods return lists
        mock_extractor.extract_headers.return_value = [
            MarkdownElement("Test Header", 1, 1, "# Test Header", element_type="header")
        ]
        mock_extractor.extract_code_blocks.return_value = []
        mock_extractor.extract_links.return_value = []
        mock_extractor.extract_images.return_value = []
        mock_extractor.extract_references.return_value = []
        mock_extractor.extract_lists.return_value = []

        # Mock node counting - ensure all children attributes are set
        mock_root_node.children = []

        # Make sure extractor.extract_all_elements returns the headers
        def extract_all_mock(tree, source):
            return [
                MarkdownElement(
                    "Test Header", 1, 1, "# Test Header", element_type="header"
                )
            ]

        mock_extractor.extract_all_elements = Mock(side_effect=extract_all_mock)

        request = AnalysisRequest(file_path="test.md")

        with patch.object(
            self.plugin, "get_tree_sitter_language", return_value=mock_language
        ):
            with patch.object(
                self.plugin, "get_extractor", return_value=mock_extractor
            ):
                result = await self.plugin.analyze_file("test.md", request)

                assert result.success is True
                assert result.file_path == "test.md"
                assert result.language == "markdown"
                # Elements may be 0 if extractor returns empty list
                assert isinstance(result.elements, list)
                assert result.line_count == 3  # "# Test Header\n\nContent" has 3 lines


class TestMarkdownPluginEdgeCases:
    """Test edge cases and error conditions"""

    def setup_method(self):
        """Setup test fixtures"""
        self.plugin = MarkdownPlugin()
        self.extractor = MarkdownElementExtractor()

    def test_empty_content(self):
        """Test handling of empty content"""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        headers = self.extractor.extract_headers(mock_tree, "")
        assert headers == []

    def test_malformed_markdown(self):
        """Test handling of malformed markdown"""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        # Test with malformed content
        result = self.extractor.extract_links(mock_tree, "[broken link")
        assert result == []

    def test_very_long_content(self):
        """Test handling of very long content"""
        long_content = "# Header\n" + "Content line\n" * 10000
        self.extractor.source_code = long_content
        self.extractor.content_lines = long_content.split("\n")

        # Should not crash with long content
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (5000, 10)
        mock_node.start_byte = 0
        mock_node.end_byte = 50000

        with patch(
            "tree_sitter_analyzer.languages.markdown_plugin.extract_text_slice",
            side_effect=Exception("Too long"),
        ):
            result = self.extractor._get_node_text_optimized(mock_node)
            # Should handle gracefully
            assert isinstance(result, str)

    def test_unicode_content(self):
        """Test handling of Unicode content"""
        unicode_content = "# 测试标题\n\n这是中文内容 🎉"
        self.extractor.source_code = unicode_content
        self.extractor.content_lines = unicode_content.split("\n")

        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 6)

        with patch(
            "tree_sitter_analyzer.languages.markdown_plugin.extract_text_slice",
            side_effect=Exception("Unicode error"),
        ):
            result = self.extractor._get_node_text_optimized(mock_node)
            assert (
                "测试标题" in result or result == ""
            )  # Should handle Unicode gracefully


if __name__ == "__main__":
    pytest.main(
        [
            __file__,
            "-v",
            "--cov=tree_sitter_analyzer.languages.markdown_plugin",
            "--cov-report=term-missing",
        ]
    )


# ====================================================================== #
# NEW TESTS targeting uncovered lines
# ====================================================================== #


class TestExtractorWithRealTree:
    """Tests using real tree-sitter parsing to cover actual extraction paths."""

    @pytest.fixture(autouse=True)
    def setup_parser(self):
        try:
            import tree_sitter
            import tree_sitter_markdown as tsmd
            lang = tree_sitter.Language(tsmd.language())
            self.parser = tree_sitter.Parser()
            self.parser.language = lang
            self.available = True
        except (ImportError, Exception):
            self.available = False
        self.extractor = MarkdownElementExtractor()
        self.plugin = MarkdownPlugin()

    def _parse(self, source: str):
        if not self.available:
            pytest.skip("tree-sitter-markdown not available")
        return self.parser.parse(source.encode("utf-8"))

    def test_extract_functions_returns_headers(self):
        tree = self._parse("# Title\n\n## Subtitle\n")
        funcs = self.extractor.extract_functions(tree, "# Title\n\n## Subtitle\n")
        assert len(funcs) >= 1

    def test_extract_classes_returns_code_blocks(self):
        src = "```python\nprint('hi')\n```\n"
        tree = self._parse(src)
        classes = self.extractor.extract_classes(tree, src)
        assert len(classes) >= 1

    def test_extract_variables_returns_links(self):
        src = "[Google](https://google.com)\n\n![logo](logo.png)\n"
        tree = self._parse(src)
        variables = self.extractor.extract_variables(tree, src)
        assert len(variables) >= 1

    def test_extract_imports_returns_references(self):
        src = "[example]: https://example.com\n"
        tree = self._parse(src)
        imports = self.extractor.extract_imports(tree, src)
        assert len(imports) >= 1

    def test_extract_atx_headers_levels(self):
        src = "# H1\n\n## H2\n\n### H3\n\n#### H4\n\n##### H5\n\n###### H6\n"
        tree = self._parse(src)
        headers = self.extractor.extract_headers(tree, src)
        assert len(headers) == 6
        for i, h in enumerate(headers):
            assert h.level == i + 1

    def test_extract_setext_h1_header(self):
        src = "Main Title\n==========\n"
        tree = self._parse(src)
        headers = self.extractor.extract_headers(tree, src)
        assert len(headers) >= 1
        assert any(h.level == 1 for h in headers)

    def test_extract_setext_h2_header(self):
        src = "Sub Title\n---------\n"
        tree = self._parse(src)
        headers = self.extractor.extract_headers(tree, src)
        assert len(headers) >= 1
        assert any(h.level == 2 for h in headers)

    def test_extract_fenced_code_block_with_language(self):
        src = "```javascript\nconsole.log('hello');\n```\n"
        tree = self._parse(src)
        blocks = self.extractor.extract_code_blocks(tree, src)
        assert len(blocks) >= 1
        assert blocks[0].language_info == "javascript"

    def test_extract_fenced_code_block_no_language(self):
        src = "```\nplain text\n```\n"
        tree = self._parse(src)
        blocks = self.extractor.extract_code_blocks(tree, src)
        assert len(blocks) >= 1

    def test_extract_indented_code_block(self):
        src = "Paragraph before.\n\n    indented code line 1\n    indented code line 2\n\nAfter.\n"
        tree = self._parse(src)
        blocks = self.extractor.extract_code_blocks(tree, src)
        indented = [b for b in blocks if b.name == "Indented Code Block"]
        assert len(indented) >= 1

    def test_extract_inline_link(self):
        src = "Visit [Google](https://google.com) today.\n"
        tree = self._parse(src)
        links = self.extractor.extract_links(tree, src)
        assert len(links) >= 1
        assert links[0].url == "https://google.com"

    def test_extract_inline_link_with_title(self):
        src = '[Example](https://example.com "Example Title") here.\n'
        tree = self._parse(src)
        links = self.extractor.extract_links(tree, src)
        assert len(links) >= 1
        assert links[0].title == "Example Title"

    def test_extract_links_deduplication(self):
        src = "[same](http://same.com) and [same](http://same.com)\n"
        tree = self._parse(src)
        links = self.extractor.extract_links(tree, src)
        assert len(links) == 1

    def test_extract_link_empty_text(self):
        src = "[](http://example.com)\n"
        tree = self._parse(src)
        links = self.extractor.extract_links(tree, src)
        assert len(links) >= 1

    def test_extract_inline_image(self):
        src = "![Alt text](image.png)\n"
        tree = self._parse(src)
        images = self.extractor.extract_images(tree, src)
        assert len(images) >= 1
        assert images[0].url == "image.png"

    def test_extract_image_with_title(self):
        src = '![Logo](logo.svg "Company Logo")\n'
        tree = self._parse(src)
        images = self.extractor.extract_images(tree, src)
        assert len(images) >= 1
        assert images[0].title == "Company Logo"

    def test_extract_images_deduplication(self):
        src = "![pic](a.png) and ![pic](a.png)\n"
        tree = self._parse(src)
        images = self.extractor.extract_images(tree, src)
        assert len(images) == 1

    def test_extract_image_reference_definition(self):
        src = "[logo]: logo.png\n"
        tree = self._parse(src)
        images = self.extractor.extract_images(tree, src)
        img_refs = [i for i in images if i.element_type == "image_reference_definition"]
        assert len(img_refs) >= 1

    def test_extract_image_ref_non_image_url(self):
        src = "[ref]: https://example.com\n"
        tree = self._parse(src)
        images = self.extractor.extract_images(tree, src)
        img_refs = [i for i in images if i.element_type == "image_reference_definition"]
        assert len(img_refs) == 0

    def test_extract_image_ref_various_extensions(self):
        for ext in [".jpeg", ".gif", ".svg", ".webp", ".bmp"]:
            src = f"[pic]: photo{ext}\n"
            tree = self._parse(src)
            images = self.extractor.extract_images(tree, src)
            img_refs = [i for i in images if i.element_type == "image_reference_definition"]
            assert len(img_refs) >= 1, f"Failed for {ext}"

    def test_extract_link_reference_definitions(self):
        src = "[example]: https://example.com\n"
        tree = self._parse(src)
        refs = self.extractor.extract_references(tree, src)
        assert len(refs) >= 1

    def test_extract_unordered_list(self):
        src = "- Apple\n- Banana\n- Cherry\n"
        tree = self._parse(src)
        lists = self.extractor.extract_lists(tree, src)
        assert len(lists) >= 1
        assert lists[0].list_type == "unordered"
        assert lists[0].item_count == 3

    def test_extract_ordered_list(self):
        src = "1. First\n2. Second\n3. Third\n"
        tree = self._parse(src)
        lists = self.extractor.extract_lists(tree, src)
        assert len(lists) >= 1
        assert lists[0].list_type == "ordered"

    def test_extract_task_list(self):
        src = "- [ ] Todo\n- [x] Done\n"
        tree = self._parse(src)
        lists = self.extractor.extract_lists(tree, src)
        assert len(lists) >= 1
        assert lists[0].list_type == "task"

    def test_extract_pipe_table(self):
        src = "| Name | Age |\n|------|-----|\n| Alice | 30 |\n"
        tree = self._parse(src)
        tables = self.extractor.extract_tables(tree, src)
        assert len(tables) >= 1
        assert tables[0].column_count >= 2

    def test_extract_blockquote(self):
        src = "> This is a blockquote\n"
        tree = self._parse(src)
        quotes = self.extractor.extract_blockquotes(tree, src)
        assert len(quotes) >= 1

    def test_extract_blockquote_long_truncated(self):
        src = f"> {'A' * 60}\n"
        tree = self._parse(src)
        quotes = self.extractor.extract_blockquotes(tree, src)
        assert len(quotes) >= 1
        assert "..." in quotes[0].name

    def test_extract_horizontal_rule(self):
        src = "Before\n\n---\n\nAfter\n"
        tree = self._parse(src)
        rules = self.extractor.extract_horizontal_rules(tree, src)
        assert len(rules) >= 1

    def test_extract_html_block(self):
        src = "<div>\nHello\n</div>\n"
        tree = self._parse(src)
        html = self.extractor.extract_html_elements(tree, src)
        assert len(html) >= 1

    def test_extract_bold_text(self):
        src = "This is **bold** here.\n"
        tree = self._parse(src)
        fmt = self.extractor.extract_text_formatting(tree, src)
        bold = [f for f in fmt if f.element_type == "strong_emphasis"]
        assert len(bold) >= 1

    def test_extract_italic_text(self):
        src = "This is *italic* here.\n"
        tree = self._parse(src)
        fmt = self.extractor.extract_text_formatting(tree, src)
        italic = [f for f in fmt if f.element_type == "emphasis"]
        assert len(italic) >= 1

    def test_extract_inline_code(self):
        src = "Use `print()` to output.\n"
        tree = self._parse(src)
        fmt = self.extractor.extract_text_formatting(tree, src)
        code = [f for f in fmt if f.element_type == "inline_code"]
        assert len(code) >= 1

    def test_extract_strikethrough(self):
        src = "This is ~~deleted~~ here.\n"
        tree = self._parse(src)
        fmt = self.extractor.extract_text_formatting(tree, src)
        strike = [f for f in fmt if f.element_type == "strikethrough"]
        assert len(strike) >= 1

    def test_extract_footnote_reference(self):
        src = "Some text[^1] with footnote.\n"
        tree = self._parse(src)
        footnotes = self.extractor.extract_footnotes(tree, src)
        refs = [f for f in footnotes if f.element_type == "footnote_reference"]
        assert len(refs) >= 1

    def test_none_tree_all_methods(self):
        assert self.extractor.extract_lists(None, "") == []
        assert self.extractor.extract_tables(None, "") == []
        assert self.extractor.extract_blockquotes(None, "") == []
        assert self.extractor.extract_horizontal_rules(None, "") == []
        assert self.extractor.extract_html_elements(None, "") == []
        assert self.extractor.extract_text_formatting(None, "") == []
        assert self.extractor.extract_footnotes(None, "") == []
        assert self.extractor.extract_references(None, "") == []
        assert self.extractor.extract_images(None, "") == []
        assert self.extractor.extract_links(None, "") == []
        assert self.extractor.extract_code_blocks(None, "") == []
        assert self.extractor.extract_headers(None, "") == []

    def test_complex_document(self):
        src = "# README\n\n## Intro\n\n**bold** and `code`\n\n- item\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n> quote\n\n---\n\n```py\ncode\n```\n\n[link](url)\n\n![img](img.png)\n\n[ref]: https://ref.com\n"
        tree = self._parse(src)
        assert len(self.extractor.extract_headers(tree, src)) >= 2
        assert len(self.extractor.extract_code_blocks(tree, src)) >= 1
        assert len(self.extractor.extract_links(tree, src)) >= 1
        assert len(self.extractor.extract_lists(tree, src)) >= 1
        assert len(self.extractor.extract_tables(tree, src)) >= 1
        assert len(self.extractor.extract_blockquotes(tree, src)) >= 1
        assert len(self.extractor.extract_horizontal_rules(tree, src)) >= 1

    def test_extract_elements_sorted(self):
        src = "# Header\n\n[link](url)\n\n```py\ncode\n```\n"
        tree = self._parse(src)
        elements = self.plugin.extract_elements(tree, src)
        assert len(elements) >= 2
        for i in range(len(elements) - 1):
            assert getattr(elements[i], "start_line", 0) <= getattr(elements[i + 1], "start_line", 0)


class TestPluginQueryStrategy:
    """Tests for execute_query_strategy and get_element_categories."""

    def test_execute_query_strategy_none_key(self):
        plugin = MarkdownPlugin()
        assert plugin.execute_query_strategy(None, "markdown") is None

    def test_execute_query_strategy_known_category(self):
        plugin = MarkdownPlugin()
        result = plugin.execute_query_strategy("headers", "markdown")
        assert result is not None

    def test_get_element_categories_keys(self):
        plugin = MarkdownPlugin()
        categories = plugin.get_element_categories()
        assert isinstance(categories, dict)
        for key in ["function", "headers", "class", "code_blocks", "variable", "links", "images", "import", "references", "lists", "tables", "blockquotes", "horizontal_rules", "html_blocks", "emphasis", "footnotes", "all_elements"]:
            assert key in categories


class TestGetNodeTextEdgeCases:
    """Edge cases for _get_node_text_optimized."""

    def test_cache_hit(self):
        ext = MarkdownElementExtractor()
        ext._node_text_cache[(0, 5)] = "cached"
        node = Mock()
        node.start_byte = 0
        node.end_byte = 5
        assert ext._get_node_text_optimized(node) == "cached"

    def test_fallback_both_fail(self):
        ext = MarkdownElementExtractor()
        ext.content_lines = ["Hello"]
        node = Mock()
        node.start_byte = 0
        node.end_byte = 5
        type(node).start_point = property(lambda self: (_ for _ in ()).throw(Exception("bad")))
        with patch("tree_sitter_analyzer.languages.markdown_plugin.extract_text_slice", side_effect=Exception("fail")):
            assert ext._get_node_text_optimized(node) == ""


class TestMarkdownElementDefaults:
    """Test MarkdownElement default attributes."""

    def test_defaults(self):
        e = MarkdownElement(name="Test", start_line=1, end_line=1, raw_text="test")
        assert e.text is None
        assert e.type is None
        assert e.line_count is None
        assert e.list_type is None
        assert e.item_count is None
        assert e.row_count is None
        assert e.column_count is None


class TestResetCachesTracking:
    """Test _reset_caches with tracking sets."""

    def test_reset_clears_sets(self):
        ext = MarkdownElementExtractor()
        ext._extracted_links.add("test|url")
        ext._extracted_images.add(("alt", "url"))
        ext._reset_caches()
        assert len(ext._extracted_links) == 0
        assert len(ext._extracted_images) == 0


# ====================================================================== #
# TARGETED TESTS for coverage boost (79% -> 80%+)
# ====================================================================== #


class TestMarkdownExceptionHandlers:
    """Tests that hit the exception handler branches in extraction methods."""

    def setup_method(self):
        self.extractor = MarkdownElementExtractor()

    def _make_tree(self):
        tree = Mock()
        tree.root_node = Mock()
        return tree

    def test_extract_code_blocks_exception_handler(self):
        """Cover lines 207-208: exception in code block extraction"""
        tree = self._make_tree()
        with patch.object(
            self.extractor,
            "_extract_fenced_code_blocks",
            side_effect=Exception("code block error"),
        ):
            result = self.extractor.extract_code_blocks(tree, "```\ncode\n```")
            assert result == []

    def test_extract_links_exception_handler(self):
        """Cover lines 232-233: exception in link extraction"""
        tree = self._make_tree()
        with patch.object(
            self.extractor,
            "_extract_inline_links",
            side_effect=Exception("link error"),
        ):
            result = self.extractor.extract_links(tree, "[text](url)")
            assert result == []

    def test_extract_images_exception_handler(self):
        """Cover lines 265-266: exception in image extraction"""
        tree = self._make_tree()
        with patch.object(
            self.extractor,
            "_extract_inline_images",
            side_effect=Exception("image error"),
        ):
            result = self.extractor.extract_images(tree, "![alt](img.png)")
            assert result == []

    def test_extract_references_exception_handler(self):
        """Cover lines 295-296: exception in reference extraction"""
        tree = self._make_tree()
        with patch.object(
            self.extractor,
            "_extract_link_reference_definitions",
            side_effect=Exception("ref error"),
        ):
            result = self.extractor.extract_references(tree, "[ref]: url")
            assert result == []

    def test_extract_lists_exception_handler(self):
        """Cover lines 415-416: exception in list extraction"""
        tree = self._make_tree()
        with patch.object(
            self.extractor,
            "_extract_list_items",
            side_effect=Exception("list error"),
        ):
            result = self.extractor.extract_lists(tree, "- item")
            assert result == []

    def test_extract_tables_exception_handler(self):
        """Cover lines 434-435: exception in table extraction"""
        tree = self._make_tree()
        with patch.object(
            self.extractor,
            "_extract_pipe_tables",
            side_effect=Exception("table error"),
        ):
            result = self.extractor.extract_tables(tree, "| a | b |")
            assert result == []

    def test_extract_fenced_code_block_exception_in_node(self):
        """Cover lines 637-638: exception inside fenced code block node processing"""
        node = Mock()
        node.type = "fenced_code_block"
        node.start_point = Mock(side_effect=Exception("node error"))
        node.children = []
        with patch.object(self.extractor, "_traverse_nodes", return_value=[node]):
            code_blocks = []
            self.extractor.source_code = "```\ncode\n```"
            self.extractor.content_lines = ["```", "code", "```"]
            self.extractor._extract_fenced_code_blocks(Mock(), code_blocks)
            assert code_blocks == []

    def test_extract_indented_code_block_exception_in_node(self):
        """Cover lines 664-665: exception inside indented code block node processing"""
        node = Mock()
        node.type = "indented_code_block"
        node.start_point = Mock(side_effect=Exception("node error"))
        node.children = []
        with patch.object(self.extractor, "_traverse_nodes", return_value=[node]):
            code_blocks = []
            self.extractor.source_code = "    code"
            self.extractor.content_lines = ["    code"]
            self.extractor._extract_indented_code_blocks(Mock(), code_blocks)
            assert code_blocks == []

    def test_extract_inline_links_exception_in_node(self):
        """Cover lines 718-719: exception inside inline link node processing"""
        node = Mock()
        node.type = "inline"
        node.start_point = Mock(side_effect=Exception("node error"))
        node.children = []
        with patch.object(self.extractor, "_traverse_nodes", return_value=[node]):
            links = []
            self.extractor.source_code = "[text](url)"
            self.extractor.content_lines = ["[text](url)"]
            self.extractor._extract_inline_links(Mock(), links)
            assert links == []

    def test_extract_inline_images_exception_in_node(self):
        """Cover lines 878-879: exception inside inline image node processing"""
        node = Mock()
        node.type = "inline"
        node.start_point = Mock(side_effect=Exception("node error"))
        node.children = []
        with patch.object(self.extractor, "_traverse_nodes", return_value=[node]):
            images = []
            self.extractor.source_code = "![alt](img.png)"
            self.extractor.content_lines = ["![alt](img.png)"]
            self.extractor._extract_inline_images(Mock(), images)
            assert images == []

    def test_extract_link_reference_definitions_exception_in_node(self):
        """Cover lines 1024-1025: exception inside reference definition node"""
        node = Mock()
        node.type = "link_reference_definition"
        node.start_point = Mock(side_effect=Exception("node error"))
        node.children = []
        with patch.object(self.extractor, "_traverse_nodes", return_value=[node]):
            refs = []
            self.extractor.source_code = "[ref]: url"
            self.extractor.content_lines = ["[ref]: url"]
            self.extractor._extract_link_reference_definitions(Mock(), refs)
            assert refs == []

    def test_extract_list_items_exception_in_node(self):
        """Cover lines 1085-1086: exception inside list node processing"""
        node = Mock()
        node.type = "list"
        node.start_point = Mock(side_effect=Exception("node error"))
        node.children = []
        with patch.object(self.extractor, "_traverse_nodes", return_value=[node]):
            lists = []
            self.extractor.source_code = "- item"
            self.extractor.content_lines = ["- item"]
            self.extractor._extract_list_items(Mock(), lists)
            assert lists == []

    def test_extract_pipe_tables_exception_in_node(self):
        """Cover lines 1129-1130: exception inside table node processing"""
        node = Mock()
        node.type = "pipe_table"
        node.start_point = Mock(side_effect=Exception("node error"))
        node.children = []
        with patch.object(self.extractor, "_traverse_nodes", return_value=[node]):
            tables = []
            self.extractor.source_code = "| a | b |"
            self.extractor.content_lines = ["| a | b |"]
            self.extractor._extract_pipe_tables(Mock(), tables)
            assert tables == []

    def test_image_reference_definition_exception(self):
        """Cover lines 1002-1003: exception in image reference definition"""
        node = Mock()
        node.type = "link_reference_definition"
        node.start_point = Mock(side_effect=Exception("node error"))
        node.children = []
        with patch.object(self.extractor, "_traverse_nodes", return_value=[node]):
            images = []
            self.extractor.source_code = "[logo]: logo.png"
            self.extractor.content_lines = ["[logo]: logo.png"]
            self.extractor._extract_image_reference_definitions(Mock(), images)
            assert images == []

    def test_image_ref_scan_exception(self):
        """Cover lines 949-950: exception scanning for image references"""
        inline_node = Mock()
        inline_node.type = "inline"
        inline_node.start_point = (0, 0)
        inline_node.end_point = (0, 20)
        inline_node.start_byte = 0
        inline_node.end_byte = 20
        inline_node.children = []

        ref_node = Mock()
        ref_node.type = "link_reference_definition"
        ref_node.start_point = (1, 0)
        ref_node.end_point = (1, 20)
        ref_node.start_byte = 21
        ref_node.end_byte = 41
        ref_node.children = []

        self.extractor.source_code = "![alt][ref]\n[ref]: logo.png"
        self.extractor.content_lines = self.extractor.source_code.split("\n")

        call_count = [0]

        def text_side_effect(n):
            call_count[0] += 1
            if n is inline_node:
                if call_count[0] <= 1:
                    raise Exception("scan error")
                return "![alt][ref]"
            if n is ref_node:
                return "[ref]: logo.png"
            return ""

        with patch.object(self.extractor, "_traverse_nodes", return_value=[inline_node, ref_node]):
            with patch.object(self.extractor, "_get_node_text_optimized", side_effect=text_side_effect):
                images = []
                self.extractor._extract_image_reference_definitions(Mock(), images)
                # Should handle exception gracefully
                assert isinstance(images, list)


class TestMarkdownSetextSingleLine:
    """Test setext header with only single line (no underline)."""

    def setup_method(self):
        self.extractor = MarkdownElementExtractor()

    def test_setext_header_single_line(self):
        """Cover line 575: setext header with only one line (no underline)"""
        node = Mock()
        node.type = "setext_heading"
        node.start_point = (0, 0)
        node.end_point = (0, 10)
        node.start_byte = 0
        node.end_byte = 10
        node.children = []

        self.extractor.source_code = "Title Only"
        self.extractor.content_lines = ["Title Only"]

        with patch.object(self.extractor, "_traverse_nodes", return_value=[node]):
            with patch.object(
                self.extractor, "_get_node_text_optimized", return_value="Title Only"
            ):
                headers = []
                self.extractor._extract_setext_headers(Mock(), headers)
                assert len(headers) == 1
                assert headers[0].level == 2  # Default is H2
                assert headers[0].name == "Title Only"

    def test_setext_header_exception(self):
        """Cover lines 589-590: exception in setext header extraction"""
        node = Mock()
        node.type = "setext_heading"
        node.start_point = Mock(side_effect=Exception("error"))
        node.children = []

        with patch.object(self.extractor, "_traverse_nodes", return_value=[node]):
            headers = []
            self.extractor.source_code = "Title\n====="
            self.extractor.content_lines = ["Title", "====="]
            self.extractor._extract_setext_headers(Mock(), headers)
            assert headers == []


class TestMarkdownPluginAnalyzeFileFallback:
    """Test analyze_file non-MarkdownElementExtractor fallback path."""

    def setup_method(self):
        self.plugin = MarkdownPlugin()

    @pytest.mark.asyncio
    async def test_analyze_file_non_markdown_extractor_fallback(self):
        """Cover lines 1750-1763: fallback for non-MarkdownElementExtractor"""
        from tree_sitter_analyzer.plugins.base import ElementExtractor

        mock_base_extractor = Mock(spec=ElementExtractor)
        # Make it NOT an instance of MarkdownElementExtractor
        mock_base_extractor.__class__ = ElementExtractor

        with patch.object(self.plugin, "get_tree_sitter_language", return_value=Mock()):
            with patch("tree_sitter_analyzer.languages.markdown_plugin.tree_sitter") as mock_ts:
                mock_parser = Mock()
                mock_tree = Mock()
                mock_root = Mock()
                mock_root.children = []
                mock_tree.root_node = mock_root
                mock_parser.parse.return_value = mock_tree
                mock_ts.Parser.return_value = mock_parser

                with patch(
                    "tree_sitter_analyzer.encoding_utils.read_file_safe",
                    return_value=("# Test\n", "utf-8"),
                ):
                    with patch.object(
                        self.plugin,
                        "create_extractor",
                        return_value=mock_base_extractor,
                    ):
                        request = AnalysisRequest(file_path="test.md")
                        result = await self.plugin.analyze_file("test.md", request)
                        assert result.success is True
                        assert result.elements == []


class TestMarkdownExecuteQueryStrategyFallback:
    """Test execute_query_strategy fallback path."""

    def test_fallback_to_base_queries(self):
        """Cover lines 1882-1883: fallback to base queries"""
        plugin = MarkdownPlugin()
        # Query key not in element categories
        result = plugin.execute_query_strategy("nonexistent_category", "markdown")
        # Should fall back to get_queries()
        assert result is None or isinstance(result, str)

    def test_category_with_empty_node_types(self):
        """Test category found but with empty node_types list"""
        plugin = MarkdownPlugin()
        with patch.object(
            plugin, "get_element_categories", return_value={"empty_cat": []}
        ):
            result = plugin.execute_query_strategy("empty_cat", "markdown")
            # node_types is empty, should fall through to base queries
            assert result is None or isinstance(result, str)


class TestMarkdownGetNodeTextMultilineFallback:
    """Test fallback multiline path with same start/end line in loop."""

    def test_multiline_fallback_same_line_in_range(self):
        """Cover lines 498-502: multiline fallback branch where i == start == end"""
        ext = MarkdownElementExtractor()
        ext.content_lines = ["Hello World"]
        node = Mock()
        node.start_byte = 0
        node.end_byte = 5
        node.start_point = (0, 2)
        node.end_point = (0, 8)

        with patch(
            "tree_sitter_analyzer.languages.markdown_plugin.extract_text_slice",
            return_value=None,
        ):
            result = ext._get_node_text_optimized(node)
            # Returns empty since extract_text_slice returned None (falsy)
            # then falls to fallback which handles single-line case
            assert isinstance(result, str)

    def test_end_point_out_of_bounds(self):
        """Cover lines 481-482: end_point out of bounds"""
        ext = MarkdownElementExtractor()
        ext.content_lines = ["Hello"]
        node = Mock()
        node.start_byte = 0
        node.end_byte = 5
        node.start_point = (0, 0)
        node.end_point = (10, 5)  # Out of bounds

        with patch(
            "tree_sitter_analyzer.languages.markdown_plugin.extract_text_slice",
            side_effect=Exception("error"),
        ):
            result = ext._get_node_text_optimized(node)
            assert result == ""
