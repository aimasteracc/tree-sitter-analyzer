"""Hyphae 订阅的应用、运行和回调所有权。"""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from ..registry.singleton_registry import get_subscription_registry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunOwner:
    manager: SubscriptionLifecycleManager
    token: str


@dataclass(frozen=True)
class WatchToken:
    app_token: str
    project_epoch: int
    project_root: str | None
    token: str


@dataclass(frozen=True)
class SubscriptionTicket:
    app_token: str
    project_epoch: int
    project_root: str | None
    run_owner: RunOwner
    session_id: str
    selector: str
    incarnation: str
    session: Any
    loop: asyncio.AbstractEventLoop
    watch_token: WatchToken | None = None


@dataclass
class _Pending:
    ticket: SubscriptionTicket
    handle: asyncio.Handle | None = None
    task: asyncio.Task[None] | None = None


class SubscriptionLifecycleManager:
    """每个 TSA 应用一个的内部 reactive 生命周期管理器。"""

    def __init__(self, project_root: str | None, registry: Any | None = None) -> None:
        self._lock = threading.Lock()
        self._registry = registry or get_subscription_registry()
        self._app_token = uuid.uuid4().hex
        self._project_root = project_root
        self._project_epoch = 0
        self._runs: set[RunOwner] = set()
        self._run_sessions: dict[RunOwner, Any] = {}
        self._records: dict[tuple[str, str], SubscriptionTicket] = {}
        self._watch_tokens: set[WatchToken] = set()
        self._pending: dict[str, _Pending] = {}

    @asynccontextmanager
    async def lifespan(self, _server: Any) -> AsyncIterator[RunOwner]:
        owner = self.begin_run()
        try:
            yield owner
        finally:
            self.retire_run(owner)

    def begin_run(self) -> RunOwner:
        """建立一个可由 SDK lifespan 持有的 run owner。"""
        owner = RunOwner(self, uuid.uuid4().hex)
        with self._lock:
            self._runs.add(owner)
        return owner

    def require_owner(self, context: Any) -> RunOwner:
        if not isinstance(context, RunOwner) or context.manager is not self:
            raise ValueError("MCP application lifespan owner is required")
        with self._lock:
            if context not in self._runs:
                raise ValueError("MCP run owner is no longer active")
        return context

    def subscribe(
        self,
        owner: RunOwner,
        session: Any,
        loop: asyncio.AbstractEventLoop,
        selector: str,
        min_interval: float,
    ) -> SubscriptionTicket:
        sid = f"session-{id(session)}"
        key = (sid, selector)
        with self._lock:
            self._require_owner_locked(owner)
            self._bind_session_locked(owner, session)
            current = self._records.get(key)
            if current is not None and current.run_owner == owner:
                self._publish_transport_locked(current, min_interval)
                return current
            ticket = SubscriptionTicket(
                self._app_token,
                self._project_epoch,
                self._project_root,
                owner,
                sid,
                selector,
                uuid.uuid4().hex,
                session,
                loop,
            )
            self._records[key] = ticket
            self._publish_transport_locked(ticket, min_interval)
            self._registry.subscribe(sid, selector)
        return ticket

    def unsubscribe(
        self,
        owner: RunOwner,
        session: Any,
        *,
        sub_id: str | None,
        selector: str | None,
    ) -> str:
        owned_sid = f"session-{id(session)}"
        sid = owned_sid
        with self._lock:
            self._require_owner_locked(owner)
            if sub_id is not None and sub_id != owned_sid:
                raise ValueError("sub_id does not belong to the current MCP connection")
            self._bind_session_locked(owner, session)
            keys = [
                key
                for key, ticket in self._records.items()
                if ticket.run_owner == owner
                and (selector is None or key[1] == selector)
            ]
            tickets = [self._records.pop(key) for key in keys]
            registry = self._registry
            for ticket in tickets:
                registry.unsubscribe(ticket.session_id, ticket.selector)
            if not registry.subscriptions_for(sid):
                registry.remove_session(sid)
                self._clear_transport_locked(sid)
        self._cancel_for(tickets)
        return sid

    def retire_run(self, owner: RunOwner) -> None:
        with self._lock:
            self._runs.discard(owner)
            self._run_sessions.pop(owner, None)
            keys = [
                key
                for key, ticket in self._records.items()
                if ticket.run_owner == owner
            ]
            tickets = [self._records.pop(key) for key in keys]
            registry = self._registry
            for ticket in tickets:
                registry.unsubscribe(ticket.session_id, ticket.selector)
                if not registry.subscriptions_for(ticket.session_id):
                    registry.remove_session(ticket.session_id)
                    self._clear_transport_locked(ticket.session_id)
        self._cancel_for(tickets)

    def rebind_project(self, project_root: str | None) -> None:
        with self._lock:
            self._project_epoch += 1
            self._project_root = project_root
            tickets = list(self._records.values())
            self._records.clear()
            self._watch_tokens.clear()
            registry = self._registry
            for ticket in tickets:
                registry.unsubscribe(ticket.session_id, ticket.selector)
                if not registry.subscriptions_for(ticket.session_id):
                    registry.remove_session(ticket.session_id)
                    self._clear_transport_locked(ticket.session_id)
        self._cancel_for(tickets)

    def issue_watch_token(self, project_root: str | None) -> WatchToken:
        with self._lock:
            if project_root != self._project_root:
                raise ValueError(
                    "watch project root does not match application project"
                )
            token = WatchToken(
                self._app_token,
                self._project_epoch,
                project_root,
                uuid.uuid4().hex,
            )
            self._watch_tokens.add(token)
            return token

    def revoke_watch_token(self, token: WatchToken | None) -> None:
        if token is None:
            return
        with self._lock:
            self._watch_tokens.discard(token)
            pending = self._pop_pending_locked(
                lambda item: item.ticket.watch_token == token
            )
        self._cancel_pending(pending)

    def is_watch_token_current(self, token: WatchToken) -> bool:
        """核验 watch token 仍属于本应用当前 raw root 与 epoch。"""
        with self._lock:
            return (
                token in self._watch_tokens
                and token.app_token == self._app_token
                and token.project_epoch == self._project_epoch
                and token.project_root == self._project_root
            )

    def snapshot_for_watch(self, token: WatchToken) -> list[SubscriptionTicket]:
        with self._lock:
            if token not in self._watch_tokens:
                return []
            return [
                SubscriptionTicket(**{**ticket.__dict__, "watch_token": token})
                for ticket in self._records.values()
                if ticket.project_epoch == token.project_epoch
            ]

    def commit_evaluation(
        self, ticket: SubscriptionTicket, snapshot: list[Any]
    ) -> bool:
        key = (ticket.session_id, ticket.selector)
        with self._lock:
            current = self._records.get(key)
            if current is None or current.incarnation != ticket.incarnation:
                return False
            token = ticket.watch_token
            if token is None or token not in self._watch_tokens:
                return False
            registry = self._registry
            added, removed = registry.compute_delta(
                ticket.session_id, ticket.selector, snapshot
            )
        return bool(added or removed)

    def schedule_send(self, ticket: SubscriptionTicket, uri: str) -> None:
        pending_id = uuid.uuid4().hex
        pending = _Pending(ticket)
        with self._lock:
            if not self._valid_locked(ticket):
                return
            self._pending[pending_id] = pending
        try:
            handle = ticket.loop.call_soon_threadsafe(self._start_send, pending_id, uri)
        except Exception:
            with self._lock:
                self._pending.pop(pending_id, None)
            logger.debug(
                "push scheduling failed for %s", ticket.session_id, exc_info=True
            )
            return
        cancel = True
        with self._lock:
            current = self._pending.get(pending_id)
            if current is pending:
                pending.handle = handle
                cancel = not self._valid_locked(ticket)
        if cancel:
            handle.cancel()

    def _start_send(self, pending_id: str, uri: str) -> None:
        with self._lock:
            pending = self._pending.get(pending_id)
            if pending is None or not self._valid_locked(pending.ticket):
                self._pending.pop(pending_id, None)
                return
            ticket = pending.ticket
        coroutine = self._send(pending_id, pending, uri)
        try:
            task = ticket.loop.create_task(coroutine)
        except Exception:
            coroutine.close()
            with self._lock:
                if self._pending.get(pending_id) is pending:
                    self._pending.pop(pending_id, None)
            logger.debug("push task creation failed", exc_info=True)
            return
        cancel = False
        with self._lock:
            current = self._pending.get(pending_id)
            if current is pending:
                pending.task = task
                cancel = not self._valid_locked(ticket)
            else:
                cancel = True
        task.add_done_callback(
            lambda done: self._finish_send(pending_id, pending, done)
        )
        if cancel:
            task.cancel()

    async def _send(self, pending_id: str, pending: _Pending, uri: str) -> None:
        from pydantic import AnyUrl

        with self._lock:
            if self._pending.get(pending_id) is not pending or not self._valid_locked(
                pending.ticket
            ):
                return
            ticket = pending.ticket
        try:
            await ticket.session.send_resource_updated(AnyUrl(uri))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("send_resource_updated failed for %s", uri, exc_info=True)

    def _finish_send(
        self, pending_id: str, pending: _Pending, task: asyncio.Task[None]
    ) -> None:
        with self._lock:
            if self._pending.get(pending_id) is pending:
                self._pending.pop(pending_id, None)
        if task.cancelled():
            return
        try:
            task.result()
        except Exception:
            logger.debug("push task failed", exc_info=True)

    def _valid_locked(self, ticket: SubscriptionTicket) -> bool:
        current = self._records.get((ticket.session_id, ticket.selector))
        return (
            current is not None
            and current.incarnation == ticket.incarnation
            and ticket.run_owner in self._runs
            and ticket.project_epoch == self._project_epoch
            and ticket.project_root == self._project_root
            and ticket.watch_token in self._watch_tokens
        )

    def _require_owner_locked(self, owner: RunOwner) -> None:
        if (
            not isinstance(owner, RunOwner)
            or owner.manager is not self
            or owner not in self._runs
        ):
            raise ValueError("MCP run owner is no longer active")

    def _bind_session_locked(self, owner: RunOwner, session: Any) -> None:
        existing = self._run_sessions.get(owner)
        if existing is not None and existing is not session:
            raise ValueError("MCP run owner is already bound to another session")
        self._run_sessions[owner] = session

    def _publish_transport_locked(
        self, ticket: SubscriptionTicket, min_interval: float
    ) -> None:
        from .tools import hyphae_subscribe_tool as hst

        hst._SESSION_LOOPS[ticket.session_id] = ticket.loop
        hst._SESSION_MIN_INTERVALS[ticket.session_id] = min_interval
        hst._SESSION_SESSIONS[ticket.session_id] = ticket.session

    def _clear_transport_locked(self, session_id: str) -> None:
        from .tools import hyphae_subscribe_tool as hst

        hst._SESSION_LOOPS.pop(session_id, None)
        hst._SESSION_MIN_INTERVALS.pop(session_id, None)
        hst._SESSION_SESSIONS.pop(session_id, None)

    def _cancel_for(self, tickets: list[SubscriptionTicket]) -> None:
        incarnations = {ticket.incarnation for ticket in tickets}
        with self._lock:
            pending = self._pop_pending_locked(
                lambda item: item.ticket.incarnation in incarnations
            )
        self._cancel_pending(pending)

    def _pop_pending_locked(self, predicate: Any) -> list[_Pending]:
        selected: list[_Pending] = []
        for pending_id, item in list(self._pending.items()):
            if predicate(item):
                selected.append(self._pending.pop(pending_id))
        return selected

    def _cancel_pending(self, pending: list[_Pending]) -> None:
        for item in pending:
            if item.handle is not None:
                try:
                    item.ticket.loop.call_soon_threadsafe(item.handle.cancel)
                except RuntimeError:
                    try:
                        item.handle.cancel()
                    except Exception:
                        logger.debug("push handle cancellation failed", exc_info=True)
            if item.task is not None:
                try:
                    item.ticket.loop.call_soon_threadsafe(item.task.cancel)
                except RuntimeError:
                    try:
                        item.task.cancel()
                    except Exception:
                        logger.debug("push task cancellation failed", exc_info=True)
