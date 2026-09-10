#!/usr/bin/env python3
"""In-process latency instrumentation (RFC-0025 Layer 5 — self-proprioception).

The project's headline promise is that it answers *instantly*. Before this
module that promise was unmeasured: no p50/p95 existed anywhere in the
package, and the only pinned latency baseline measured *process startup* on
one platform. CLAUDE.md §11 is explicit — a non-functional claim that is not
an executable invariant is a **belief**, and beliefs rot silently. This module
is the scoreboard that turns the claim into a number.

Design decisions (and why)
--------------------------

**Reservoir = fixed-capacity ring buffer of the most recent
:data:`DEFAULT_WINDOW` samples, per ``(tool, action, tier)`` key.**
A streaming quantile estimator (P², t-digest) was the alternative. The ring
buffer wins here because:

* Percentiles over the window are **exact sample values** (nearest-rank, no
  interpolation) — a scoreboard whose entire purpose is trustworthy numbers
  should not ship an error term that has to be explained away.
* Percentiles are **recency-weighted**, which is what a live health surface
  wants. An all-history p95 keeps the process's very first cold call forever
  and slowly becomes a fossil.
* ``O(1)`` per record, zero allocation after warm-up, hard memory bound of
  ``window`` ints per key. No dependency.

The exact **count** is kept in a separate counter, so counts are never
windowed even though percentiles are.

**On by default.** An opt-in metric is a metric nobody has. The cost is two
:func:`time.perf_counter_ns` calls plus a deque append under an uncontended
lock — nanoseconds against routes measured in milliseconds-to-seconds. Set
``TSA_LATENCY_INSTRUMENTATION=0`` to opt out.

**Tier is a definition, not a cache probe.** ``cold`` = the call *started*
before any call on that ``(tool, action)`` had *completed*; ``warm`` = it
started after one had; ``cached`` is only ever set by a caller that explicitly
knows it served from a cache. The report echoes :data:`TIER_DEFINITION` so
nobody mistakes the derived label for a measured cache hit.

The tier is reserved at **entry** to :meth:`LatencyRecorder.measure`, not at
exit. Classifying at exit classifies by *completion order*, and the MCP
lowlevel server dispatches concurrently (``tg.start_soon``), so two
simultaneous first-time calls on one route — both genuinely paying the cold
cost — would be labelled one cold and one warm. That put a multi-second cold
sample straight into the warm p95, contradicting this module's own contract
that "a cold answer never pollutes a warm p95". Concurrent first calls are all
cold, because none of them could benefit from state the others had not
produced yet.

**Thread-safety guarantee.** :meth:`LatencyRecorder.record`,
:meth:`LatencyRecorder.snapshot` and :meth:`LatencyRecorder.reset` are safe
under concurrent calls from multiple threads and multiple event loops (a
single :class:`threading.Lock` serialises all mutation, and ``snapshot``
copies under that lock). What is *not* claimed: a timing is the wall-clock
span of the measured block, so two overlapping ``await``\\ s each report their
own elapsed wall time **including time spent suspended**. Concurrency inflates
per-call latency; that is real, observable behaviour, not a recorder bug.

**Scope.** In-process only. There is deliberately no persistence layer: a
fresh CLI process therefore has an empty recorder and honestly reports
:data:`NO_OBSERVATIONS`. The long-lived MCP server is where observations
accumulate; ``scripts/measure_self_health_baseline.py`` drives routes
in-process to produce a durable baseline.
"""

from __future__ import annotations

import math
import os
import threading
import time
from collections import deque
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass

__all__ = [
    "DEFAULT_WINDOW",
    "ENV_ENABLED",
    "NO_OBSERVATIONS",
    "PERCENTILE_METHOD",
    "STATUS_OK",
    "TIER_CACHED",
    "TIER_COLD",
    "TIER_DEFINITION",
    "TIER_WARM",
    "LatencyRecorder",
    "LatencySnapshot",
    "RouteLatency",
    "get_latency_recorder",
    "percentile_ns",
]

#: Samples retained per ``(tool, action, tier)`` key. 256 keeps the memory
#: bound trivial (a few KB across the whole facade surface) while giving a
#: p95 that is backed by ~13 samples in the tail rather than 1.
DEFAULT_WINDOW = 256

#: Opt-out environment variable. Instrumentation is ON by default; set this
#: to one of ``0`` / ``false`` / ``no`` / ``off`` to disable it.
ENV_ENABLED = "TSA_LATENCY_INSTRUMENTATION"

