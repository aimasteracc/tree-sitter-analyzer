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
    entries: dict[str, Any], snapshot: Any, connection: Any, expires_at: float
) -> Any | None:
    """Refresh an identical capability and close its redundant new copy."""
    for entry in entries.values():
        existing = entry.snapshot
        if (
            existing.canonical_root == snapshot.canonical_root
            and existing.source_fingerprint == snapshot.source_fingerprint
            and existing.index_fingerprint == snapshot.index_fingerprint
            and existing.source_generation == snapshot.source_generation
            and existing.completeness == snapshot.completeness
            and existing.reason == snapshot.reason
            and existing.file_count == snapshot.file_count
        ):
            entry.expires_at = expires_at
            connection.close()
            return existing
    return None


def _would_exceed_capacity(
    entries: dict[str, Any],
    charged_bytes: int,
    max_snapshots: int,
    max_charged_bytes: int,
) -> bool:
    live = sum(entry.charged_bytes for entry in entries.values())
    return len(entries) >= max_snapshots or live + charged_bytes > max_charged_bytes
