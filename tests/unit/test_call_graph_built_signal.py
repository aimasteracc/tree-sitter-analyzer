"""Regression coverage for authoritative call-graph-built state (#708)."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer import _ast_cache_callgraph_state as callgraph_state
from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.mcp.tools.callees_tool import CodeGraphCalleesTool
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool
from tree_sitter_analyzer.mcp.tools.codegraph_relation_tool import (
    CodeGraphRelationToolMixin,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_call_graph_state_marker_round_trip() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        assert callgraph_state.call_graph_built(conn) is False

        callgraph_state.mark_call_graph_built(conn)
        assert callgraph_state.call_graph_built(conn) is True

        callgraph_state.clear_call_graph_built(conn)
        assert callgraph_state.call_graph_built(conn) is False
    finally:
        conn.close()


def test_call_graph_state_write_failures_do_not_raise() -> None:
    class BrokenConn:
        def execute(self, *args: object, **kwargs: object) -> object:
            raise sqlite3.OperationalError("locked")

        def commit(self) -> None:
            raise AssertionError("commit should not run after execute fails")

    broken = BrokenConn()

    callgraph_state.mark_call_graph_built(broken)  # type: ignore[arg-type]
    callgraph_state.clear_call_graph_built(broken)  # type: ignore[arg-type]


def test_call_graph_built_false_when_state_table_has_no_row() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute(
            "CREATE TABLE ast_call_graph_state "
            "(id INTEGER PRIMARY KEY, built INTEGER NOT NULL, built_at REAL NOT NULL)"
        )
        conn.commit()

        assert callgraph_state.call_graph_built(conn) is False
    finally:
        conn.close()


def test_call_graph_built_supports_tuple_rows() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        callgraph_state.mark_call_graph_built(conn)

        assert callgraph_state.call_graph_built(conn) is True
    finally:
        conn.close()


def _seed_partial_ast_cache_without_call_graph(root: Path) -> None:
    """Create an AST-cache row that predates the call-graph-built marker."""
    source = "def solo():\n    return 1\n"
    source_path = root / "solo.py"
    source_path.write_text(source, encoding="utf-8")

    cache = ASTCache(str(root))
    conn = cache.get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO ast_index "
        "(file_path, content_hash, language, mtime_ns, file_size, "
        "extractor_version, symbols_json, imports_json, structure_json, indexed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "solo.py",
            "partial-cache-without-call-graph",
            "python",
            source_path.stat().st_mtime_ns,
            len(source.encode("utf-8")),
            0,
            json.dumps(
                {
                    "symbols": [
                        {
                            "name": "solo",
                            "kind": "function",
                            "line": 1,
                            "end_line": 2,
                            "params": "",
                        }
                    ]
                }
            ),
            "[]",
            "{}",
            "2026-06-15T00:00:00+00:00",
        ),
    )
    conn.commit()
    cache.close()


def _seed_call_edges_without_built_marker(root: Path) -> None:
    """Create real CALLS edges while leaving the authoritative marker false."""
    source_path = root / "calls.py"
    source_path.write_text(
        "def caller():\n    target()\n\ndef target():\n    return 1\n",
        encoding="utf-8",
    )
    cache = ASTCache(str(root))
    try:
        result = cache.index_file(str(source_path))
        assert result["status"] == "indexed"
        assert cache.has_call_edges() is True
        callgraph_state.clear_call_graph_built(cache.get_conn())
        assert cache.call_graph_built() is False
    finally:
        cache.close()


def _call_graph_built_at(cache: ASTCache) -> float:
    row = (
        cache.get_conn()
        .execute("SELECT built_at FROM ast_call_graph_state WHERE id = 1")
        .fetchone()
    )
    assert row is not None
    return float(row["built_at"])


def test_resolve_only_does_not_mark_call_graph_built_for_partial_cache(
    tmp_path: Path,
) -> None:
    _seed_partial_ast_cache_without_call_graph(tmp_path)

    cache = ASTCache(str(tmp_path))
    try:
        assert cache.call_graph_built() is False

        result = cache.index_project(resolve_only=True)

        assert result["mode_used"] == "resolve_only"
        assert cache.call_graph_built() is False
    finally:
        cache.close()


def test_partial_incremental_index_does_not_stamp_call_graph_built_marker(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def b():\n    return 2\n", encoding="utf-8")

    cache = ASTCache(str(tmp_path))
    try:
        result = cache.index_project(max_files=1, workers=0)

        assert result["indexed"] == 1
        assert result["truncated_by_max_files"] is True
        assert cache.call_graph_built() is False
    finally:
        cache.close()


def test_single_file_reindex_refreshes_existing_call_graph_built_marker(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "sample.py"
    source_path.write_text("def sample():\n    return 1\n", encoding="utf-8")

    cache = ASTCache(str(tmp_path))
    try:
        result = cache.index_project(force=True, workers=0)
        assert result["indexed"] == 1
        assert cache.call_graph_built() is True
        before = _call_graph_built_at(cache)

        time.sleep(0.01)
        source_path.write_text("def sample():\n    return 2\n", encoding="utf-8")
        single = cache.index_file(str(source_path))

        assert single["status"] == "indexed"
        assert cache.call_graph_built() is True
        assert _call_graph_built_at(cache) > before
    finally:
        cache.close()


def test_cache_call_graph_built_degrades_false_on_reader_error() -> None:
    class BrokenCache:
        def call_graph_built(self) -> bool:
            raise RuntimeError("boom")

    assert CodeGraphRelationToolMixin._cache_call_graph_built(BrokenCache()) is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_cls", "count_key"),
    [
        (CodeGraphCallersTool, "caller_count"),
        (CodeGraphCalleesTool, "callee_count"),
    ],
)
async def test_partial_ast_cache_without_call_graph_marker_hints_full_index(
    tmp_path: Path,
    tool_cls: type[CodeGraphCallersTool] | type[CodeGraphCalleesTool],
    count_key: str,
) -> None:
    _seed_partial_ast_cache_without_call_graph(tmp_path)

    tool = tool_cls(str(tmp_path))
    result = await tool.execute({"function_name": "solo", "output_format": "json"})

    assert result["verdict"] == "NOT_FOUND"
    assert result[count_key] == 0
    assert "--full-index" in result["next_step"]
    assert result["agent_summary"]["next_step"] == result["next_step"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_cls", "count_key"),
    [
        (CodeGraphCallersTool, "caller_count"),
        (CodeGraphCalleesTool, "callee_count"),
    ],
)
async def test_existing_edges_without_call_graph_marker_still_hint_full_index(
    tmp_path: Path,
    tool_cls: type[CodeGraphCallersTool] | type[CodeGraphCalleesTool],
    count_key: str,
) -> None:
    _seed_call_edges_without_built_marker(tmp_path)

    tool = tool_cls(str(tmp_path))
    result = await tool.execute({"function_name": "missing", "output_format": "json"})

    assert result["verdict"] == "NOT_FOUND"
    assert result[count_key] == 0
    assert "--full-index" in result["next_step"]
    assert result["agent_summary"]["next_step"] == result["next_step"]


@pytest.mark.timeout(60)
def test_cli_callers_partial_ast_cache_matches_mcp_full_index_hint(
    tmp_path: Path,
) -> None:
    _seed_partial_ast_cache_without_call_graph(tmp_path)

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "tree_sitter_analyzer",
            "--callers",
            "solo",
            "--project-root",
            str(tmp_path),
            "--format",
            "json",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    result: dict[str, Any] = json.loads(proc.stdout)
    assert result["verdict"] == "NOT_FOUND"
    assert result["caller_count"] == 0
    assert "--full-index" in result["next_step"]
    assert result["agent_summary"]["next_step"] == result["next_step"]


# --- _completed_full_index_sweep (staticmethod) -----------------------------


def test_completed_full_index_sweep_true_when_clean() -> None:
    stats = {"truncated_by_max_files": False, "errors": 0, "skipped": 0}
    assert ASTCache._completed_full_index_sweep(stats) is True


def test_completed_full_index_sweep_false_when_truncated() -> None:
    stats = {"truncated_by_max_files": True, "errors": 0, "skipped": 0}
    assert ASTCache._completed_full_index_sweep(stats) is False


def test_completed_full_index_sweep_false_when_errors() -> None:
    stats = {"truncated_by_max_files": False, "errors": 1, "skipped": 0}
    assert ASTCache._completed_full_index_sweep(stats) is False


def test_completed_full_index_sweep_false_when_skipped() -> None:
    stats = {"truncated_by_max_files": False, "errors": 0, "skipped": 1}
    assert ASTCache._completed_full_index_sweep(stats) is False


def test_completed_full_index_sweep_true_on_empty_stats_defaults() -> None:
    # Missing keys default to not-truncated / 0 errors / 0 skipped.
    assert ASTCache._completed_full_index_sweep({}) is True


# --- _indexed_source_files_are_complete -------------------------------------


def test_indexed_source_files_complete_false_on_empty_source_set(
    tmp_path: Path,
) -> None:
    # No source files on disk → degenerate empty set → never "complete".
    cache = ASTCache(str(tmp_path))
    try:
        assert cache._indexed_source_files_are_complete() is False
    finally:
        cache.close()


def test_indexed_source_files_complete_true_when_index_matches_source(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    try:
        result = cache.index_project(force=True, workers=0)
        assert result["indexed"] == 1
        assert cache._indexed_source_files_are_complete() is True
    finally:
        cache.close()


def test_indexed_source_files_complete_false_when_source_added_after_index(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    try:
        result = cache.index_project(force=True, workers=0)
        assert result["indexed"] == 1
        # A new source file the index has never seen breaks the equality.
        (tmp_path / "b.py").write_text("def b():\n    return 2\n", encoding="utf-8")
        assert cache._indexed_source_files_are_complete() is False
    finally:
        cache.close()


# --- _mark_single_file_index_complete_if_needed -----------------------------


def test_mark_single_file_complete_skips_non_indexed_status(
    tmp_path: Path,
) -> None:
    cache = ASTCache(str(tmp_path))
    try:
        assert cache.call_graph_built() is False
        # status not in {indexed, cached} → early return, no marker written.
        cache._mark_single_file_index_complete_if_needed(
            had_built_marker=True, result={"status": "error", "reason": "boom"}
        )
        assert cache.call_graph_built() is False
    finally:
        cache.close()


def test_mark_single_file_complete_skips_skipped_status(
    tmp_path: Path,
) -> None:
    cache = ASTCache(str(tmp_path))
    try:
        assert cache.call_graph_built() is False
        cache._mark_single_file_index_complete_if_needed(
            had_built_marker=True, result={"status": "skipped"}
        )
        assert cache.call_graph_built() is False
    finally:
        cache.close()


def test_mark_single_file_complete_no_marker_when_index_incomplete(
    tmp_path: Path,
) -> None:
    # status is indexable, but there was no prior marker and the source set is
    # not fully indexed → neither branch fires, falls through without marking.
    (tmp_path / "unindexed.py").write_text("def u():\n    return 0\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    try:
        assert cache.call_graph_built() is False
        assert cache._indexed_source_files_are_complete() is False
        cache._mark_single_file_index_complete_if_needed(
            had_built_marker=False, result={"status": "indexed"}
        )
        assert cache.call_graph_built() is False
    finally:
        cache.close()
