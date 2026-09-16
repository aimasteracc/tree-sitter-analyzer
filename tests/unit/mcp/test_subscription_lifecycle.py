"""R1b lifecycle manager 的确定性并发回归。"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from tree_sitter_analyzer.registry.subscription_registry import SubscriptionRegistry


def test_2026_09_14_retire_between_enqueue_and_handle_publish_cancels_handle() -> None:
    """starter handle 返回前 retire 时，返回的确切 handle 不能失去跟踪。"""
    from tree_sitter_analyzer.mcp.subscription_lifecycle import (
        SubscriptionLifecycleManager,
    )

    class Handle:
        cancelled = False

        def cancel(self) -> None:
            self.cancelled = True

    class Loop:
        def __init__(self) -> None:
            self.handle = Handle()

        def call_soon_threadsafe(self, callback: Any, *args: Any) -> Handle:
            if callback.__name__ == "_start_send":
                manager.retire_run(owner)
            else:
                callback(*args)
            return self.handle

    manager = SubscriptionLifecycleManager(
        "/project", SubscriptionRegistry(min_interval_s=0.0)
    )
    owner = manager.begin_run()
    loop = Loop()
    manager.subscribe(owner, object(), loop, ".function", 0.0)
    token = manager.issue_watch_token("/project")
    ticket = manager.snapshot_for_watch(token)[0]

    manager.schedule_send(ticket, "tsa://hyphae/.function")

    assert loop.handle.cancelled is True
    assert manager._pending == {}


def test_2026_09_14_create_task_failure_closes_coroutine_and_clears_pending() -> None:
    """loop 拒绝 create_task 时不得留下 pending 或未 await coroutine。"""
    from tree_sitter_analyzer.mcp.subscription_lifecycle import (
        SubscriptionLifecycleManager,
    )

    class Handle:
        def cancel(self) -> None:
            return None

    class Loop:
        coroutine: Any = None

        def call_soon_threadsafe(self, callback: Any, *args: Any) -> Handle:
            callback(*args)
            return Handle()

        def create_task(self, coroutine: Any) -> None:
            self.coroutine = coroutine
            raise RuntimeError("task factory closed")

    manager = SubscriptionLifecycleManager(
        "/project", SubscriptionRegistry(min_interval_s=0.0)
    )
    owner = manager.begin_run()
    loop = Loop()
    manager.subscribe(owner, object(), loop, ".function", 0.0)
    token = manager.issue_watch_token("/project")

    manager.schedule_send(
        manager.snapshot_for_watch(token)[0], "tsa://hyphae/.function"
    )

    assert manager._pending == {}
    assert loop.coroutine.cr_frame is None


@pytest.mark.asyncio
async def test_2026_09_14_retire_record_before_cancel_cannot_reserve_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """retire 已移除 record 而尚未 cancel 时，send 不能取得 reservation。"""
    import threading

    from tree_sitter_analyzer.mcp.subscription_lifecycle import (
        SubscriptionLifecycleManager,
    )

    class Handle:
        def cancel(self) -> None:
            return None

    class Loop:
        def call_soon_threadsafe(self, _callback: Any, *_args: Any) -> Handle:
            return Handle()

    sent: list[str] = []

    class Session:
        async def send_resource_updated(self, _uri: object) -> None:
            sent.append("sent")

    manager = SubscriptionLifecycleManager(
        "/project", SubscriptionRegistry(min_interval_s=0.0)
    )
    owner = manager.begin_run()
    manager.subscribe(owner, Session(), Loop(), ".function", 0.0)
    token = manager.issue_watch_token("/project")
    ticket = manager.snapshot_for_watch(token)[0]
    manager.schedule_send(ticket, "tsa://hyphae/.function")
    pending_id, pending = next(iter(manager._pending.items()))
    records_removed = threading.Event()
    release_cancel = threading.Event()
    real_cancel = manager._cancel_for

    def paused_cancel(tickets: list[Any]) -> None:
        records_removed.set()
        assert release_cancel.wait(3)
        real_cancel(tickets)

    monkeypatch.setattr(manager, "_cancel_for", paused_cancel)
    retiring = asyncio.create_task(asyncio.to_thread(manager.retire_run, owner))
    assert await asyncio.to_thread(records_removed.wait, 3)
    await manager._send(pending_id, pending, "tsa://hyphae/.function")
    release_cancel.set()
    await retiring

    assert sent == []


def test_owner_root_and_session_guards_reject_before_mutation() -> None:
    """外来owner/ID、错误root及同owner换session均在写入前拒绝。"""
    from tree_sitter_analyzer.mcp.subscription_lifecycle import (
        SubscriptionLifecycleManager,
    )

    registry = SubscriptionRegistry(min_interval_s=0.0)
    manager = SubscriptionLifecycleManager("/project", registry)
    foreign_manager = SubscriptionLifecycleManager("/project")
    owner = manager.begin_run()
    foreign_owner = foreign_manager.begin_run()
    session = object()
    ticket = manager.subscribe(owner, session, object(), ".function", 0.0)

    assert manager.require_owner(owner) is owner
    assert manager.subscribe(owner, session, object(), ".function", 1.0) is ticket

    with pytest.raises(ValueError, match="lifespan owner"):
        manager.require_owner(object())
    with pytest.raises(ValueError, match="current MCP connection"):
        manager.unsubscribe(owner, session, sub_id="session-foreign", selector=None)
    with pytest.raises(ValueError, match="another session"):
        manager.subscribe(owner, object(), object(), ".class", 0.0)
    with pytest.raises(ValueError, match="no longer active"):
        manager.subscribe(foreign_owner, object(), object(), ".class", 0.0)
    with pytest.raises(ValueError, match="project root"):
        manager.issue_watch_token("/other")

    assert registry.subscriptions_for(ticket.session_id) == [".function"]


@pytest.mark.asyncio
async def test_lifespan_retires_owner_after_body() -> None:
    """公开lifespan在正常退出后撤销run owner。"""
    from tree_sitter_analyzer.mcp.subscription_lifecycle import (
        SubscriptionLifecycleManager,
    )

    manager = SubscriptionLifecycleManager("/project")
    async with manager.lifespan(object()) as owner:
        assert manager.require_owner(owner) is owner

    with pytest.raises(ValueError, match="no longer active"):
        manager.require_owner(owner)


def test_rebind_removes_last_registry_session_and_pre_watch_ticket_is_stale() -> None:
    """项目换绑清理最后订阅；未绑定watch token的旧ticket不能提交求值。"""
    from tree_sitter_analyzer.mcp.subscription_lifecycle import (
        SubscriptionLifecycleManager,
    )

    registry = SubscriptionRegistry(min_interval_s=0.0)
    manager = SubscriptionLifecycleManager("/project", registry)
    owner = manager.begin_run()
    ticket = manager.subscribe(owner, object(), object(), ".function", 0.0)

    assert manager.commit_evaluation(ticket, [{"name": "stale"}]) is False
    manager.rebind_project("/next")

    assert registry.subscriptions_for(ticket.session_id) == []


def test_revoked_watch_cannot_commit_or_reserve_a_notification() -> None:
    """watch token撤销后，旧求值不得改写基线或建立pending通知。"""
    from tree_sitter_analyzer.mcp.subscription_lifecycle import (
        SubscriptionLifecycleManager,
    )

    registry = SubscriptionRegistry(min_interval_s=0.0)
    manager = SubscriptionLifecycleManager("/project", registry)
    owner = manager.begin_run()
    ticket = manager.subscribe(owner, object(), object(), ".function", 0.0)
    token = manager.issue_watch_token("/project")
    watch_ticket = manager.snapshot_for_watch(token)[0]
    manager.revoke_watch_token(token)

    assert (
        manager.commit_evaluation_and_schedule(
            watch_ticket,
            [{"name": "stale"}],
            "tsa://hyphae/.function",
        )
        is False
    )
    assert registry._subs[ticket.session_id][ticket.selector].last_snapshot == []
    assert manager._pending == {}


def test_scheduling_failure_clears_only_its_pending_reservation() -> None:
    """loop拒绝线程投递时清理确切pending，并保留有效订阅。"""
    from tree_sitter_analyzer.mcp.subscription_lifecycle import (
        SubscriptionLifecycleManager,
    )

    class ClosedLoop:
        def call_soon_threadsafe(self, _callback: Any, *_args: Any) -> None:
            raise RuntimeError("loop closed")

    registry = SubscriptionRegistry(min_interval_s=0.0)
    manager = SubscriptionLifecycleManager("/project", registry)
    owner = manager.begin_run()
    ticket = manager.subscribe(owner, object(), ClosedLoop(), ".function", 0.0)
    token = manager.issue_watch_token("/project")

    manager.schedule_send(
        manager.snapshot_for_watch(token)[0], "tsa://hyphae/.function"
    )

    assert manager._pending == {}
    assert registry.subscriptions_for(ticket.session_id) == [".function"]


@pytest.mark.asyncio
async def test_watch_token_revocation_preserves_already_accepted_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """撤销watch token后，已原子接纳的通知仍须送达且旧token不能再排队。"""
    from tree_sitter_analyzer.mcp.subscription_lifecycle import (
        SubscriptionLifecycleManager,
    )

    started = asyncio.Event()
    release = asyncio.Event()
    finished = asyncio.Event()
    sent = 0

    class Session:
        async def send_resource_updated(self, _uri: object) -> None:
            nonlocal sent
            sent += 1
            started.set()
            await release.wait()

    manager = SubscriptionLifecycleManager("/project")
    owner = manager.begin_run()
    loop = asyncio.get_running_loop()
    manager.subscribe(owner, Session(), loop, ".function", 0.0)
    original_finish = manager._finish_send

    def finish_send(pending_id: str, pending: Any, task: asyncio.Task[None]) -> None:
        original_finish(pending_id, pending, task)
        finished.set()

    monkeypatch.setattr(manager, "_finish_send", finish_send)
    old_token = manager.issue_watch_token("/project")
    new_token = manager.issue_watch_token("/project")
    old_ticket = manager.snapshot_for_watch(old_token)[0]
    new_ticket = manager.snapshot_for_watch(new_token)[0]
    assert manager.commit_evaluation_and_schedule(
        old_ticket,
        [{"name": "old-token-change"}],
        "tsa://hyphae/.function",
    )
    manager.schedule_send(new_ticket, "tsa://hyphae/.function")
    old_pending, new_pending = manager._pending.values()
    old_handle = old_pending.handle
    new_handle = new_pending.handle
    assert old_handle is not None
    assert new_handle is not None

    manager.revoke_watch_token(None)
    manager.revoke_watch_token(old_token)
    await asyncio.wait_for(started.wait(), timeout=1)

    assert manager.is_watch_token_current(old_token) is False
    assert manager.snapshot_for_watch(old_token) == []
    assert manager.is_watch_token_current(new_token) is True
    assert old_handle.cancelled() is False
    assert new_handle.cancelled() is False
    assert len(manager._pending) == 2
    assert sent == 2
    manager.schedule_send(old_ticket, "tsa://hyphae/.function")
    assert len(manager._pending) == 2
    assert old_pending.task is not None
    assert new_pending.task is not None

    release.set()
    await asyncio.wait_for(old_pending.task, timeout=1)
    await asyncio.wait_for(new_pending.task, timeout=1)
    await asyncio.sleep(0)
    await asyncio.wait_for(finished.wait(), timeout=1)
    assert manager._pending == {}


def test_retire_during_task_publication_cancels_exact_task() -> None:
    """create_task返回前退役时，新task必须被取消而不能成为孤儿。"""
    from tree_sitter_analyzer.mcp.subscription_lifecycle import (
        SubscriptionLifecycleManager,
    )

    class Handle:
        def cancel(self) -> None:
            return None

    class Task:
        cancelled = False

        def add_done_callback(self, _callback: Any) -> None:
            return None

        def cancel(self) -> None:
            self.cancelled = True

    class Loop:
        def __init__(self) -> None:
            self.task = Task()

        def call_soon_threadsafe(self, callback: Any, *args: Any) -> Handle:
            callback(*args)
            return Handle()

        def create_task(self, coroutine: Any) -> Task:
            coroutine.close()
            manager.retire_run(owner)
            return self.task

    manager = SubscriptionLifecycleManager(
        "/project", SubscriptionRegistry(min_interval_s=0.0)
    )
    owner = manager.begin_run()
    loop = Loop()
    manager.subscribe(owner, object(), loop, ".function", 0.0)
    token = manager.issue_watch_token("/project")

    manager.schedule_send(
        manager.snapshot_for_watch(token)[0], "tsa://hyphae/.function"
    )

    assert loop.task.cancelled is True
    assert manager._pending == {}


@pytest.mark.asyncio
async def test_retire_cancels_started_send_and_runs_cancelled_completion() -> None:
    """退役取消真实已启动send，完成回调显式处理CancelledError。"""
    from tree_sitter_analyzer.mcp.subscription_lifecycle import (
        SubscriptionLifecycleManager,
    )

    started = asyncio.Event()

    class Session:
        async def send_resource_updated(self, _uri: object) -> None:
            started.set()
            await asyncio.Event().wait()

    manager = SubscriptionLifecycleManager(
        "/project", SubscriptionRegistry(min_interval_s=0.0)
    )
    owner = manager.begin_run()
    loop = asyncio.get_running_loop()
    manager.subscribe(owner, Session(), loop, ".function", 0.0)
    token = manager.issue_watch_token("/project")
    manager.schedule_send(
        manager.snapshot_for_watch(token)[0], "tsa://hyphae/.function"
    )
    await asyncio.wait_for(started.wait(), timeout=1)
    task = next(iter(manager._pending.values())).task
    assert task is not None

    manager.retire_run(owner)
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0)

    assert task.cancelled()
    assert manager._pending == {}


def test_failed_completion_is_diagnostic_and_identity_scoped() -> None:
    """异常完成只收尾其pending identity，不向事件循环传播。"""
    from tree_sitter_analyzer.mcp.subscription_lifecycle import (
        SubscriptionLifecycleManager,
        _Pending,
    )

    class FailedTask:
        def cancelled(self) -> bool:
            return False

        def result(self) -> None:
            raise RuntimeError("send failed")

    manager = SubscriptionLifecycleManager("/project")
    owner = manager.begin_run()
    ticket = manager.subscribe(owner, object(), object(), ".function", 0.0)
    pending = _Pending(ticket)
    manager._pending["old"] = pending

    manager._finish_send("old", pending, FailedTask())  # type: ignore[arg-type]

    assert manager._pending == {}


def test_closed_loop_cancellation_is_best_effort_for_handle_and_task() -> None:
    """closed loop及拒绝cancel的对象不能打断owner退役。"""
    from tree_sitter_analyzer.mcp.subscription_lifecycle import (
        SubscriptionLifecycleManager,
        _Pending,
    )

    class RefusesCancel:
        def cancel(self) -> None:
            raise RuntimeError("already closed")

    class ClosedLoop:
        def call_soon_threadsafe(self, _callback: Any, *_args: Any) -> None:
            raise RuntimeError("loop closed")

    manager = SubscriptionLifecycleManager("/project")
    owner = manager.begin_run()
    ticket = manager.subscribe(owner, object(), ClosedLoop(), ".function", 0.0)
    pending = _Pending(ticket, handle=RefusesCancel(), task=RefusesCancel())  # type: ignore[arg-type]
    manager._pending["closed"] = pending

    manager.retire_run(owner)

    assert manager._pending == {}


def test_rebind_cleans_last_selector_without_touching_other_app() -> None:
    """同session先保留sibling、最后清maps，且不清另一应用。"""
    from tree_sitter_analyzer.mcp.subscription_lifecycle import (
        SubscriptionLifecycleManager,
    )
    from tree_sitter_analyzer.mcp.tools import hyphae_subscribe_tool as hst

    registry = SubscriptionRegistry(min_interval_s=0.0)
    first = SubscriptionLifecycleManager("/first", registry)
    second = SubscriptionLifecycleManager("/second", registry)
    first_owner, second_owner = first.begin_run(), second.begin_run()
    first_session, second_session = object(), object()
    first_ticket = first.subscribe(
        first_owner, first_session, object(), ".function", 0.0
    )
    first.subscribe(first_owner, first_session, object(), ".class", 0.0)
    second_ticket = second.subscribe(
        second_owner, second_session, object(), ".class", 0.0
    )

    try:
        first.rebind_project("/next")

        assert registry.subscriptions_for(first_ticket.session_id) == []
        assert first_ticket.session_id not in hst._SESSION_SESSIONS
        assert registry.subscriptions_for(second_ticket.session_id) == [".class"]
        assert hst._SESSION_SESSIONS[second_ticket.session_id] is second_session
    finally:
        second.retire_run(second_owner)


def test_create_task_failure_after_retire_preserves_replacement() -> None:
    """task创建中退役后抛错，只关闭旧coroutine，不删除replacement。"""
    from tree_sitter_analyzer.mcp.subscription_lifecycle import (
        SubscriptionLifecycleManager,
    )

    class Handle:
        def cancel(self) -> None:
            return None

    class Loop:
        coroutine: Any = None

        def call_soon_threadsafe(self, callback: Any, *args: Any) -> Handle:
            callback(*args)
            return Handle()

        def create_task(self, coroutine: Any) -> None:
            self.coroutine = coroutine
            manager.retire_run(old_owner)
            new_owner = manager.begin_run()
            replacements.append(
                manager.subscribe(new_owner, session, object(), ".function", 0.0)
            )
            raise RuntimeError("task factory failed after retirement")

    manager = SubscriptionLifecycleManager("/project")
    old_owner = manager.begin_run()
    session = object()
    replacements: list[Any] = []
    loop = Loop()
    manager.subscribe(old_owner, session, loop, ".function", 0.0)
    token = manager.issue_watch_token("/project")

    manager.schedule_send(
        manager.snapshot_for_watch(token)[0], "tsa://hyphae/.function"
    )

    assert loop.coroutine.cr_frame is None
    assert manager._pending == {}
    assert (
        manager._records[(replacements[0].session_id, ".function")] is replacements[0]
    )
