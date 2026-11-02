"""RFC-0042 P2b: the per-snapshot memo's key, copy, storage and eviction rules.

End-to-end identity and fault injection on a real index are in
``tests/integration/test_resident_snapshot_memo.py``.
"""

from __future__ import annotations

import threading
from typing import Any

import pytest

from tree_sitter_analyzer.resident import loader, snapshot_memo


class _Snap:
    """A cache with a certified-snapshot identity, like ``CertifiedSnapshotCache``."""

    def __init__(self, root: str = "/r", snapshot: str = "s1") -> None:
        self.key = ("certified-snapshot", root, snapshot, "fp", "gen")
        self.storable = True

    def graph_input_identity(self) -> tuple[str, ...]:
        return self.key

    def memo_storable(self) -> bool:
        return self.storable


@pytest.fixture(autouse=True)
def _fresh(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(loader.ENV_VAR, raising=False)
    snapshot_memo.clear()
    yield
    snapshot_memo.clear()


def _counting(value: Any) -> tuple[list[int], Any]:
    calls: list[int] = []

    def compute() -> Any:
        calls.append(1)
        return value

    return calls, compute


def test_a_hit_returns_an_equal_independent_copy() -> None:
    cache = _Snap()
    calls, compute = _counting([{"file": "a.py", "bound_to": {"line": 1}}])
    first = snapshot_memo.cached(cache, "r", ("x",), compute)
    first[0]["bound_to"]["line"] = 99  # the caller's copy is its own
    first.append({})
    second = snapshot_memo.cached(cache, "r", ("x",), compute)
    assert second == [{"file": "a.py", "bound_to": {"line": 1}}]
    second[0]["file"] = "b.py"
    assert snapshot_memo.cached(cache, "r", ("x",), compute)[0]["file"] == "a.py"
    assert calls == [1]
    assert snapshot_memo.stats()["hits"] == 2


def test_copy_value_copies_containers_and_shares_scalars() -> None:
    value = {"a": [1, (2, [3])], "b": {4}, "c": frozenset({5}), "d": "s"}
    copied = snapshot_memo.copy_value(value)
    assert copied == value
    assert copied["a"] is not value["a"]
    assert copied["a"][1][1] is not value["a"][1][1]
    assert copied["b"] is not value["b"]
    assert copied["c"] is value["c"]


def test_none_failures_and_late_reads_are_not_stored() -> None:
    cache = _Snap()
    calls, compute = _counting(None)
    assert snapshot_memo.cached(cache, "r", (), compute) is None
    assert snapshot_memo.cached(cache, "r", (), compute) is None
    assert calls == [1, 1]

    def boom() -> Any:
        raise RuntimeError("INDEX_SNAPSHOT_DEADLINE")

    with pytest.raises(RuntimeError):
        snapshot_memo.cached(cache, "e", (), boom)
    cache.storable = False  # the owner's deadline passed during the read
    calls, compute = _counting([1])
    assert snapshot_memo.cached(cache, "late", (), compute) == [1]
    assert snapshot_memo.cached(cache, "late", (), compute) == [1]
    assert calls == [1, 1]
    assert snapshot_memo.stats()["stored"] == 0


def test_no_identity_off_or_unhashable_args_read_directly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls, compute = _counting([1])
    snapshot_memo.cached(object(), "r", (), compute)  # an uncertified cache
    snapshot_memo.cached(object(), "r", (), compute)
    assert calls == [1, 1]

    class _Live:
        def graph_input_identity(self) -> tuple[str, ...]:
            return ("live", "/r", "x")  # not a certified snapshot

    snapshot_memo.cached(_Live(), "r", (), compute)
    snapshot_memo.cached(_Snap(), "r", ([1],), compute)  # unhashable argument
    snapshot_memo.cached(_Snap(), "r", ([1],), compute)
    monkeypatch.setenv(loader.ENV_VAR, "off")
    snapshot_memo.cached(_Snap(), "off", (), compute)
    snapshot_memo.cached(_Snap(), "off", (), compute)
    assert len(calls) == 7
    assert snapshot_memo.stats()["stored"] == 0

    class _Broken:
        def graph_input_identity(self) -> tuple[str, ...]:
            raise RuntimeError("INDEX_SNAPSHOT_CLOSED")

    assert snapshot_memo.snapshot_key(_Broken()) is None


def test_a_new_snapshot_of_a_root_drops_the_old_memo() -> None:
    old, new = _Snap(snapshot="s1"), _Snap(snapshot="s2")
    snapshot_memo.cached(old, "r", (), lambda: [1])
    assert snapshot_memo.keys() == [old.key]
    calls, compute = _counting([2])
    assert snapshot_memo.cached(new, "r", (), compute) == [2]
    assert snapshot_memo.keys() == [new.key]
    assert calls == [1]
    # The old snapshot's key is never answered from the new snapshot's memo.
    calls, compute = _counting([1])
    assert snapshot_memo.cached(old, "r", (), compute) == [1]
    assert calls == [1]


def test_at_most_max_snapshots_and_max_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for index in range(snapshot_memo.MAX_SNAPSHOTS + 2):
        snapshot_memo.cached(_Snap(root=f"/r{index}"), "r", (), lambda i=index: [i])
    assert snapshot_memo.stats()["snapshots"] == snapshot_memo.MAX_SNAPSHOTS
    snapshot_memo.clear()
    monkeypatch.setattr(snapshot_memo, "MAX_ENTRIES", 2)
    cache = _Snap()
    for index in range(5):
        snapshot_memo.cached(cache, "r", (index,), lambda i=index: [i])
    assert snapshot_memo.stats()["entries"] <= 3


def test_an_entry_is_served_only_under_its_owner_key() -> None:
    cache = _Snap()
    snapshot_memo.cached(cache, "r", (), lambda: [1])
    with snapshot_memo._lock:
        memo = snapshot_memo._memos[cache.key]
        memo[snapshot_memo._OWNER] = ("certified-snapshot", "/r", "forged", "f", "g")
    calls, compute = _counting([2])
    assert snapshot_memo.cached(cache, "r", (), compute) == [2]
    assert calls == [1]


def test_racing_readers_agree() -> None:
    cache = _Snap()
    results: list[Any] = []
    errors: list[BaseException] = []
    start = threading.Barrier(16)

    def run() -> None:
        try:
            start.wait(10)
            for index in range(50):
                results.append(
                    snapshot_memo.cached(
                        cache, "r", (index % 5,), lambda i=index: [i % 5]
                    )
                )
        except BaseException as exc:  # noqa: BLE001 — reported below
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(16)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert errors == []
    assert len(results) == 800
    assert all(result in ([0], [1], [2], [3], [4]) for result in results)
