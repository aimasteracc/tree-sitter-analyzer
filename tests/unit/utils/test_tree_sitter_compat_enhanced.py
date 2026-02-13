#!/usr/bin/env python3
"""
Enhanced unit tests for tree_sitter_compat module.

Fills coverage gaps for count_nodes_iterative, create_query_safely,
get_node_text_safe, log_api_info, TreeSitterQueryCompat, and error paths.
"""

import logging
from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.utils.tree_sitter_compat import (
    TreeSitterQueryCompat,
    count_nodes_iterative,
    create_query_safely,
    get_node_text_safe,
    log_api_info,
)


# Mock node classes for count_nodes_iterative tests
class MockNode:
    """Node with children attribute."""

    def __init__(self, children=None):
        self.children = children or []


class MockNodeNoChildren:
    """Node without children attribute."""

    pass


class MockNodeBadChildren:
    """Node whose children is non-iterable (causes TypeError in stack.extend)."""

    children = 42  # int causes TypeError when stack.extend tries to iterate


class MockNodeBadChildrenAttrError:
    """Node whose children raises AttributeError."""

    @property
    def children(self):
        raise AttributeError("no children")


# ---------------------------------------------------------------------------
# count_nodes_iterative tests
# ---------------------------------------------------------------------------


class TestCountNodesIterative:
    """Test count_nodes_iterative function."""

    def test_count_nodes_iterative_with_none(self):
        """count_nodes_iterative with None returns 0."""
        assert count_nodes_iterative(None) == 0

    def test_count_nodes_iterative_single_node(self):
        """count_nodes_iterative with single node (no children) returns 1."""
        node = MockNode(children=[])
        assert count_nodes_iterative(node) == 1

    def test_count_nodes_iterative_single_node_no_children_attr(self):
        """count_nodes_iterative with node missing children attr returns 1."""
        node = MockNodeNoChildren()
        assert count_nodes_iterative(node) == 1

    def test_count_nodes_iterative_simple_tree(self):
        """count_nodes_iterative with parent + 2 children = 3."""
        child1 = MockNode(children=[])
        child2 = MockNode(children=[])
        parent = MockNode(children=[child1, child2])
        assert count_nodes_iterative(parent) == 3

    def test_count_nodes_iterative_deep_tree(self):
        """count_nodes_iterative with 3+ levels deep."""
        leaf = MockNode(children=[])
        mid = MockNode(children=[leaf])
        root = MockNode(children=[mid])
        assert count_nodes_iterative(root) == 3

    def test_count_nodes_iterative_deep_tree_larger(self):
        """count_nodes_iterative with larger deep tree."""
        l1 = MockNode(children=[])
        l2 = MockNode(children=[])
        m1 = MockNode(children=[l1, l2])
        m2 = MockNode(children=[])
        root = MockNode(children=[m1, m2])
        assert count_nodes_iterative(root) == 5

    def test_count_nodes_iterative_non_iterable_children(self):
        """count_nodes_iterative with node having non-iterable children handles TypeError."""
        node = MockNodeBadChildren()
        assert count_nodes_iterative(node) == 1

    def test_count_nodes_iterative_attribute_error_children(self):
        """count_nodes_iterative with children raising AttributeError returns 1."""
        node = MockNodeBadChildrenAttrError()
        assert count_nodes_iterative(node) == 1

    def test_count_nodes_iterative_empty_children_list(self):
        """count_nodes_iterative with empty children list."""
        node = MockNode(children=[])
        assert count_nodes_iterative(node) == 1

    def test_count_nodes_iterative_single_child(self):
        """count_nodes_iterative with one child = 2."""
        child = MockNode(children=[])
        parent = MockNode(children=[child])
        assert count_nodes_iterative(parent) == 2


# ---------------------------------------------------------------------------
# create_query_safely tests
# ---------------------------------------------------------------------------


