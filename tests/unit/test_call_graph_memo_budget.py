"""RFC-0043 §4: the call-graph memo is bounded by an estimated byte budget across roots."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer import call_graph_memo as memo


@pytest.fixture(autouse=True)
def _fresh(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(memo.GRAPH_MB_ENV, raising=False)
    memo.clear()
    yield
    memo.clear()


def _state(elements: int) -> dict:
    # one dict entry with a list of ``elements - 2`` items: 1 + 1 + (elements - 2)
    return {"_callers": {"k": list(range(elements - 2))}}


@pytest.mark.parametrize(
    ("raw", "megabytes"),
    [(None, 256), ("64", 64), ("0", 256), ("-3", 256), ("lots", 256), (" 8 ", 8)],
)
def test_budget_from_environment(
    monkeypatch: pytest.MonkeyPatch, raw: str | None, megabytes: int
) -> None:
    if raw is not None:
        monkeypatch.setenv(memo.GRAPH_MB_ENV, raw)

    assert memo.budget_bytes() == megabytes * 1024 * 1024


def test_estimate_counts_entries_two_levels_deep() -> None:
    state = {
        "_callers": {"a": [1, 2, 3], "b": {4, 5}},
        "_functions": [1, 2],
        "_built": True,
    }

    # 3 top-level values + 2 dict keys + 5 inner items + 2 list items
    assert memo.estimate_state_bytes(state) == 12 * memo.BYTES_PER_ELEMENT


def test_lru_root_is_evicted_when_the_bytes_exceed_the_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(memo, "BYTES_PER_ELEMENT", 1024 * 1024)  # 1 element = 1 MiB
    monkeypatch.setenv(memo.GRAPH_MB_ENV, "10")
    memo.store("a", "da", _state(4))
    memo.store("b", "db", _state(4))
    assert memo.lookup("a", "da") is not None  # "a" is now the most recent
    memo.store("c", "dc", _state(4))  # 12 MiB > 10: evict "b"

    assert memo.lookup("b", "db") is None
    assert memo.lookup("a", "da") is not None
    assert memo.lookup("c", "dc") is not None
    assert memo.stats()["bytes"] == 8 * 1024 * 1024


def test_the_root_just_stored_is_kept_even_over_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(memo, "BYTES_PER_ELEMENT", 1024 * 1024)
    monkeypatch.setenv(memo.GRAPH_MB_ENV, "3")
    memo.store("a", "da", _state(2))
    memo.store("big", "dbig", _state(20))

    assert memo.lookup("big", "dbig") is not None
    assert memo.lookup("a", "da") is None
    assert list(memo.stats()["roots"]) == ["big"]


def test_root_count_bound_still_applies() -> None:
    for index in range(memo._MAX_ROOTS + 2):
        memo.store(f"r{index}", f"d{index}", _state(3))

    assert len(memo.stats()["roots"]) == memo._MAX_ROOTS
    assert memo.lookup("r0", "d0") is None


def test_replacing_a_root_replaces_its_size(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(memo, "BYTES_PER_ELEMENT", 1)
    memo.store("a", "d1", _state(10))
    memo.store("a", "d2", _state(4))

    assert memo.stats()["roots"] == {"a": 4}
    assert memo.lookup("a", "d1") is None


def test_discard_and_clear_forget_sizes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(memo, "BYTES_PER_ELEMENT", 1)
    memo.store("a", "da", _state(4))
    memo.store("b", "db", _state(4))
    memo.discard("a")

    assert memo.stats()["roots"] == {"b": 4}
    memo.clear()
    assert memo.stats() == {"roots": {}, "bytes": 0, "budget": memo.budget_bytes()}


def test_extra_keys_of_an_evicted_root_are_forgotten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(memo, "BYTES_PER_ELEMENT", 1024 * 1024)
    monkeypatch.setenv(memo.GRAPH_MB_ENV, "5")
    state = _state(4)
    memo.store("a", "da", state)
    assert memo.add_key("a", state, "extra")
    memo.store("b", "db", _state(4))  # 8 MiB > 5: evict "a"

    assert memo.lookup("a", "extra") is None
    assert "a" not in memo._EXTRA_KEYS
