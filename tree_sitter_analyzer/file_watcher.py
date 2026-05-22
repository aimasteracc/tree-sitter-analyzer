#!/usr/bin/env python3
"""
File Watcher Daemon — Background file change detection for AST cache.

Monitors source files for changes and triggers incremental re-indexing
automatically. Part of the P1 Incremental Sync feature.

Two backends:
  - Polling: pure-stdlib, zero deps, works everywhere
  - Watchdog: efficient OS-native filesystem events (optional)

When a change is detected, the watcher triggers IncrementalSync.sync()
to update only the affected files in the SQLite AST cache.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .ast_cache import _EXT_TO_LANG
from .incremental_sync import IncrementalSync

logger = logging.getLogger(__name__)

_DEFAULT_DEBOUNCE_SEC = 2.0
_DEFAULT_POLL_INTERVAL_SEC = 5.0


@dataclass
class WatcherEvent:
    timestamp: float
    file_path: str
    event_type: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "file_path": self.file_path,
            "event_type": self.event_type,
        }


@dataclass
class WatcherStats:
    events_processed: int = 0
    syncs_triggered: int = 0
    last_sync_at: float = 0.0
    errors: int = 0
    uptime_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "events_processed": self.events_processed,
            "syncs_triggered": self.syncs_triggered,
            "last_sync_at": self.last_sync_at,
            "errors": self.errors,
            "uptime_seconds": round(self.uptime_seconds, 1),
        }


class FileWatcherDaemon:
    """
    Background file watcher that triggers incremental AST cache syncs.

    Usage::

        from tree_sitter_analyzer.ast_cache import ASTCache
        from tree_sitter_analyzer.file_watcher import FileWatcherDaemon

        cache = ASTCache("/path/to/project")
        watcher = FileWatcherDaemon(cache)
        watcher.start()   # spawns background thread
        # ... files change on disk ...
        stats = watcher.get_stats()
        watcher.stop()

    The daemon uses a polling approach by default. If ``watchdog`` is
    installed, pass ``backend="watchdog"`` for OS-native file events.
    """

    def __init__(
        self,
        cache: Any,
        *,
        poll_interval: float = _DEFAULT_POLL_INTERVAL_SEC,
        debounce: float = _DEFAULT_DEBOUNCE_SEC,
        backend: str = "poll",
        on_sync: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._cache = cache
        self._sync = IncrementalSync(cache)
        self._poll_interval = max(1.0, poll_interval)
        self._debounce = debounce
        self._backend = backend
        self._on_sync = on_sync

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._started_at: float = 0.0

        self._pending: set[str] = set()
        self._pending_lock = threading.Lock()
        self._debounce_timer: threading.Timer | None = None

        self._stats = WatcherStats()
        self._stats_lock = threading.Lock()

        self._snapshot: dict[str, float] = {}
        self._snapshot_lock = threading.Lock()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._started_at = time.monotonic()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="tsa-file-watcher",
            daemon=True,
        )
        self._thread.start()
        logger.info("file_watcher started (backend=%s)", self._backend)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._debounce_timer is not None:
            self._debounce_timer.cancel()
            self._debounce_timer = None
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        logger.info("file_watcher stopped")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def get_stats(self) -> dict[str, Any]:
        with self._stats_lock:
            stats = WatcherStats(
                events_processed=self._stats.events_processed,
                syncs_triggered=self._stats.syncs_triggered,
                last_sync_at=self._stats.last_sync_at,
                errors=self._stats.errors,
            )
        if self._started_at:
            stats.uptime_seconds = time.monotonic() - self._started_at
        return stats.to_dict()

    def trigger_sync(self) -> dict[str, Any]:
        return self._do_sync()

    def _run_loop(self) -> None:
        if self._backend == "watchdog":
            self._run_watchdog()
        else:
            self._run_polling()

    def _run_polling(self) -> None:
        self._take_snapshot()
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=self._poll_interval)
            if self._stop_event.is_set():
                break
            changed = self._detect_changes()
            for path in changed:
                self._enqueue(path)
        self._flush_pending()

    def _run_watchdog(self) -> None:
        try:
            from watchdog.observers import Observer
        except ImportError:
            logger.warning("watchdog not installed, falling back to polling")
            self._run_polling()
            return

        project_root = self._cache.project_root
        handler = _WatchdogHandler(self._enqueue)
        observer = Observer()
        observer.schedule(handler, project_root, recursive=True)
        observer.start()

        try:
            while not self._stop_event.is_set():
                self._stop_event.wait(timeout=1.0)
        finally:
            observer.stop()
            observer.join(timeout=5.0)
        self._flush_pending()

    def _take_snapshot(self) -> None:
        snapshot: dict[str, float] = {}
        project_root = self._cache.project_root
        for dirpath, dirnames, filenames in os.walk(project_root):
            dirnames[:] = [
                d for d in dirnames if d not in _EXT_TO_LANG and not d.startswith(".")
            ]
            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in _EXT_TO_LANG:
                    continue
                full = os.path.join(dirpath, fname)
                try:
                    mtime = os.path.getmtime(full)
                    snapshot[full] = mtime
                except OSError:
                    pass
        with self._snapshot_lock:
            self._snapshot = snapshot

    def _detect_changes(self) -> list[str]:
        current: dict[str, float] = {}
        project_root = self._cache.project_root
        for dirpath, dirnames, filenames in os.walk(project_root):
            dirnames[:] = [
                d for d in dirnames if d not in _EXT_TO_LANG and not d.startswith(".")
            ]
            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in _EXT_TO_LANG:
                    continue
                full = os.path.join(dirpath, fname)
                try:
                    mtime = os.path.getmtime(full)
                    current[full] = mtime
                except OSError:
                    pass

        changed: list[str] = []
        with self._snapshot_lock:
            for path, mtime in current.items():
                old_mtime = self._snapshot.get(path)
                if old_mtime is None or old_mtime != mtime:
                    changed.append(path)
            for path in self._snapshot:
                if path not in current:
                    changed.append(path)
            self._snapshot = current

        return changed

    def _enqueue(self, file_path: str) -> None:
        with self._pending_lock:
            self._pending.add(file_path)
        with self._stats_lock:
            self._stats.events_processed += 1

        if self._debounce_timer is not None:
            self._debounce_timer.cancel()
        self._debounce_timer = threading.Timer(self._debounce, self._flush_pending)
        self._debounce_timer.daemon = True
        self._debounce_timer.start()

    def _flush_pending(self) -> None:
        with self._pending_lock:
            pending = self._pending.copy()
            self._pending.clear()

        if not pending:
            return

        result = self._do_sync()
        if self._on_sync:
            try:
                self._on_sync(result)
            except Exception:
                logger.debug("on_sync callback error", exc_info=True)

    def _do_sync(self) -> dict[str, Any]:
        try:
            result = self._sync.sync()
            with self._stats_lock:
                self._stats.syncs_triggered += 1
                self._stats.last_sync_at = time.time()
            return result.to_dict()
        except Exception as exc:
            with self._stats_lock:
                self._stats.errors += 1
            logger.error("sync failed: %s", exc)
            return {"error": str(exc)}


class _WatchdogHandler:
    __slots__ = ("_callback",)

    def __init__(self, callback: Callable[[str], None]) -> None:
        self._callback = callback

    def dispatch(self, event: Any) -> None:
        if getattr(event, "is_directory", False):
            return
        src = getattr(event, "src_path", "")
        if not src:
            return
        ext = os.path.splitext(src)[1].lower()
        if ext not in _EXT_TO_LANG:
            return
        self._callback(src)
