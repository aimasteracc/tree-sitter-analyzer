"""Tests for incremental authoritative call-graph pipeline repair."""

from __future__ import annotations

import sqlite3

import pytest

from tree_sitter_analyzer.cache.callgraph_state import (
    CALL_GRAPH_PIPELINE_VERSION,
    call_graph_built,
    mark_call_graph_built_strict,
)
from tree_sitter_analyzer.incremental_sync import SyncResult
from tree_sitter_analyzer.incremental_sync_callgraph import (
    pipeline_repair_required,
    run_call_graph_pipeline,
)


class _PipelineCache:
    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.calls: list[str] = []
        self.cross_result: object = {"resolved": 1, "errors": 0}
        self.synapse_result: object = {"resolved": 2, "errors": 0}
        self.unresolved_result: object = {"resolved": 3, "errors": 0}

    def get_conn(self) -> sqlite3.Connection:
        return self.conn

    def backfill_cross_file_edges(self) -> object:
        self.calls.append("cross_file")
        return self.cross_result

    def _run_synapse_backfill(self) -> object:
        self.calls.append("synapse")
        return self.synapse_result

    def _run_unresolved_refs_backfill(self) -> object:
        self.calls.append("unresolved")
        return self.unresolved_result


def test_pipeline_runs_all_three_stages_in_order_with_exact_counters() -> None:
    cache = _PipelineCache()

    complete, resolved = run_call_graph_pipeline(cache)

    assert (complete, resolved, cache.calls) == (
        True,
        2,
        ["cross_file", "synapse", "unresolved"],
    )


def test_cross_file_failure_prevents_pipeline_certification() -> None:
    cache = _PipelineCache()
    cache.cross_result = {"resolved": 0, "errors": 1}

    complete, resolved = run_call_graph_pipeline(cache)
    if complete:
        mark_call_graph_built_strict(cache.conn)

    assert (complete, resolved, call_graph_built(cache.conn)) == (False, 2, False)


def test_nonmapping_stage_prevents_pipeline_certification() -> None:
    cache = _PipelineCache()
    cache.synapse_result = None

    complete, resolved = run_call_graph_pipeline(cache)

    assert (complete, resolved) == (False, 0)


def test_old_pipeline_marker_is_not_current() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE ast_call_graph_state("
        "id INTEGER PRIMARY KEY, built INTEGER NOT NULL, built_at REAL NOT NULL, "
        "pipeline_version INTEGER NOT NULL DEFAULT 0)"
    )
    conn.execute(
        "INSERT INTO ast_call_graph_state VALUES (1, 1, 1.0, ?)",
        (CALL_GRAPH_PIPELINE_VERSION - 1,),
    )

    assert call_graph_built(conn) is False


def test_pipeline_repair_required_for_stale_marker() -> None:
    result = type(
        "Result",
        (),
        {
            "new_files": 0,
            "updated_files": 0,
            "deleted_files": 0,
            "changed_during_run": 0,
        },
    )()

    assert pipeline_repair_required(result, marker_current=False) is True


def test_pipeline_publishes_exact_diagnostic_for_each_failed_stage() -> None:
    # PR #1253 review 3757240532: suppressed failures must reach MCP callers.
    cache = _PipelineCache()
    cache.cross_result = None
    cache.synapse_result = {"resolved": 0, "errors": 2}

    def unresolved_failure() -> object:
        cache.calls.append("unresolved")
        raise RuntimeError("failed")

    cache._run_unresolved_refs_backfill = unresolved_failure
    result = SyncResult()

    complete, resolved = run_call_graph_pipeline(cache, result)

    assert (complete, resolved, result.backfill_errors, result.errors) == (
        False,
        0,
        3,
        3,
    )
    assert result.details == [
        {
            "stage": "cross_file",
            "considered": "backfill",
            "action": "backfill",
            "status": "warning",
            "reason": "BACKFILL_RESULT_NOT_MAPPING",
        },
        {
            "stage": "synapse",
            "considered": "backfill",
            "action": "backfill",
            "status": "warning",
            "reason": "BACKFILL_REPORTED_ERRORS",
        },
        {
            "stage": "unresolved",
            "considered": "backfill",
            "action": "backfill",
            "status": "warning",
            "reason": "BACKFILL_EXCEPTION:RuntimeError",
        },
    ]


def test_noninteger_synapse_resolved_count_is_not_published() -> None:
    # PR #1253: malformed counters cannot cross the pipeline boundary.
    cache = _PipelineCache()
    cache.synapse_result = {"resolved": "2", "errors": 0}

    complete, resolved = run_call_graph_pipeline(cache)

    assert (complete, resolved) == (True, 0)


