"""RFC-0001 watch→push bridge: push only on real delta (Codex P2 on #317)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from tree_sitter_analyzer.mcp import watch_push_bridge
from tree_sitter_analyzer.mcp.watch_push_bridge import (
    collect_changed_pairs,
    make_on_sync_callback,
)
from tree_sitter_analyzer.registry.subscription_registry import SubscriptionRegistry


def _seed(registry: SubscriptionRegistry, session: str, selector: str, snap: list):
    """Subscribe and prime the stored snapshot so later diffs are meaningful."""
    registry.subscribe(session, selector)
    # First compute_delta stores the baseline snapshot (added == snap).
    registry.compute_delta(session, selector, snap)


def test_unchanged_selector_is_not_pushed() -> None:
    """A sync event that does not move the result pushes nothing."""
    reg = SubscriptionRegistry(min_interval_s=0.0)
    snap = [{"name": "foo", "file": "a.py", "line": 1}]
    _seed(reg, "s1", ".function", snap)

    # Re-evaluate returns the IDENTICAL snapshot — no delta.
    changed = collect_changed_pairs(reg, lambda sid, sel: list(snap))
    assert changed == []


def test_changed_selector_is_pushed() -> None:
    """When the selector result moves, exactly that pair is returned."""
    reg = SubscriptionRegistry(min_interval_s=0.0)
    _seed(reg, "s1", ".function", [{"name": "foo", "file": "a.py", "line": 1}])

    new_snap = [
        {"name": "foo", "file": "a.py", "line": 1},
        {"name": "bar", "file": "b.py", "line": 2},
    ]
    changed = collect_changed_pairs(reg, lambda sid, sel: list(new_snap))
    assert changed == [("s1", ".function")]


def test_only_the_moved_selector_among_many_is_pushed() -> None:
    """An unrelated subscription is not woken when another selector changes."""
    reg = SubscriptionRegistry(min_interval_s=0.0)
    stable = [{"name": "foo", "file": "a.py", "line": 1}]
    moving = [{"name": "baz", "file": "c.py", "line": 3}]
    _seed(reg, "s1", ".stable", stable)
    _seed(reg, "s1", ".moving", moving)

    def evaluate(_sid: str, selector: str) -> list:
        if selector == ".moving":
            return [*moving, {"name": "new", "file": "d.py", "line": 4}]
        return list(stable)

    changed = collect_changed_pairs(reg, evaluate)
    assert changed == [("s1", ".moving")]


def test_failed_evaluation_preserves_snapshot_and_throttle_time() -> None:
    """2026-09-14：求值失败不能伪装成空结果并污染有效基线。"""
    reg = SubscriptionRegistry(min_interval_s=0.0)
    snap = [{"name": "foo", "file": "a.py", "line": 1}]
    _seed(reg, "s1", ".function", snap)
    sub = reg._subs["s1"][".function"]
    last_sent_at = sub.last_sent_at

    def fail(_session_id: str, _selector: str) -> list[Any]:
        raise RuntimeError("数据库暂时不可用")

    assert collect_changed_pairs(reg, fail) == []
    assert sub.last_snapshot == snap
    assert sub.last_sent_at == last_sent_at


def test_failed_pair_does_not_starve_healthy_pair() -> None:
    """2026-09-14：一个订阅失败时，本轮仍须继续处理其余健康订阅。"""
    reg = SubscriptionRegistry(min_interval_s=0.0)
    stable = [{"name": "old", "file": "a.py", "line": 1}]
    _seed(reg, "s1", ".broken", stable)
    _seed(reg, "s1", ".healthy", stable)

    def evaluate(_session_id: str, selector: str) -> list[Any]:
        if selector == ".broken":
            raise ValueError("选择器求值失败")
        return [{"name": "new", "file": "b.py", "line": 2}]

    assert collect_changed_pairs(reg, evaluate) == [("s1", ".healthy")]


def test_successful_empty_snapshot_is_a_real_removal() -> None:
    """2026-09-14：成功返回空列表仍表示真实删除，不能与异常混为一谈。"""
    reg = SubscriptionRegistry(min_interval_s=0.0)
    _seed(reg, "s1", ".function", [{"name": "foo", "file": "a.py", "line": 1}])

    assert collect_changed_pairs(reg, lambda _sid, _sel: []) == [("s1", ".function")]
    assert reg._subs["s1"][".function"].last_snapshot == []


def test_failed_evaluation_recovers_against_last_good_snapshot() -> None:
    """2026-09-14：失败后相同结果不通知，新结果仍按最后有效基线产生变化。"""
    reg = SubscriptionRegistry(min_interval_s=0.0)
    old = [{"name": "old", "file": "a.py", "line": 1}]
    new = [{"name": "new", "file": "b.py", "line": 2}]
    _seed(reg, "s1", ".function", old)

    def fail(_session_id: str, _selector: str) -> list[Any]:
        raise RuntimeError("临时失败")

    assert collect_changed_pairs(reg, fail) == []
    assert collect_changed_pairs(reg, lambda _sid, _sel: list(old)) == []
    assert collect_changed_pairs(reg, lambda _sid, _sel: list(new)) == [
        ("s1", ".function")
    ]


class _FakeCache:
    def __init__(self, _project_root: str, results: list[dict[str, Any]]) -> None:
        self._results = results

    def get_functions(self) -> list[dict[str, Any]]:
        return list(self._results)


class _PendingFuture:
    def add_done_callback(self, _callback: Callable[[Any], None]) -> None:
        return None


def _capture_bridge_schedules(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    scheduled: list[tuple[str, str]] = []

    class _Loop:
        def is_closed(self) -> bool:
            return False

    monkeypatch.setattr(watch_push_bridge, "get_session_loop", lambda _sid: _Loop())

    def capture(coro: Any, _loop: Any) -> _PendingFuture:
        scheduled.append(
            (coro.cr_frame.f_locals["session_id"], coro.cr_frame.f_locals["uri"])
        )
        coro.close()
        return _PendingFuture()

    monkeypatch.setattr(watch_push_bridge.asyncio, "run_coroutine_threadsafe", capture)
    return scheduled


@pytest.mark.parametrize("failure_layer", ["cache", "parse", "evaluate"])
def test_real_bridge_failure_preserves_subscription_and_recovers(
    monkeypatch: pytest.MonkeyPatch,
    failure_layer: str,
) -> None:
    """2026-09-14：真实桥接路径的缓存、解析或求值异常均不得制造推送或退订。"""
    from tree_sitter_analyzer import ast_cache, hyphae
    from tree_sitter_analyzer.registry import singleton_registry

    reg = SubscriptionRegistry(min_interval_s=0.0)
    monkeypatch.setattr(singleton_registry, "get_subscription_registry", lambda: reg)
    reg.subscribe("s1", ".function")
    results = [{"name": "foo", "file": "a.py", "line": 1}]
    monkeypatch.setattr(ast_cache, "ASTCache", lambda root: _FakeCache(root, results))
    scheduled = _capture_bridge_schedules(monkeypatch)
    callback = make_on_sync_callback("/project")

    callback({})
    assert len(scheduled) == 1
    scheduled.clear()
    baseline = list(reg._subs["s1"][".function"].last_snapshot)

    with monkeypatch.context() as failure_patch:
        if failure_layer == "cache":
            failure_patch.setattr(
                ast_cache,
                "ASTCache",
                lambda _root: (_ for _ in ()).throw(RuntimeError("缓存失败")),
            )
        elif failure_layer == "parse":
            failure_patch.setattr(
                hyphae,
                "parse",
                lambda _selector: (_ for _ in ()).throw(ValueError("解析失败")),
            )
        else:
            failure_patch.setattr(
                hyphae.Evaluator,
                "eval",
                lambda _self, _ast: (_ for _ in ()).throw(RuntimeError("求值失败")),
            )

        callback({})
    assert scheduled == []
    assert reg.subscriptions_for("s1") == [".function"]
    assert reg._subs["s1"][".function"].last_snapshot == baseline

    callback({})
    assert scheduled == []

    results.append({"name": "bar", "file": "b.py", "line": 2})
    callback({})
    assert len(scheduled) == 1


def test_missing_project_root_leaves_registry_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2026-09-14：缺少项目根时不得构造缓存、推送或改写已有快照。"""
    from tree_sitter_analyzer import ast_cache
    from tree_sitter_analyzer.registry import singleton_registry

    reg = SubscriptionRegistry(min_interval_s=0.0)
    monkeypatch.setattr(singleton_registry, "get_subscription_registry", lambda: reg)
    snap = [{"name": "foo", "file": "a.py", "line": 1}]
    _seed(reg, "s1", ".function", snap)
    sub = reg._subs["s1"][".function"]
    last_sent_at = sub.last_sent_at
    monkeypatch.setattr(
        ast_cache,
        "ASTCache",
        lambda _root: pytest.fail("缺少项目根时不应构造缓存"),
    )
    scheduled = _capture_bridge_schedules(monkeypatch)

    make_on_sync_callback(None)({})

    assert scheduled == []
    assert reg.subscriptions_for("s1") == [".function"]
    assert sub.last_snapshot == snap
    assert sub.last_sent_at == last_sent_at