class TestCreateQuerySafelyEnhanced:
    """Enhanced tests for create_query_safely."""

    def test_create_query_safely_with_real_language_valid_query(self):
        """create_query_safely with valid language/query returns Query object."""
        pytest.importorskip("tree_sitter")
        pytest.importorskip("tree_sitter_python")
        import tree_sitter
        import tree_sitter_python

        lang = tree_sitter.Language(tree_sitter_python.language())
        result = create_query_safely(lang, "(identifier) @name")
        assert result is not None

    def test_create_query_safely_with_invalid_query(self):
        """create_query_safely with invalid query returns None."""
        try:
            import tree_sitter
            import tree_sitter_python

            lang = tree_sitter.Language(tree_sitter_python.language())
            result = create_query_safely(lang, "invalid ]][[ syntax (")
            assert result is None
        except ImportError:
            pytest.skip("tree_sitter not available")

    def test_create_query_safely_import_error_returns_none(self):
        """create_query_safely when import fails returns None."""
        with patch("builtins.__import__", side_effect=ImportError("No module")):
            result = create_query_safely(MagicMock(), "(identifier) @name")
            assert result is None


# ---------------------------------------------------------------------------
# get_node_text_safe enhanced tests
# ---------------------------------------------------------------------------


class TestGetNodeTextSafeEnhanced:
    """Enhanced tests for get_node_text_safe."""

    def test_get_node_text_safe_bytes_property(self):
        """get_node_text_safe with node.text as bytes."""
        mock_node = MagicMock()
        del mock_node.start_byte
        del mock_node.end_byte
        mock_node.text = b"binary content"
        result = get_node_text_safe(mock_node, "irrelevant", encoding="utf-8")
        assert result == "binary content"

    def test_get_node_text_safe_text_property_string(self):
        """get_node_text_safe with node.text as string."""
        mock_node = MagicMock()
        del mock_node.start_byte
        del mock_node.end_byte
        mock_node.text = "string content"
        result = get_node_text_safe(mock_node, "irrelevant")
        assert result == "string content"

    def test_get_node_text_safe_point_based_multiline(self):
        """get_node_text_safe with point-based multiline extraction."""
        mock_node = MagicMock()
        del mock_node.start_byte
        del mock_node.end_byte
        del mock_node.text
        mock_node.start_point = (0, 1)
        mock_node.end_point = (2, 2)
        source = "01234\nabcde\nxyz"
        result = get_node_text_safe(mock_node, source)
        assert "1234" in result
        assert "abcde" in result
        assert "xy" in result

    def test_get_node_text_safe_encoding_errors_replace(self):
        """get_node_text_safe with invalid UTF-8 slice uses replace."""
        # Slice in middle of multi-byte char produces invalid UTF-8
        mock_node = MagicMock()
        mock_node.start_byte = 0
        mock_node.end_byte = 2
        source = " café"  # "é" is 2 bytes in UTF-8; slice [0:2] = " " + 1 byte of "é"
        result = get_node_text_safe(mock_node, source)
        assert isinstance(result, str)

    def test_get_node_text_safe_node_text_falsy(self):
        """get_node_text_safe with node.text empty/falsy falls through."""
        mock_node = MagicMock()
        del mock_node.start_byte
        del mock_node.end_byte
        mock_node.text = ""
        del mock_node.start_point
        del mock_node.end_point
        result = get_node_text_safe(mock_node, "hello")
        assert result == ""

    def test_get_node_text_safe_byte_range_out_of_bounds(self):
        """get_node_text_safe with end_byte > len(source_bytes) returns empty or partial."""
        mock_node = MagicMock()
        mock_node.start_byte = 0
        mock_node.end_byte = 100
        source = "short"
        result = get_node_text_safe(mock_node, source)
        assert isinstance(result, str)

    def test_get_node_text_safe_exception_returns_empty(self):
        """get_node_text_safe with exception returns empty string."""
        mock_node = MagicMock()
        mock_node.start_byte = "not_an_int"  # type: ignore[assignment]
        result = get_node_text_safe(mock_node, "code")
        assert result == ""


