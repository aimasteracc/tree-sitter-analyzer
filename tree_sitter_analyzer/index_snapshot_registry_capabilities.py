"""Reusable selection and deadline-aware locking for index capabilities."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def newest_reusable(
    entries: dict[str, Any], canonical_root: str, now: float
) -> Any | None:
    """Select the newest unexpired capability for one canonical project root."""
    candidates = [
        entry
        for entry in entries.values()
        if entry.snapshot.canonical_root == canonical_root and entry.expires_at > now
    ]
    return max(candidates, key=lambda item: item.expires_at, default=None)


def acquire_io_lock(
    lock: Any, deadline: float | None, clock: Callable[[], float]
) -> bool:
    """Acquire one snapshot I/O lock without crossing an optional deadline."""
    if deadline is None:
        lock.acquire()
        return True
    acquired = lock.acquire(timeout=max(0.0, deadline - clock()))
    if not acquired:
        raise RuntimeError("INDEX_SNAPSHOT_DEADLINE")
    if clock() >= deadline:
        lock.release()
        raise RuntimeError("INDEX_SNAPSHOT_DEADLINE")
    return True
