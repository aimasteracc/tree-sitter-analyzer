"""RFC-0032 follow-up (#1664 item 1): the publication-lease wait bound is 30 s.

Measured on Windows (record ``e6-lease-wait`` in
``rfcs/evidence/0032-feasibility/observations.jsonl``): the publish critical
section of a refresh of this repository held the lease for 3.4 to 6.6 s, so the
old 5 s bound reported ``INDEX_WRITER_BUSY`` for ordinary contention. The wait
ends as soon as the holder releases the lease.

The interleaving is deterministic: the holder releases only after the waiter has
opened its lease connection; no sleep decides the outcome.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import tree_sitter_analyzer.cache.generation_store as store_owner
from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.cache.generation_routing import generation_storage_path
from tree_sitter_analyzer.cache.generation_store import GenerationStore

_EVENT_WAIT_S = 30


def _published_store(root: Path) -> GenerationStore:
    (root / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    cache = ASTCache(str(root))
    try:
        cache.index_project()
    finally:
        cache.close()
    return GenerationStore(
        str(root),
        str(generation_storage_path(str(root))),
        logical_path=str(root / ".ast-cache" / "index.db"),
    )


def test_lease_wait_bound_is_the_rfc_30_seconds():
    assert store_owner.LEASE_TIMEOUT_S == 30.0


def test_waiter_gets_the_lease_when_the_holder_releases_it(tmp_path, monkeypatch):
    store = _published_store(tmp_path)
    lock_path = generation_storage_path(str(tmp_path)) / "publication.lock.db"
    holder = sqlite3.connect(lock_path)
    holder.execute("BEGIN IMMEDIATE")
    waiting = threading.Event()
    timeouts: list[float] = []
    real_connect = sqlite3.connect

    def connect(database, *args, **kwargs):
        connection = real_connect(database, *args, **kwargs)
        if Path(database) == lock_path:
            timeouts.append(kwargs["timeout"])
            waiting.set()
        return connection

    monkeypatch.setattr(store_owner.sqlite3, "connect", connect)
    outcome: list[object] = []

    def capture() -> None:
        try:
            outcome.append(store.capture())
        except BaseException as exc:  # reported below, not swallowed
            outcome.append(exc)

    waiter = threading.Thread(target=capture)
    waiter.start()
    try:
        assert waiting.wait(_EVENT_WAIT_S)
    finally:
        holder.close()  # the other writer finishes its critical section
        waiter.join(_EVENT_WAIT_S)
    assert not waiter.is_alive()
    assert timeouts == [30.0]
    assert len(outcome) == 1
    assert not isinstance(outcome[0], BaseException), outcome[0]
    assert outcome[0].parent == store.active_selector()
