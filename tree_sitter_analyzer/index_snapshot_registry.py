"""Bounded admission helpers for process-local index snapshots."""

from __future__ import annotations

import os
import secrets
import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Literal, cast


def ensure_capacity(
    entries: dict[str, Any],
    charged_bytes: int,
    max_snapshots: int,
    max_charged_bytes: int,
) -> None:
    """Evict oldest unpinned entries until one actual copy can be admitted."""
    if charged_bytes > max_charged_bytes:
        raise RuntimeError("INDEX_SNAPSHOT_CAPACITY")
    while _would_exceed_capacity(
        entries, charged_bytes, max_snapshots, max_charged_bytes
    ):
        candidates = [
            (key, entry) for key, entry in entries.items() if entry.readers == 0
        ]
        if not candidates:
            raise RuntimeError("INDEX_SNAPSHOT_CAPACITY")
        key, entry = min(candidates, key=lambda item: item[1].expires_at)
        entries.pop(key)
        entry.connection.close()


def reuse_snapshot(
    entries: dict[str, Any],
    snapshot: Any,
    connection: Any,
    expires_at: float,
    capture_deadline: float,
) -> Any | None:
    """Reuse only an identity whose logical and physical status is unchanged."""
    for key, entry in tuple(entries.items()):
        existing = entry.snapshot
        same_logical_identity = (
            existing.canonical_root == snapshot.canonical_root
            and existing.source_fingerprint == snapshot.source_fingerprint
            and existing.index_fingerprint == snapshot.index_fingerprint
            and existing.source_generation == snapshot.source_generation
            and existing.completeness == snapshot.completeness
            and existing.reason == snapshot.reason
            and existing.file_count == snapshot.file_count
            and existing.symbol_projection_exact == snapshot.symbol_projection_exact
            and existing.source_scope == snapshot.source_scope
        )
        if not same_logical_identity:
            continue
        if existing.physical_storage_identity == snapshot.physical_storage_identity:
            entry.expires_at = expires_at
            entry.capture_deadline = capture_deadline
            connection.close()
            return existing
        # A VACUUM or other physical-only rewrite must not refresh a capability
        # whose published metrics are stale. Retire it as soon as it is unpinned.
        if entry.readers == 0:
            entries.pop(key)
            entry.connection.close()
        else:
            entry.expires_at = float("-inf")
    return None


def _would_exceed_capacity(
    entries: dict[str, Any],
    charged_bytes: int,
    max_snapshots: int,
    max_charged_bytes: int,
) -> bool:
    live = sum(entry.charged_bytes for entry in entries.values())
    return len(entries) >= max_snapshots or live + charged_bytes > max_charged_bytes


@dataclass(frozen=True, slots=True)
class IndexSnapshot:
    snapshot_id: str | None
    source_fingerprint: str | None
    index_fingerprint: str | None
    source_generation: str | None
    completeness: Literal["complete", "partial", "unknown"]
    reason: str | None
    canonical_root: str | None
    file_count: int
    physical_storage_identity: tuple[int, int, int, int, int, int] | None = None
    symbol_projection_exact: bool | None = None
    source_scope: Any | None = None


@dataclass(slots=True)
class _Entry:
    snapshot: IndexSnapshot
    connection: sqlite3.Connection
    charged_bytes: int
    expires_at: float
    capture_deadline: float
    readers: int = 0
    io_lock: Any = field(default_factory=threading.RLock)