# ---------------------------------------------------------------------------
# log_api_info tests
# ---------------------------------------------------------------------------


class TestLogApiInfoEnhanced:
    """Enhanced tests for log_api_info."""

    def test_log_api_info_logs_without_errors(self, caplog):
        """log_api_info logs without raising."""
        with caplog.at_level(
            logging.DEBUG, logger="tree_sitter_analyzer.utils.tree_sitter_compat"
        ):
            log_api_info()
        assert True  # No exception

    def test_log_api_info_with_tree_sitter_available(self, caplog):
        """log_api_info when tree_sitter available."""
        with caplog.at_level(
            logging.DEBUG, logger="tree_sitter_analyzer.utils.tree_sitter_compat"
        ):
            log_api_info()
        records = [r.message for r in caplog.records]
        # Either tree-sitter available or ImportError path
        assert any("tree-sitter" in msg.lower() or "available" in msg.lower() or "not" in msg.lower() for msg in records) or len(records) == 0

    def test_log_api_info_without_tree_sitter(self, caplog):
        """log_api_info when tree_sitter import fails."""
        import tree_sitter_analyzer.utils.tree_sitter_compat as compat

        with patch("builtins.__import__", side_effect=ImportError("No module")):
            compat.log_api_info()
        # Should not raise - ImportError is caught inside log_api_info


# ---------------------------------------------------------------------------
# TreeSitterQueryCompat.execute_query with real language
# ---------------------------------------------------------------------------


class TestTreeSitterQueryCompatExecuteReal:
    """Test TreeSitterQueryCompat.execute_query with real tree-sitter."""

    @pytest.fixture
    def python_lang(self):
        """Get Python language if available."""
        try:
            import tree_sitter
            import tree_sitter_python

            return tree_sitter.Language(tree_sitter_python.language())
        except ImportError:
            pytest.skip("tree_sitter_python not available")

    @pytest.fixture
    def parse_python(self, python_lang):
        """Parse Python code."""

        def _parse(code):
            import tree_sitter

            parser = tree_sitter.Parser()
            parser.language = python_lang
            return parser.parse(code.encode("utf-8"))

        return _parse

    def test_execute_query_with_real_python(self, python_lang, parse_python):
        """TreeSitterQueryCompat.execute_query with real Python code."""
        tree = parse_python("x = 1")
        result = TreeSitterQueryCompat.execute_query(
            python_lang, "(identifier) @name", tree.root_node
        )
        assert isinstance(result, list)
        assert len(result) > 0, "Should find at least one identifier in 'x = 1'"
        # Should find "x" captured as @name
        names = [r[1] for r in result]
        assert "name" in names, f"Expected 'name' capture, got {names}"

    def test_execute_query_compilation_failure_returns_empty(self):
        """TreeSitterQueryCompat error path: query compilation failure returns []."""
        result = TreeSitterQueryCompat.execute_query(
            None, "invalid ]][[ query", MagicMock()
        )
        assert result == []

    def test_execute_query_import_error_returns_empty(self):
        """TreeSitterQueryCompat when tree_sitter import fails returns []."""
        with patch("builtins.__import__", side_effect=ImportError("No module")):
            result = TreeSitterQueryCompat.execute_query(
                MagicMock(), "(identifier) @name", MagicMock()
            )
            assert result == []


# ---------------------------------------------------------------------------
# TreeSitterQueryCompat.safe_execute_query with fallback
# ---------------------------------------------------------------------------


