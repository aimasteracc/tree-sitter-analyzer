#!/usr/bin/env python3
"""Supplement markdown plugin tests — targets bare-minimum extractor paths."""

from unittest.mock import MagicMock

from tree_sitter_analyzer.languages.markdown_plugin import (
    MarkdownElementExtractor,
    MarkdownPlugin,
)


class MockNode:
    def __init__(
        self,
        node_type,
        start_point=(0, 0),
        end_point=(0, 1),
        children=None,
        text="",
        start_byte=0,
        end_byte=1,
    ):
        self.type = node_type
        self.start_point = start_point
        self.end_point = end_point
        self.start_byte = start_byte
        self.end_byte = end_byte
        self._children = children or []
        self._text = text

    @property
    def children(self):
        return self._children

    @property
    def text(self):
        return self._text.encode() if isinstance(self._text, str) else self._text


class TestMarkdownSupplement:
    """Target extractors that require minimal mocking."""

    def _mk_tree(self, root_children, source=""):
        tree = MagicMock()
        root = MockNode("document", children=root_children)
        tree.root_node = root
        return tree

    def test_extract_headers_empty(self):
        ext = MarkdownElementExtractor()
        tree = self._mk_tree([])
        headers = ext.extract_headers(tree, "some markdown")
        assert isinstance(headers, list)

    def test_extract_links_empty(self):
        ext = MarkdownElementExtractor()
        tree = self._mk_tree([])
        links = ext.extract_links(tree, "text")
        assert isinstance(links, list)

    def test_extract_images_empty(self):
        ext = MarkdownElementExtractor()
        tree = self._mk_tree([])
        imgs = ext.extract_images(tree, "text")
        assert isinstance(imgs, list)

    def test_extract_blockquotes_empty(self):
        ext = MarkdownElementExtractor()
        tree = self._mk_tree([])
        bqs = ext.extract_blockquotes(tree, "text")
        assert isinstance(bqs, list)

    def test_extract_code_blocks_empty(self):
        ext = MarkdownElementExtractor()
        tree = self._mk_tree([])
        cbs = ext.extract_code_blocks(tree, "text")
        assert isinstance(cbs, list)

    def test_extract_references_empty(self):
        ext = MarkdownElementExtractor()
        tree = self._mk_tree([])
        refs = ext.extract_references(tree, "text")
        assert isinstance(refs, list)

    def test_plugin_get_queries(self):
        plugin = MarkdownPlugin()
        queries = plugin.get_queries()
        assert isinstance(queries, dict)

    def test_extract_functions_empty(self):
        ext = MarkdownElementExtractor()
        tree = self._mk_tree([])
        funcs = ext.extract_functions(tree, "text")
        assert isinstance(funcs, list)

    def test_extract_classes_empty(self):
        ext = MarkdownElementExtractor()
        tree = self._mk_tree([])
        classes = ext.extract_classes(tree, "text")
        assert isinstance(classes, list)

    def test_extract_variables_empty(self):
        ext = MarkdownElementExtractor()
        tree = self._mk_tree([])
        vars_ = ext.extract_variables(tree, "text")
        assert isinstance(vars_, list)

    def test_extract_imports_empty(self):
        ext = MarkdownElementExtractor()
        tree = self._mk_tree([])
        imports = ext.extract_imports(tree, "text")
        assert isinstance(imports, list)


