#!/usr/bin/env python3
"""Unit tests for tree_sitter_compat — 9% → 65%+ coverage with 22 tests."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.utils.tree_sitter_compat import (
    TreeSitterQueryCompat,
    count_nodes_iterative,
    create_query_safely,
    get_node_text_safe,
    log_api_info,
)


class TestCreateQuerySafely:
    def test_ok(self):
        m = MagicMock()
        m.Query = MagicMock()
        with patch.dict(sys.modules, {"tree_sitter": m}):
            assert create_query_safely(MagicMock(), "q") is m.Query()

    def test_fail(self):
        m = MagicMock()
        m.Query.side_effect = Exception()
        with patch.dict(sys.modules, {"tree_sitter": m}):
            assert create_query_safely(MagicMock(), "q") is None


class TestGetNodeTextSafe:
    def test_bytes(self):
        n = MagicMock()
        n.start_byte = 0
        n.end_byte = 5
        assert get_node_text_safe(n, "hello") == "hello"

    def test_bytes_oob(self):
        n = MagicMock()
        n.start_byte = 100
        n.end_byte = 200
        n.text = b"fallback"
        assert get_node_text_safe(n, "short") == "fallback"

    def test_text_bytes(self):
        n = MagicMock()
        del n.start_byte
        del n.end_byte
        n.text = b"hi"
        assert get_node_text_safe(n, "x") == "hi"

    def test_text_str(self):
        n = MagicMock()
        del n.start_byte
        del n.end_byte
        n.text = "hi"
        assert "hi" in get_node_text_safe(n, "x")

    def test_point_single(self):
        n = MagicMock()
        del n.start_byte
        del n.end_byte
        del n.text
        n.start_point = (0, 6)
        n.end_point = (0, 11)
        assert get_node_text_safe(n, "hello world") == "world"

    def test_point_multi(self):
        n = MagicMock()
        del n.start_byte
        del n.end_byte
        del n.text
        n.start_point = (0, 6)
        n.end_point = (2, 2)
        r = get_node_text_safe(n, "hello w\nmid\nend")
        assert "w" in r

    def test_no_attrs(self):
        n = MagicMock()
        del n.start_byte
        del n.end_byte
        del n.text
        del n.start_point
        del n.end_point
        assert get_node_text_safe(n, "x") == ""


class TestCountNodesIterative:
    def test_none(self):
        assert count_nodes_iterative(None) == 0

    def test_one(self):
        n = MagicMock()
        n.children = []
        assert count_nodes_iterative(n) == 1

    def test_tree(self):
        a = MagicMock(children=[])
        b = MagicMock(children=[])
        p = MagicMock(children=[a, b])
        assert count_nodes_iterative(p) == 3

    def test_no_children_attr(self):
        n = MagicMock()
        del n.children
        assert count_nodes_iterative(n) == 1


class TestLogApiInfo:
    def test_no_raise(self):
        """Test that log_api_info does not raise and returns None."""
        result = log_api_info()
        assert result is None


class TestQueryCompat:
    def test_safe_ok(self):
        with patch.object(
            TreeSitterQueryCompat, "execute_query", return_value=[("n", "c")]
        ):
            assert TreeSitterQueryCompat.safe_execute_query(None, "", None) == [
                ("n", "c")
            ]

    def test_safe_fallback(self):
        with patch.object(
            TreeSitterQueryCompat, "execute_query", side_effect=Exception
        ):
            assert TreeSitterQueryCompat.safe_execute_query(None, "", None, []) == []

    def test_old_callable_tuple(self):
        q = MagicMock(return_value=[(MagicMock(), "x")])
        assert len(TreeSitterQueryCompat._execute_old_api(q, MagicMock())) == 1

    def test_old_callable_obj(self):
        m = MagicMock()
        m.node = MagicMock()
        m.name = "x"
        q = MagicMock(return_value=[m])
        r = TreeSitterQueryCompat._execute_old_api(q, MagicMock())
        assert r[0][1] == "x"

    def test_old_non_callable(self):
        assert (
            TreeSitterQueryCompat._execute_old_api(MagicMock(spec=[]), MagicMock())
            == []
        )

    def test_old_exception(self):
        q = MagicMock(side_effect=Exception)
        assert TreeSitterQueryCompat._execute_old_api(q, MagicMock()) == []

    def test_modern_exception(self):
        q = MagicMock()
        q.matches.side_effect = Exception()
        with pytest.raises(Exception):  # noqa: B017
            TreeSitterQueryCompat._execute_modern_api(q, MagicMock())

    def test_legacy_exception(self):
        q = MagicMock()
        q.captures.side_effect = Exception()
        with pytest.raises(Exception):  # noqa: B017
            TreeSitterQueryCompat._execute_legacy_api(q, MagicMock())
