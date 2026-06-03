"""TDD tests for BFS graph traversal in _ast_cache_graph.py.

These tests were written BEFORE the extraction of _bfs_callers/_bfs_callees
from ASTCache into module-level functions. They pin the exact contract so
the refactoring stays behaviour-preserving.

All tests use an in-memory SQLite connection with the minimal call-edges
schema — no ASTCache instance needed, proving the functions are pure.
"""

from __future__ import annotations

import json
import sqlite3

from tree_sitter_analyzer._ast_cache_graph import bfs_callees, bfs_callers
from tree_sitter_analyzer.graph.edge_store import EdgeKind, symbol_node

# ---------------------------------------------------------------------------
# Fixtures
#
# B1.2 moved the CALLS read path from ``ast_call_edges`` to the unified
# ``edges`` table.  The fixture therefore populates ``edges`` CALLS rows in the
# exact shape the production write path produces (node ids via ``symbol_node``,
# scalars in the metadata JSON blob, real name/file columns).
# ---------------------------------------------------------------------------


def _make_conn() -> sqlite3.Connection:
    from tree_sitter_analyzer.graph.edge_store import EDGE_STORE_SCHEMA

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(EDGE_STORE_SCHEMA)
    return conn


def _insert_edge(
    conn: sqlite3.Connection,
    caller_name: str,
    caller_file: str,
    callee_name: str,
    file_path: str,
    callee_line: int = 10,
    caller_line: int = 5,
    callee_resolved_file: str = "",
    callee_full: str = "",
) -> None:
    source = symbol_node(caller_file, caller_name, caller_line)
    target_file = callee_resolved_file or caller_file
    target = symbol_node(target_file, callee_name, callee_line)
    metadata = {
        "language": "python",
        "caller_name": caller_name,
        "caller_line": caller_line,
        "callee_name": callee_name,
        "callee_full": callee_full or callee_name,
        "callee_resolution": "unknown",
        "callee_resolved_file": callee_resolved_file,
    }
    # B1.3: resolution scalars are real columns (the readers no longer
    # json_extract them); populate both so this fixture matches production rows.
    conn.execute(
        "INSERT OR REPLACE INTO edges "
        "(source_node_id, target_node_id, kind, line, provenance, metadata, "
        " caller_name, callee_name, file_path, caller_line, callee_full, "
        " callee_line, language, callee_resolution, callee_resolved_file) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            source,
            target,
            EdgeKind.CALLS.value,
            callee_line,
            "tree-sitter",
            json.dumps(metadata, ensure_ascii=False, sort_keys=True),
            caller_name,
            callee_name,
            caller_file,
            caller_line,
            callee_full or callee_name,
            callee_line,
            "python",
            "unknown",
            callee_resolved_file,
        ),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# bfs_callers
# ---------------------------------------------------------------------------


