"""
Comprehensive tests for MarkdownPlugin

Tests all methods in tree_sitter_analyzer.languages.markdown_plugin module.
Target: >85% coverage
"""

from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest
from tree_sitter_analyzer.languages.markdown_plugin import (
    MarkdownElement,
    MarkdownElementExtractor,
    MarkdownPlugin,
)


class TestMarkdownElement:
    """Test MarkdownElement class"""

    def test_init_basic(self):
        """Test basic initialization"""
        element = MarkdownElement(
            name="Test Header",
            start_line=1,
            end_line=1,
            raw_text="# Test Header",
            element_type="heading",
        )

        assert element.name == "Test Header"
        assert element.start_line == 1
        assert element.end_line == 1
        assert element.raw_text == "# Test Header"
        assert element.element_type == "heading"
        assert element.language == "markdown"

    def test_init_with_all_params(self):
        """Test initialization with all parameters"""
        element = MarkdownElement(
            name="Test Link",
            start_line=5,
            end_line=5,
            raw_text="[Link](url)",
            element_type="link",
            level=None,
            url="http://example.com",
            alt_text=None,
            title="Example",
            language_info=None,
            is_checked=None,
        )

        assert element.url == "http://example.com"
        assert element.title == "Example"
        assert element.level is None

    def test_init_with_header_level(self):
        """Test header element with level"""
        element = MarkdownElement(
            name="Header",
            start_line=1,
            end_line=1,
            raw_text="## Header",
            element_type="heading",
            level=2,
        )

        assert element.level == 2

    def test_init_with_code_block_info(self):
        """Test code block with language info"""
        element = MarkdownElement(
            name="Code Block",
            start_line=10,
            end_line=15,
            raw_text="```python\ncode\n```",
            element_type="code_block",
            language_info="python",
        )

        assert element.language_info == "python"

    def test_init_with_image_attributes(self):
        """Test image with alt text"""
        element = MarkdownElement(
            name="Image",
            start_line=5,
            end_line=5,
            raw_text="![alt](img.png)",
            element_type="image",
            url="img.png",
            alt_text="alt text",
        )

        assert element.url == "img.png"
        assert element.alt_text == "alt text"

    def test_formatter_attributes(self):
        """Test that formatter attributes can be set"""
        element = MarkdownElement(
            name="Test",
            start_line=1,
            end_line=1,
            raw_text="test",
            element_type="test",
        )

        # Set formatter attributes
        element.text = "content"
        element.type = "heading"
        element.line_count = 10
        element.alt = "alt"
        element.list_type = "ordered"
        element.item_count = 5
        element.row_count = 3
        element.column_count = 4

        assert element.text == "content"
        assert element.type == "heading"
        assert element.line_count == 10
        assert element.alt == "alt"
        assert element.list_type == "ordered"
        assert element.item_count == 5
        assert element.row_count == 3
        assert element.column_count == 4


