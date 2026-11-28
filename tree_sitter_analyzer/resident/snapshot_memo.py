"""RFC-0042 P2b: per-snapshot memo of the edge-layer check readers.

The edge-layer checks of RFC-0040 (checks 1–5: unresolved inbound, declaring
file, name-only lines, unattributed module sites, evidence base) read SQL from
the request's certified snapshot: a private in-memory copy of the index, named
by a random snapshot ID that is never reused and immutable for its lifetime.
Profiling (RFC-0042, ``rich``) puts 16 % of a warm ``nav callers`` there, most
of it decoding the same classified call sites of the declaring file again on
every request.

This module memoizes **the same functions over the same immutable input**:
``memo[(snapshot_key, reader, args)] -> result``, where ``snapshot_key`` is the
certified snapshot identity (``CertifiedSnapshotCache.graph_input_identity``:
canonical root, snapshot ID, index fingerprint, source generation). A miss calls
today's reader; nothing is reimplemented, so no semantics can drift.

Trust (RFC-0042 R0/R1):

* **Keyed only by the certified snapshot identity**, never by a path or a
  generation. A refresh, republish or watcher sync gives the next request a new
  snapshot ID, so an old entry can never be looked up for it; the memo of the
  previous snapshot of the same root is dropped as soon as a new one is used.
  Every entry carries its key and a hit re-checks it.
* **Index-derived only.** Readers that touch source text (the external-producer
  verdicts, the review gates) keep reading the source live; only their SQL
  inputs are memoized. A memo is never freshness evidence, and ``complete``
  still comes only from ``callers_checks.prove()``.
* **Failures are not remembered.** An exception propagates as today and a
  ``None`` result ("could not be read") is returned without being stored, so a
  transient failure never becomes the answer. A result is stored only when the
  snapshot owner's deadline still holds after the read: its connection
  interrupts queries past the deadline, and some readers turn that interrupt
  into an empty list, which must stay a one-request degradation.
* **Callers get their own copy.** Results are lists and dicts that callers may
  extend or sort; every hit returns a deep copy of the stored value.
* ``TSA_RESIDENT=off`` disables the memo; an uncertified cache (the live
  ``ASTCache``) has no snapshot identity and is never memoized.
"""

from __future__ import annotations

import sqlite3
import sys
import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable, Mapping
from itertools import islice
from typing import Any, TypeVar

from . import loader
from .parse_facts import estimate_bytes

T = TypeVar("T")

#: At most this many snapshots (one per project root) keep a memo.
MAX_SNAPSHOTS = 4
#: At most this many entries per snapshot; past it, results are computed, not stored.
#: Measured: 218 entries after 40 rich targets (both forms) retain about 372 KB
#: (1.7 KB each), so the bound keeps one snapshot's memo near 14 MB at most.
MAX_ENTRIES = 8_192
#: RFC-0043 Phase C: estimated bytes of every snapshot's memo together. Past it the
#: least recently used snapshots are dropped (never the one just stored), and a
#: per-name entry that would push its own snapshot past it is computed, not stored.
MAX_BYTES = 128 * 1024 * 1024
#: Items of a whole-snapshot table measured to estimate its size (rows x mean).
_TABLE_SAMPLE = 64
#: Per-row overhead of the dict behind a table (hash slot and entry).
_ROW_OVERHEAD = 48

_lock = threading.Lock()
#: Snapshot key -> {(reader, args): value}; oldest first.
_memos: OrderedDict[tuple[str, ...], dict[Hashable, Any]] = OrderedDict()
#: Snapshot key -> estimated bytes of its memo.
_sizes: dict[tuple[str, ...], int] = {}
_stats = {"hits": 0, "misses": 0, "stored": 0, "dropped_snapshots": 0}
#: Sentinel key inside each memo: the snapshot key it belongs to (belt and braces).
_OWNER = object()


def snapshot_key(cache: Any) -> tuple[str, ...] | None:
    """The certified snapshot identity of ``cache``; ``None`` when it has none or off."""
    if loader.mode() == "off":
        return None
    identity = getattr(cache, "graph_input_identity", None)
    if not callable(identity):
        return None
    try:
        key = identity()
    except Exception:  # noqa: BLE001 — no identity: no memo, today's read
        return None
    if (
        not isinstance(key, tuple)
        or len(key) < 3
        or key[0] != "certified-snapshot"
        or not all(isinstance(part, str) and part for part in key)
    ):
        return None
    return key


