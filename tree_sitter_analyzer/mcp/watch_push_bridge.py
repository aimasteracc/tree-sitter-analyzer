"""RFC-0001 标准 4：watch→push 桥接器。

本模块把后台线程 ``FileWatcherDaemon`` 接入应用拥有的订阅生命周期管理器。
同步事件到达后，桥接器收集所有活跃的会话与选择器，基于更新后的索引重新求值，
计算新增与删除差异，并通过管理器可撤销的线程到事件循环交接来调度
``send_resource_updated(uri)``。

推送采用尽力而为语义：会话循环缺失或关闭时移除会话，发送失败只记录诊断，
均不阻塞监听循环。求值失败保留最后有效快照，不能伪装成真实删除。
"""

from __future__ import annotations

import logging
from typing import Any

from .resources.hyphae_resource import uri_from_selector

logger = logging.getLogger(__name__)


def make_on_sync_callback(
    project_root: str | None,
    lifecycle_manager: Any | None = None,
    watch_token: Any | None = None,
) -> Any:
    """Return an ``on_sync`` callable suitable for ``FileWatcherDaemon``.

    The returned function accepts ``sync_result`` (the dict from IncrementalSync)
    and drives the push pipeline for all active subscriptions.
    """

    def _on_sync(sync_result: dict[str, Any]) -> None:
        if lifecycle_manager is None or watch_token is None:
            return
        _drive_subscriptions(project_root, sync_result, lifecycle_manager, watch_token)

    return _on_sync


def _drive_subscriptions(
    project_root: str | None,
    sync_result: dict[str, Any],
    lifecycle_manager: Any,
    watch_token: Any,
) -> None:
    """Re-evaluate each subscription and push deltas.  Called on the watcher thread."""
    if not project_root:
        return

    def _evaluate(session_id: str, selector: str) -> list[Any]:
        from ..ast_cache import ASTCache
        from ..hyphae import Evaluator, parse

        selector_ast = parse(selector)
        cache = ASTCache(project_root)
        evaluator = Evaluator(cache)
        items = evaluator.eval(selector_ast)
        return [
            {
                "name": getattr(item, "name", str(item)),
                "file": getattr(item, "file", ""),
                "line": getattr(item, "line", 0),
            }
            for item in items
        ]

    for ticket in lifecycle_manager.snapshot_for_watch(watch_token):
        try:
            snapshot = _evaluate(ticket.session_id, ticket.selector)
        except Exception:
            logger.debug(
                "subscription evaluation failed for session %s selector %s",
                ticket.session_id,
                ticket.selector,
                exc_info=True,
            )
            continue
        if lifecycle_manager.commit_evaluation(ticket, snapshot):
            lifecycle_manager.schedule_send(ticket, uri_from_selector(ticket.selector))


def collect_changed_pairs(
    registry: Any,
    evaluate: Any,
) -> list[tuple[str, str]]:
    """Return the ``(session_id, selector)`` pairs whose result changed.

    ``compute_delta`` atomically applies the ``min_interval`` throttle, diffs
    the snapshot against the stored one, and updates the stored snapshot — so
    an unrelated file save (or a throttled event) yields an empty delta and the
    pair is omitted. This honours the RFC-0001 contract: notify only when the
    selector result actually moves, never on every sync event.
    """
    changed: list[tuple[str, str]] = []
    for session_id in registry.all_sessions():
        for selector in registry.subscriptions_for(session_id):
            try:
                snapshot = evaluate(session_id, selector)
            except Exception:
                logger.debug(
                    "subscription evaluation failed for session %s selector %s",
                    session_id,
                    selector,
                    exc_info=True,
                )
                continue
            added, removed = registry.compute_delta(session_id, selector, snapshot)
            if added or removed:
                changed.append((session_id, selector))
    return changed
