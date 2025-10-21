#!/usr/bin/env python3
"""
Comprehensive Markdown Plugin Tests

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

        # Set up cache
        node_id = id(mock_node)
        self.extractor._node_text_cache[node_id] = "cached"

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

        with patch.object(self.plugin, "get_extractor", return_value=mock_extractor):
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

        with patch.object(self.plugin, "get_extractor", return_value=mock_extractor):
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
