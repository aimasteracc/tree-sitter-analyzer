"""RFC-0001 criterion 4: watch→push bridge.

Wires the ``FileWatcherDaemon`` (background thread) to the
``SubscriptionRegistry`` (process-wide singleton). When a sync event
fires the bridge:

1. Gathers all active (session_id, selector) pairs from the registry.
2. Re-evaluates each selector against the updated index.
3. Computes the delta (added / removed items).
4. Schedules ``send_resource_updated(uri)`` on the captured asyncio loop
   via ``asyncio.run_coroutine_threadsafe`` (thread → loop bridge).

Delivery is **best-effort**: a dead session, a closed loop, or an
evaluation error silently removes the subscription rather than blocking
the watch loop.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .resources.hyphae_resource import uri_from_selector
from .tools.hyphae_subscribe_tool import get_session_loop

logger = logging.getLogger(__name__)


def make_on_sync_callback(
    project_root: str | None,
) -> Any:
    """Return an ``on_sync`` callable suitable for ``FileWatcherDaemon``.

    The returned function accepts ``sync_result`` (the dict from IncrementalSync)
    and drives the push pipeline for all active subscriptions.
    """

    def _on_sync(sync_result: dict[str, Any]) -> None:
        _drive_subscriptions(project_root, sync_result)

    return _on_sync


def _drive_subscriptions(
    project_root: str | None,
    sync_result: dict[str, Any],
) -> None:
    """Re-evaluate each subscription and push deltas.  Called on the watcher thread."""
    from .._singleton_registry import get_subscription_registry

    registry = get_subscription_registry()

    def _evaluate(session_id: str, selector: str) -> list[Any]:
        if not project_root:
            return []
        try:
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
        except Exception:
            return []

    def _push(session_id: str, selector: str) -> None:
        loop = get_session_loop(session_id)
        if loop is None or loop.is_closed():
            registry.remove_session(session_id)
            return
        uri = uri_from_selector(selector)
        try:
            future = asyncio.run_coroutine_threadsafe(
                _send_update(session_id, uri),
                loop,
            )
            future.add_done_callback(
                lambda f: _handle_push_result(f, session_id, selector, registry)
            )
        except Exception:
            logger.debug(
                "push scheduling failed for session %s", session_id, exc_info=True
            )

    registry.notify_all(
        evaluate=lambda sid, sel: _evaluate(sid, sel),
    )

    # Fire the push for sessions that got a delta
    for session_id in registry.all_sessions():
        for selector in registry.subscriptions_for(session_id):
            _push(session_id, selector)


async def _send_update(session_id: str, uri: str) -> None:
    """Coroutine that sends resource-updated; runs on the captured loop."""
    try:
        from mcp.server import Server

        server = Server.current()
        if server is not None:
            await server.request_context.session.send_resource_updated(uri)
    except Exception:
        logger.debug("send_resource_updated failed for %s", uri, exc_info=True)


def _handle_push_result(
    future: Any,
    session_id: str,
    selector: str,
    registry: Any,
) -> None:
    """Callback on push future completion — GC dead sessions."""
    try:
        future.result()
    except Exception:
        logger.debug(
            "push future error for session %s selector %s",
            session_id,
            selector,
            exc_info=True,
        )
        registry.unsubscribe(session_id, selector)