class TestMarkdownSetextHeaders:
    """Tests for _extract_setext_headers method (lines 558-590)"""

    def setup_method(self):
        self.extractor = MarkdownElementExtractor()

    def test_extract_setext_header_h1(self):
        """Test setext heading extraction for H1 (===)"""
        from unittest.mock import Mock, patch

        content = "Heading 1\n======="
        mock_root = Mock()

        # Create setext heading node
        setext_node = Mock()
        setext_node.children = []
        setext_node.type = "setext_heading"
        setext_node.start_point = (0, 0)
        setext_node.end_point = (1, 7)

        mock_root.children = [setext_node]

        with patch.object(
            self.extractor, "_get_node_text_optimized", return_value="Heading 1\n======="
        ):
            headers = []
            self.extractor._extract_setext_headers(mock_root, headers)

            assert len(headers) == 1
            assert headers[0].name == "Heading 1"
            assert headers[0].level == 1
            assert headers[0].type == "heading"

    def test_extract_setext_header_h2(self):
        """Test setext heading extraction for H2 (---)"""
        from unittest.mock import Mock, patch

        content = "Heading 2\n-------"
        mock_root = Mock()

        setext_node = Mock()
        setext_node.children = []
        setext_node.type = "setext_heading"
        setext_node.start_point = (0, 0)
        setext_node.end_point = (1, 7)

        mock_root.children = [setext_node]

        with patch.object(
            self.extractor, "_get_node_text_optimized", return_value="Heading 2\n-------"
        ):
            headers = []
            self.extractor._extract_setext_headers(mock_root, headers)

            assert len(headers) == 1
            assert headers[0].name == "Heading 2"
            assert headers[0].level == 2
            assert headers[0].type == "heading"

    def test_extract_setext_header_default_level(self):
        """Test setext heading with unrecognized underline (default level 2)"""
        from unittest.mock import Mock, patch

        # Underline that doesn't start with = or -
        mock_root = Mock()
        setext_node = Mock()
        setext_node.children = []
        setext_node.type = "setext_heading"
        setext_node.start_point = (0, 0)
        setext_node.end_point = (1, 5)

        mock_root.children = [setext_node]

        with patch.object(
            self.extractor, "_get_node_text_optimized", return_value="Title\n+++++"
        ):
            headers = []
            self.extractor._extract_setext_headers(mock_root, headers)

            assert len(headers) == 1
            assert headers[0].level == 2  # Default

    def test_extract_setext_header_single_line(self):
        """Test setext heading with single-line content (lines 575)"""
        from unittest.mock import Mock, patch

        mock_root = Mock()
        setext_node = Mock()
        setext_node.children = []
        setext_node.type = "setext_heading"
        setext_node.start_point = (0, 0)
        setext_node.end_point = (0, 10)

        mock_root.children = [setext_node]

        with patch.object(
            self.extractor, "_get_node_text_optimized", return_value="Short Title"
        ):
            headers = []
            self.extractor._extract_setext_headers(mock_root, headers)

            assert len(headers) == 1
            assert headers[0].name == "Short Title"
            assert headers[0].text == "Short Title"

    def test_extract_setext_header_empty_content(self):
        """Test setext heading with empty content"""
        from unittest.mock import Mock, patch

        mock_root = Mock()
        setext_node = Mock()
        setext_node.children = []
        setext_node.type = "setext_heading"
        setext_node.start_point = (0, 0)
        setext_node.end_point = (1, 3)

        mock_root.children = [setext_node]

        with patch.object(
            self.extractor, "_get_node_text_optimized", return_value="\n==="
        ):
            headers = []
            self.extractor._extract_setext_headers(mock_root, headers)

            assert len(headers) == 1
            assert headers[0].name == "==="
            assert headers[0].text == "==="
            assert headers[0].level == 2

    def test_extract_setext_header_exception(self):
        """Test setext heading extraction with exception (lines 589-590)"""
        from unittest.mock import Mock, patch

        mock_root = Mock()
        setext_node = Mock()
        setext_node.children = []
        setext_node.type = "setext_heading"
        setext_node.start_point = (0, 0)
        setext_node.end_point = (1, 7)

        mock_root.children = [setext_node]

        # Make _get_node_text_optimized raise an exception
        with patch.object(
            self.extractor, "_get_node_text_optimized", side_effect=RuntimeError("test error")
        ):
            headers = []
            # Should not raise, just log debug
            self.extractor._extract_setext_headers(mock_root, headers)
            assert len(headers) == 0

    def test_extract_setext_header_multiple(self):
        """Test multiple setext headers in sequence"""
        from unittest.mock import Mock, patch

        mock_root = Mock()

        h1_node = Mock()
        h1_node.children = []
        h1_node.type = "setext_heading"
        h1_node.start_point = (0, 0)
        h1_node.end_point = (1, 7)

        h2_node = Mock()
        h2_node.children = []
        h2_node.type = "setext_heading"
        h2_node.start_point = (3, 0)
        h2_node.end_point = (4, 7)

        mock_root.children = [h1_node, h2_node]

        with patch.object(
            self.extractor,
            "_get_node_text_optimized",
            side_effect=["Title\n======", "Subtitle\n-------"],
        ):
            headers = []
            self.extractor._extract_setext_headers(mock_root, headers)

            assert len(headers) == 2
            assert headers[0].level == 1
            assert headers[1].level == 2