#: An empty value counts as falsey too: ``TSA_LATENCY_INSTRUMENTATION=`` reads
#: as "explicitly set to nothing", which no operator means as "on".
_FALSEY = frozenset({"", "0", "false", "no", "off"})

TIER_COLD = "cold"
TIER_WARM = "warm"
TIER_CACHED = "cached"

#: Stable sentinel for "we have not measured this". Never report ``0.0`` for
#: an unmeasured percentile — a zero that means "unmeasured" is exactly the
#: belief-shaped output this module exists to eliminate.
NO_OBSERVATIONS = "NO_OBSERVATIONS"
STATUS_OK = "OK"

#: Placeholder for routes that have no action (e.g. ``set_project_path``).
_NO_ACTION = "-"

PERCENTILE_METHOD = "nearest-rank (exact sample value, no interpolation)"

TIER_DEFINITION = (
    "cold = the call STARTED before any call on this (tool, action) had "
    "COMPLETED in this process, so it cannot have benefited from warm state — "
    "concurrent first calls are therefore all cold, not one cold and one warm; "
    "warm = the call started after at least one call on this route completed; "
    "cached = reported explicitly by a caching layer. "
    "cold/warm is a process-lifetime definition, NOT a measured cache probe."
)


def percentile_ns(samples: Sequence[int], pct: float) -> int | None:
    """Return the nearest-rank ``pct`` percentile of *samples*, in ns.

    Nearest-rank means the result is always an **actual observed sample**:
    ``index = ceil(pct / 100 * n) - 1`` on the sorted samples, clamped into
    range. No interpolation, so an expected value can be hand-checked, and
    ``percentile_ns(s, 50) <= percentile_ns(s, 95)`` holds by construction
    because the index is monotonic in ``pct``.

    Returns ``None`` for an empty sample — never ``0``.

    Examples:
        >>> percentile_ns([10, 20, 30, 40, 50, 60, 70, 80, 90, 100], 50)
        50
        >>> percentile_ns([10, 20, 30, 40, 50, 60, 70, 80, 90, 100], 95)
        100
        >>> percentile_ns([], 50) is None
        True
    """
    count = len(samples)
    if count == 0:
        return None
    ordered = sorted(samples)
    rank = math.ceil(pct / 100.0 * count)
    index = min(max(rank - 1, 0), count - 1)
    return ordered[index]


def _ns_to_ms(value: int | None) -> float | None:
    """Convert nanoseconds to milliseconds, preserving ``None``."""
    if value is None:
        return None
    return round(value / 1_000_000, 3)


def _route_key(tool: str, action: str | None) -> tuple[str, str]:
    """Normalise ``(tool, action)`` into the stable reservoir route key."""
    return (str(tool), action if action else _NO_ACTION)


@dataclass(frozen=True)
class RouteLatency:
    """Immutable per-``(tool, action, tier)`` latency summary."""

    tool: str
    action: str
    tier: str
    count: int
    samples_in_window: int
    p50_ns: int | None
    p95_ns: int | None

    @property
    def p50_ms(self) -> float | None:
        return _ns_to_ms(self.p50_ns)

    @property
    def p95_ms(self) -> float | None:
        return _ns_to_ms(self.p95_ns)

    def as_report_row(self) -> dict[str, object]:
        """Render as a JSON-safe report row.

        ``p50_ms`` / ``p95_ms`` are ``None`` (JSON ``null``) rather than
        ``0.0`` when there is nothing to report.
        """
        return {
            "tool": self.tool,
            "action": self.action,
            "tier": self.tier,
            "count": self.count,
            "samples_in_window": self.samples_in_window,
            "p50_ms": self.p50_ms,
            "p95_ms": self.p95_ms,
        }


@dataclass(frozen=True)
class LatencySnapshot:
    """Immutable point-in-time view of every recorded route."""

    routes: tuple[RouteLatency, ...]
    total_invocations: int
    window: int
    enabled: bool

    @property
    def status(self) -> str:
        """:data:`STATUS_OK` when anything was observed, else
        :data:`NO_OBSERVATIONS`."""
        return STATUS_OK if self.routes else NO_OBSERVATIONS


class _Reservoir:
    """Bounded ring buffer plus an unwindowed exact count."""

    __slots__ = ("count", "samples")

    def __init__(self, window: int) -> None:
        self.samples: deque[int] = deque(maxlen=window)
        self.count = 0

    def add(self, elapsed_ns: int) -> None:
        self.samples.append(elapsed_ns)
        self.count += 1


