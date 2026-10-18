"""RFC-0032 follow-up (#1664 item 2): ``ensure_indexed`` must not swallow a typed
admission failure on a project that has never been indexed.

Before the fix, a busy publication lease during the first warm made
``ensure_indexed`` log the exception and return ``None``. The MCP incremental
sync route then reported an untyped ``Failed to initialize AST cache`` and the
auto-index warm reported ``auto-index failed``, while the watcher on the same
project returned the typed ``INDEX_WRITER_BUSY`` payload.

The interleaving is deterministic: another connection holds the publication
lease (``BEGIN IMMEDIATE`` on ``publication.lock.db``) for the whole call.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

import tree_sitter_analyzer.cache.generation_store as store_owner
from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.cache.admission import (
    INDEX_WRITER_BUSY,
    IndexWriteAdmissionError,
)
from tree_sitter_analyzer.cache.generation_routing import generation_storage_path
from tree_sitter_analyzer.mcp.tools.auto_index_tool import CodeGraphAutoIndexTool
from tree_sitter_analyzer.mcp.tools.incremental_sync_tool import (
    CodeGraphIncrementalSyncTool,
)
from tree_sitter_analyzer.mcp.utils import auto_index_guard
from tree_sitter_analyzer.mcp.utils.auto_index_guard import ensure_indexed, is_indexed

_BUSY = {
    "success": False,
    "verdict": "ERROR",
    "error_code": INDEX_WRITER_BUSY,
    "cause_code": INDEX_WRITER_BUSY,
    "retryable": True,
    "retry_after_ms": 5000,
    "next_action": "recapture",
}


def _core(payload: dict) -> dict:
    return {key: payload.get(key) for key in _BUSY}


@pytest.fixture(autouse=True)
def _fresh_guard() -> Iterator[None]:
    auto_index_guard.reset()
    yield
    auto_index_guard.reset()


def _never_indexed(root: Path) -> Path:
    (root / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    assert not (generation_storage_path(str(root)) / "active.json").exists()
    return root


@contextmanager
def _held_lease(root: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Another writer holds the publication lease before the first publication."""
    monkeypatch.setattr(store_owner, "LEASE_TIMEOUT_S", 0.05)
    storage = generation_storage_path(str(root))
    storage.mkdir(parents=True, exist_ok=True)
    holder = sqlite3.connect(storage / "publication.lock.db")
    try:
        holder.execute("BEGIN IMMEDIATE")
        yield
    finally:
        holder.close()


def _run_cli(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, dict]:
    from tree_sitter_analyzer.cli_main import main

    with patch.object(sys, "argv", ["tree_sitter_analyzer", *argv]):
        with pytest.raises(SystemExit) as exc_info:
            main()
    out = capsys.readouterr().out
    return int(exc_info.value.code or 0), json.loads(out[out.index("{") :])


def test_ensure_indexed_raises_typed_busy_on_never_indexed_project(
    tmp_path, monkeypatch
):
    root = _never_indexed(tmp_path)
    with _held_lease(root, monkeypatch):
        with pytest.raises(IndexWriteAdmissionError) as raised:
            ensure_indexed(str(root))
    assert (raised.value.code, raised.value.cause_code) == (
        INDEX_WRITER_BUSY,
        INDEX_WRITER_BUSY,
    )
    assert (raised.value.retryable, raised.value.retry_after_ms) == (True, 5000)
    # A refused warm is not remembered as indexed; the next call retries.
    assert is_indexed(str(root)) is False
    assert not (generation_storage_path(str(root)) / "active.json").exists()


def test_ensure_indexed_still_serves_a_populated_cache_when_busy(tmp_path, monkeypatch):
    # A populated cache stays a usable fallback; only the cold case had no answer.
    root = _never_indexed(tmp_path)
    cache = ASTCache(str(root))
    try:
        cache.index_project()
    finally:
        cache.close()
    from tree_sitter_analyzer.cache import callgraph_state

    monkeypatch.setattr(
        callgraph_state, "call_graph_marker_is_current", lambda _conn: False
    )
    with _held_lease(root, monkeypatch):
        served = ensure_indexed(str(root))
    try:
        assert served is not None
        assert served.get_stats()["total_files"] == 1
    finally:
        served.close()


def test_never_indexed_busy_payload_matches_across_mcp_cli_and_watcher(
    tmp_path, monkeypatch, capsys
):
    from tree_sitter_analyzer.file_watcher import FileWatcherDaemon

    root = _never_indexed(tmp_path)
    with _held_lease(root, monkeypatch):
        sync = asyncio.run(
            CodeGraphIncrementalSyncTool(str(root)).execute({"mode": "sync"})
        )
        warm = asyncio.run(CodeGraphAutoIndexTool(str(root)).execute({"mode": "warm"}))
        code, cli = _run_cli(
            ["--project-root", str(root), "--incremental-sync"], capsys
        )
        cache = ASTCache(str(root))
        watcher = FileWatcherDaemon(cache, poll_interval=1, debounce=0)
        try:
            with patch.object(watcher, "_request_sync"):
                watched = watcher.trigger_sync()
        finally:
            watcher.stop()
            cache.close()
    assert code == 1
    assert _core(sync) == _core(warm) == _core(cli) == _core(watched) == _BUSY
    assert sync["next_step"] == warm["next_step"] == cli["next_step"]
    assert sync["next_step"] == watched["next_step"]
    # Each route keeps its own sanitized ``error`` text.
    assert (
        sync["error"]
        == cli["error"]
        == "Sync failed: IndexWriterBusy: INDEX_WRITER_BUSY"
    )
    assert watched["error"] == INDEX_WRITER_BUSY
    # The warm route keeps its historical ``reason`` key next to the typed fields.
    assert warm["reason"] == "auto-index failed"
    assert not (generation_storage_path(str(root)) / "active.json").exists()


def test_refactor_tool_reports_the_typed_busy_payload(tmp_path, monkeypatch):
    from tree_sitter_analyzer.mcp.tools.codegraph_refactor_tool import (
        CodeGraphRefactorTool,
    )

    root = _never_indexed(tmp_path)
    with _held_lease(root, monkeypatch):
        result = asyncio.run(
            CodeGraphRefactorTool(str(root)).execute(
                {"symbol": "alpha", "new_name": "omega", "mode": "preview"}
            )
        )
    assert _core(result) == _BUSY
    assert (root / "a.py").read_text(encoding="utf-8").startswith("def alpha")


def test_visualization_falls_back_to_source_when_the_warm_is_refused(
    tmp_path, monkeypatch
):
    # Read-only: a refused first warm is not an error; the graph is parsed from
    # source (``CallGraph``), never presented as index-backed.
    from tree_sitter_analyzer.call_graph import CachedCallGraph, CallGraph
    from tree_sitter_analyzer.mcp.tools.codegraph_visualization_hub import (
        CodeGraphVisualizationHub,
    )

    root = _never_indexed(tmp_path)
    hub = CodeGraphVisualizationHub(str(root))
    with _held_lease(root, monkeypatch):
        assert hub.cache() is None
        graph = hub.call_graph()
    assert isinstance(graph, CallGraph)
    assert not isinstance(graph, CachedCallGraph)
    assert is_indexed(str(root)) is False