@pytest.mark.parametrize(
    ("resolved_file", "symbol_id"),
    [("missing.py", None), ("present.py", 999)],
)
def test_dangling_call_resolution_rejects_pipeline_marker(
    resolved_file: str,
    symbol_id: int | None,
) -> None:
    # PR #1253 thread 3761514123: certification rejects both dangling keys.
    from tree_sitter_analyzer.graph.edge_store import EdgeStore

    conn = sqlite3.connect(":memory:")
    EdgeStore(conn)
    conn.execute("CREATE TABLE ast_index (file_path TEXT PRIMARY KEY)")
    conn.execute("INSERT INTO ast_index(file_path) VALUES ('present.py')")
    conn.execute(
        "CREATE TABLE ast_symbol_rows (id INTEGER PRIMARY KEY, file_path TEXT)"
    )
    conn.execute(
        "INSERT INTO edges (source_node_id, target_node_id, kind, "
        "callee_resolved_file, callee_symbol_id) VALUES (?, ?, 'calls', ?, ?)",
        ("caller.py:caller:1", "function:target", resolved_file, symbol_id),
    )

    with pytest.raises(
        sqlite3.OperationalError, match="CALL_GRAPH_DANGLING_RESOLUTION"
    ):
        mark_call_graph_built_strict(conn)

    assert call_graph_built(conn) is False


def test_dangling_resolved_file_without_index_table_is_inconsistent() -> None:
    # PR #1253 thread 3761514123: absence of canonical file rows is fail-closed.
    from tree_sitter_analyzer.cache.callgraph_state import (
        call_graph_edges_are_consistent,
    )
    from tree_sitter_analyzer.graph.edge_store import EdgeStore

    conn = sqlite3.connect(":memory:")
    EdgeStore(conn)
    conn.execute(
        "INSERT INTO edges (source_node_id, target_node_id, kind, "
        "callee_resolved_file) VALUES ('caller', 'target', 'calls', 'missing.py')"
    )

    assert call_graph_edges_are_consistent(conn) is False


def test_dangling_symbol_without_symbol_table_is_inconsistent() -> None:
    # PR #1253 thread 3761514123: absence of canonical symbol rows is fail-closed.
    from tree_sitter_analyzer.cache.callgraph_state import (
        call_graph_edges_are_consistent,
    )
    from tree_sitter_analyzer.graph.edge_store import EdgeStore

    conn = sqlite3.connect(":memory:")
    EdgeStore(conn)
    conn.execute("CREATE TABLE ast_index (file_path TEXT PRIMARY KEY)")
    conn.execute("INSERT INTO ast_index(file_path) VALUES ('present.py')")
    conn.execute(
        "INSERT INTO edges (source_node_id, target_node_id, kind, "
        "callee_resolved_file, callee_symbol_id) "
        "VALUES ('caller', 'target', 'calls', 'present.py', 999)"
    )

    assert call_graph_edges_are_consistent(conn) is False


def test_resolved_symbol_must_belong_to_resolved_file() -> None:
    # PR #1253 thread 3763655048: symbol identity and file target are one fact.
    from tree_sitter_analyzer.cache.callgraph_state import (
        call_graph_edges_are_consistent,
    )
    from tree_sitter_analyzer.graph.edge_store import EdgeStore

    conn = sqlite3.connect(":memory:")
    EdgeStore(conn)
    conn.execute("CREATE TABLE ast_index (file_path TEXT PRIMARY KEY)")
    conn.executemany(
        "INSERT INTO ast_index(file_path) VALUES (?)",
        [("resolved.py",), ("other.py",)],
    )
    conn.execute(
        "CREATE TABLE ast_symbol_rows (id INTEGER PRIMARY KEY, file_path TEXT)"
    )
    conn.execute("INSERT INTO ast_symbol_rows VALUES (7, 'other.py')")
    conn.execute(
        "INSERT INTO edges (source_node_id, target_node_id, kind, "
        "callee_resolved_file, callee_symbol_id) "
        "VALUES ('caller', 'target', 'calls', 'resolved.py', 7)"
    )

    assert call_graph_edges_are_consistent(conn) is False


def test_marker_certification_rechecks_consistency_after_writer_lock(
    monkeypatch,
) -> None:
    # PR #1253 thread 3763600672: marker publication and final check are atomic.
    from tree_sitter_analyzer.cache import callgraph_state

    conn = sqlite3.connect(":memory:")
    checks = iter((True, False))
    monkeypatch.setattr(
        callgraph_state,
        "call_graph_edges_are_consistent",
        lambda _conn: next(checks),
    )

    with pytest.raises(
        sqlite3.OperationalError, match="CALL_GRAPH_DANGLING_RESOLUTION"
    ):
        callgraph_state.mark_call_graph_built_strict(conn)

    rows = conn.execute(
        "SELECT id, built, pipeline_version FROM ast_call_graph_state"
    ).fetchall()
    assert rows == []
