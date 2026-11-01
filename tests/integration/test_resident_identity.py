"""RFC-0042 P1: the background loader changes when work is done, never an answer.

On a real indexed fixture, every answer with the loader on equals today's
answer (loader off, cold process state) field for field, except timing and
cost fields. After the load the first query neither captures a snapshot nor
builds a graph. A request that arrives while the loader is capturing or
building waits for that work instead of doing it twice. Resident state built
for one index generation is never served for another (fault injection).
"""

from __future__ import annotations

import asyncio
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer import (
    call_graph,
    call_graph_memo,
    call_graph_snapshot_inputs,
    call_graph_warm,
    index_snapshot,
)
from tree_sitter_analyzer.mcp.tools import certification_timeouts
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool
from tree_sitter_analyzer.resident import loader

_AN_HOUR_NS = 3600 * 1_000_000_000
_SOURCES = {
    "widget.py": (
        "class Widget:\n"
        "    def used(self):\n"
        "        return 1\n\n"
        "    def unused(self):\n"
        "        return 2\n\n\n"
        "def run(w: Widget):\n"
        "    return w.used()\n"
    ),
    "pkg/__init__.py": "from .helper import helper\n",
    "pkg/helper.py": "def helper():\n    return 3\n\n\ndef top():\n    return helper()\n",
    "app.py": (
        "from pkg.helper import helper, top\n"
        "from widget import Widget, run\n\n\n"
        "def main():\n"
        "    run(Widget())\n"
        "    return helper() + top()\n"
    ),
}
_SECOND_CALLER = "\n\ndef again():\n    return helper()\n"
_QUERIES = [
    ("used", "widget.py"),
    ("Widget.used", "widget.py"),
    ("Widget.unused", "widget.py"),
    ("helper", "pkg/helper.py"),
    ("top", "pkg/helper.py"),
    ("run", "widget.py"),
    ("main", "app.py"),
    ("does_not_exist", "app.py"),
]
#: Timing, process and cost fields: they differ between any two runs.
_VOLATILE = re.compile(
    r"(^|_)(seconds|wall|elapsed\w*|cpu\w*|ms|duration\w*|time|timing|timings|"
    r"started\w*|finished\w*|generated_at|\w+_seconds|\w+_ms)$|^query_cost$"
)
_LOADER_THREAD = "tsa-resident-loader"


def _stable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _stable(v) for k, v in value.items() if not _VOLATILE.search(k)}
    if isinstance(value, list):
        return [_stable(v) for v in value]
    return value


def _cold() -> None:
    """A fresh process: no snapshot lease, no graph memo, no remembered digests."""
    index_snapshot.REGISTRY.close_all()
    call_graph_memo.clear()
    call_graph_snapshot_inputs.clear()
    certification_timeouts.clear()


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(certification_timeouts.DIR_ENV, str(tmp_path / "timeouts"))
    monkeypatch.delenv(loader.ENV_VAR, raising=False)
    monkeypatch.delenv(call_graph_warm.ENV_VAR, raising=False)
    _cold()
    loader.reset()
    call_graph_warm.enable()
    loader.enable()
    yield
    loader.shutdown(timeout=30)
    loader.reset()
    call_graph_warm.wait(timeout=30)
    call_graph_warm.disable()
    _cold()


def _backdate(root: Path) -> None:
    stamp = time.time_ns() - _AN_HOUR_NS
    for path in [*root.rglob("*.py"), root / "pkg", root]:
        os.utime(path, ns=(stamp, stamp))


async def _index(root: Path) -> None:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    result = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 50}
    )
    assert result["published"] is True


@pytest.fixture
async def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    for rel, text in _SOURCES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    _backdate(root)
    await _index(root)
    _cold()
    return root


def _args(name: str, file_path: str) -> dict[str, Any]:
    return {"function_name": name, "file_path": file_path, "include_bodies": False}


async def _ask_all(root: Path) -> list[Any]:
    tool = CodeGraphCallersTool(str(root))
    return [_stable(await tool.execute(_args(*q))) for q in _QUERIES]