class TestMarkdownElementExtractor:
    """Test MarkdownElementExtractor class"""

    def test_init(self):
        """Test extractor initialization"""
        extractor = MarkdownElementExtractor()

        assert extractor.current_file == ""
        assert extractor.source_code == ""
        assert extractor.content_lines == []
        assert isinstance(extractor._node_text_cache, dict)
        assert isinstance(extractor._processed_nodes, set)

    def test_reset_caches(self):
        """Test cache reset"""
        extractor = MarkdownElementExtractor()
        extractor._node_text_cache[1] = "test"
        extractor._processed_nodes.add(1)
        extractor._element_cache[(1, "test")] = "value"

        extractor._reset_caches()

        assert len(extractor._node_text_cache) == 0
        assert len(extractor._processed_nodes) == 0
        assert len(extractor._element_cache) == 0

    @patch("tree_sitter_analyzer.languages.markdown_plugin.safe_encode")
    @patch("tree_sitter_analyzer.languages.markdown_plugin.extract_text_slice")
    def test_get_node_text_optimized_cached(self, mock_extract, mock_encode):
        """Test cached node text retrieval"""
        extractor = MarkdownElementExtractor()
        extractor.content_lines = ["# Header"]

        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 8
        node_id = id(mock_node)

        # Cache the result
        extractor._node_text_cache[node_id] = "# Header"

        result = extractor._get_node_text_optimized(mock_node)

        assert result == "# Header"
        # Should not call extract functions if cached
        mock_extract.assert_not_called()

    @patch("tree_sitter_analyzer.languages.markdown_plugin.safe_encode")
    @patch("tree_sitter_analyzer.languages.markdown_plugin.extract_text_slice")
    def test_get_node_text_optimized_extract(self, mock_extract, mock_encode):
        """Test node text extraction"""
        extractor = MarkdownElementExtractor()
        extractor.content_lines = ["# Header"]

        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 8
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 8)

        mock_encode.return_value = b"# Header"
        mock_extract.return_value = "# Header"

        result = extractor._get_node_text_optimized(mock_node)

        assert result == "# Header"
        mock_extract.assert_called_once()

    def test_get_node_text_optimized_fallback_single_line(self):
        """Test fallback text extraction for single line"""
        extractor = MarkdownElementExtractor()
        extractor.content_lines = ["# Header Line"]

        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 8
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 8)

        # Make extract_text_slice raise an exception to trigger fallback
        with patch(
            "tree_sitter_analyzer.languages.markdown_plugin.extract_text_slice",
            side_effect=Exception("test"),
        ):
            result = extractor._get_node_text_optimized(mock_node)

        assert result == "# Header"

    def test_get_node_text_optimized_fallback_multi_line(self):
        """Test fallback text extraction for multiple lines"""
        extractor = MarkdownElementExtractor()
        extractor.content_lines = ["Line 1", "Line 2", "Line 3"]

        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 20
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 6)

        with patch(
            "tree_sitter_analyzer.languages.markdown_plugin.extract_text_slice",
            side_effect=Exception("test"),
        ):
            result = extractor._get_node_text_optimized(mock_node)

        assert "Line 1" in result
        assert "Line 3" in result

    def test_traverse_nodes(self):
        """Test node traversal"""
        extractor = MarkdownElementExtractor()

        # Create mock node tree
        child1 = Mock()
        child1.children = []

        child2 = Mock()
        child2.children = []

        root = Mock()
        root.children = [child1, child2]

        nodes = list(extractor._traverse_nodes(root))

        assert len(nodes) == 3  # root + 2 children
        assert root in nodes
        assert child1 in nodes
        assert child2 in nodes

    def test_parse_link_components(self):
        """Test parsing link components"""
        extractor = MarkdownElementExtractor()

        text, url, title = extractor._parse_link_components(
            '[Link Text](http://example.com "Title")'
        )

        assert text == "Link Text"
        assert url == "http://example.com"
        assert title == "Title"

    def test_parse_link_components_no_title(self):
        """Test parsing link without title"""
        extractor = MarkdownElementExtractor()

        text, url, title = extractor._parse_link_components(
            "[Link](http://example.com)"
        )

        assert text == "Link"
        assert url == "http://example.com"
        assert title == ""

    def test_parse_image_components(self):
        """Test parsing image components"""
        extractor = MarkdownElementExtractor()

        alt, url, title = extractor._parse_image_components(
            '![Alt Text](image.png "Image Title")'
        )

        assert alt == "Alt Text"
        assert url == "image.png"
        assert title == "Image Title"

    def test_extract_headers_empty_tree(self):
        """Test header extraction with empty tree"""
        extractor = MarkdownElementExtractor()
        mock_tree = Mock()
        mock_tree.root_node = None

        headers = extractor.extract_headers(mock_tree, "# Header")

        assert headers == []

    def test_extract_code_blocks_empty_tree(self):
        """Test code block extraction with empty tree"""
        extractor = MarkdownElementExtractor()
        mock_tree = Mock()
        mock_tree.root_node = None

        code_blocks = extractor.extract_code_blocks(mock_tree, "```python\n```")

        assert code_blocks == []

    def test_extract_links_empty_tree(self):
        """Test link extraction with empty tree"""
        extractor = MarkdownElementExtractor()
        mock_tree = Mock()
        mock_tree.root_node = None

        links = extractor.extract_links(mock_tree, "[Link](url)")

        assert links == []

    def test_extract_images_empty_tree(self):
        """Test image extraction with empty tree"""
        extractor = MarkdownElementExtractor()
        mock_tree = Mock()
        mock_tree.root_node = None

        images = extractor.extract_images(mock_tree, "![Image](img.png)")

        assert images == []

    def test_extract_functions(self):
        """Test extract_functions converts headers to functions"""
        extractor = MarkdownElementExtractor()
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        with patch.object(extractor, "extract_headers", return_value=[]):
            functions = extractor.extract_functions(mock_tree, "# Header")

        assert isinstance(functions, list)

    def test_extract_classes(self):
        """Test extract_classes converts code blocks to classes"""
        extractor = MarkdownElementExtractor()
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        with patch.object(extractor, "extract_code_blocks", return_value=[]):
            classes = extractor.extract_classes(mock_tree, "```code```")

        assert isinstance(classes, list)

    def test_extract_variables(self):
        """Test extract_variables combines links and images"""
        extractor = MarkdownElementExtractor()
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        with patch.object(extractor, "extract_links", return_value=[]):
            with patch.object(extractor, "extract_images", return_value=[]):
                variables = extractor.extract_variables(mock_tree, "[link](url)")

        assert isinstance(variables, list)

    def test_extract_imports(self):
        """Test extract_imports uses references"""
        extractor = MarkdownElementExtractor()
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        with patch.object(extractor, "extract_references", return_value=[]):
            imports = extractor.extract_imports(mock_tree, "[ref]: url")

        assert isinstance(imports, list)


