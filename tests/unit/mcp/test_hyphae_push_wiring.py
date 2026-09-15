"""覆盖 RFC-0001 session 捕获、生命周期所有权和 manager 发送路径。"""

from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from typing import Any

import pytest
from mcp.server.lowlevel import Server
from mcp.server.lowlevel.server import RequestContext, request_ctx
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import TextContent, Tool

from tree_sitter_analyzer.mcp.subscription_lifecycle import (
    SubscriptionLifecycleManager,
)
from tree_sitter_analyzer.mcp.tools import hyphae_subscribe_tool as hst
from tree_sitter_analyzer.registry.singleton_registry import (
    get_subscription_registry,
    reset_subscription_registry,
)


@contextmanager
def _request_session(session: Any, manager: SubscriptionLifecycleManager, owner: Any):
    token = request_ctx.set(
        RequestContext(
            request_id="test",
            meta=None,
            session=session,
            lifespan_context=owner,
        )
    )
    try:
        yield
    finally:
        request_ctx.reset(token)


def _owned_tools(tmp_path: Any):
    manager = SubscriptionLifecycleManager(str(tmp_path))
    owner = manager.begin_run()
    return (
        manager,
        owner,
        hst.HyphaeSubscribeTool(str(tmp_path), manager),
        hst.HyphaeUnsubscribeTool(str(tmp_path), manager),
    )


def _watch_ticket(
    manager: SubscriptionLifecycleManager, project_root: str, selector: str
):
    token = manager.issue_watch_token(project_root)
    return next(
        ticket
        for ticket in manager.snapshot_for_watch(token)
        if ticket.selector == selector
    )


@pytest.fixture(autouse=True)
def _clean_subscription_state():
    """隔离全局 registry 与传输映射。"""
    reset_subscription_registry()
    hst._SESSION_LOOPS.clear()
    hst._SESSION_MIN_INTERVALS.clear()
    hst._SESSION_SESSIONS.clear()
    yield
    reset_subscription_registry()
    hst._SESSION_LOOPS.clear()
    hst._SESSION_MIN_INTERVALS.clear()
    hst._SESSION_SESSIONS.clear()


def test_capture_session_obj_returns_none_outside_request_context() -> None:
    """Outside an MCP request, request_ctx is unset → capture returns None,
    never raising (the bridge degrades gracefully)."""
    assert hst._capture_session_obj() is None


def test_session_obj_store_roundtrip() -> None:
    """get_session_obj returns what was captured, and None for unknown ids."""
    sentinel = object()
    hst._SESSION_SESSIONS["sess-x"] = sentinel
    try:
        assert hst.get_session_obj("sess-x") is sentinel
        assert hst.get_session_obj("missing") is None
    finally:
        hst._SESSION_SESSIONS.pop("sess-x", None)


def test_session_loop_store_roundtrip() -> None:
    """get_session_loop mirrors the captured loop; None when absent."""
    loop = asyncio.new_event_loop()
    try:
        hst._SESSION_LOOPS["sess-y"] = loop
        assert hst.get_session_loop("sess-y") is loop
        assert hst.get_session_loop("nope") is None
    finally:
        hst._SESSION_LOOPS.pop("sess-y", None)
        loop.close()


@pytest.mark.asyncio
async def test_schedule_send_rejects_retired_ticket(tmp_path) -> None:
    """run 退出后的旧 ticket 不得排入发送，也不得触达 session。"""
    sent: list[object] = []

    class Session:
        async def send_resource_updated(self, uri: object) -> None:
            sent.append(uri)

    manager, owner, subscribe, _ = _owned_tools(tmp_path)
    with _request_session(Session(), manager, owner):
        await subscribe.execute({"selector": ".function"})
    ticket = _watch_ticket(manager, str(tmp_path), ".function")
    manager.retire_run(owner)
    manager.schedule_send(ticket, "tsa://hyphae/.function")
    assert sent == []
    assert manager._pending == {}