def copy_value(value: Any) -> Any:
    """A deep copy of JSON-like reader results (dict, list, tuple, set; scalars shared)."""
    if isinstance(value, dict):
        return {k: copy_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [copy_value(v) for v in value]
    if isinstance(value, tuple):
        return tuple(copy_value(v) for v in value)
    if isinstance(value, set):
        return {copy_value(v) for v in value}
    return value


def cached(
    cache: Any,
    reader: str,
    args: Hashable,
    compute: Callable[[], T],
) -> T:
    """``compute()`` once per certified snapshot of ``cache``, ``reader`` and ``args``.

    Without a snapshot identity (uncertified cache, switch off) this is just
    ``compute()``.
    """
    key = snapshot_key(cache)
    if key is None:
        return compute()
    entry = (reader, args)
    try:
        hash(entry)
    except TypeError:  # unhashable arguments: read as today
        return compute()
    with _lock:
        memo = _memos.get(key)
        if memo is not None and memo.get(_OWNER) == key and entry in memo:
            _memos.move_to_end(key)
            _stats["hits"] += 1
            stored = memo[entry]
            hit = True
        else:
            hit = False
            _stats["misses"] += 1
    if hit:
        return copy_value(stored)  # type: ignore[no-any-return]
    value = compute()
    if value is None or not _storable(cache):
        return value
    _store(key, entry, copy_value(value))
    return value


def cached_table(cache: Any, name: str, compute: Callable[[], T]) -> T:
    """RFC-0042 P3-lite: a whole-snapshot table, computed once per snapshot.

    Same key, trust and failure rules as :func:`cached`, with two differences
    that only suit tables: the value must be immutable (a ``MappingProxyType``
    of tuples), so a hit returns the stored object itself instead of a deep
    copy; and a table is stored even past :data:`MAX_ENTRIES` (there are a few
    fixed table names per snapshot, and a table that is never stored would be
    rebuilt on every read).
    """
    key = snapshot_key(cache)
    if key is None:
        return compute()
    entry = ("table", name)
    with _lock:
        memo = _memos.get(key)
        if memo is not None and memo.get(_OWNER) == key and entry in memo:
            _memos.move_to_end(key)
            _stats["hits"] += 1
            return memo[entry]  # type: ignore[no-any-return]
        _stats["misses"] += 1
    value = compute()
    if value is None or not _storable(cache):
        return value
    _store(key, entry, value, bounded=False)
    return value


def _storable(cache: Any) -> bool:
    """The cache confirms the read finished before its deadline (no interrupt seen)."""
    check = getattr(cache, "memo_storable", None)
    if not callable(check):
        return False
    try:
        return bool(check())
    except Exception:  # noqa: BLE001 — in doubt, do not remember
        return False


def _store(
    key: tuple[str, ...], entry: Hashable, value: Any, *, bounded: bool = True
) -> None:
    size = estimate_entry(entry, value, table=not bounded)
    with _lock:
        memo = _memos.get(key)
        if memo is None:
            # A new snapshot of a root replaces that root's previous memo at once:
            # its key is never asked again, and memory stays at one per root.
            for old in [k for k in _memos if k[1] == key[1]]:
                _drop(old)
            memo = {_OWNER: key}
            _memos[key] = memo
            _sizes[key] = 0
            while len(_memos) > MAX_SNAPSHOTS:
                _drop(next(iter(_memos)))
        if entry in memo:
            return  # the same reader over the same snapshot: the same value
        if bounded and (len(memo) > MAX_ENTRIES or _sizes[key] + size > MAX_BYTES):
            return
        memo[entry] = value
        _sizes[key] += size
        _memos.move_to_end(key)
        _stats["stored"] += 1
        # RFC-0043 Phase C: the byte budget across snapshots; the snapshot just
        # used stays (without it, a root larger than the budget would rebuild its
        # tables on every read).
        while sum(_sizes.values()) > MAX_BYTES and len(_memos) > 1:
            _drop(next(k for k in _memos if k != key))


def _drop(key: tuple[str, ...]) -> None:
    """Forget one snapshot's memo (``_lock`` held)."""
    del _memos[key]
    _sizes.pop(key, None)
    _stats["dropped_snapshots"] += 1


def estimate_entry(entry: Hashable, value: Any, *, table: bool = False) -> int:
    """Estimated bytes of one memo entry (RFC-0043 Phase C).

    A per-name result is measured deeply (they are small: about 1.7 KB each on
    rich). A whole-snapshot table can hold hundreds of thousands of rows, so it
    is estimated as rows x the mean size of its first rows.
    """
    if table and isinstance(value, Mapping):
        rows = len(value)
        sample = list(islice(value.items(), _TABLE_SAMPLE))
        if not sample:
            return sys.getsizeof(value) + estimate_bytes(entry)
        measured = sum(estimate_bytes(k) + estimate_bytes(_plain(v)) for k, v in sample)
        mean = measured / len(sample) + _ROW_OVERHEAD
        return int(rows * mean) + sys.getsizeof(value) + estimate_bytes(entry)
    return estimate_bytes(_plain(value)) + estimate_bytes(entry)


def _plain(value: Any) -> Any:
    """``sqlite3.Row`` values as tuples, so their fields are counted (ES alias rows)."""
    if isinstance(value, sqlite3.Row):
        return tuple(value)
    if isinstance(value, tuple):
        return tuple(_plain(item) for item in value)
    return value


def stats() -> dict[str, int]:
    with _lock:
        out = dict(_stats)
        out["snapshots"] = len(_memos)
        out["entries"] = sum(len(memo) - 1 for memo in _memos.values())
        out["bytes"] = sum(_sizes.values())
        return out


def keys() -> list[tuple[str, ...]]:
    """Snapshot keys that hold a memo (tests and the status report)."""
    with _lock:
        return list(_memos)


def clear() -> None:
    """Forget every memo (tests; memory pressure)."""
    with _lock:
        _memos.clear()
        _sizes.clear()
        for name in _stats:
            _stats[name] = 0


__all__ = [
    "cached",
    "cached_table",
    "clear",
    "copy_value",
    "estimate_entry",
    "keys",
    "snapshot_key",
    "stats",
]