class TestBfsCallers:
    def test_no_callers_returns_empty(self):
        conn = _make_conn()
        result = bfs_callers(conn, "orphan", None, max_depth=1)
        assert result == []

    def test_single_caller_found_no_file(self):
        conn = _make_conn()
        _insert_edge(conn, "alpha", "a.py", "target", "b.py")
        result = bfs_callers(conn, "target", None, max_depth=1)
        assert len(result) == 1
        assert result[0]["caller_name"] == "alpha"
        assert result[0]["caller_file"] == "a.py"

    def test_single_caller_found_with_file(self):
        conn = _make_conn()
        _insert_edge(
            conn, "alpha", "a.py", "target", "b.py", callee_resolved_file="b.py"
        )
        result = bfs_callers(conn, "target", "b.py", max_depth=1)
        assert len(result) == 1
        assert result[0]["caller_name"] == "alpha"

    def test_file_filter_excludes_other_file(self):
        conn = _make_conn()
        _insert_edge(
            conn, "alpha", "a.py", "target", "b.py", callee_resolved_file="b.py"
        )
        _insert_edge(
            conn, "beta", "c.py", "target", "d.py", callee_resolved_file="d.py"
        )
        result = bfs_callers(conn, "target", "b.py", max_depth=1)
        assert len(result) == 1
        assert result[0]["caller_name"] == "alpha"

    def test_depth_field_populated(self):
        conn = _make_conn()
        _insert_edge(conn, "alpha", "a.py", "target", "b.py")
        result = bfs_callers(conn, "target", None, max_depth=1)
        assert result[0]["depth"] == 1

    def test_deduplication_via_visited_set(self):
        """Same caller-file-line edge should not appear twice."""
        conn = _make_conn()
        # Insert same edge twice with different callee_full
        _insert_edge(
            conn,
            "alpha",
            "a.py",
            "target",
            "b.py",
            caller_line=5,
            callee_full="module.target",
        )
        _insert_edge(
            conn,
            "alpha",
            "a.py",
            "target",
            "b.py",
            caller_line=5,
            callee_full="other.target",
        )
        result = bfs_callers(conn, "target", None, max_depth=1)
        # Dedup key is caller_file:caller_name:caller_line — first win
        assert len(result) == 1

    def test_max_depth_zero_returns_empty(self):
        conn = _make_conn()
        _insert_edge(conn, "alpha", "a.py", "target", "b.py")
        result = bfs_callers(conn, "target", None, max_depth=0)
        assert result == []

    def test_callee_file_falls_back_to_file_path(self):
        """When callee_resolved_file is empty, callee_file in result = file_path.

        In the unified ``edges`` model ``file_path`` is the caller's file, so an
        unresolved callee's reported file falls back to that caller file.
        """
        conn = _make_conn()
        _insert_edge(conn, "alpha", "a.py", "target", "b.py", callee_resolved_file="")
        result = bfs_callers(conn, "target", None, max_depth=1)
        assert result[0]["callee_file"] == "a.py"  # falls back to caller file_path

    def test_callee_file_uses_resolved_when_present(self):
        conn = _make_conn()
        _insert_edge(
            conn, "alpha", "a.py", "target", "b.py", callee_resolved_file="resolved.py"
        )
        result = bfs_callers(conn, "target", None, max_depth=1)
        assert result[0]["callee_file"] == "resolved.py"

    def test_fallback_file_path_query_when_resolved_file_not_found(self):
        """When querying with callee_file, try callee_resolved_file first,
        then fall back to file_path query.

        With unified ``edges`` the unresolved edge's ``file_path`` is the
        caller file (``a.py``), so the fallback query matches on that.
        """
        conn = _make_conn()
        # Edge has callee_resolved_file empty; file_path = caller file a.py
        _insert_edge(conn, "alpha", "a.py", "target", "b.py", callee_resolved_file="")
        result = bfs_callers(conn, "target", "a.py", max_depth=1)
        assert len(result) == 1
        assert result[0]["caller_name"] == "alpha"

    def test_multiple_callers_all_returned(self):
        conn = _make_conn()
        _insert_edge(conn, "a1", "x.py", "tgt", "y.py", caller_line=1)
        _insert_edge(conn, "a2", "x.py", "tgt", "y.py", caller_line=2)
        _insert_edge(conn, "a3", "z.py", "tgt", "y.py", caller_line=3)
        result = bfs_callers(conn, "tgt", None, max_depth=1)
        assert len(result) == 3
        caller_names = {r["caller_name"] for r in result}
        assert caller_names == {"a1", "a2", "a3"}

    def test_transitive_callers_depth2(self):
        """With max_depth=2, BFS should also return callers-of-callers."""
        conn = _make_conn()
        # root → alpha → target. The first hop's caller is alpha@a.py, so the
        # root→alpha edge must resolve its callee (alpha) to a.py for the
        # second hop to link (file_path is the caller file in unified edges).
        _insert_edge(conn, "alpha", "a.py", "target", "b.py")
        _insert_edge(conn, "root", "r.py", "alpha", "a.py", callee_resolved_file="a.py")
        result = bfs_callers(conn, "target", None, max_depth=2)
        caller_names = {r["caller_name"] for r in result}
        assert "alpha" in caller_names
        assert "root" in caller_names