class TestMarkdownExceptionHandlers:
    """Tests for exception handler paths in various extraction methods"""

    def setup_method(self):
        self.extractor = MarkdownElementExtractor()

    def test_extract_code_blocks_exception(self):
        """Test code block extraction exception handler (lines 207-208)"""
        from unittest.mock import Mock, patch

        mock_tree = Mock()
        mock_root = Mock()
        mock_tree.root_node = mock_root

        # Make _traverse_nodes raise an exception
        with patch.object(
            self.extractor, "_traverse_nodes", side_effect=RuntimeError("traverse error")
        ):
            result = self.extractor.extract_code_blocks(mock_tree, "# test")
            assert result == []

    def test_extract_links_exception_handler(self):
        """Test link extraction exception handler (lines 232-233)"""
        from unittest.mock import Mock, patch

        mock_tree = Mock()
        mock_root = Mock()
        mock_tree.root_node = mock_root

        with patch.object(
            self.extractor, "_traverse_nodes", side_effect=RuntimeError("link error")
        ):
            result = self.extractor.extract_links(mock_tree, "# test")
            assert result == []

    def test_extract_images_exception_handler(self):
        """Test image extraction exception handler (lines 265-266)"""
        from unittest.mock import Mock, patch

        mock_tree = Mock()
        mock_root = Mock()
        mock_tree.root_node = mock_root

        with patch.object(
            self.extractor, "_traverse_nodes", side_effect=RuntimeError("image error")
        ):
            result = self.extractor.extract_images(mock_tree, "# test")
            assert result == []

    def test_extract_references_exception_handler(self):
        """Test reference extraction exception handler (lines 295-296)"""
        from unittest.mock import Mock, patch

        mock_tree = Mock()
        mock_root = Mock()
        mock_tree.root_node = mock_root

        with patch.object(
            self.extractor, "_traverse_nodes", side_effect=RuntimeError("ref error")
        ):
            result = self.extractor.extract_references(mock_tree, "# test")
            assert result == []

    def test_extract_blockquotes_exception_handler(self):
        """Test blockquote extraction exception handler (lines 314-315)"""
        from unittest.mock import Mock, patch

        mock_tree = Mock()
        mock_root = Mock()
        mock_tree.root_node = mock_root

        with patch.object(
            self.extractor, "_traverse_nodes", side_effect=RuntimeError("bq error")
        ):
            result = self.extractor.extract_blockquotes(mock_tree, "# test")
            assert result == []

    def test_extract_horizontal_rules_exception_handler(self):
        """Test horizontal rule extraction exception handler (lines 333-334)"""
        from unittest.mock import Mock, patch

        mock_tree = Mock()
        mock_root = Mock()
        mock_tree.root_node = mock_root

        with patch.object(
            self.extractor, "_traverse_nodes", side_effect=RuntimeError("hr error")
        ):
            result = self.extractor.extract_horizontal_rules(mock_tree, "# test")
            assert result == []

    def test_extract_html_elements_exception_handler(self):
        """Test HTML element extraction exception handler (lines 354-355)"""
        from unittest.mock import Mock, patch

        mock_tree = Mock()
        mock_root = Mock()
        mock_tree.root_node = mock_root

        with patch.object(
            self.extractor, "_traverse_nodes", side_effect=RuntimeError("html error")
        ):
            result = self.extractor.extract_html_elements(mock_tree, "# test")
            assert result == []

    def test_extract_text_formatting_exception_handler(self):
        """Test text formatting extraction exception handler (lines 377-378)"""
        from unittest.mock import Mock, patch

        mock_tree = Mock()
        mock_root = Mock()
        mock_tree.root_node = mock_root

        with patch.object(
            self.extractor, "_traverse_nodes", side_effect=RuntimeError("fmt error")
        ):
            result = self.extractor.extract_text_formatting(mock_tree, "# test")
            assert result == []

    def test_extract_footnotes_exception_handler(self):
        """Test footnote extraction exception handler (lines 396-397)"""
        from unittest.mock import Mock, patch

        mock_tree = Mock()
        mock_root = Mock()
        mock_tree.root_node = mock_root

        with patch.object(
            self.extractor, "_traverse_nodes", side_effect=RuntimeError("fn error")
        ):
            result = self.extractor.extract_footnotes(mock_tree, "# test")
            assert result == []

    def test_extract_lists_exception_handler(self):
        """Test list extraction exception handler (lines 415-416)"""
        from unittest.mock import Mock, patch

        mock_tree = Mock()
        mock_root = Mock()
        mock_tree.root_node = mock_root

        with patch.object(
            self.extractor, "_traverse_nodes", side_effect=RuntimeError("list error")
        ):
            result = self.extractor.extract_lists(mock_tree, "# test")
            assert result == []

    def test_extract_tables_exception_handler(self):
        """Test table extraction exception handler (lines 434-435)"""
        from unittest.mock import Mock, patch

        mock_tree = Mock()
        mock_root = Mock()
        mock_tree.root_node = mock_root

        with patch.object(
            self.extractor, "_traverse_nodes", side_effect=RuntimeError("table error")
        ):
            result = self.extractor.extract_tables(mock_tree, "# test")
            assert result == []

    def test_extract_headers_exception_handler(self):
        """Test header extraction exception handler"""
        from unittest.mock import Mock, patch

        mock_tree = Mock()
        mock_root = Mock()
        mock_tree.root_node = mock_root

        with patch.object(
            self.extractor, "_traverse_nodes", side_effect=RuntimeError("header error")
        ):
            result = self.extractor.extract_headers(mock_tree, "# test")
            assert result == []