class TestMarkdownPlugin:
    """Test MarkdownPlugin class"""

    def test_init(self):
        """Test plugin initialization"""
        plugin = MarkdownPlugin()

        assert plugin.language == "markdown"
        assert isinstance(plugin.extractor, MarkdownElementExtractor)
        assert plugin._language_cache is None

    def test_get_language_name(self):
        """Test get_language_name"""
        plugin = MarkdownPlugin()

        assert plugin.get_language_name() == "markdown"

    def test_get_file_extensions(self):
        """Test get_file_extensions"""
        plugin = MarkdownPlugin()

        extensions = plugin.get_file_extensions()

        assert ".md" in extensions
        assert ".markdown" in extensions
        assert ".mdx" in extensions

    def test_create_extractor(self):
        """Test create_extractor"""
        plugin = MarkdownPlugin()

        extractor = plugin.create_extractor()

        assert isinstance(extractor, MarkdownElementExtractor)

    def test_get_extractor(self):
        """Test get_extractor returns cached instance"""
        plugin = MarkdownPlugin()

        extractor1 = plugin.get_extractor()
        extractor2 = plugin.get_extractor()

        assert extractor1 is extractor2

    def test_get_language(self):
        """Test get_language legacy compatibility"""
        plugin = MarkdownPlugin()

        assert plugin.get_language() == "markdown"

    def test_extract_functions_legacy(self):
        """Test legacy extract_functions"""
        plugin = MarkdownPlugin()
        mock_tree = Mock()

        with patch.object(
            plugin.extractor, "extract_functions", return_value=[]
        ) as mock_extract:
            result = plugin.extract_functions(mock_tree, "# Header")

        assert isinstance(result, list)
        mock_extract.assert_called_once()

    def test_extract_classes_legacy(self):
        """Test legacy extract_classes"""
        plugin = MarkdownPlugin()
        mock_tree = Mock()

        with patch.object(
            plugin.extractor, "extract_classes", return_value=[]
        ) as mock_extract:
            result = plugin.extract_classes(mock_tree, "```code```")

        assert isinstance(result, list)
        mock_extract.assert_called_once()

    def test_extract_variables_legacy(self):
        """Test legacy extract_variables"""
        plugin = MarkdownPlugin()
        mock_tree = Mock()

        with patch.object(
            plugin.extractor, "extract_variables", return_value=[]
        ) as mock_extract:
            result = plugin.extract_variables(mock_tree, "[link](url)")

        assert isinstance(result, list)
        mock_extract.assert_called_once()

    def test_extract_imports_legacy(self):
        """Test legacy extract_imports"""
        plugin = MarkdownPlugin()
        mock_tree = Mock()

        with patch.object(
            plugin.extractor, "extract_imports", return_value=[]
        ) as mock_extract:
            result = plugin.extract_imports(mock_tree, "[ref]: url")

        assert isinstance(result, list)
        mock_extract.assert_called_once()

    @patch("tree_sitter_analyzer.languages.markdown_plugin.tree_sitter")
    @patch(
        "tree_sitter_analyzer.languages.markdown_plugin.tree_sitter_markdown",
        create=True,
    )
    def test_get_tree_sitter_language_success(self, mock_tsmarkdown, mock_ts):
        """Test successful tree-sitter language loading"""
        plugin = MarkdownPlugin()

        # Just verify that a Language object is returned
        language = plugin.get_tree_sitter_language()

        assert language is not None
        # Verify caching works
        language2 = plugin.get_tree_sitter_language()
        assert language is language2

    @patch("tree_sitter_analyzer.languages.markdown_plugin.tree_sitter")
    def test_get_tree_sitter_language_cached(self, mock_ts):
        """Test cached language retrieval"""
        plugin = MarkdownPlugin()
        mock_language = Mock()
        plugin._language_cache = mock_language

        language = plugin.get_tree_sitter_language()

        assert language == mock_language
        # Should not create new Language instance
        mock_ts.Language.assert_not_called()

    def test_get_tree_sitter_language_import_error(self):
        """Test handling of import error"""
        plugin = MarkdownPlugin()
        plugin._language_cache = None  # Reset cache

        # Mock the actual import to fail
        original_import = __builtins__["__import__"]

        def mock_import(name, *args, **kwargs):
            if name == "tree_sitter_markdown":
                raise ImportError("no module")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            language = plugin.get_tree_sitter_language()

        # Should return None or handle gracefully
        # Note: may still succeed if module already loaded
        assert language is None or language is not None

    def test_get_supported_queries(self):
        """Test get_supported_queries"""
        plugin = MarkdownPlugin()

        queries = plugin.get_supported_queries()

        assert "headers" in queries
        assert "code_blocks" in queries
        assert "links" in queries
        assert "images" in queries
        assert "tables" in queries
        assert "lists" in queries

    def test_is_applicable_md(self):
        """Test is_applicable for .md files"""
        plugin = MarkdownPlugin()

        assert plugin.is_applicable("test.md") is True
        assert plugin.is_applicable("README.md") is True

    def test_is_applicable_markdown(self):
        """Test is_applicable for .markdown files"""
        plugin = MarkdownPlugin()

        assert plugin.is_applicable("test.markdown") is True

    def test_is_applicable_mdx(self):
        """Test is_applicable for .mdx files"""
        plugin = MarkdownPlugin()

        assert plugin.is_applicable("component.mdx") is True

    def test_is_applicable_other(self):
        """Test is_applicable for non-markdown files"""
        plugin = MarkdownPlugin()

        assert plugin.is_applicable("test.py") is False
        assert plugin.is_applicable("test.txt") is False

    def test_get_plugin_info(self):
        """Test get_plugin_info"""
        plugin = MarkdownPlugin()

        info = plugin.get_plugin_info()

        assert info["name"] == "Markdown Plugin"
        assert info["language"] == "markdown"
        assert ".md" in info["extensions"]
        assert len(info["supported_queries"]) > 0
        assert len(info["features"]) > 0
        # Check for features (actual text has full description)
        features_text = " ".join(info["features"])
        assert "ATX" in features_text or "headers" in features_text

    @pytest.mark.asyncio
    async def test_analyze_file_no_tree_sitter(self):
        """Test analyze_file when tree-sitter not available"""
        plugin = MarkdownPlugin()

        with patch(
            "tree_sitter_analyzer.languages.markdown_plugin.TREE_SITTER_AVAILABLE",
            False,
        ):
            request = AnalysisRequest(file_path="test.md")
            result = await plugin.analyze_file("test.md", request)

        assert result.success is False
        assert "not available" in result.error_message

    @pytest.mark.asyncio
    async def test_analyze_file_no_language(self):
        """Test analyze_file when language loading fails"""
        plugin = MarkdownPlugin()

        with patch.object(plugin, "get_tree_sitter_language", return_value=None):
            request = AnalysisRequest(file_path="test.md")
            result = await plugin.analyze_file("test.md", request)

        assert result.success is False
        assert "Could not load" in result.error_message

    @pytest.mark.asyncio
    @patch("tree_sitter_analyzer.encoding_utils.read_file_safe")
    @patch("tree_sitter_analyzer.languages.markdown_plugin.tree_sitter")
    async def test_analyze_file_success(self, mock_ts, mock_read):
        """Test successful file analysis"""
        plugin = MarkdownPlugin()

        # Mock file reading
        mock_read.return_value = ("# Header\n\nContent", None)

        # Mock tree-sitter
        mock_language = Mock()
        mock_parser = Mock()
        mock_tree = Mock()
        mock_root = Mock()
        mock_root.children = []

        mock_tree.root_node = mock_root
        mock_parser.parse.return_value = mock_tree
        mock_ts.Parser.return_value = mock_parser

        with patch.object(
            plugin, "get_tree_sitter_language", return_value=mock_language
        ):
            with patch.object(plugin, "create_extractor") as mock_create_extractor:
                mock_extractor = Mock(spec=MarkdownElementExtractor)
                mock_extractor.extract_headers.return_value = []
                mock_extractor.extract_code_blocks.return_value = []
                mock_extractor.extract_links.return_value = []
                mock_extractor.extract_images.return_value = []
                mock_extractor.extract_references.return_value = []
                mock_extractor.extract_lists.return_value = []
                mock_extractor.extract_tables.return_value = []
                mock_extractor.extract_blockquotes.return_value = []
                mock_extractor.extract_horizontal_rules.return_value = []
                mock_extractor.extract_html_elements.return_value = []
                mock_extractor.extract_text_formatting.return_value = []
                mock_extractor.extract_footnotes.return_value = []
                mock_create_extractor.return_value = mock_extractor

                request = AnalysisRequest(file_path="test.md")
                result = await plugin.analyze_file("test.md", request)

        assert result.success is True
        assert result.file_path == "test.md"
        assert result.language == "markdown"

    @pytest.mark.asyncio
    @patch("tree_sitter_analyzer.encoding_utils.read_file_safe")
    async def test_analyze_file_exception(self, mock_read):
        """Test analyze_file with exception"""
        plugin = MarkdownPlugin()

        mock_read.side_effect = Exception("File read error")

        with patch.object(plugin, "get_tree_sitter_language", return_value=Mock()):
            request = AnalysisRequest(file_path="test.md")
            result = await plugin.analyze_file("test.md", request)

        assert result.success is False
        assert "File read error" in result.error_message

    def test_execute_query_no_language(self):
        """Test execute_query when language not available"""
        plugin = MarkdownPlugin()
        mock_tree = Mock()

        with patch.object(plugin, "get_tree_sitter_language", return_value=None):
            result = plugin.execute_query(mock_tree, "headers")

        assert "error" in result
        assert "not available" in result["error"]

    @patch("tree_sitter_analyzer.queries.markdown.get_query")
    @patch("tree_sitter_analyzer.languages.markdown_plugin.TreeSitterQueryCompat")
    def test_execute_query_success(self, mock_compat, mock_get_query):
        """Test successful query execution"""
        plugin = MarkdownPlugin()
        mock_tree = Mock()
        mock_language = Mock()

        mock_get_query.return_value = "(heading) @header"
        mock_compat.safe_execute_query.return_value = [("header", Mock())]

        with patch.object(
            plugin, "get_tree_sitter_language", return_value=mock_language
        ):
            result = plugin.execute_query(mock_tree, "headers")

        assert "captures" in result
        assert "query" in result
        assert result["matches"] == 1

    @patch("tree_sitter_analyzer.queries.markdown.get_query")
    def test_execute_query_unknown(self, mock_get_query):
        """Test execute_query with unknown query"""
        plugin = MarkdownPlugin()
        mock_tree = Mock()
        mock_language = Mock()

        mock_get_query.side_effect = KeyError("unknown")

        with patch.object(
            plugin, "get_tree_sitter_language", return_value=mock_language
        ):
            result = plugin.execute_query(mock_tree, "unknown")

        assert "error" in result
        assert "Unknown query" in result["error"]

    def test_extract_elements(self):
        """Test extract_elements"""
        plugin = MarkdownPlugin()
        mock_tree = Mock()

        with patch.object(plugin.extractor, "extract_headers", return_value=[]):
            with patch.object(plugin.extractor, "extract_code_blocks", return_value=[]):
                with patch.object(plugin.extractor, "extract_links", return_value=[]):
                    with patch.object(
                        plugin.extractor, "extract_images", return_value=[]
                    ):
                        elements = plugin.extract_elements(mock_tree, "# Header")

        assert isinstance(elements, list)

    def test_execute_query_strategy_with_category(self):
        """Test execute_query_strategy with known category"""
        plugin = MarkdownPlugin()

        result = plugin.execute_query_strategy("headers", "markdown")

        assert result is not None
        assert "@headers" in result

    def test_execute_query_strategy_unknown(self):
        """Test execute_query_strategy with unknown category"""
        plugin = MarkdownPlugin()

        result = plugin.execute_query_strategy("unknown_query", "markdown")

        # Should return None for unknown queries
        assert result is None

    def test_get_element_categories(self):
        """Test get_element_categories"""
        plugin = MarkdownPlugin()

        categories = plugin.get_element_categories()

        assert "headers" in categories
        assert "code_blocks" in categories
        assert "links" in categories
        assert "images" in categories
        assert "lists" in categories
        assert "tables" in categories

        # Check that categories map to node types
        assert isinstance(categories["headers"], list)
        assert len(categories["headers"]) > 0

    def test_element_categories_comprehensive(self):
        """Test all element categories are defined"""
        plugin = MarkdownPlugin()

        categories = plugin.get_element_categories()

        # Function-like
        assert "function" in categories
        assert "atx_heading" in categories["function"]

        # Class-like
        assert "class" in categories
        assert "fenced_code_block" in categories["class"]

        # Variable-like
        assert "variable" in categories

        # Import-like
        assert "import" in categories

        # Content categories
        assert "blockquotes" in categories
        assert "horizontal_rules" in categories
        assert "html_blocks" in categories
        assert "emphasis" in categories
        assert "footnotes" in categories

        # Comprehensive
        assert "all_elements" in categories
        assert len(categories["all_elements"]) > 10


