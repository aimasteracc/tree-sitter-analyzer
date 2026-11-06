"""RFC-0043 Phase C: the per-snapshot memo counts its entries and tables against
one byte budget."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

import pytest

from tree_sitter_analyzer.resident import loader, parse_facts, snapshot_memo


class _Snap:
    def __init__(self, root: str = "/r", snapshot: str = "s1") -> None:
        self.key = ("certified-snapshot", root, snapshot, "fp", "gen")

    def graph_input_identity(self) -> tuple[str, ...]:
        return self.key

    def memo_storable(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def _fresh(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(loader.ENV_VAR, raising=False)
    snapshot_memo.clear()
    yield
    snapshot_memo.clear()


def _rows(count: int) -> list[dict[str, Any]]:
    return [{"file": f"f{index}.py", "line": index} for index in range(count)]


def test_stored_entries_are_counted_and_cleared() -> None:
    cache = _Snap()
    value = _rows(3)
    snapshot_memo.cached(cache, "r", ("a",), lambda: value)

    expected = parse_facts.estimate_bytes(value) + parse_facts.estimate_bytes(
        ("r", ("a",))
    )
    assert snapshot_memo.stats()["bytes"] == expected
    snapshot_memo.clear()
    assert snapshot_memo.stats()["bytes"] == 0


def test_an_entry_past_the_budget_is_computed_not_stored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = _Snap()
    small = snapshot_memo.estimate_entry(("r", ("a",)), _rows(1))
    monkeypatch.setattr(snapshot_memo, "MAX_BYTES", small + 10)
    calls: list[int] = []

    def big() -> list[dict[str, Any]]:
        calls.append(1)
        return _rows(50)

    snapshot_memo.cached(cache, "r", ("a",), lambda: _rows(1))
    first = snapshot_memo.cached(cache, "r", ("b",), big)
    second = snapshot_memo.cached(cache, "r", ("b",), big)

    assert first == second == _rows(50)
    assert calls == [1, 1]
    assert snapshot_memo.stats()["entries"] == 1


def test_least_recently_used_snapshots_leave_first_but_not_the_current(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    one = snapshot_memo.estimate_entry(("r", ()), _rows(20))
    monkeypatch.setattr(snapshot_memo, "MAX_BYTES", int(one * 2.5))
    roots = [_Snap(root=f"/r{index}") for index in range(3)]
    snapshot_memo.cached(roots[0], "r", (), lambda: _rows(20))
    snapshot_memo.cached(roots[1], "r", (), lambda: _rows(20))
    snapshot_memo.cached(roots[0], "r", (), lambda: _rows(20))  # hit: newest
    snapshot_memo.cached(roots[2], "r", (), lambda: _rows(20))

    kept = snapshot_memo.keys()
    assert roots[1].key not in kept
    assert roots[0].key in kept and roots[2].key in kept
    assert snapshot_memo.stats()["bytes"] <= int(one * 2.5)


def test_a_table_larger_than_the_budget_is_kept_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(snapshot_memo, "MAX_BYTES", 1_000)
    other = _Snap(root="/other")
    snapshot_memo.cached(other, "r", (), lambda: _rows(1))
    cache = _Snap()
    table = MappingProxyType({f"name{i}": (("a.py", i),) for i in range(500)})
    calls: list[int] = []

    def build() -> Any:
        calls.append(1)
        return table

    assert snapshot_memo.cached_table(cache, "t", build) is table
    assert snapshot_memo.cached_table(cache, "t", build) is table
    assert calls == [1]
    assert snapshot_memo.keys() == [cache.key]  # the other snapshot made room


def test_table_estimate_scales_with_rows() -> None:
    def table(rows: int) -> Any:
        return MappingProxyType({f"name{i}": (("a.py", i),) for i in range(rows)})

    small = snapshot_memo.estimate_entry(("table", "t"), table(100), table=True)
    large = snapshot_memo.estimate_entry(("table", "t"), table(10_000), table=True)
    empty = snapshot_memo.estimate_entry(("table", "t"), table(0), table=True)
    exact = parse_facts.estimate_bytes(dict(table(100)))

    assert 50 < large / small < 150
    assert empty < small
    assert small >= exact  # errs high: per-row overhead on top of the rows


def test_a_new_snapshot_of_a_root_releases_its_bytes() -> None:
    snapshot_memo.cached(_Snap(snapshot="s1"), "r", (), lambda: _rows(20))
    before = snapshot_memo.stats()["bytes"]
    snapshot_memo.cached(_Snap(snapshot="s2"), "r", (), lambda: _rows(1))

    assert 0 < snapshot_memo.stats()["bytes"] < before
    assert len(snapshot_memo.keys()) == 1
