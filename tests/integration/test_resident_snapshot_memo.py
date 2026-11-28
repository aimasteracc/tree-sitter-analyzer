"""RFC-0042 P2b on a real index: the per-snapshot memo never changes an answer.

The edge-layer check readers (RFC-0040 checks 1–5) are memoized per certified
snapshot identity. Every answer equals today's (``TSA_RESIDENT=off``, cold
state) field for field except timing and cost; every memoized reader returns
what a fresh read of the same snapshot returns; a warm request decodes no call
site again. Fault injection: a memo entry of a snapshot that a republish, a
refresh or a watcher sync replaced is never served, and an edit without a
refresh gives today's answer (source text is always read live).
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer import index_snapshot
from tree_sitter_analyzer.graph import edge_store
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool
from tree_sitter_analyzer.resident import loader, snapshot_memo

from . import test_resident_identity as base
from .test_resident_identity import _args, _backdate, _cold, _index, _load, _stable

_isolated = base._isolated

#: The identity fixture plus code that reaches every edge-layer reader: computed
#: dispatch in a declaring file, a callable produced by an imported (external)
#: function, a module-level call site and an aliased import.
_SOURCES = {
    **base._SOURCES,
    "router.py": (
        "import functools\n"
        "from pkg.helper import helper as assist\n\n\n"
        "class Router:\n"
        "    def handle(self, name):\n"
        "        return getattr(self, name)()\n\n"
        "    def route(self, x):\n"
        "        return functools.partial(self.handle, x)()\n\n"
        "    def used(self):\n"
        "        return assist()\n\n\n"
        "def build():\n"
        "    return Router().route('used')\n\n\n"
        "HANDLERS = {'a': build}\n\n\n"
        "def dispatch(name):\n"
        "    return HANDLERS[name]()\n\n\n"
        "build()\n"
    ),
}
_QUERIES = [
    *base._QUERIES,
    ("Router.handle", "router.py"),
    ("handle", "router.py"),
    ("Router.route", "router.py"),
    ("build", "router.py"),
    ("used", "router.py"),
    ("dispatch", "router.py"),
]
#: Rebinds the imported producer and mutates the literal dispatch table: both
#: external-producer verdicts change, and they read the source live.
_REBIND = "\n\nfunctools = None\nHANDLERS['b'] = build\n"


@pytest.fixture(autouse=True)
def _fresh_memo():
    snapshot_memo.clear()
    yield
    snapshot_memo.clear()


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


async def _ask_all(root: Path) -> list[Any]:
    tool = CodeGraphCallersTool(str(root))
    return [_stable(await tool.execute(_args(*q))) for q in _QUERIES]


async def _today(root: Path, monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    with monkeypatch.context() as patch:
        patch.setenv(loader.ENV_VAR, "off")
        answers = []
        for query in _QUERIES:
            _cold()
            tool = CodeGraphCallersTool(str(root))
            answers.append(_stable(await tool.execute(_args(*query))))
    _cold()
    return answers


class _Decodes:
    """Counts call-site decodes of declaring files (the memoized SQL work)."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.count = 0
        original = edge_store.EdgeStore._classified_call_sites_in_file

        def counted(store: Any, file_path: str) -> Any:
            self.count += 1
            return original(store, file_path)

        monkeypatch.setattr(
            edge_store.EdgeStore, "_classified_call_sites_in_file", counted
        )


def _edit(root: Path, rel: str, extra: str) -> None:
    path = root / rel
    path.write_text(_SOURCES[rel] + extra, encoding="utf-8")
    _backdate(root)