@pytest.mark.asyncio
async def test_schedule_send_calls_ticket_session(tmp_path) -> None:
    """有效 ticket 经 captured loop 调用其真实 session 发送方法。"""
    sent: list[object] = []
    completed = asyncio.Event()

    class FakeSession:
        async def send_resource_updated(self, uri: object) -> None:
            sent.append(uri)
            completed.set()

    manager, owner, subscribe, _ = _owned_tools(tmp_path)
    with _request_session(FakeSession(), manager, owner):
        await subscribe.execute({"selector": ".function"})
    ticket = _watch_ticket(manager, str(tmp_path), ".function")
    manager.schedule_send(ticket, "tsa://hyphae/.function")
    await asyncio.wait_for(completed.wait(), timeout=1)

    assert len(sent) == 1
    # Wrapped as AnyUrl — str round-trips back to the scheme.
    assert str(sent[0]).startswith("tsa://hyphae/")


@pytest.mark.asyncio
async def test_same_connection_across_request_tasks_reuses_sub_id(tmp_path) -> None:
    """2026-09-14：请求 task 变化不能改变连接级 sub_id。"""
    session = object()
    manager, owner, tool, _ = _owned_tools(tmp_path)

    async def subscribe(selector: str) -> tuple[dict[str, Any], asyncio.Task[Any]]:
        task = asyncio.current_task()
        assert task is not None
        with _request_session(session, manager, owner):
            result = await tool.execute({"selector": selector})
        return result, task

    first = asyncio.create_task(subscribe(".function"))
    first_result, first_task = await first
    second = asyncio.create_task(subscribe(".class"))
    second_result, second_task = await second

    assert first_task is not second_task
    assert first_result["sub_id"] == second_result["sub_id"]
    assert hst.get_session_obj(first_result["sub_id"]) is session
    assert hst.get_session_loop(first_result["sub_id"]) is asyncio.get_running_loop()


@pytest.mark.asyncio
async def test_different_connections_are_isolated(tmp_path) -> None:
    """2026-09-14：不同 ServerSession 必须得到不同所有权句柄。"""
    manager = SubscriptionLifecycleManager(str(tmp_path))
    results = []
    for session, selector in ((object(), ".function"), (object(), ".class")):
        owner = manager.begin_run()
        tool = hst.HyphaeSubscribeTool(str(tmp_path), manager)
        with _request_session(session, manager, owner):
            results.append(await tool.execute({"selector": selector}))
    assert results[0]["sub_id"] != results[1]["sub_id"]


@pytest.mark.asyncio
async def test_subscribe_without_request_context_fails_before_mutation(
    tmp_path,
) -> None:
    """2026-09-14：缺少连接上下文时不得产生任何状态。"""
    with pytest.raises(ValueError, match="MCP request context"):
        await hst.HyphaeSubscribeTool(str(tmp_path)).execute({"selector": ".function"})
    assert get_subscription_registry().subscription_count() == 0
    assert hst._SESSION_LOOPS == {}
    assert hst._SESSION_MIN_INTERVALS == {}
    assert hst._SESSION_SESSIONS == {}


@pytest.mark.asyncio
async def test_subscribe_publishes_only_after_transport_state(
    monkeypatch, tmp_path
) -> None:
    """2026-09-14：registry 发布订阅时，bridge 所需映射必须已就绪。"""
    session = object()
    manager, owner, tool, _ = _owned_tools(tmp_path)

    class ObservingRegistry:
        def subscribe(self, session_id: str, selector: str) -> None:
            assert hst.get_session_obj(session_id) is session
            assert hst.get_session_loop(session_id) is asyncio.get_running_loop()
            assert hst.get_session_min_interval(session_id) == 0.25

    manager._registry = ObservingRegistry()
    with _request_session(session, manager, owner):
        await tool.execute({"selector": ".function", "min_interval": 0.25})


