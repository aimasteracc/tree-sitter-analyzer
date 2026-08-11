"""Bounded admission helpers for process-local index snapshots."""

from __future__ import annotations

from typing import Any


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