# --------------------------------------------------------------------------- #
# Identity and purity
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_answers_are_identical_with_and_without_the_memo(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    today = await _today(project, monkeypatch)
    cold = await _ask_all(project)  # fills the memo
    filled = snapshot_memo.stats()
    warm = await _ask_all(project)  # served from it
    served = snapshot_memo.stats()
    # The warm pass stores nothing new: every stored reader result was a hit.
    assert served["stored"] == filled["stored"] == filled["entries"]
    assert (
        served["hits"] - filled["hits"] >= filled["entries"]
    )  # ratchet: nondeterministic a reader may be asked more than once per question
    assert cold == today
    assert warm == today
    assert any(a["completeness"] == "complete" for a in today)
    assert any(a["completeness"] != "complete" for a in today)


@pytest.mark.asyncio
async def test_a_warm_request_decodes_no_call_site_again(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _ask_all(project)
    decodes = _Decodes(monkeypatch)
    await _ask_all(project)
    assert decodes.count == 0
    monkeypatch.setenv(loader.ENV_VAR, "off")
    await _ask_all(project)
    # Today's path decodes the declaring files again on every request.
    assert decodes.count >= len(
        _QUERIES
    )  # ratchet: nondeterministic two decodes (unresolved, excluded) per declaring file


def _readers(cache: Any, names: list[str], files: list[str]) -> list[Any]:
    from tree_sitter_analyzer.mcp.tools.callers_call_lines import call_edge_lines
    from tree_sitter_analyzer.mcp.tools.callers_external_producers import (
        ExternalProducers,
    )

    out: list[Any] = [cache.has_call_edges()]
    for name in names:
        out += [
            cache.symbol_declaring_files(name),
            cache.symbol_definitions(name),
            cache.count_unresolved_callers(name),
            cache.unresolved_caller_sites(name),
            cache.query_callers(name),
            call_edge_lines(cache, name),
        ]
        for file in files:
            out += [
                cache.count_unresolved_callers(name, file, frozenset()),
                cache.unresolved_caller_sites(name, file, {(file, 1)}),
                cache.query_callers(name, file),
            ]
    producers = ExternalProducers(cache, cache.project_root)
    for file in files:
        out += [
            cache.unresolved_call_sites_in_file(file),
            cache.excluded_call_sites_in_file(file),
            producers._language(file),
            producers._bindings(file),
            producers._project_tops(),
            producers._indexed_paths(),
        ]
    return out


@pytest.mark.asyncio
async def test_every_memoized_reader_equals_a_fresh_read_of_the_snapshot(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    names = ["used", "helper", "top", "run", "main", "handle", "route", "build"]
    names += ["assist", "partial", "getattr", "nope"]
    files = sorted(
        str(p.relative_to(project)).replace(os.sep, "/") for p in project.rglob("*.py")
    )
    with index_snapshot.certified_index_read(str(project)) as owner:
        assert owner is not None
        cache = owner.query_cache()
        with monkeypatch.context() as patch:
            patch.setenv(loader.ENV_VAR, "off")
            fresh = _readers(cache, names, files)
        assert snapshot_memo.stats()["stored"] == 0
        filled = _readers(cache, names, files)
        stored = snapshot_memo.stats()["stored"]
        assert stored == snapshot_memo.stats()["entries"]
        hit = _readers(cache, names, files)
        assert snapshot_memo.stats()["stored"] == stored  # all hits
    assert filled == fresh
    assert hit == fresh


# --------------------------------------------------------------------------- #
# Fault injection: another snapshot's memo is never served
# --------------------------------------------------------------------------- #


def _poison_all() -> tuple[str, ...]:
    """Replace every stored site list with one bogus site; returns the key."""
    keys = snapshot_memo.keys()
    assert len(keys) == 1
    bogus = {"file": "nowhere.py", "line": 1, "callee": "x", "caller": "<module>"}
    with snapshot_memo._lock:
        memo = snapshot_memo._memos[keys[0]]
        for entry, value in list(memo.items()):
            if isinstance(value, list):
                memo[entry] = [dict(bogus)]
            elif isinstance(value, bool):
                memo[entry] = not value
    return keys[0]


@pytest.mark.asyncio
async def test_a_poisoned_memo_is_served_only_for_its_own_snapshot(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clean = await _ask_all(project)
    old = _poison_all()
    # Same snapshot: the poisoned entries answer — the test can see them.
    assert await _ask_all(project) != clean

    _edit(project, "pkg/helper.py", base._SECOND_CALLER)
    await _index(project)  # republish: the next request leases a new snapshot
    after = await _ask_all(project)
    assert old not in snapshot_memo.keys()
    assert after == await _today(project, monkeypatch)
    assert {c["name"] for c in after[3]["callers"]} >= {"top", "again"}


@pytest.mark.asyncio
async def test_a_refresh_and_a_watcher_sync_never_see_the_old_memo(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.file_watcher import FileWatcherDaemon

    await _ask_all(project)
    _poison_all()
    _edit(project, "pkg/helper.py", base._SECOND_CALLER)
    cache = ASTCache(str(project))
    try:
        cache.index_project(workers=0)
    finally:
        cache.close()
    assert await _ask_all(project) == await _today(project, monkeypatch)

    await _ask_all(project)
    _poison_all()
    _edit(project, "router.py", "\n\ndef later():\n    return build()\n")
    cache = ASTCache(str(project))
    watcher = FileWatcherDaemon(cache, poll_interval=1, debounce=0)
    try:
        watcher.trigger_sync()
    finally:
        watcher.stop()
        cache.close()
    assert await _ask_all(project) == await _today(project, monkeypatch)


async def _sequence(root: Path, mode: str, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Ask, edit without a refresh, ask again: one process, one switch value."""
    with monkeypatch.context() as patch:
        if mode == "off":
            patch.setenv(loader.ENV_VAR, "off")
        _cold()
        snapshot_memo.clear()
        before = await _ask_all(root)
        _edit(root, "router.py", _REBIND)
        after = await _ask_all(root)
        (root / "router.py").write_text(_SOURCES["router.py"], encoding="utf-8")
        _backdate(root)
    return before, after


@pytest.mark.asyncio
async def test_an_edit_without_a_refresh_gives_todays_answer(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Source text is read live (R1): rebinding an imported name is seen at once."""
    today = await _sequence(project, "off", monkeypatch)
    resident = await _sequence(project, "background", monkeypatch)
    assert resident == today
    # The edit changed answers (the verdicts were re-derived from the new text).
    changed = [q for q, a, b in zip(_QUERIES, *resident, strict=True) if a != b]
    assert ("dispatch", "router.py") in changed


@pytest.mark.asyncio
async def test_a_renewed_lease_keeps_its_memo(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    status = _load(project)
    assert status["certified"] is None, status
    await _ask_all(project)
    key = snapshot_memo.keys()
    assert loader._renew_once(str(project)) is None
    hits = snapshot_memo.stats()["hits"]
    decodes = _Decodes(monkeypatch)
    assert await _ask_all(project) == await _ask_all(project)
    assert snapshot_memo.keys() == key  # same snapshot ID after the renewal
    assert snapshot_memo.stats()["hits"] > hits
    assert decodes.count == 0


# --------------------------------------------------------------------------- #
# Concurrency
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_concurrent_requests_agree_with_today(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    today = await _today(project, monkeypatch)
    answers: list[list[Any]] = []
    errors: list[BaseException] = []

    def run() -> None:
        try:
            for _ in range(2):
                answers.append(asyncio.run(_ask_all(project)))
        except BaseException as exc:  # noqa: BLE001 — reported below
            errors.append(exc)

    threads = [threading.Thread(target=run, daemon=True) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(180)
    assert errors == []
    assert len(answers) == 8
    assert all(batch == today for batch in answers)


@pytest.mark.asyncio
async def test_requests_racing_a_republish_never_mix_snapshots(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    query = _QUERIES[3]
    _edit(project, "pkg/helper.py", base._SECOND_CALLER)
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
    assert answers
    assert [a for a in answers if a not in (before, after)] == []