@pytest.mark.asyncio
async def test_selector_unsubscribe_retains_transport_until_last_selector(
    tmp_path,
) -> None:
    """2026-09-14：退订一项后其余 selector 仍可发送，最后一项才清理。"""
    sent: list[str] = []
    completed = asyncio.Event()

    class Session:
        async def send_resource_updated(self, uri: object) -> None:
            sent.append(str(uri))
            completed.set()

    session = Session()
    manager, owner, subscribe, unsubscribe = _owned_tools(tmp_path)
    with _request_session(session, manager, owner):
        first = await subscribe.execute({"selector": ".function", "min_interval": 0.25})
        await subscribe.execute({"selector": ".class", "min_interval": 0.25})
        await unsubscribe.execute({"selector": ".function"})
    assert get_subscription_registry().subscriptions_for(first["sub_id"]) == [".class"]
    assert hst.get_session_obj(first["sub_id"]) is session
    assert hst.get_session_loop(first["sub_id"]) is asyncio.get_running_loop()
    assert hst.get_session_min_interval(first["sub_id"]) == 0.25
    ticket = _watch_ticket(manager, str(tmp_path), ".class")
    manager.schedule_send(ticket, "tsa://hyphae/classes%28%29")
    await asyncio.wait_for(completed.wait(), timeout=1)
    assert len(sent) == 1

    with _request_session(session, manager, owner):
        await unsubscribe.execute({"selector": ".class"})
    assert first["sub_id"] not in get_subscription_registry().all_sessions()
    assert hst.get_session_obj(first["sub_id"]) is None
    assert hst.get_session_loop(first["sub_id"]) is None


@pytest.mark.asyncio
async def test_foreign_sub_id_is_rejected_without_state_change(tmp_path) -> None:
    """2026-09-14：连接不能借显式 sub_id 修改另一连接。"""
    manager = SubscriptionLifecycleManager(str(tmp_path))
    owner_run, foreign_run = manager.begin_run(), manager.begin_run()
    subscribe = hst.HyphaeSubscribeTool(str(tmp_path), manager)
    unsubscribe = hst.HyphaeUnsubscribeTool(str(tmp_path), manager)
    owner, foreigner = object(), object()
    with _request_session(owner, manager, owner_run):
        owned = await subscribe.execute({"selector": ".function"})
    with _request_session(foreigner, manager, foreign_run):
        foreign = await subscribe.execute({"selector": ".class"})
    before_subs = {
        owned["sub_id"]: get_subscription_registry().subscriptions_for(owned["sub_id"]),
        foreign["sub_id"]: get_subscription_registry().subscriptions_for(
            foreign["sub_id"]
        ),
    }
    before_maps = (
        dict(hst._SESSION_LOOPS),
        dict(hst._SESSION_MIN_INTERVALS),
        dict(hst._SESSION_SESSIONS),
    )
    with _request_session(foreigner, manager, foreign_run):
        with pytest.raises(ValueError, match="does not belong"):
            await unsubscribe.execute({"sub_id": owned["sub_id"]})
    assert {
        owned["sub_id"]: get_subscription_registry().subscriptions_for(owned["sub_id"]),
        foreign["sub_id"]: get_subscription_registry().subscriptions_for(
            foreign["sub_id"]
        ),
    } == before_subs
    assert (
        hst._SESSION_LOOPS,
        hst._SESSION_MIN_INTERVALS,
        hst._SESSION_SESSIONS,
    ) == before_maps


@pytest.mark.asyncio
async def test_unsubscribe_all_and_repeat_are_idempotent(tmp_path) -> None:
    """2026-09-14：整会话退订清理全部状态，重复调用仍幂等。"""
    session = object()
    manager, owner, subscribe, unsubscribe = _owned_tools(tmp_path)
    with _request_session(session, manager, owner):
        result = await subscribe.execute({"selector": ".function"})
        await subscribe.execute({"selector": ".class"})
        await unsubscribe.execute({"sub_id": result["sub_id"]})
        await unsubscribe.execute({"sub_id": result["sub_id"]})
    assert get_subscription_registry().subscriptions_for(result["sub_id"]) == []
    assert hst.get_session_obj(result["sub_id"]) is None
    assert hst.get_session_loop(result["sub_id"]) is None
    assert result["sub_id"] not in hst._SESSION_MIN_INTERVALS