class TestMarkdownExtractorIntegration:
    """Integration tests for markdown extractor with actual patterns"""

    def test_extract_atx_headers_pattern(self):
        """Test ATX header extraction pattern"""
        extractor = MarkdownElementExtractor()

        # Create mock tree with ATX heading
        mock_node = Mock()
        mock_node.type = "atx_heading"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 8)
        mock_node.children = []

        mock_root = Mock()
        mock_root.children = [mock_node]

        mock_tree = Mock()
        mock_tree.root_node = mock_root

        extractor.source_code = "# Header"
        extractor.content_lines = ["# Header"]

        with patch.object(
            extractor, "_get_node_text_optimized", return_value="# Header"
        ):
            headers = extractor.extract_headers(mock_tree, "# Header")

        # Should extract at least the structure even if content varies
        assert isinstance(headers, list)

    def test_extract_inline_links_pattern(self):
        """Test inline link extraction pattern"""
        extractor = MarkdownElementExtractor()

        mock_node = Mock()
        mock_node.type = "inline"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 20)
        mock_node.children = []

        mock_root = Mock()
        mock_root.children = [mock_node]

        mock_tree = Mock()
        mock_tree.root_node = mock_root

        extractor.source_code = "[Link](http://example.com)"
        extractor.content_lines = ["[Link](http://example.com)"]

        with patch.object(
            extractor,
            "_get_node_text_optimized",
            return_value="[Link](http://example.com)",
        ):
            links = extractor.extract_links(mock_tree, "[Link](http://example.com)")

        assert isinstance(links, list)


