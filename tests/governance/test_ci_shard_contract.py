"""Pin the macOS test-lane sharding contract (#1910)."""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from tests.pytest_shard import parse_shard, select_shard, shard_of

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "reusable-test.yml"
SHARDS = 2


def _items(count: int) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(nodeid=f"tests/unit/test_mod_{i % 97}.py::test_{i}[{i}]")
        for i in range(count)
    ]


@pytest.mark.parametrize("count", [1, 2, 3, 5])
def test_shards_partition_the_selection_exactly(count: int) -> None:
    """Disjoint shards whose union is the whole selection: nothing is dropped."""
    items = _items(2000)
    seen: list[str] = []
    for index in range(1, count + 1):
        selected, deselected = select_shard(items, index, count)
        assert len(selected) + len(deselected) == len(items)
        seen.extend(item.nodeid for item in selected)
    assert sorted(seen) == sorted(item.nodeid for item in items)


def test_shards_are_balanced_and_stable() -> None:
    items = _items(4000)
    sizes = [len(select_shard(items, i, SHARDS)[0]) for i in (1, 2)]
    assert abs(sizes[0] - sizes[1]) < 0.1 * len(items)
    # Pure function of the node id: independent of collection order or siblings.
    assert shard_of("tests/a.py::t", SHARDS) == shard_of("tests/a.py::t", SHARDS)
    assert (
        select_shard(items[::-1], 1, SHARDS)[0]
        == select_shard(items, 1, SHARDS)[0][::-1]
    )


@pytest.mark.parametrize("bad", ["", "1", "0/2", "3/2", "a/b", "1/0", "-1/2"])
def test_parse_shard_rejects_malformed_values(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_shard(bad)


def test_parse_shard_accepts_one_based_index() -> None:
    assert parse_shard("1/2") == (1, 2)
    assert parse_shard("2/2") == (2, 2)


def _job(name: str) -> dict:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return workflow["jobs"][name]


def test_full_matrix_shards_only_macos() -> None:
    """macOS runs shards 1 and 2 for every version; other OSes run one lane."""
    matrix = _job("test-matrix-full")["strategy"]["matrix"]
    assert matrix["shard"] == [1, 2]
    excluded = {(e["os"], e["shard"]) for e in matrix["exclude"] if "shard" in e}
    assert excluded == {("ubuntu-latest", 2), ("windows-latest", 2)}
    assert not any(
        e.get("os") == "macos-latest" and "shard" in e for e in matrix["exclude"]
    )


def test_pr_matrix_runs_both_macos_shards() -> None:
    entries = _job("test-matrix-pr")["strategy"]["matrix"]["include"]
    macos = [e for e in entries if e["os"] == "macos-latest"]
    assert sorted(e["shard"] for e in macos) == [1, 2]
    assert not any("shard" in e for e in entries if e["os"] != "macos-latest")


def test_no_coverage_step_passes_the_shard_on_macos_only() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    pattern = re.escape(
        "${{ runner.os == 'macOS' && format('--shard={0}/2 "
        "--session-timeout=1080', matrix.shard) || '' }}"
    )
    assert len(re.findall(pattern, text)) == 2
    # Failure artifacts of the two shards must not collide on one name.
    assert text.count("-shard${{ matrix.shard || 1 }}-attempt") == 2