@pytest.mark.asyncio
async def test_unsubscribe_without_context_preserves_existing_state(tmp_path) -> None:
    """2026-09-14：无调用者连接时退订必须在任何写入前失败。"""
    session = object()
    manager, owner, subscribe, unsubscribe = _owned_tools(tmp_path)
    with _request_session(session, manager, owner):
        result = await subscribe.execute({"selector": ".function"})
    before_maps = (
        dict(hst._SESSION_LOOPS),
        dict(hst._SESSION_MIN_INTERVALS),
        dict(hst._SESSION_SESSIONS),
    )
    with pytest.raises(ValueError, match="MCP request context"):
        await unsubscribe.execute({"sub_id": result["sub_id"]})
    assert get_subscription_registry().subscriptions_for(result["sub_id"]) == [
        ".function"
    ]
    assert (
        hst._SESSION_LOOPS,
        hst._SESSION_MIN_INTERVALS,
        hst._SESSION_SESSIONS,
    ) == before_maps


@pytest.mark.asyncio
async def test_foreign_or_retired_owner_fails_before_mutation(tmp_path) -> None:
    """不同应用或已退出 run 的 owner 都不能注册订阅。"""
    manager, owner, subscribe, _ = _owned_tools(tmp_path)
    other_manager = SubscriptionLifecycleManager(str(tmp_path))
    foreign_owner = other_manager.begin_run()
    session = object()

    for invalid_owner in (foreign_owner, owner):
        if invalid_owner is owner:
            manager.retire_run(owner)
        before_maps = (
            dict(hst._SESSION_LOOPS),
            dict(hst._SESSION_MIN_INTERVALS),
            dict(hst._SESSION_SESSIONS),
        )
        with _request_session(session, manager, invalid_owner):
            with pytest.raises(ValueError, match="owner"):
                await subscribe.execute({"selector": ".function"})
        assert get_subscription_registry().subscription_count() == 0
        assert (
            hst._SESSION_LOOPS,
            hst._SESSION_MIN_INTERVALS,
            hst._SESSION_SESSIONS,
        ) == before_maps


@pytest.mark.asyncio
async def test_same_app_reuses_session_only_with_fresh_run_owner(tmp_path) -> None:
    """同一应用再次运行时，相同连接对象也必须取得 fresh owner。"""
    manager, first_owner, subscribe, _ = _owned_tools(tmp_path)
    session = object()
    with _request_session(session, manager, first_owner):
        first = await subscribe.execute({"selector": ".function"})
    first_ticket = manager._records[(first["sub_id"], ".function")]
    manager.retire_run(first_owner)

    second_owner = manager.begin_run()
    with _request_session(session, manager, second_owner):
        second = await subscribe.execute({"selector": ".function"})
    second_ticket = manager._records[(second["sub_id"], ".function")]
    assert second["sub_id"] == first["sub_id"]
    assert second_ticket.run_owner is second_owner
    assert second_ticket.incarnation != first_ticket.incarnation


@pytest.mark.asyncio
async def test_selector_incarnation_survives_repeat_but_changes_after_delete(
    tmp_path,
) -> None:
    """重复订阅保留 identity，删除后重订必须生成新 identity。"""
    manager, owner, subscribe, unsubscribe = _owned_tools(tmp_path)
    session = object()
    with _request_session(session, manager, owner):
        first = await subscribe.execute({"selector": ".function"})
        first_ticket = manager._records[(first["sub_id"], ".function")]
        await subscribe.execute({"selector": ".function"})
        repeated_ticket = manager._records[(first["sub_id"], ".function")]
        await unsubscribe.execute({"selector": ".function"})
        await subscribe.execute({"selector": ".function"})
        replacement_ticket = manager._records[(first["sub_id"], ".function")]

    assert repeated_ticket.incarnation == first_ticket.incarnation
    assert replacement_ticket.incarnation != first_ticket.incarnation


