"""Tests for incremental authoritative call-graph pipeline repair."""

from __future__ import annotations

import sqlite3

from tree_sitter_analyzer.cache.callgraph_state import (
    CALL_GRAPH_PIPELINE_VERSION,
    call_graph_built,
    mark_call_graph_built_strict,
)
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