class TestMarkdownGetNodeTextOptimized:
    """Tests for _get_node_text_optimized edge cases"""

    def setup_method(self):
        self.extractor = MarkdownElementExtractor()

    def test_text_extraction_with_empty_source(self):
        """Test _get_node_text_optimized with empty source code"""
        from unittest.mock import Mock

        self.extractor.source_code = ""
        self.extractor.content_lines = []
        self.extractor._node_text_cache = {}

        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (1, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 0

        result = self.extractor._get_node_text_optimized(mock_node)
        assert result == ""

    def test_text_extraction_bounds_check(self):
        """Test _get_node_text_optimized bounds check (line 482)"""
        from unittest.mock import Mock, patch

        self.extractor.source_code = "hello"
        self.extractor.content_lines = ["hello"]
        self.extractor._node_text_cache = {}

        mock_node = Mock()
        mock_node.start_point = (5, 0)  # Out of bounds
        mock_node.end_point = (10, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 5

        # Make the optimized path fail to reach fallback bounds check
        with patch(
            "tree_sitter_analyzer.languages.markdown_plugin.extract_text_slice",
            side_effect=RuntimeError("slice error"),
        ):
            result = self.extractor._get_node_text_optimized(mock_node)
            assert result == ""

    def test_text_extraction_exception_fallback(self):
        """Test _get_node_text_optimized fallback after optimized path fails (lines 514-516)"""
        from unittest.mock import Mock, patch

        self.extractor.source_code = "test"
        self.extractor.content_lines = ["test"]
        self.extractor._node_text_cache = {}

        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 4)
        mock_node.start_byte = 0
        mock_node.end_byte = 4

        # Mock safe_encode to raise an exception, forcing fallback path
        with patch(
            "tree_sitter_analyzer.languages.markdown_plugin.safe_encode",
            side_effect=RuntimeError("encode error"),
        ):
            result = self.extractor._get_node_text_optimized(mock_node)
            # Fallback extraction should succeed and return the text
            assert result == "test"
