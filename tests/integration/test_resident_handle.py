"""RFC-0042 P2a on a real index: one validated handle replaces the per-request probes.

Every answer read through the resident handle equals today's answer
(``TSA_RESIDENT=off``, cold process state) field for field, except timing and
cost fields. Fault injection: a handle left over from before a republish, a
refresh or a watcher sync, a selector replaced in place, a database that
regained a write bit, and a rebuild in progress all give today's answer. The
rebuild flag is read on every request; no connection outlives a request; and
requests racing a republish see the old or the new generation, never a mix.
"""

from __future__ import annotations

import asyncio
import os
import stat
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer.cache import (
    build_state,
    generation_routing,
    live_index_probe,
    query_cost,
)
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool
from tree_sitter_analyzer.resident import handle, loader

from . import test_resident_identity as base
from .test_resident_identity import (
    _QUERIES,
    _SECOND_CALLER,
    _SOURCES,
    _args,
    _ask_all,
    _backdate,
    _index,
    _load,
    _stable,
    _today,
)

project = base.project
_isolated = base._isolated


@pytest.fixture(autouse=True)
def _fresh_handles():
    handle.reset()
    yield
    handle.reset()


class _Probes:
    """Counts today's probe work: live-index probes and cost-tier index opens."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.probes = 0
        self.cost_opens = 0
        self.resolves = 0
        probe = live_index_probe.probe_live_index_uncached
        opened = query_cost._compute_index_holds_rows
        resolve = generation_routing.resolve_index_location

        def counted_resolve(*args: Any, **kwargs: Any) -> Any:
            self.resolves += 1
            return resolve(*args, **kwargs)

        def counted_probe(*args: Any, **kwargs: Any) -> Any:
            self.probes += 1
            return probe(*args, **kwargs)

        def counted_open(*args: Any, **kwargs: Any) -> Any:
            self.cost_opens += 1
            return opened(*args, **kwargs)

        monkeypatch.setattr(
            live_index_probe, "probe_live_index_uncached", counted_probe
        )
        monkeypatch.setattr(query_cost, "_compute_index_holds_rows", counted_open)
        monkeypatch.setattr(
            generation_routing, "resolve_index_location", counted_resolve
        )

    def reset(self) -> None:
        self.probes = 0
        self.cost_opens = 0
        self.resolves = 0


async def _ask(root: Path, query: tuple[str, str]) -> Any:
    return _stable(await CodeGraphCallersTool(str(root)).execute(_args(*query)))


def _edit(root: Path) -> None:
    helper = root / "pkg" / "helper.py"
    helper.write_text(_SOURCES["pkg/helper.py"] + _SECOND_CALLER, encoding="utf-8")
    _backdate(root)


# --------------------------------------------------------------------------- #
# Identity and the probe collapse
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_answers_are_identical_with_and_without_the_handle(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    today = await _today(project, monkeypatch)
    first = await _ask_all(project)
    assert handle.peek(str(project)) is not None
    assert first == today
    assert await _ask_all(project) == today  # warm, handle reused
    assert handle.stats()["reused"] >= len(_QUERIES)


@pytest.mark.asyncio
async def test_first_use_builds_the_handle_and_off_never_does(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(loader.ENV_VAR, "off")
    await _ask(project, _QUERIES[1])
    assert handle.peek(str(project)) is None
    assert handle.stats()["built"] == 0
    monkeypatch.setenv(loader.ENV_VAR, "first-use")
    await _ask(project, _QUERIES[1])
    assert handle.peek(str(project)) is not None


@pytest.mark.asyncio
async def test_warm_requests_probe_nothing(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _ask_all(project)
    probes = _Probes(monkeypatch)
    for query in _QUERIES:
        await _ask(project, query)
    # No probe, no cost-tier index open, and no index location resolved at all.
    assert (probes.probes, probes.cost_opens, probes.resolves) == (0, 0, 0)

    # The same request with the switch off probes as today: the certification
    # ruling and the cost tier each open the live index.
    monkeypatch.setenv(loader.ENV_VAR, "off")
    probes.reset()
    await _ask(project, _QUERIES[1])
    assert probes.probes == 2


@pytest.mark.asyncio
async def test_the_loader_publishes_the_handle_and_the_cost_tier(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    today = await _today(project, monkeypatch)
    status = _load(project)
    assert status["handle"] is True, status
    assert handle.peek(str(project)) is not None
    probes = _Probes(monkeypatch)
    assert await _ask_all(project) == today
    # The first request after the load opens no index for its cost tier.
    assert (probes.probes, probes.cost_opens) == (0, 0)


# --------------------------------------------------------------------------- #
# Fault injection: a stale handle is never used
# --------------------------------------------------------------------------- #


def _poison(root: Path) -> handle.ResidentHandle:
    """Make the stored handle claim the call-graph marker is not exact."""
    stored = handle.peek(str(root))
    assert isinstance(stored, handle.ResidentHandle)
    probe = replace(stored.live_probe, call_graph_exact=False)
    poisoned = replace(stored, live_probe=probe)
    with handle._lock:
        handle._handles[str(root)] = poisoned
    return poisoned


class _CertifiedReads:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from tree_sitter_analyzer import index_snapshot

        self.count = 0
        original = index_snapshot.certified_index_read

        def counted(*args: Any, **kwargs: Any) -> Any:
            self.count += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(index_snapshot, "certified_index_read", counted)


@pytest.mark.asyncio
async def test_a_poisoned_handle_is_used_only_for_its_own_generation(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _ask_all(project)
    _poison(project)
    reads = _CertifiedReads(monkeypatch)
    await _ask(project, _QUERIES[3])
    # Same generation: the poisoned ruling is what the request sees (visible here).
    assert reads.count == 0

    _edit(project)
    await _index(project)  # republish: a new selector and a new sealed database
    after = await _ask_all(project)
    # The poisoned handle was dropped: every question certified again.
    assert reads.count == len(_QUERIES)
    assert after == await _today(project, monkeypatch)
    assert {c["name"] for c in after[3]["callers"]} >= {"top", "again"}


@pytest.mark.asyncio
async def test_a_refresh_drops_the_handle(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tree_sitter_analyzer.ast_cache import ASTCache

    await _ask_all(project)
    before = handle.peek(str(project))
    _edit(project)
    cache = ASTCache(str(project))
    try:
        result = cache.index_project(workers=0)
    finally:
        cache.close()
    assert result.get("published", True)
    after = await _ask_all(project)
    assert handle.peek(str(project)) != before
    assert after == await _today(project, monkeypatch)


@pytest.mark.asyncio
async def test_a_watcher_sync_drops_the_handle(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.file_watcher import FileWatcherDaemon

    await _ask_all(project)
    _poison(project)
    _edit(project)
    cache = ASTCache(str(project))
    watcher = FileWatcherDaemon(cache, poll_interval=1, debounce=0)
    try:
        watcher.trigger_sync()
    finally:
        watcher.stop()
        cache.close()
    after = await _ask_all(project)
    assert handle.peek(str(project)).live_probe.call_graph_exact is True
    assert after == await _today(project, monkeypatch)


def _replace_in_place(path: Path) -> None:
    """Rewrite ``path`` with the same bytes and times: only its file ID changes."""
    data = path.read_bytes()
    info = os.stat(path)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    os.utime(temporary, ns=(info.st_atime_ns, info.st_mtime_ns))
    os.replace(temporary, path)


@pytest.mark.asyncio
async def test_a_selector_replaced_with_equal_bytes_and_times_drops_the_handle(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _ask_all(project)
    stored = handle.peek(str(project))
    assert stored is not None
    _poison(project)
    _replace_in_place(Path(stored.selector_path))
    assert handle.file_stamp(stored.selector_path) != stored.selector_stamp
    reads = _CertifiedReads(monkeypatch)
    resident = await _ask_all(project)
    # Rebuilt from today's probe, not the poisoned one: every question certified.
    assert reads.count == len(_QUERIES)
    assert resident == await _today(project, monkeypatch)


@pytest.mark.asyncio
async def test_a_database_that_regained_a_write_bit_is_not_cached(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _ask_all(project)
    stored = handle.peek(str(project))
    assert stored is not None
    database = stored.database
    mode = stat.S_IMODE(os.lstat(database).st_mode)
    os.chmod(database, mode | stat.S_IWUSR)
    try:
        assert handle.acquire(str(project)) is None
        assert handle.peek(str(project)) is None
        assert await _ask_all(project) == await _today(project, monkeypatch)
        assert handle.peek(str(project)) is None
    finally:
        os.chmod(database, mode)


@pytest.mark.asyncio
async def test_the_rebuild_flag_is_read_on_every_request(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _ask_all(project)
    assert handle.peek(str(project)) is not None
    reads: list[int] = []

    def rebuilding(conn: Any, **_kwargs: Any) -> bool:
        reads.append(1)
        return True

    monkeypatch.setattr(build_state, "build_in_progress", rebuilding)
    resident = await _ask(project, _QUERIES[3])
    assert resident["data_source"] == "cache_rebuilding"
    # Read by the batch check and again by the answer, as today.
    assert len(reads) == 2
    reads.clear()
    await _ask(project, _QUERIES[3])
    assert len(reads) == 2  # never cached across requests
    today = await _today(project, monkeypatch)
    assert resident == today[3]


@pytest.mark.asyncio
async def test_no_connection_outlives_a_request(project: Path) -> None:
    await _ask_all(project)
    stored = handle.peek(str(project))
    assert stored is not None
    assert handle._REQUEST.get() is None
    # An open SQLite handle would block a rename on Windows (it pins a retired
    # generation, #1631); after the request the database can be moved freely.
    database = stored.database
    moved = database.with_name("moved.db")
    os.replace(database, moved)
    os.replace(moved, database)


@pytest.mark.asyncio
async def test_a_root_without_an_index_has_no_handle(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    answer = await _ask(tmp_path, ("f", "a.py"))
    assert answer["completeness"] != "complete"
    assert handle.peek(str(tmp_path)) is None


# --------------------------------------------------------------------------- #
# Concurrency
# --------------------------------------------------------------------------- #


def test_racing_acquires_agree(project: Path) -> None:
    results: list[Any] = []
    errors: list[BaseException] = []
    start = threading.Barrier(16)

    def run() -> None:
        try:
            start.wait(10)
            results.append(handle.acquire(str(project)))
        except BaseException as exc:  # noqa: BLE001 — reported below
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(16)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    assert errors == []
    assert len(results) == 16 and all(r is not None for r in results)
    assert len({(r.selector_stamp, r.database_stamp) for r in results}) == 1
    assert handle.peek(str(project)) in results


@pytest.mark.asyncio
async def test_requests_racing_a_republish_see_one_generation(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    query = _QUERIES[3]
    # The edit lands first, so the two states are "edited source, old index" and
    # "edited source, new index"; each request must give today's answer for one.
    _edit(project)
    before = (await _today(project, monkeypatch))[3]
    stop = threading.Event()
    answers: list[Any] = []
    errors: list[BaseException] = []

    def ask_loop() -> None:
        tool = CodeGraphCallersTool(str(project))
        while not stop.is_set():
            try:
                answers.append(_stable(asyncio.run(tool.execute(_args(*query)))))
            except BaseException as exc:  # noqa: BLE001 — reported below
                errors.append(exc)
                return

    threads = [threading.Thread(target=ask_loop, daemon=True) for _ in range(4)]
    for thread in threads:
        thread.start()
    time.sleep(0.5)
    await _index(project)
    time.sleep(0.5)
    stop.set()
    for thread in threads:
        thread.join(120)
    after = (await _today(project, monkeypatch))[3]
    assert errors == []
    assert answers, "no request completed"
    allowed = [before, after]
    unexpected = [a for a in answers if a not in allowed]
    assert unexpected == []
    # A complete answer only where today's answer for that state is complete.
    for answer in answers:
        if answer.get("completeness") == "complete":
            assert answer in [a for a in allowed if a.get("completeness") == "complete"]