class IndexSnapshotRegistry:
    """Bounded process-local owner for immutable snapshot capabilities."""

    def __init__(
        self,
        *,
        clock: Callable[[], float],
        max_snapshots: Callable[[], int],
        max_charged_bytes: Callable[[], int],
        ttl_seconds: Callable[[], float],
        capture_deadline_seconds: Callable[[], float],
    ) -> None:
        self._clock = clock
        self._max_snapshots = max_snapshots
        self._max_charged_bytes = max_charged_bytes
        self._ttl_seconds = ttl_seconds
        self._capture_deadline_seconds = capture_deadline_seconds
        self._lock = threading.RLock()
        self._entries: dict[str, _Entry] = {}

    def ensure_capacity(self, charged_bytes: int) -> None:
        with self._lock:
            self._purge(self._clock())
            ensure_capacity(
                self._entries,
                charged_bytes,
                self._max_snapshots(),
                self._max_charged_bytes(),
            )

    def publish(
        self,
        snapshot: IndexSnapshot,
        connection: sqlite3.Connection,
        charged_bytes: int,
        capture_deadline: float | None = None,
        *,
        pin: bool = False,
    ) -> IndexSnapshot:
        """Atomically publish/reuse a capability and optionally pin its entry."""
        with self._lock:
            now = self._clock()
            deadline = (
                capture_deadline
                if capture_deadline is not None
                else now + self._capture_deadline_seconds()
            )
            self._purge(now)
            existing = reuse_snapshot(
                self._entries,
                snapshot,
                connection,
                now + self._ttl_seconds(),
                deadline,
            )
            if existing is not None:
                published = cast(IndexSnapshot, existing)
                if pin:
                    self._entries[cast(str, published.snapshot_id)].readers += 1
                return published
            self.ensure_capacity(charged_bytes)
            snapshot_id = "idxsnap_" + secrets.token_urlsafe(24)
            published = IndexSnapshot(
                snapshot_id,
                snapshot.source_fingerprint,
                snapshot.index_fingerprint,
                snapshot.source_generation,
                snapshot.completeness,
                snapshot.reason,
                snapshot.canonical_root,
                snapshot.file_count,
                snapshot.physical_storage_identity,
                snapshot.symbol_projection_exact,
                snapshot.source_scope,
            )
            self._entries[snapshot_id] = _Entry(
                published,
                connection,
                charged_bytes,
                now + self._ttl_seconds(),
                deadline,
                readers=int(pin),
            )
            return published

    def release_pin(self, snapshot_id: str) -> None:
        with self._lock:
            entry = self._entries.get(snapshot_id)
            if entry is None or entry.readers <= 0:
                raise ValueError("INDEX_SNAPSHOT_UNKNOWN")
            entry.readers -= 1
            self._purge(self._clock())

    @contextmanager
    def pin_reusable(self, project_root: str) -> Iterator[IndexSnapshot | None]:
        """Pin the newest live capability for ``project_root`` without recopying it."""
        canonical_root = os.path.realpath(os.path.abspath(project_root))
        with self._lock:
            now = self._clock()
            self._purge(now)
            candidates = [
                entry
                for entry in self._entries.values()
                if entry.snapshot.canonical_root == canonical_root
                and entry.expires_at > now
            ]
            entry = max(candidates, key=lambda item: item.expires_at, default=None)
            if entry is not None:
                entry.readers += 1
        try:
            yield entry.snapshot if entry is not None else None
        finally:
            if entry is not None:
                with self._lock:
                    entry.readers -= 1
                    self._purge(self._clock())

    @contextmanager
    def acquire(
        self, snapshot_id: str, project_root: str, source_generation: str | None = None
    ) -> Iterator[tuple[IndexSnapshot, sqlite3.Connection]]:
        canonical_root = os.path.realpath(os.path.abspath(project_root))
        with self._lock:
            now = self._clock()
            self._purge(now)
            entry = self._entries.get(snapshot_id)
            if entry is None or entry.expires_at <= now:
                raise ValueError("INDEX_SNAPSHOT_UNKNOWN")
            if entry.snapshot.canonical_root != canonical_root:
                raise ValueError("INDEX_SNAPSHOT_ROOT_MISMATCH")
            if (
                source_generation is not None
                and source_generation != entry.snapshot.source_generation
            ):
                raise ValueError("SOURCE_GENERATION_MISMATCH")
            entry.readers += 1
        entry.io_lock.acquire()
        try:
            yield entry.snapshot, entry.connection
        finally:
            entry.io_lock.release()
            with self._lock:
                entry.readers -= 1
                self._purge(self._clock())

    def capture_deadline(self, snapshot_id: str) -> float:
        with self._lock:
            entry = self._entries.get(snapshot_id)
            if entry is None:
                raise ValueError("INDEX_SNAPSHOT_UNKNOWN")
            return entry.capture_deadline

    def symbol_projection_exact(self, snapshot_id: str) -> bool | None:
        """Return the projection verdict cached during private-copy capture."""
        with self._lock:
            entry = self._entries.get(snapshot_id)
            if entry is None:
                raise ValueError("INDEX_SNAPSHOT_UNKNOWN")
            return entry.snapshot.symbol_projection_exact

    def close_all(self) -> None:
        with self._lock:
            entries = tuple(self._entries.values())
            self._entries.clear()
        for entry in entries:
            entry.connection.close()

    def _purge(self, now: float) -> None:
        for key in [
            key
            for key, entry in self._entries.items()
            if entry.expires_at <= now and entry.readers == 0
        ]:
            self._entries.pop(key).connection.close()
