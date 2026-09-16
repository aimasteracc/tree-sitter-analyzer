"""RFC-0001 watch→push bridge: push only on real delta (Codex P2 on #317)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

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


def test_successful_empty_snapshot_is_a_real_removal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2026-09-14：生产 bridge 的真实空结果表示删除，不与异常混同。"""
    from tree_sitter_analyzer import ast_cache, hyphae
    from tree_sitter_analyzer.mcp.subscription_lifecycle import (
        SubscriptionLifecycleManager,
    )

    reg = SubscriptionRegistry(min_interval_s=0.0)
    manager = SubscriptionLifecycleManager("/project", reg)
    owner = manager.begin_run()
    ticket = manager.subscribe(owner, object(), object(), ".function", 0.0)
    token = manager.issue_watch_token("/project")
    old = [{"name": "foo", "file": "a.py", "line": 1}]
    reg.compute_delta(ticket.session_id, ticket.selector, old)
    monkeypatch.setattr(ast_cache, "ASTCache", lambda root: _FakeCache(root, []))
    monkeypatch.setattr(hyphae, "parse", lambda selector: selector)
    monkeypatch.setattr(hyphae.Evaluator, "eval", lambda _self, _ast: [])
    scheduled = _capture_bridge_schedules(monkeypatch, manager)

    make_on_sync_callback("/project", manager, token)({})

    assert scheduled == [(ticket.session_id, "tsa://hyphae/.function")]
    assert reg._subs[ticket.session_id][ticket.selector].last_snapshot == []


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


def _capture_bridge_schedules(
    monkeypatch: pytest.MonkeyPatch, manager: Any
) -> list[tuple[str, str]]:
    scheduled: list[tuple[str, str]] = []

    def capture(ticket: Any, snapshot: list[Any], uri: str) -> bool:
        if not manager.commit_evaluation(ticket, snapshot):
            return False
        scheduled.append((ticket.session_id, uri))
        return True

    monkeypatch.setattr(manager, "commit_evaluation_and_schedule", capture)
    return scheduled


def test_callback_without_lifecycle_authority_is_a_safe_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Embedding漏装manager/token时，callback不得进入求值或全局fallback。"""
    from tree_sitter_analyzer.mcp import watch_push_bridge

    monkeypatch.setattr(
        watch_push_bridge,
        "_drive_subscriptions",
        lambda *_args: pytest.fail("unauthorized callback reached bridge"),
    )

    make_on_sync_callback("/project")({})
    make_on_sync_callback("/project", object(), None)({})


@pytest.mark.parametrize("failure_layer", ["cache", "parse", "evaluate"])
def test_real_bridge_failure_preserves_subscription_and_recovers(
    monkeypatch: pytest.MonkeyPatch,
    failure_layer: str,
) -> None:
    """2026-09-14：生产 bridge 的单项失败保留基线，其他健康项继续。"""
    from tree_sitter_analyzer import ast_cache, hyphae
    from tree_sitter_analyzer.mcp.subscription_lifecycle import (
        SubscriptionLifecycleManager,
    )

    reg = SubscriptionRegistry(min_interval_s=0.0)
    manager = SubscriptionLifecycleManager("/project", reg)
    owner = manager.begin_run()
    session = object()
    broken = manager.subscribe(owner, session, object(), ".function", 0.0)
    healthy = manager.subscribe(owner, session, object(), ".class", 0.0)
    token = manager.issue_watch_token("/project")
    results = [{"name": "foo", "file": "a.py", "line": 1}]
    monkeypatch.setattr(ast_cache, "ASTCache", lambda root: _FakeCache(root, results))
    monkeypatch.setattr(hyphae, "parse", lambda selector: selector)
    monkeypatch.setattr(
        hyphae.Evaluator,
        "eval",
        lambda self, _ast: self._cache.get_functions(),
    )
    scheduled = _capture_bridge_schedules(monkeypatch, manager)
    callback = make_on_sync_callback("/project", manager, token)

    callback({})
    assert len(scheduled) == 2
    scheduled.clear()
    broken_state = reg._subs[broken.session_id][broken.selector]
    baseline = list(broken_state.last_snapshot)
    last_sent_at = broken_state.last_sent_at

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
            results.append({"name": "bar", "file": "b.py", "line": 2})
            failure_patch.setattr(
                hyphae.Evaluator,
                "eval",
                lambda self, ast: (
                    (_ for _ in ()).throw(RuntimeError("求值失败"))
                    if ast == ".function"
                    else self._cache.get_functions()
                ),
            )
        callback({})

    expected = (
        []
        if failure_layer != "evaluate"
        else [(healthy.session_id, "tsa://hyphae/.class")]
    )
    assert scheduled == expected
    assert reg.subscriptions_for(broken.session_id) == [".function", ".class"]
    assert broken_state.last_snapshot == baseline
    assert broken_state.last_sent_at == last_sent_at

    scheduled.clear()
    callback({})
    expected_recovery = 1 if failure_layer == "evaluate" else 0
    assert len(scheduled) == expected_recovery

    if failure_layer != "evaluate":
        results.append({"name": "bar", "file": "b.py", "line": 2})
        callback({})
        assert len(scheduled) == 2


def test_missing_project_root_leaves_registry_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2026-09-14：缺少项目根时不得构造缓存、推送或改写已有快照。"""
    from tree_sitter_analyzer import ast_cache
    from tree_sitter_analyzer.mcp.subscription_lifecycle import (
        SubscriptionLifecycleManager,
    )

    reg = SubscriptionRegistry(min_interval_s=0.0)
    manager = SubscriptionLifecycleManager(None, reg)
    owner = manager.begin_run()
    ticket = manager.subscribe(owner, object(), object(), ".function", 0.0)
    token = manager.issue_watch_token(None)
    snap = [{"name": "foo", "file": "a.py", "line": 1}]
    reg.compute_delta(ticket.session_id, ticket.selector, snap)
    sub = reg._subs[ticket.session_id][ticket.selector]
    last_sent_at = sub.last_sent_at
    monkeypatch.setattr(
        ast_cache,
        "ASTCache",
        lambda _root: pytest.fail("缺少项目根时不应构造缓存"),
    )
    scheduled = _capture_bridge_schedules(monkeypatch, manager)

    make_on_sync_callback(None, manager, token)({})

    assert scheduled == []
    assert reg.subscriptions_for(ticket.session_id) == [".function"]
    assert sub.last_snapshot == snap
    assert sub.last_sent_at == last_sent_at


