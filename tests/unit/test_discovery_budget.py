"""首次捕获的发现预算随目录项数放宽，仍越界时诚实失败（#1601）。

用假时钟模拟负载下每项 5 ms / 62.5 ms 的打开成本，不构造真实的 2,800 文件树。
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

import pytest

import tree_sitter_analyzer.index_candidate_walker as walker
import tree_sitter_analyzer.indexing_snapshot as snapshots
from tree_sitter_analyzer.cache.source_recheck import recheck_discovery_seconds
from tree_sitter_analyzer.discovery_budget import discovery_budget_seconds

_ENTRIES = 2_800


class _Clock:
    """每处理一项前进固定秒数的假单调时钟。"""

    def __init__(self, step: float) -> None:
        self.now = 0.0
        self.step = step

    def monotonic(self) -> float:
        return self.now

    def tick(self) -> None:
        self.now += self.step


def _slow_walk(clock: _Clock, root: str):
    def walk(_root: str):
        for index in range(_ENTRIES):
            clock.tick()
            yield os.path.join(root, f"unsupported-{index}.txt")

    return walk


def _snapshot(tmp_path, monkeypatch, step: float) -> snapshots.IndexCandidateSnapshot:
    clock = _Clock(step)
    monkeypatch.setattr(snapshots, "time", SimpleNamespace(monotonic=clock.monotonic))
    return snapshots.build_index_candidate_snapshot(
        str(tmp_path),
        max_files=_ENTRIES,
        exclude_patterns=frozenset(),
        walk_fn=_slow_walk(clock, str(tmp_path)),
        language_fn=lambda _path: None,
    )


def test_budget_formula_is_shared_with_publish_recheck() -> None:
    # #1601: 首次捕获与 #1597 复核共用同一公式，不引入第三个公式。
    previous = SimpleNamespace(discovered=_ENTRIES)
    assert (
        discovery_budget_seconds(_ENTRIES),
        recheck_discovery_seconds(previous),
    ) == (
        58.0,
        58.0,
    )


def test_first_capture_finishes_2800_slow_entries(tmp_path, monkeypatch) -> None:
    # #1601: 5 ms/项共 14 s，超过旧的固定 5 s，但在 30 s + 10 ms/项之内。
    snapshot = _snapshot(tmp_path, monkeypatch, 0.005)

    assert (snapshot.discovery_error, snapshot.discovered, snapshot.errors) == (
        None,
        _ENTRIES,
        0,
    )


def test_first_capture_still_fails_honestly_when_too_slow(
    tmp_path, monkeypatch
) -> None:
    # #1601: 62.5 ms/项在第 572 项越过 30 + 0.01 * 572 s，失败关闭为预算错误。
    snapshot = _snapshot(tmp_path, monkeypatch, 0.0625)

    assert (snapshot.discovery_error, snapshot.discovered, snapshot.errors) == (
        "INDEX_CANDIDATE_DISCOVERY_BUDGET",
        572,
        1,
    )


class _Entry:
    def __init__(self, clock: _Clock, index: int) -> None:
        self._clock = clock
        self.name = f"unsupported-{index}.txt"
        self.path = f"/root/{self.name}"

    def is_dir(self, *, follow_symlinks: bool) -> bool:
        self._clock.tick()
        return False


class _Scanner:
    def __init__(self, entries: list[Any]) -> None:
        self._entries = iter(entries)

    def __next__(self) -> Any:
        return next(self._entries)

    def close(self) -> None:
        return None


def _walk(monkeypatch, step: float) -> list[str]:
    clock = _Clock(step)
    entries = [_Entry(clock, index) for index in range(_ENTRIES)]
    monkeypatch.setattr(walker, "time", SimpleNamespace(monotonic=clock.monotonic))
    monkeypatch.setattr(walker.os, "name", "nt")
    monkeypatch.setattr(walker.os, "scandir", lambda _path: _Scanner(entries))
    return list(
        snapshots.walk_index_candidate_entries("/root", excluded_dir_names=frozenset())
    )


def test_walker_default_budget_scales_with_entries(monkeypatch) -> None:
    # #1601: 遍历器自身的默认预算同样放宽，2,800 项全部产出。
    assert len(_walk(monkeypatch, 0.005)) == _ENTRIES


def test_walker_default_budget_still_bounds_slow_walk(monkeypatch) -> None:
    # #1601: 越界仍抛类型化预算错误，而不是无界遍历。
    with pytest.raises(
        walker.CandidateDiscoveryBudgetExceeded,
        match="INDEX_CANDIDATE_DISCOVERY_BUDGET",
    ):
        _walk(monkeypatch, 0.0625)
