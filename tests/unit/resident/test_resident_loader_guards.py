"""RFC-0042 P1: the loader takes no lease where a request would take none.

The lease step mirrors the request's own guards in ``callers_tool``: a live
index whose call-graph marker rules certification out, a remembered capture
timeout (#1710), or a capture that publishes no owner. Each guard is reported
in the load status and leaves today's path to the request.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tree_sitter_analyzer import call_graph_warm, index_snapshot
from tree_sitter_analyzer.cache import generation_routing, live_index_probe
from tree_sitter_analyzer.mcp.tools import certification_timeouts
from tree_sitter_analyzer.resident import loader


@pytest.fixture(autouse=True)
def _fresh(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv(certification_timeouts.DIR_ENV, str(tmp_path / "timeouts"))
    loader.reset()
    yield
    loader.reset()


def _no_probe(monkeypatch: pytest.MonkeyPatch, exact: bool | None) -> None:
    probe = None if exact is None else SimpleNamespace(call_graph_exact=exact)
    monkeypatch.setattr(live_index_probe, "probe_live_index", lambda _root: probe)


def test_a_selector_that_cannot_be_read_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def invalid(_root: Any) -> Any:
        raise ValueError("selector")

    monkeypatch.setattr(generation_routing, "resolve_index_path", invalid)
    assert loader.load(str(tmp_path)) == {
        "state": "skipped",
        "reason": "INDEX_GENERATION_SELECTOR_INVALID",
    }


def test_no_lease_when_the_call_graph_marker_rules_certification_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_probe(monkeypatch, exact=False)
    assert loader._lease(str(tmp_path)) == "CALL_GRAPH_INCOMPLETE"


def test_no_lease_while_a_capture_timeout_is_remembered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_probe(monkeypatch, exact=None)
    monkeypatch.setattr(certification_timeouts, "should_skip", lambda _root: True)
    recorded: list[Any] = []
    monkeypatch.setattr(certification_timeouts, "record", lambda *a: recorded.append(a))
    assert loader._lease(str(tmp_path)) == "CERTIFICATION_TIMEOUT_REMEMBERED"
    assert recorded == []  # the loader never records a timeout itself


def test_a_capture_without_an_owner_reports_its_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_probe(monkeypatch, exact=None)
    monkeypatch.setattr(certification_timeouts, "should_skip", lambda _root: False)

    @contextmanager
    def no_owner(_root: str) -> Any:
        yield None

    monkeypatch.setattr(index_snapshot, "certified_index_read", no_owner)
    monkeypatch.setattr(index_snapshot, "_certified_index_read_reason", lambda: None)
    assert loader._lease(str(tmp_path)) == "INDEX_SNAPSHOT_UNKNOWN"
    monkeypatch.setattr(
        index_snapshot, "_certified_index_read_reason", lambda: "SOURCE_INDEX_MISMATCH"
    )
    assert loader._lease(str(tmp_path)) == "SOURCE_INDEX_MISMATCH"
    assert loader._bind_snapshot_graph(str(tmp_path)) == "INDEX_SNAPSHOT_UNKNOWN"


def test_a_graph_that_does_not_build_on_the_lease_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tree_sitter_analyzer import call_graph

    class _Owner:
        def query_cache(self) -> Any:
            return object()

    @contextmanager
    def owner(_root: str) -> Any:
        yield _Owner()

    monkeypatch.setattr(index_snapshot, "certified_index_read", owner)
    monkeypatch.setattr(call_graph.CachedCallGraph, "build", lambda _self: None)
    assert loader._bind_snapshot_graph(str(tmp_path)) == "GRAPH_NOT_BUILT"


# --------------------------------------------------------------------------- #
# call_graph_warm.warm_now: the start-time build obeys the post-publish rules
# --------------------------------------------------------------------------- #


def test_warm_now_does_nothing_unless_enabled(tmp_path: Path) -> None:
    call_graph_warm.disable()
    assert call_graph_warm.warm_now(str(tmp_path)) is None


def test_warm_now_does_nothing_after_shutdown(tmp_path: Path) -> None:
    call_graph_warm.enable()
    try:
        call_graph_warm.shutdown(timeout=1)  # a stopping server builds nothing new
        assert call_graph_warm.warm_now(str(tmp_path)) is None
    finally:
        call_graph_warm.enable()  # reopens
        call_graph_warm.disable()


def test_warm_now_never_runs_beside_an_in_flight_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    call_graph_warm.enable()
    release = threading.Event()
    running = threading.Thread(target=release.wait, args=(10,), daemon=True)
    running.start()
    key = call_graph_warm._key(str(tmp_path))
    monkeypatch.setitem(call_graph_warm._threads, key, running)
    try:
        assert call_graph_warm.warm_now(str(tmp_path)) == {"in_flight": True}
    finally:
        release.set()
        running.join(5)
        call_graph_warm.disable()


# --------------------------------------------------------------------------- #
# Server hook on SDKs without a notification table
# --------------------------------------------------------------------------- #


def test_no_initialized_hook_without_a_notification_table() -> None:
    from tree_sitter_analyzer.mcp.server import _register_resident_start

    server = SimpleNamespace()  # an MCP 2.x adapter exposes no handler dict
    _register_resident_start(server, object())
    assert not hasattr(server, "notification_handlers")