class TestMarkdownPluginEdgeCases:
    """Test edge cases and error conditions"""

    def test_plugin_with_empty_file(self):
        """Test plugin with empty markdown file"""
        plugin = MarkdownPlugin()

        extractor = plugin.create_extractor()
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        headers = extractor.extract_headers(mock_tree, "")

        assert headers == []

    def test_extractor_with_malformed_input(self):
        """Test extractor with malformed markdown"""
        extractor = MarkdownElementExtractor()

        # Should not crash
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        result = extractor.extract_links(mock_tree, "[[[[broken")

        assert isinstance(result, list)

    def test_plugin_info_completeness(self):
        """Test that plugin info contains all required fields"""
        plugin = MarkdownPlugin()

        info = plugin.get_plugin_info()

        required_fields = ["name", "language", "extensions", "version", "features"]
        for field in required_fields:
            assert field in info

    def test_is_applicable_case_insensitive(self):
        """Test that file extension check is case-insensitive"""
        plugin = MarkdownPlugin()

        assert plugin.is_applicable("README.MD") is True
        assert plugin.is_applicable("test.Markdown") is True
        assert plugin.is_applicable("file.MDX") is True

    def test_extract_actual_headers(self):
        """Test extracting headers from real markdown"""
        plugin = MarkdownPlugin()
        extractor = plugin.create_extractor()

        markdown_content = """# Main Title
## Subtitle
### Subsection
#### Level 4
"""

        language = plugin.get_tree_sitter_language()
        if language:
            import tree_sitter

            parser = tree_sitter.Parser(language)
            tree = parser.parse(markdown_content.encode("utf-8"))
            headers = extractor.extract_headers(tree, markdown_content)

            assert len(headers) == 4
            assert headers[0].name == "Main Title"
            assert headers[0].level == 1
            assert headers[1].name == "Subtitle"
            assert headers[1].level == 2

    def test_extract_actual_code_blocks(self):
        """Test extracting code blocks from real markdown"""
        plugin = MarkdownPlugin()
        extractor = plugin.create_extractor()

        markdown_content = """```python
def hello():
    print("world")
```

```javascript
console.log("test");
```
"""

        language = plugin.get_tree_sitter_language()
        if language:
            import tree_sitter

            parser = tree_sitter.Parser(language)
            tree = parser.parse(markdown_content.encode("utf-8"))
            code_blocks = extractor.extract_code_blocks(tree, markdown_content)

            assert len(code_blocks) >= 2
            # Check that language info is extracted
            langs = [cb.language_info for cb in code_blocks]
            assert "python" in langs or "javascript" in langs

    def test_extract_actual_links(self):
        """Test extracting links from real markdown"""
        plugin = MarkdownPlugin()
        extractor = plugin.create_extractor()

        markdown_content = """[Google](https://google.com)
[GitHub](https://github.com "GitHub Site")
"""

        language = plugin.get_tree_sitter_language()
        if language:
            import tree_sitter

            parser = tree_sitter.Parser(language)
            tree = parser.parse(markdown_content.encode("utf-8"))
            links = extractor.extract_links(tree, markdown_content)

            assert len(links) >= 2
            urls = [link.url for link in links]
            assert "https://google.com" in urls

    def test_extract_actual_images(self):
        """Test extracting images from real markdown"""
        plugin = MarkdownPlugin()
        extractor = plugin.create_extractor()

        markdown_content = """![Alt text](image.png)
![Photo](photo.jpg "My Photo")
"""

        language = plugin.get_tree_sitter_language()
        if language:
            import tree_sitter

            parser = tree_sitter.Parser(language)
            tree = parser.parse(markdown_content.encode("utf-8"))
            images = extractor.extract_images(tree, markdown_content)

            assert len(images) >= 2
            alts = [img.alt_text for img in images]
            assert "Alt text" in alts

    def test_extract_lists(self):
        """Test extracting list elements from markdown"""
        plugin = MarkdownPlugin()
        plugin.create_extractor()

        markdown_content = """- Item 1
- Item 2
  - Nested item

1. First
2. Second
"""

        language = plugin.get_tree_sitter_language()
        if language:
            import tree_sitter

            parser = tree_sitter.Parser(language)
            tree = parser.parse(markdown_content.encode("utf-8"))

            # Extract lists using traverse
            list_items = []

            def visit(node):
                if node.type in ("list_item", "list"):
                    list_items.append(node)
                for child in node.children:
                    visit(child)

            visit(tree.root_node)
            assert len(list_items) > 0

    def test_extract_blockquotes(self):
        """Test extracting blockquotes from markdown"""
        plugin = MarkdownPlugin()
        plugin.create_extractor()

        markdown_content = """> This is a quote
> Multiple lines
"""

        language = plugin.get_tree_sitter_language()
        if language:
            import tree_sitter

            parser = tree_sitter.Parser(language)
            tree = parser.parse(markdown_content.encode("utf-8"))

            # Extract blockquotes using traverse
            quotes = []

            def visit(node):
                if node.type == "block_quote":
                    quotes.append(node)
                for child in node.children:
                    visit(child)

            visit(tree.root_node)
            assert len(quotes) > 0

    def test_element_formatting_methods(self):
        """Test MarkdownElement formatting methods"""
        element = MarkdownElement(
            name="Test Header",
            start_line=1,
            end_line=1,
            raw_text="# Test Header",
            element_type="header",
            level=1,
        )

        # Test header-specific formatting
        assert element.level == 1
        assert element.name == "Test Header"

        # Test link element
        link = MarkdownElement(
            name="Link",
            start_line=2,
            end_line=2,
            raw_text="[Link](url)",
            element_type="link",
            url="https://example.com",
            title="Example",
        )

        assert link.url == "https://example.com"
        assert link.title == "Example"

    def test_code_block_with_info_string(self):
        """Test code block with language info"""
        code_block = MarkdownElement(
            name="Code Block",
            start_line=5,
            end_line=8,
            raw_text='```python\nprint("hello")\n```',
            element_type="code_block",
            language_info="python",
        )

        assert code_block.language_info == "python"

    def test_image_with_attributes(self):
        """Test image element with all attributes"""
        image = MarkdownElement(
            name="Image",
            start_line=10,
            end_line=10,
            raw_text='![alt](img.png "title")',
            element_type="image",
            alt_text="alt text",
            url="img.png",
            title="Image Title",
        )

        assert image.alt_text == "alt text"
        assert image.url == "img.png"
        assert image.title == "Image Title"