# ---------------------------------------------------------------------------
# bfs_callees
# ---------------------------------------------------------------------------


class TestBfsCallees:
    def test_no_callees_returns_empty(self):
        conn = _make_conn()
        result = bfs_callees(conn, "leaf", None, max_depth=1)
        assert result == []

    def test_single_callee_found_no_file(self):
        conn = _make_conn()
        _insert_edge(conn, "caller", "a.py", "callee", "a.py")
        result = bfs_callees(conn, "caller", None, max_depth=1)
        assert len(result) == 1
        assert result[0]["callee_name"] == "callee"

    def test_single_callee_found_with_file(self):
        conn = _make_conn()
        _insert_edge(conn, "caller", "a.py", "callee", "a.py")
        result = bfs_callees(conn, "caller", "a.py", max_depth=1)
        assert len(result) == 1
        assert result[0]["callee_name"] == "callee"

    def test_file_filter_works(self):
        conn = _make_conn()
        _insert_edge(conn, "fn", "a.py", "callee1", "a.py")
        _insert_edge(conn, "fn", "b.py", "callee2", "b.py")
        result = bfs_callees(conn, "fn", "a.py", max_depth=1)
        assert len(result) == 1
        assert result[0]["callee_name"] == "callee1"

    def test_depth_field_populated(self):
        conn = _make_conn()
        _insert_edge(conn, "caller", "a.py", "callee", "a.py")
        result = bfs_callees(conn, "caller", None, max_depth=1)
        assert result[0]["depth"] == 1

    def test_deduplication_via_visited_set(self):
        """Same callee-file-line should appear only once."""
        conn = _make_conn()
        _insert_edge(conn, "caller", "a.py", "callee", "a.py", callee_line=10)
        _insert_edge(
            conn,
            "caller",
            "a.py",
            "callee",
            "a.py",
            callee_line=10,
            callee_full="m.callee",
        )
        result = bfs_callees(conn, "caller", None, max_depth=1)
        assert len(result) == 1

    def test_max_depth_zero_returns_empty(self):
        conn = _make_conn()
        _insert_edge(conn, "caller", "a.py", "callee", "a.py")
        result = bfs_callees(conn, "caller", None, max_depth=0)
        assert result == []

    def test_callee_resolved_file_in_result(self):
        conn = _make_conn()
        _insert_edge(
            conn, "caller", "a.py", "callee", "b.py", callee_resolved_file="resolved.py"
        )
        result = bfs_callees(conn, "caller", None, max_depth=1)
        assert result[0]["callee_resolved_file"] == "resolved.py"

    def test_callee_file_falls_back_to_file_path(self):
        # Unified edges: file_path is the caller file, so an unresolved callee
        # reports that caller file as its location.
        conn = _make_conn()
        _insert_edge(conn, "caller", "a.py", "callee", "b.py", callee_resolved_file="")
        result = bfs_callees(conn, "caller", None, max_depth=1)
        assert result[0]["callee_file"] == "a.py"

    def test_multiple_callees_all_returned(self):
        conn = _make_conn()
        _insert_edge(conn, "root", "r.py", "c1", "r.py", callee_line=1)
        _insert_edge(conn, "root", "r.py", "c2", "r.py", callee_line=2)
        _insert_edge(conn, "root", "r.py", "c3", "r.py", callee_line=3)
        result = bfs_callees(conn, "root", None, max_depth=1)
        assert len(result) == 3

    def test_transitive_callees_depth2(self):
        """With max_depth=2, BFS should also return callees of callees."""
        conn = _make_conn()
        # root → alpha → leaf
        _insert_edge(conn, "root", "r.py", "alpha", "a.py")
        _insert_edge(conn, "alpha", "a.py", "leaf", "l.py")
        result = bfs_callees(conn, "root", None, max_depth=2)
        callee_names = {r["callee_name"] for r in result}
        assert "alpha" in callee_names
        assert "leaf" in callee_names