@pytest.mark.asyncio
async def test_same_root_app_managers_retire_independently(tmp_path) -> None:
    """同一 raw root 的两个应用不得共享 run 所有权或清理范围。"""
    first_manager, first_owner, first_tool, _ = _owned_tools(tmp_path)
    second_manager, second_owner, second_tool, _ = _owned_tools(tmp_path)
    first_session, second_session = object(), object()
    with _request_session(first_session, first_manager, first_owner):
        first = await first_tool.execute({"selector": ".function"})
    with _request_session(second_session, second_manager, second_owner):
        second = await second_tool.execute({"selector": ".class"})

    first_manager.retire_run(first_owner)
    assert get_subscription_registry().subscriptions_for(first["sub_id"]) == []
    assert get_subscription_registry().subscriptions_for(second["sub_id"]) == [".class"]
    assert hst.get_session_obj(second["sub_id"]) is second_session


@pytest.mark.asyncio
async def test_real_sdk_connections_enforce_session_ownership(tmp_path) -> None:
    """2026-09-14：真实内存流固定连接身份、隔离和整会话退订。"""
    manager = SubscriptionLifecycleManager(str(tmp_path))
    server: Server[Any] = Server("hyphae-session-test", lifespan=manager.lifespan)
    subscribe = hst.HyphaeSubscribeTool(str(tmp_path), manager)
    unsubscribe = hst.HyphaeUnsubscribeTool(str(tmp_path), manager)
    request_tasks: list[asyncio.Task[Any]] = []

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="subscribe",
                description="测试订阅入口",
                inputSchema={"type": "object"},
            ),
            Tool(
                name="unsubscribe",
                description="测试退订入口",
                inputSchema={"type": "object"},
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        task = asyncio.current_task()
        assert task is not None
        request_tasks.append(task)
        tool = subscribe if name == "subscribe" else unsubscribe
        result = await tool.execute(arguments)
        return [TextContent(type="text", text=json.dumps(result))]

    async with create_connected_server_and_client_session(server) as first_client:
        first = await first_client.call_tool("subscribe", {"selector": ".function"})
        second = await first_client.call_tool("subscribe", {"selector": ".class"})
        first_result = json.loads(first.content[0].text)  # type: ignore[union-attr]
        second_result = json.loads(second.content[0].text)  # type: ignore[union-attr]

        async with create_connected_server_and_client_session(server) as second_client:
            foreign = await second_client.call_tool(
                "subscribe", {"selector": ".import"}
            )
            foreign_result = json.loads(  # type: ignore[union-attr]
                foreign.content[0].text
            )
            registry = get_subscription_registry()
            before = {
                first_result["sub_id"]: registry.subscriptions_for(
                    first_result["sub_id"]
                ),
                foreign_result["sub_id"]: registry.subscriptions_for(
                    foreign_result["sub_id"]
                ),
            }
            before_maps = (
                dict(hst._SESSION_LOOPS),
                dict(hst._SESSION_MIN_INTERVALS),
                dict(hst._SESSION_SESSIONS),
            )
            rejected = await second_client.call_tool(
                "unsubscribe", {"sub_id": first_result["sub_id"]}
            )
            assert rejected.isError is True
            assert {
                session_id: registry.subscriptions_for(session_id)
                for session_id in before
            } == before
            assert (
                hst._SESSION_LOOPS,
                hst._SESSION_MIN_INTERVALS,
                hst._SESSION_SESSIONS,
            ) == before_maps

            removed = await first_client.call_tool(
                "unsubscribe", {"sub_id": first_result["sub_id"]}
            )
            assert removed.isError is not True
            assert registry.subscriptions_for(first_result["sub_id"]) == []
            assert registry.subscriptions_for(foreign_result["sub_id"]) == [".import"]
            assert hst.get_session_obj(first_result["sub_id"]) is None
            assert hst.get_session_obj(foreign_result["sub_id"]) is not None

    assert request_tasks[0] is not request_tasks[1]
    assert first_result["sub_id"] == second_result["sub_id"]
    assert first_result["sub_id"] != foreign_result["sub_id"]