async def _today(root: Path, monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Today's answers: switch off, cold state, one fresh tool per question."""
    with monkeypatch.context() as patch:
        patch.setenv(loader.ENV_VAR, "off")
        answers = []
        for query in _QUERIES:
            _cold()
            tool = CodeGraphCallersTool(str(root))
            answers.append(_stable(await tool.execute(_args(*query))))
    _cold()
    return answers


def _load(root: Path) -> dict[str, Any]:
    assert loader.start(str(root)) is True
    assert loader.wait(str(root), timeout=60)
    status = loader.status(str(root)) or {}
    assert status.get("state") in {"ready", "skipped", "failed"}, status
    return status


class _Counter:
    """Counts snapshot captures and graph builds after a memo miss, per thread."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from tree_sitter_analyzer.cache import graph_input_rows

        self.captures: list[str] = []
        self.builds: list[str] = []
        self.edge_reads: list[str] = []
        capture = index_snapshot._capture_existing_snapshot
        build = call_graph.CachedCallGraph._build_after_miss
        read = graph_input_rows.read_edge_source

        def counted_capture(*args: Any, **kwargs: Any) -> Any:
            self.captures.append(threading.current_thread().name)
            return capture(*args, **kwargs)

        def counted_build(graph: Any, *args: Any, **kwargs: Any) -> Any:
            self.builds.append(threading.current_thread().name)
            return build(graph, *args, **kwargs)

        def counted_read(*args: Any, **kwargs: Any) -> Any:
            self.edge_reads.append(threading.current_thread().name)
            return read(*args, **kwargs)

        monkeypatch.setattr(
            index_snapshot, "_capture_existing_snapshot", counted_capture
        )
        monkeypatch.setattr(
            call_graph.CachedCallGraph, "_build_after_miss", counted_build
        )
        monkeypatch.setattr(graph_input_rows, "read_edge_source", counted_read)

    def reset(self) -> None:
        self.captures.clear()
        self.builds.clear()
        self.edge_reads.clear()


# --------------------------------------------------------------------------- #
# Identity
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_answers_are_identical_with_and_without_the_loader(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    today = await _today(project, monkeypatch)
    status = _load(project)
    assert status["state"] == "ready", status
    assert status["certified"] is None, status  # the fixture certifies
    resident = await _ask_all(project)
    assert resident == today
    # Warm again (memo and lease reused): still the same answers.
    assert await _ask_all(project) == today


@pytest.mark.asyncio
async def test_the_first_query_after_the_load_neither_captures_nor_builds(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    today = await _today(project, monkeypatch)
    counter = _Counter(monkeypatch)
    _load(project)
    assert counter.captures == [_LOADER_THREAD]
    assert counter.builds == [_LOADER_THREAD]
    counter.reset()
    tool = CodeGraphCallersTool(str(project))
    answer = _stable(await tool.execute(_args(*_QUERIES[1])))
    assert answer == today[1]
    assert counter.captures == []  # the loader's lease is reused
    assert counter.builds == []  # the loader's graph is adopted
    # ... through the leased snapshot's remembered digest (#1774): no edge re-read.
    assert counter.edge_reads == []


@pytest.mark.asyncio
async def test_an_edit_without_a_refresh_gives_todays_answer(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Resident data is never freshness evidence (R1): the edit is seen as today."""
    _load(project)
    helper = project / "pkg" / "helper.py"
    helper.write_text(_SOURCES["pkg/helper.py"] + _SECOND_CALLER, encoding="utf-8")
    resident = await _ask_all(project)
    today = await _today(project, monkeypatch)
    assert resident == today
    assert all(a.get("completeness") != "complete" for a in resident[3:4])


# --------------------------------------------------------------------------- #
# Concurrency: requests that arrive while the loader works
# --------------------------------------------------------------------------- #


def _ask_in_thread(
    root: Path, query: tuple[str, str]
) -> tuple[threading.Thread, list[Any]]:
    out: list[Any] = []

    def run() -> None:
        tool = CodeGraphCallersTool(str(root))
        out.append(_stable(asyncio.run(tool.execute(_args(*query)))))

    thread = threading.Thread(target=run, name="request", daemon=True)
    thread.start()
    return thread, out


def _block_in_loader(
    monkeypatch: pytest.MonkeyPatch, owner: Any, name: str
) -> tuple[threading.Event, threading.Event]:
    """Make ``owner.name`` block in the loader thread until released."""
    entered, release = threading.Event(), threading.Event()
    original = getattr(owner, name)

    def gated(*args: Any, **kwargs: Any) -> Any:
        if threading.current_thread().name == _LOADER_THREAD:
            entered.set()
            assert release.wait(30)
        return original(*args, **kwargs)

    monkeypatch.setattr(owner, name, gated)
    return entered, release


@pytest.mark.asyncio
async def test_a_request_during_the_background_capture_reuses_it(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    today = (await _today(project, monkeypatch))[3]
    counter = _Counter(monkeypatch)
    entered, release = _block_in_loader(
        monkeypatch, index_snapshot, "_capture_existing_snapshot"
    )
    assert loader.start(str(project)) is True
    assert entered.wait(10)
    thread, out = _ask_in_thread(project, _QUERIES[3])
    time.sleep(0.3)
    assert thread.is_alive(), "the request waits for the in-flight capture"
    release.set()
    thread.join(60)
    assert loader.wait(str(project), timeout=60)
    assert out == [today]
    assert counter.captures == [_LOADER_THREAD]  # captured once, by the loader


@pytest.mark.asyncio
async def test_a_request_during_the_background_graph_build_builds_nothing(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    today = (await _today(project, monkeypatch))[3]
    counter = _Counter(monkeypatch)
    entered, release = _block_in_loader(
        monkeypatch, call_graph.CachedCallGraph, "_build_after_miss"
    )
    assert loader.start(str(project)) is True
    assert entered.wait(10)
    thread, out = _ask_in_thread(project, _QUERIES[3])
    time.sleep(0.3)
    release.set()
    thread.join(60)
    assert loader.wait(str(project), timeout=60)
    assert out == [today]
    assert counter.builds == [_LOADER_THREAD]  # one build, the request waited


# --------------------------------------------------------------------------- #
# Fault injection: resident state of another generation is never served
# --------------------------------------------------------------------------- #


def _poison_resident_graph(root: Path) -> None:
    """Replace the loader's graph state with one that has no edges at all."""
    canonical = str(root.resolve())
    state = call_graph_memo.latest(canonical)
    assert isinstance(state, dict) and state["_built"] is True, "no stored graph"
    poisoned = dict(state)
    for name in ("_callers", "_callees", "_possible_callers", "_call_edges"):
        if name in poisoned:
            poisoned[name] = type(poisoned[name])()
    with call_graph_memo._LOCK:
        digest, _ = call_graph_memo._MEMO[canonical]
        call_graph_memo._MEMO[canonical] = (digest, poisoned)


@pytest.mark.asyncio
async def test_a_poisoned_resident_graph_is_served_only_for_its_own_key(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = await _today(project, monkeypatch)
    _load(project)
    _poison_resident_graph(project)
    # Same key: the poisoned resident graph is what answers — the test can see it.
    poisoned = await _ask_all(project)
    assert poisoned != before

    helper = project / "pkg" / "helper.py"
    helper.write_text(_SOURCES["pkg/helper.py"] + _SECOND_CALLER, encoding="utf-8")
    _backdate(project)
    await _index(project)  # new generation: new snapshot, new graph input digest

    # Another key: the poisoned state is never served; today's path answers.
    after = await _ask_all(project)
    today = await _today(project, monkeypatch)
    assert after == today
    assert {c["name"] for c in after[3]["callers"]} >= {"top", "again"}


# --------------------------------------------------------------------------- #
# What the loader never does
# --------------------------------------------------------------------------- #


def test_a_root_without_an_index_is_skipped_and_never_indexed(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    status = _load(tmp_path)
    assert status["state"] == "skipped"
    assert status["reason"] == "MISSING_INDEX"
    assert not (tmp_path / ".ast-cache").exists()


@pytest.mark.asyncio
async def test_a_rebuilding_index_is_skipped(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tree_sitter_analyzer.mcp.tools import index_rebuild_signal

    monkeypatch.setattr(index_rebuild_signal, "is_index_rebuilding", lambda _r: True)
    counter = _Counter(monkeypatch)
    status = _load(project)
    assert status == {**status, "state": "skipped", "reason": "INDEX_REBUILDING"}
    assert counter.captures == [] and counter.builds == []