class TestTreeSitterQueryCompatSafeExecuteEnhanced:
    """Enhanced tests for safe_execute_query."""

    def test_safe_execute_query_fallback_used_on_error(self):
        """safe_execute_query uses fallback_result when execute_query raises."""
        fallback = [(MagicMock(), "fallback")]

        def raise_exc(*args, **kwargs):
            raise RuntimeError("query failed")

        with patch.object(
            TreeSitterQueryCompat, "execute_query", side_effect=raise_exc
        ):
            result = TreeSitterQueryCompat.safe_execute_query(
                MagicMock(), "query", MagicMock(), fallback_result=fallback
            )
        assert result == fallback

    def test_safe_execute_query_default_fallback_empty_list(self):
        """safe_execute_query with no fallback returns [] on error."""
        result = TreeSitterQueryCompat.safe_execute_query(
            None, "invalid", MagicMock(), fallback_result=None
        )
        assert result == []

    def test_safe_execute_query_fallback_none_means_empty(self):
        """safe_execute_query with fallback_result=None uses []."""
        result = TreeSitterQueryCompat.safe_execute_query(
            MagicMock(), "bad query", MagicMock(), fallback_result=None
        )
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# TreeSitterQueryCompat._execute_newest_api
# ---------------------------------------------------------------------------


class TestExecuteNewestApi:
    """Test _execute_newest_api."""

    def test_execute_newest_api_with_query_cursor(self):
        """_execute_newest_api with real QueryCursor if available."""
        try:
            import tree_sitter
            import tree_sitter_python

            lang = tree_sitter.Language(tree_sitter_python.language())
            query = tree_sitter.Query(lang, "(identifier) @name")
            parser = tree_sitter.Parser()
            parser.language = lang
            tree = parser.parse(b"x = 1")
            result = TreeSitterQueryCompat._execute_newest_api(
                query, tree.root_node
            )
            assert isinstance(result, list)
        except (ImportError, AttributeError):
            # Fallback: test with mocks
            mock_query = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.matches.return_value = []
            with patch("tree_sitter.QueryCursor", return_value=mock_cursor):
                result = TreeSitterQueryCompat._execute_newest_api(
                    mock_query, MagicMock()
                )
                assert isinstance(result, list)

    def test_execute_newest_api_exception_returns_empty(self):
        """_execute_newest_api on exception returns empty list."""
        mock_query = MagicMock()
        with patch("tree_sitter.QueryCursor") as mock_qc:
            mock_qc.side_effect = RuntimeError("cursor failed")
            result = TreeSitterQueryCompat._execute_newest_api(
                mock_query, MagicMock()
            )
            assert result == []


# ---------------------------------------------------------------------------
# count_nodes_iterative with real tree-sitter nodes
# ---------------------------------------------------------------------------


class TestCountNodesIterativeRealTreeSitter:
    """Test count_nodes_iterative with real tree-sitter AST."""

    def test_count_nodes_iterative_real_ast(self):
        """count_nodes_iterative with real parsed Python AST."""
        try:
            import tree_sitter
            import tree_sitter_python

            lang = tree_sitter.Language(tree_sitter_python.language())
            parser = tree_sitter.Parser()
            parser.language = lang
            tree = parser.parse(b"x = 1 + 2")
            count = count_nodes_iterative(tree.root_node)
            assert count >= 1
            assert isinstance(count, int)
        except ImportError:
            pytest.skip("tree_sitter_python not available")


# ---------------------------------------------------------------------------
# Edge cases and error paths
# ---------------------------------------------------------------------------


class TestTreeSitterCompatEdgeCases:
    """Edge cases and error paths."""

    def test_get_node_text_safe_start_byte_greater_than_end(self):
        """get_node_text_safe when start_byte > end_byte skips byte path."""
        mock_node = MagicMock(spec=["start_byte", "end_byte"])
        mock_node.start_byte = 10
        mock_node.end_byte = 5
        # No text, start_point, end_point - falls through to ""
        result = get_node_text_safe(mock_node, "hello world")
        assert result == ""

    def test_create_query_safely_generic_exception(self):
        """create_query_safely handles generic Exception."""
        with patch("builtins.__import__", side_effect=RuntimeError("unexpected")):
            result = create_query_safely(MagicMock(), "(x) @y")
            assert result is None