class LatencyRecorder:
    """Bounded, thread-safe, per-``(tool, action, tier)`` latency reservoirs.

    See the module docstring for the reservoir choice, the on-by-default
    decision, the tier definition, and the exact thread-safety guarantee.
    """

    def __init__(self, window: int = DEFAULT_WINDOW, enabled: bool | None = None):
        if window < 1:
            raise ValueError(f"window must be >= 1, got {window!r}")
        self._window = window
        self._enabled = _env_enabled() if enabled is None else bool(enabled)
        self._lock = threading.Lock()
        self._routes: dict[tuple[str, str, str], _Reservoir] = {}
        # Routes that have had at least one call *complete*. Keyed on
        # completion, not on start, so a call that begins while the first call
        # on its route is still in flight is correctly classified cold — it had
        # no warm state to benefit from. See :data:`TIER_DEFINITION`.
        self._completed: set[tuple[str, str]] = set()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def window(self) -> int:
        return self._window

    def record(
        self,
        tool: str,
        action: str | None,
        elapsed_ns: int,
        *,
        tier: str | None = None,
    ) -> None:
        """Record one observation. A no-op when instrumentation is disabled.

        *tier* defaults to :data:`TIER_COLD` until a call on this route has
        completed, then :data:`TIER_WARM`. Pass it explicitly (e.g.
        :data:`TIER_CACHED`, or the tier :meth:`measure` reserved at entry)
        when the caller knows better than the derivation.
        """
        if not self._enabled:
            return
        route = _route_key(tool, action)
        with self._lock:
            if tier is None:
                tier = self._classify_locked(route)
            self._completed.add(route)
            key = (route[0], route[1], str(tier))
            reservoir = self._routes.get(key)
            if reservoir is None:
                reservoir = _Reservoir(self._window)
                self._routes[key] = reservoir
            reservoir.add(int(elapsed_ns))

    def _classify_locked(self, route: tuple[str, str]) -> str:
        """Derive the tier for *route*. Caller must hold ``self._lock``."""
        return TIER_WARM if route in self._completed else TIER_COLD

    @contextmanager
    def measure(
        self, tool: str, action: str | None, *, tier: str | None = None
    ) -> Iterator[None]:
        """Time the wrapped block and record it.

        The tier is decided **at entry**, not at exit. Deciding it at exit
        classifies by completion order, so under the MCP server's concurrent
        dispatch (``tg.start_soon``) two simultaneous first-time calls on one
        route — both genuinely paying the cold cost — would be labelled one
        cold and one warm, putting a multi-second cold sample into the warm
        p95. Entry-time classification makes both cold, which is the honest
        answer: neither could benefit from state the other had not produced yet.

        When instrumentation is disabled this is a true no-op — no
        ``perf_counter_ns`` calls at all, not merely a discarded record.

        Records even when the body raises — a route that fails slowly is
        exactly the route you need represented in the p95.
        """
        if not self._enabled:
            yield
            return
        if tier is None:
            with self._lock:
                tier = self._classify_locked(_route_key(tool, action))
        started = time.perf_counter_ns()
        try:
            yield
        finally:
            self.record(tool, action, time.perf_counter_ns() - started, tier=tier)

    def snapshot(self) -> LatencySnapshot:
        """Return an immutable summary, sorted by ``(tool, action, tier)``."""
        with self._lock:
            items = [
                (key, reservoir.count, list(reservoir.samples))
                for key, reservoir in self._routes.items()
            ]
        routes = tuple(
            RouteLatency(
                tool=tool,
                action=action,
                tier=tier,
                count=count,
                samples_in_window=len(samples),
                p50_ns=percentile_ns(samples, 50),
                p95_ns=percentile_ns(samples, 95),
            )
            for (tool, action, tier), count, samples in sorted(items)
        )
        return LatencySnapshot(
            routes=routes,
            total_invocations=sum(route.count for route in routes),
            window=self._window,
            enabled=self._enabled,
        )

    def reset(self) -> None:
        """Drop every reservoir and forget which routes have completed."""
        with self._lock:
            self._routes.clear()
            self._completed.clear()


def _env_enabled() -> bool:
    """Instrumentation is ON unless the opt-out env var says otherwise."""
    raw = os.environ.get(ENV_ENABLED)
    if raw is None:
        return True
    return raw.strip().lower() not in _FALSEY


#: Process-global recorder. Reset between tests by ``tests/conftest.py``.
_recorder: LatencyRecorder | None = None
_recorder_lock = threading.Lock()


def get_latency_recorder() -> LatencyRecorder:
    """Return the process-global :class:`LatencyRecorder`, creating it once."""
    global _recorder
    recorder = _recorder
    if recorder is not None:
        return recorder
    with _recorder_lock:
        if _recorder is None:
            _recorder = LatencyRecorder()
        return _recorder
