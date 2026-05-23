"""Homeostasis loop classifier: detect grade regressions, alert on drops.

Reads the latest history row for each changed file, recomputes via the
injected scorer, classifies the transition and emits a :class:`Notifier`
event when the file's health regressed. The actual file-watching is
delegated to :class:`FileWatcherDaemon` — this module owns the
classifier + cooldown bookkeeping and the runner wrapper that wires
them together.

Grade ordering (LOWER LETTER == BETTER): A < B < C < D < F

Alerting rules (combined with logical OR; both gated by per-file cooldown):
    (a) strict worsening — ``new`` is worse than ``prev`` AND at least one of:
          - ``new`` is at or below threshold (we entered/are in danger),
          - ``prev`` was at or below threshold (we are still in danger),
          - the worsening is large (>= 2 grade steps).
        Pure single-step jitter wholly above threshold (e.g. A -> B with
        threshold = C) does NOT fire.
    (b) edge trigger — ``prev`` was strictly above threshold (or unknown)
        AND ``new`` is at or below threshold. Cold start (no prev) fires
        this rule when ``new`` is at or below threshold.

Level-only repeats (F -> F, C -> C) are silently suppressed.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from ._health_history import HealthHistory

logger = logging.getLogger(__name__)


# LOWER value == BETTER grade. F (worst) is highest.
GRADE_ORDER: dict[str, int] = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}
_VALID_GRADES = frozenset(GRADE_ORDER.keys())


# ------------------------------------------------------------------ helpers


def is_worse_grade(new_grade: str, prev_grade: str) -> bool:
    """True iff ``new_grade`` is strictly worse than ``prev_grade``."""
    return GRADE_ORDER.get(new_grade, -1) > GRADE_ORDER.get(prev_grade, -1)


def _at_or_below(grade: str, threshold: str) -> bool:
    """True iff ``grade`` is at or below the threshold (worse-or-equal)."""
    return GRADE_ORDER.get(grade, -1) >= GRADE_ORDER.get(threshold, -1)


def _strictly_above(grade: str, threshold: str) -> bool:
    """True iff ``grade`` is strictly better than the threshold."""
    return GRADE_ORDER.get(grade, -1) < GRADE_ORDER.get(threshold, -1)


# ------------------------------------------------------------------ types


class _ScorerLike(Protocol):
    """Duck-typed scorer; matches :class:`HealthScorer`."""

    def score_file(self, file_path: str) -> Any: ...


class _NotifierLike(Protocol):
    def dispatch(self, event: dict[str, Any]) -> None: ...


# ------------------------------------------------------------------ classifier loop


class HealthHomeostasisLoop:
    """Stateful classifier that decides which file changes deserve alerts.

    The loop holds:
      - injected ``scorer`` (any object with ``score_file``)
      - injected ``history`` (a :class:`HealthHistory`)
      - injected ``notifier``
      - per-file last-alert timestamp for cooldown enforcement
    """

    def __init__(
        self,
        *,
        threshold_grade: str = "C",
        cooldown: float = 0.0,
        history: HealthHistory,
        notifier: _NotifierLike,
        scorer: _ScorerLike | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if threshold_grade not in _VALID_GRADES:
            raise ValueError(
                f"threshold_grade must be one of {sorted(_VALID_GRADES)}, "
                f"got {threshold_grade!r}"
            )
        self._threshold_grade = threshold_grade
        self._cooldown = max(0.0, float(cooldown))
        self._history = history
        self._notifier = notifier
        self._scorer = scorer
        self._clock = clock

        self._last_alert: dict[str, float] = {}
        self._lock = threading.Lock()

    @property
    def threshold_grade(self) -> str:
        return self._threshold_grade

    # ---- public callback ----------------------------------------------

    def on_sync_callback(self, changed_files: set[str] | list[str]) -> None:
        """For each changed file: rescore, classify, alert + persist."""
        if not changed_files:
            return
        scorer = self._scorer
        if scorer is None:
            logger.debug("HealthHomeostasisLoop.on_sync_callback: no scorer")
            return

        for file_path in changed_files:
            try:
                self._process_one(file_path, scorer)
            except Exception as exc:  # pragma: no cover — defensive
                logger.debug("homeostasis: %s failed: %s", file_path, exc)

    # ---- internals ----------------------------------------------------

    def _process_one(self, file_path: str, scorer: _ScorerLike) -> None:
        score = scorer.score_file(file_path)
        new_grade = str(getattr(score, "grade", "F"))
        new_total = float(getattr(score, "total", 0.0))
        dimensions = getattr(score, "dimensions", {}) or {}

        prev = self._history.last(file_path)
        prev_grade = prev[0] if prev is not None else None
        prev_total = prev[1] if prev is not None else None

        should_alert = self._should_alert(prev_grade, new_grade)
        now = self._clock()

        if should_alert and not self._in_cooldown(file_path, now):
            event = self._build_event(
                file_path=file_path,
                new_grade=new_grade,
                new_total=new_total,
                prev_grade=prev_grade,
                prev_total=prev_total,
            )
            try:
                self._notifier.dispatch(event)
            except Exception as exc:
                logger.debug("homeostasis notifier dispatch failed: %s", exc)
            with self._lock:
                self._last_alert[file_path] = now

        # Always persist the latest reading — even on no-alert paths the
        # history is the next call's "previous_grade".
        try:
            self._history.append(
                file_path,
                score=new_total,
                grade=new_grade,
                dimensions=dimensions,
                trigger="watch",
            )
        except Exception as exc:
            logger.debug("homeostasis history append failed: %s", exc)

    def _should_alert(
        self,
        prev_grade: str | None,
        new_grade: str,
    ) -> bool:
        """Apply the two-rule classifier — see module docstring."""
        threshold = self._threshold_grade

        # Cold start: alert iff new grade is at or below threshold.
        if prev_grade is None:
            return _at_or_below(new_grade, threshold)

        # Rule (a) strict worsening, with above-threshold jitter suppression.
        # A single-step regression that stays strictly above threshold is
        # noise; a multi-step plunge (delta >= 2 grade letters) is real even
        # if both grades are still above threshold.
        worsened = is_worse_grade(new_grade, prev_grade)
        if worsened:
            in_danger = _at_or_below(new_grade, threshold) or _at_or_below(
                prev_grade, threshold
            )
            delta_grades = GRADE_ORDER.get(new_grade, 0) - GRADE_ORDER.get(
                prev_grade, 0
            )
            if in_danger or delta_grades >= 2:
                return True

        # Rule (b) edge trigger — crossing from above to at-or-below.
        if _strictly_above(prev_grade, threshold) and _at_or_below(
            new_grade, threshold
        ):
            return True

        return False

    def _in_cooldown(self, file_path: str, now: float) -> bool:
        if self._cooldown <= 0.0:
            return False
        with self._lock:
            last = self._last_alert.get(file_path)
        if last is None:
            return False
        return (now - last) < self._cooldown

    def _build_event(
        self,
        *,
        file_path: str,
        new_grade: str,
        new_total: float,
        prev_grade: str | None,
        prev_total: float | None,
    ) -> dict[str, Any]:
        delta = float(new_total) - float(prev_total) if prev_total is not None else 0.0
        ts = datetime.now(tz=timezone.utc).isoformat()
        return {
            "file": file_path,
            "grade": new_grade,
            "previous_grade": prev_grade,
            "total": new_total,
            "delta_score": delta,
            "recommendation": _build_recommendation(new_grade, prev_grade),
            "timestamp_iso": ts,
        }


def _build_recommendation(new_grade: str, prev_grade: str | None) -> str:
    """One-liner action hint, used in the template payload."""
    if prev_grade is None:
        return f"Health graded {new_grade} on first sync — review file."
    if is_worse_grade(new_grade, prev_grade):
        return (
            f"Health regressed {prev_grade} -> {new_grade}; investigate recent edits."
        )
    return f"Health at {new_grade}; review file."


# ------------------------------------------------------------------ runner


def run_watch_health(
    *,
    project_root: str | Path,
    threshold_grade: str = "C",
    interval: float = 5.0,
    debounce: float = 0.5,
    cooldown: float = 0.0,
    history_keep: int = 50,
    notify_channels: list[str] | None = None,
    notify_file: str | Path | None = None,
    on_degradation: str | None = None,
    webhook_url: str | None = None,
    backend: str = "poll",
    stop_event: threading.Event | None = None,
) -> int:
    """Blocking entrypoint: spin up the daemon and the homeostasis loop.

    Returns the exit code (``0`` on clean shutdown). The CLI wraps this
    in a thread or runs it directly depending on the surface.
    """
    # Imports kept local so module load does not pull in the file watcher.
    from .ast_cache import ASTCache
    from .file_watcher import FileWatcherDaemon
    from .health_notifier import build_notifier
    from .health_scorer import HealthScorer

    root = str(project_root)

    history = HealthHistory(root)
    notifier = build_notifier(
        notify_channels or ["stdout"],
        file_path=notify_file,
        webhook_url=webhook_url,
        shell_template=on_degradation,
    )
    scorer = HealthScorer()
    loop = HealthHomeostasisLoop(
        threshold_grade=threshold_grade,
        cooldown=cooldown,
        history=history,
        notifier=notifier,
        scorer=scorer,
    )

    cache = ASTCache(root)

    def _on_sync(result: dict[str, Any]) -> None:
        changed = _extract_changed_files(result, project_root=root)
        if not changed:
            return
        loop.on_sync_callback(changed)
        if history_keep > 0:
            for path in changed:
                try:
                    history.prune(path, history_keep)
                except Exception:
                    pass

    daemon = FileWatcherDaemon(
        cache,
        poll_interval=max(1.0, float(interval)),
        debounce=float(debounce),
        backend=backend,
        on_sync=_on_sync,
    )
    daemon.start()

    try:
        if stop_event is not None:
            stop_event.wait()
        else:
            # No external signal — block forever; caller is responsible
            # for SIGINT handling. We use a sentinel Event so the loop
            # below is interruptible.
            sentinel = threading.Event()
            sentinel.wait()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            daemon.stop(timeout=5.0)
        finally:
            history.close()
    return 0


def _extract_changed_files(
    sync_result: dict[str, Any],
    *,
    project_root: str | Path | None = None,
) -> set[str]:
    """Pull changed file paths out of an ``IncrementalSync.SyncResult.to_dict()``.

    The canonical shape (see :class:`tree_sitter_analyzer.incremental_sync.SyncResult`)
    is a dict whose ``"details"`` value is a list of per-file dicts of the form::

        {"file": "<rel_path>", "action": "indexed"|"updated"|"deleted", ...}

    We keep only files that still exist on disk (``"indexed"`` or ``"updated"``;
    ``"deleted"`` rows have nothing to rescore) and join each relative path with
    ``project_root`` so the homeostasis loop, the scorer, and the history all
    see the same absolute path string.

    Legacy/loose shapes (a top-level list under ``changed_files`` / ``files`` /
    ``files_changed``) are also tolerated for forward compatibility.
    """
    if not isinstance(sync_result, dict):
        return set()  # type: ignore[unreachable]

    root_str = str(project_root) if project_root is not None else None

    def _to_abs(rel_or_abs: str) -> str:
        if not rel_or_abs:
            return ""
        if os.path.isabs(rel_or_abs) or root_str is None:
            return rel_or_abs
        return os.path.join(root_str, rel_or_abs)

    out: set[str] = set()

    details = sync_result.get("details")
    if isinstance(details, list):
        for entry in details:
            if not isinstance(entry, dict):
                continue
            action = entry.get("action")
            if action == "deleted":
                # Deleted files can't be rescored; skip cleanly.
                continue
            rel = entry.get("file")
            if not isinstance(rel, str) or not rel:
                continue
            abs_path = _to_abs(rel)
            if abs_path:
                out.add(abs_path)

    # Legacy shapes — keep tolerant fallbacks for any older callers.
    for key in ("changed_files", "files_changed", "files"):
        raw = sync_result.get(key)
        if isinstance(raw, (list, tuple, set)):
            for item in raw:
                if not item:
                    continue
                abs_path = _to_abs(str(item))
                if abs_path:
                    out.add(abs_path)

    return out


# ------------------------------------------------------------------ class form
# Some tests probe either WatchHealthRunner OR run_watch_health. Provide a
# thin class wrapper for symmetry with the rest of the CLI.


class WatchHealthRunner:
    """Threaded wrapper around :func:`run_watch_health`.

    Exposes ``.start()`` / ``.stop()`` so the CLI integration test can
    treat the runner identically whether it is a class or a function.
    """

    def __init__(
        self,
        *,
        project_root: str | Path,
        threshold_grade: str = "C",
        interval: float = 5.0,
        debounce: float = 0.5,
        cooldown: float = 0.0,
        history_keep: int = 50,
        notify_channels: list[str] | None = None,
        notify_file: str | Path | None = None,
        on_degradation: str | None = None,
        webhook_url: str | None = None,
        backend: str = "poll",
    ) -> None:
        self._kwargs = {
            "project_root": project_root,
            "threshold_grade": threshold_grade,
            "interval": interval,
            "debounce": debounce,
            "cooldown": cooldown,
            "history_keep": history_keep,
            "notify_channels": notify_channels,
            "notify_file": notify_file,
            "on_degradation": on_degradation,
            "webhook_url": webhook_url,
            "backend": backend,
        }
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()

        def _go() -> None:
            run_watch_health(stop_event=self._stop_event, **self._kwargs)  # type: ignore[arg-type]

        self._thread = threading.Thread(
            target=_go,
            name="tsa-watch-health",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)