def test_2026_09_14_eval_completion_cannot_mutate_resubscribed_incarnation() -> None:
    """求值中退订再重订后，旧求值结果不能成为新订阅基线。"""
    from tree_sitter_analyzer.mcp.subscription_lifecycle import (
        SubscriptionLifecycleManager,
    )

    reg = SubscriptionRegistry(min_interval_s=0.0)
    manager = SubscriptionLifecycleManager("/project", reg)
    owner = manager.begin_run()
    session = object()
    first = manager.subscribe(owner, session, object(), ".function", 0.0)
    token = manager.issue_watch_token("/project")
    old_ticket = manager.snapshot_for_watch(token)[0]
    manager.unsubscribe(owner, session, sub_id=first.session_id, selector=".function")
    manager.subscribe(owner, session, object(), ".function", 0.0)

    assert manager.commit_evaluation(old_ticket, [{"name": "stale"}]) is False
    replacement = reg._subs[first.session_id][".function"]
    assert replacement.last_snapshot == []
    assert replacement.last_sent_at == 0.0


@pytest.mark.asyncio
async def test_2026_09_14_queued_send_cannot_target_replacement_session() -> None:
    """排队后 replacement 占用同一 ID 时，旧 send 不得动态查到 replacement。"""
    from tree_sitter_analyzer.mcp.subscription_lifecycle import (
        SubscriptionLifecycleManager,
    )

    sent: list[str] = []

    class Session:
        async def send_resource_updated(self, _uri: object) -> None:
            sent.append("replacement")

    reg = SubscriptionRegistry(min_interval_s=0.0)
    manager = SubscriptionLifecycleManager("/project", reg)
    owner = manager.begin_run()
    old_session = Session()
    first = manager.subscribe(
        owner, old_session, asyncio.get_running_loop(), ".function", 0.0
    )
    token = manager.issue_watch_token("/project")
    ticket = manager.snapshot_for_watch(token)[0]
    manager.schedule_send(ticket, "tsa://hyphae/.function")
    manager.unsubscribe(
        owner, old_session, sub_id=first.session_id, selector=".function"
    )
    manager.subscribe(owner, old_session, asyncio.get_running_loop(), ".function", 0.0)
    await asyncio.sleep(0)

    assert sent == []


