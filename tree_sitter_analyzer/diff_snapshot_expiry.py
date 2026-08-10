"""Request-independent hard-deadline scheduling for frozen snapshots."""

from __future__ import annotations

import threading
from collections.abc import Callable


class SnapshotExpiryScheduler:
    """Own at most one daemon timer for each bounded registry state."""

    def __init__(
        self,
        factory: Callable[[float, Callable[[], None]], object] = threading.Timer,
    ) -> None:
        self._factory = factory
        self._timers: dict[str, object] = {}

    def schedule(
        self,
        sid: str,
        delay: float,
        callback: Callable[[], None],
    ) -> None:
        timer: object | None = None
        try:
            timer = self._factory(max(0.0, delay), callback)
            timer.daemon = True  # type: ignore[attr-defined]
            self._timers[sid] = timer
            timer.start()  # type: ignore[attr-defined]
        except Exception:
            self._timers.pop(sid, None)
            if timer is not None:
                try:
                    timer.cancel()  # type: ignore[attr-defined]
                except Exception:
                    pass
            raise

    def fired(self, sid: str) -> None:
        self._timers.pop(sid, None)

    def cancel(self, sid: str) -> None:
        timer = self._timers.pop(sid, None)
        if timer is not None:
            timer.cancel()  # type: ignore[attr-defined]

    def cancel_all(self) -> None:
        for sid in tuple(self._timers):
            self.cancel(sid)


def schedule_expiry(
    scheduler: SnapshotExpiryScheduler,
    sid: str,
    delay: float,
    callback: Callable[[], None],
    rollback: Callable[[], None],
) -> None:
    """Publish a timer atomically with its owning registry state."""
    try:
        scheduler.schedule(sid, delay, callback)
    except Exception:
        rollback()
        raise
