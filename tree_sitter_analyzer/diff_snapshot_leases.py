"""Thread-owned consumers for process-local frozen diff snapshots."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .diff_snapshot_registry import FrozenDiffSnapshot


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
