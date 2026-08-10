"""Bounded route-lease tombstones for diff snapshots."""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .diff_snapshot_registry import FrozenDiffSnapshot


class ClosedLeaseTombstones:
    """Fixed-size, expiring LRU of already-closed lease token pairs."""

    def __init__(
        self,
        *,
        capacity: int,
        lifetime_seconds: float,
        clock: Callable[[], float],
    ) -> None:
        self._capacity = capacity
        self._lifetime_seconds = lifetime_seconds
        self._clock = clock
        self._items: OrderedDict[str, tuple[str, float]] = OrderedDict()

    def sweep(self, *, now: float | None = None) -> None:
        if now is None:
            now = self._clock()
        self._items = OrderedDict(
            (snapshot_id, value)
            for snapshot_id, value in self._items.items()
            if now - value[1] < self._lifetime_seconds
        )
        self._trim()

    def check(self, snapshot_id: str, lease_id: str) -> tuple[bool, str | None]:
        """Return whether a tombstone exists and any token mismatch error."""
        value = self._items.get(snapshot_id)
        if value is None:
            return False, None
        self._items.move_to_end(snapshot_id)
        error = None if value[0] == lease_id else "DIFF_SNAPSHOT_LEASE_MISMATCH"
        return True, error

    def remember(self, snapshot_id: str, lease_id: str) -> None:
        self._items[snapshot_id] = (lease_id, self._clock())
        self._items.move_to_end(snapshot_id)
        self._trim()

    def _trim(self) -> None:
        while len(self._items) > self._capacity:
            self._items.popitem(last=False)

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)

    def __setitem__(self, snapshot_id: str, value: tuple[str, float]) -> None:
        """Compatibility seam for tests that seed pre-sweep tombstones."""
        self._items[snapshot_id] = value

    def __contains__(self, snapshot_id: object) -> bool:
        return snapshot_id in self._items


class SnapshotConsumer:
    """Thread-owned snapshot pin; release is idempotent and synchronized."""

    def __init__(self, registry: Any, snapshot: FrozenDiffSnapshot, pin: str) -> None:
        self._registry = registry
        self.snapshot = snapshot
        self._pin = pin
        self._owner = threading.get_ident()
        self._released = False
        self._lock = threading.Lock()

    def release(self) -> None:
        with self._lock:
            if self._released:
                return
            if threading.get_ident() != self._owner:
                raise RuntimeError("DIFF_SNAPSHOT_WRONG_THREAD")
            self._registry._release(self.snapshot.snapshot_id, self._pin, self._owner)
            self._released = True

    def __enter__(self) -> FrozenDiffSnapshot:
        return self.snapshot

    def __exit__(self, *_: object) -> None:
        self.release()
