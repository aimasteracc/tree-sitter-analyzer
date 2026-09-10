"""Cumulative byte accounting for bounded source-oracle inventories."""

from __future__ import annotations

import sys
from collections.abc import Callable, Sized
from dataclasses import dataclass

from .source_oracle import SourceOracleError

_DICT_SLOT_BYTES = 16
_SET_SLOT_BYTES = 16
_SEQUENCE_SLOT_BYTES = 8


@dataclass
class ByteLedger:
    """Track storage retained across successive bounded oracle reads."""

    ceiling: int
    charged: int = 0

    @property
    def remaining(self) -> int:
        return self.ceiling - self.charged

    def require_available(self, amount: int) -> None:
        """Fail without charging when a temporary allocation cannot fit."""
        if amount < 0 or amount > self.remaining:
            raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")

    def charge(self, amount: int) -> None:
        self.require_available(amount)
        self.charged += amount


def entry_map_storage(entries: dict[bytes, bytes]) -> int:
    """Conservatively estimate retained dict, key, and value storage."""
    return (
        sys.getsizeof(entries)
        + sum(
            sys.getsizeof(key) + sys.getsizeof(value) for key, value in entries.items()
        )
        + len(entries) * _DICT_SLOT_BYTES
    )


def path_set_storage(paths: set[bytes]) -> int:
    """Conservatively estimate a retained set and its owned byte strings."""
    return (
        sys.getsizeof(paths)
        + sum(sys.getsizeof(path) for path in paths)
        + len(paths) * _SET_SLOT_BYTES
    )


def container_storage(items: Sized) -> int:
    """Conservatively estimate an already-built pointer container."""
    return sys.getsizeof(items) + len(items) * _SEQUENCE_SLOT_BYTES


def parse_head_entries(
    raw: bytes,
    *,
    deadline: float,
    byte_ceiling: int,
    max_paths: int,
    remaining_fn: Callable[[float], float],
) -> dict[bytes, bytes]:
    """Parse HEAD rows while accounting for raw and duplicated dict storage."""
    if len(raw) > byte_ceiling:
        raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
    entries: dict[bytes, bytes] = {}
    # The complete bounded subprocess buffer remains live while bytes slices and
    # dict storage are created. Check after every row so hostile inventories stop
    # before validation or later settings/temp-file work can continue.
    offset = 0
    while offset < len(raw):
        remaining_fn(deadline)
        terminator = raw.find(b"\0", offset)
        if terminator < 0:
            terminator = len(raw)
        row = raw[offset:terminator]
        offset = terminator + 1
        if not row:
            continue
        header, separator, path = row.partition(b"\t")
        fields = header.split(b" ")
        if not separator or not path or len(fields) != 3:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        try:
            int(fields[0], 8)
            int(fields[2], 16)
        except ValueError as exc:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR") from exc
        if fields[1] not in (b"blob", b"commit") or path in entries:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        entries[path] = header
        if (
            len(entries) > max_paths
            or len(raw) + entry_map_storage(entries) > byte_ceiling
        ):
            raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
    return entries
