"""RFC-0001: SubscriptionRegistry — watch→push bridge for Hyphae selectors.

Tracks which MCP sessions have subscribed to which Hyphae selector expressions.
When a file changes the registry re-evaluates the selector, computes a delta
vs the previous snapshot, and calls ``send_resource_updated`` so the MCP client
can re-read the changed resource.

RFC-0001 criterion 1 (this module): SubscriptionRegistry + delta computation,
pure and unit-tested.
RFC-0001 criteria 2-5 (wired in server.py / search_facade.py): subscribe/
unsubscribe actions, tsa:// resource reads, watch bridge, throttle + GC.
"""

from __future__ import annotations

import threading
import time
import weakref
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _Subscription:
    """One active subscription: session → selector → last snapshot."""

    session_id: str
    selector: str
    last_snapshot: list[Any] = field(default_factory=list)
    last_sent_at: float = 0.0


class SubscriptionRegistry:
    """Thread-safe registry mapping sessions to Hyphae selector subscriptions.

    Responsibilities:
    - Register / unregister subscriptions.
    - Compute deltas (added/removed items) between successive evaluations.
    - Throttle re-evaluations per subscription (``min_interval_s``).
    - Garbage-collect dead sessions via weakref callback (when the caller
      provides a session-death notifier) or explicit ``remove_session``.

    This class is **pure** — it has no I/O. The caller (server.py or a
    background thread) drives evaluation and sends ``send_resource_updated``
    via the callback it injects at construction time.
    """

    def __init__(
        self,
        *,
        min_interval_s: float = 2.0,
        on_delta: Callable[[str, str, list[Any], list[Any]], None] | None = None,
    ) -> None:
        """
        Parameters
        ----------
        min_interval_s:
            Minimum seconds between re-evaluations for the same subscription.
        on_delta:
            Callback fired when a delta is detected:
            ``on_delta(session_id, selector, added, removed)``.
        """
        self._lock = threading.Lock()
        self._subs: dict[str, dict[str, _Subscription]] = {}
        self._min_interval_s = min_interval_s
        self._on_delta = on_delta

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def subscribe(self, session_id: str, selector: str) -> None:
        """Register *session_id* as watching *selector*.  Idempotent."""
        with self._lock:
            if session_id not in self._subs:
                self._subs[session_id] = {}
            if selector not in self._subs[session_id]:
                self._subs[session_id][selector] = _Subscription(
                    session_id=session_id,
                    selector=selector,
                )

    def unsubscribe(self, session_id: str, selector: str) -> None:
        """Remove *selector* from *session_id*.  No-op if absent."""
        with self._lock:
            self._subs.get(session_id, {}).pop(selector, None)

    def remove_session(self, session_id: str) -> None:
        """Remove all subscriptions for a dead/disconnected session."""
        with self._lock:
            self._subs.pop(session_id, None)

    def subscriptions_for(self, session_id: str) -> list[str]:
        """Return the list of active selectors for *session_id*."""
        with self._lock:
            return list(self._subs.get(session_id, {}).keys())

    def all_sessions(self) -> list[str]:
        """Return all sessions that have at least one active subscription."""
        with self._lock:
            return list(self._subs.keys())

    def subscription_count(self) -> int:
        """Total number of (session, selector) pairs currently tracked."""
        with self._lock:
            return sum(len(selectors) for selectors in self._subs.values())

    # ------------------------------------------------------------------
    # Delta computation
    # ------------------------------------------------------------------

    def compute_delta(
        self,
        session_id: str,
        selector: str,
        new_snapshot: list[Any],
    ) -> tuple[list[Any], list[Any]]:
        """Compare *new_snapshot* with the stored last snapshot.

        Returns ``(added, removed)`` — items that appeared in / disappeared
        from the snapshot since the last call.  If the subscription does not
        exist or the throttle window has not elapsed, returns ``([], [])``.

        Updates the stored snapshot to *new_snapshot* when a delta is found.
        """
        now = time.monotonic()
        with self._lock:
            sub = self._subs.get(session_id, {}).get(selector)
            if sub is None:
                return [], []
            if now - sub.last_sent_at < self._min_interval_s:
                return [], []

            old_set = {_hashable(item) for item in sub.last_snapshot}
            new_set = {_hashable(item) for item in new_snapshot}

            if old_set == new_set:
                return [], []

            added = [item for item in new_snapshot if _hashable(item) not in old_set]
            removed = [
                item for item in sub.last_snapshot if _hashable(item) not in new_set
            ]

            sub.last_snapshot = list(new_snapshot)
            sub.last_sent_at = now

        return added, removed

    def notify_change(
        self,
        session_id: str,
        selector: str,
        new_snapshot: list[Any],
    ) -> None:
        """Compute delta and, if non-empty, fire ``on_delta`` callback."""
        added, removed = self.compute_delta(session_id, selector, new_snapshot)
        if (added or removed) and self._on_delta is not None:
            self._on_delta(session_id, selector, added, removed)

    def notify_all(
        self,
        evaluate: Callable[[str, str], list[Any]],
    ) -> None:
        """Re-evaluate every active (session, selector) pair.

        *evaluate* is called with ``(session_id, selector)`` and must return
        the current snapshot for that selector.  Deltas are fired via the
        ``on_delta`` callback registered at construction.
        """
        with self._lock:
            pairs = [
                (sid, sel) for sid, selectors in self._subs.items() for sel in selectors
            ]
        for session_id, selector in pairs:
            try:
                snapshot = evaluate(session_id, selector)
                self.notify_change(session_id, selector, snapshot)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # GC helpers
    # ------------------------------------------------------------------

    def gc_empty_sessions(self) -> int:
        """Remove sessions with no remaining subscriptions.  Returns count removed."""
        with self._lock:
            dead = [sid for sid, sels in self._subs.items() if not sels]
            for sid in dead:
                del self._subs[sid]
            return len(dead)

    def register_weakref_cleanup(self, session_obj: Any, session_id: str) -> None:
        """Remove *session_id* automatically when *session_obj* is garbage-collected."""
        weakref.finalize(session_obj, self.remove_session, session_id)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _hashable(item: Any) -> Any:
    """Convert a snapshot item to a hashable representation for set operations."""
    if isinstance(item, dict):
        try:
            return tuple(sorted((k, _hashable(v)) for k, v in item.items()))
        except TypeError:
            return str(item)
    if isinstance(item, list):
        try:
            return tuple(_hashable(v) for v in item)
        except TypeError:
            return str(item)
    return item
