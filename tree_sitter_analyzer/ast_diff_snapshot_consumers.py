"""Validate and decode immutable files for AST diff snapshot consumers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SnapshotSources:
    old_source: str
    new_source: str


def decode_snapshot_sources(frozen: Any) -> SnapshotSources | None:
    """Return strict UTF-8 sources only for supported ordinary file records."""
    if (
        not getattr(frozen.record, "old_available", frozen.old_bytes is not None)
        or not getattr(frozen.record, "new_available", frozen.new_bytes is not None)
        or getattr(frozen.record, "status", None) in ("R", "C")
        or getattr(frozen.record, "unsupported_kind", None) is not None
        or frozen.record.binary
        or any(
            kind not in ("file", "missing")
            for kind in (
                getattr(frozen.record, "old_kind", "file"),
                getattr(frozen.record, "new_kind", "file"),
            )
        )
    ):
        return None
    try:
        return SnapshotSources(
            (frozen.old_bytes or b"").decode("utf-8", "strict"),
            (frozen.new_bytes or b"").decode("utf-8", "strict"),
        )
    except UnicodeDecodeError:
        return None