@pytest.mark.asyncio
async def test_2026_09_14_old_failed_completion_does_not_remove_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """旧 future 的失败回调只能收尾旧 incarnation。"""
    from tree_sitter_analyzer.mcp.subscription_lifecycle import (
        SubscriptionLifecycleManager,
    )

    started = asyncio.Event()

    class Session:
        async def send_resource_updated(self, _uri: object) -> None:
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                raise RuntimeError("old send failed") from None

    reg = SubscriptionRegistry(min_interval_s=0.0)
    manager = SubscriptionLifecycleManager("/project", reg)
    finished = asyncio.Event()
    original_finish = manager._finish_send

    def finish_send(pending_id: str, pending: Any, task: asyncio.Task[None]) -> None:
        original_finish(pending_id, pending, task)
        finished.set()

    monkeypatch.setattr(manager, "_finish_send", finish_send)
    owner = manager.begin_run()
    session = Session()
    loop = asyncio.get_running_loop()
    loop_errors: list[dict[str, Any]] = []
    previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: loop_errors.append(context))
    first = manager.subscribe(owner, session, loop, ".function", 0.0)
    token = manager.issue_watch_token("/project")
    old_ticket = manager.snapshot_for_watch(token)[0]
    manager.schedule_send(old_ticket, "tsa://hyphae/.function")
    await asyncio.wait_for(started.wait(), timeout=1)
    old_task = next(iter(manager._pending.values())).task
    assert old_task is not None
    manager.unsubscribe(owner, session, sub_id=first.session_id, selector=".function")
    manager.subscribe(owner, session, loop, ".function", 0.0)
    try:
        await asyncio.wait_for(old_task, timeout=1)
        await asyncio.wait_for(finished.wait(), timeout=1)
    finally:
        loop.set_exception_handler(previous_handler)

    assert reg.subscriptions_for(first.session_id) == [".function"]
    assert manager._pending == {}
    assert loop_errors == []


@pytest.mark.asyncio
@pytest.mark.parametrize("same_root", [True, False])
async def test_2026_09_14_canonical_apps_do_not_cross_evaluate(
    tmp_path, monkeypatch: pytest.MonkeyPatch, same_root: bool
) -> None:
    """两个 canonical app 即使同 root，也只能驱动各自真实 run 的订阅。"""
    import json

    from mcp.shared.memory import create_connected_server_and_client_session

    from tree_sitter_analyzer import ast_cache, hyphae
    from tree_sitter_analyzer.file_watcher import FileWatcherDaemon
    from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
    from tree_sitter_analyzer.mcp.tools import hyphae_subscribe_tool as hst
    from tree_sitter_analyzer.registry.singleton_registry import (
        reset_subscription_registry,
    )

    root_a = tmp_path / "a"
    root_b = root_a if same_root else tmp_path / "b"
    root_a.mkdir()
    if not same_root:
        root_b.mkdir()
    app_a = TreeSitterAnalyzerMCPServer(str(root_a))
    app_b = TreeSitterAnalyzerMCPServer(str(root_b))
    monkeypatch.setattr(FileWatcherDaemon, "start", lambda _self: None)
    evaluated: list[tuple[str, str]] = []

    class Cache:
        def __init__(self, root: str) -> None:
            self.root = root

    class Evaluator:
        def __init__(self, cache: Cache) -> None:
            self.cache = cache

        def eval(self, selector: str) -> list[Any]:
            evaluated.append((self.cache.root, selector))
            return []

    try:
        async with create_connected_server_and_client_session(
            app_a.create_server()
        ) as client_a:
            async with create_connected_server_and_client_session(
                app_b.create_server()
            ) as client_b:
                first = await client_a.call_tool(
                    "search", {"action": "subscribe", "selector": ".function"}
                )
                second = await client_b.call_tool(
                    "search", {"action": "subscribe", "selector": ".class"}
                )
                assert (
                    json.loads(first.content[0].text)["sub_id"]
                    != json.loads(  # type: ignore[union-attr]
                        second.content[0].text  # type: ignore[union-attr]
                    )["sub_id"]
                )
                cache_a = app_a.tools["index"].action_map["cache"]
                await cache_a.execute({"mode": "watch_start"})
                monkeypatch.setattr(ast_cache, "ASTCache", Cache)
                monkeypatch.setattr(hyphae, "parse", lambda selector: selector)
                monkeypatch.setattr(hyphae, "Evaluator", Evaluator)
                cache_a._watcher._on_sync({})
                assert evaluated == [(str(root_a), ".function")]
    finally:
        reset_subscription_registry()
        hst._SESSION_LOOPS.clear()
        hst._SESSION_MIN_INTERVALS.clear()
        hst._SESSION_SESSIONS.clear()
