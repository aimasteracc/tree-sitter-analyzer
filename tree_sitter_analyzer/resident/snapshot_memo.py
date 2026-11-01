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

import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Any, TypeVar

from . import loader

T = TypeVar("T")

#: At most this many snapshots (one per project root) keep a memo.
MAX_SNAPSHOTS = 4
#: At most this many entries per snapshot; past it, results are computed, not stored.
MAX_ENTRIES = 20_000

_lock = threading.Lock()
#: Snapshot key -> {(reader, args): value}; oldest first.
_memos: OrderedDict[tuple[str, ...], dict[Hashable, Any]] = OrderedDict()
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


def _storable(cache: Any) -> bool:
    """The cache confirms the read finished before its deadline (no interrupt seen)."""
    check = getattr(cache, "memo_storable", None)
    if not callable(check):
        return False
    try:
        return bool(check())
    except Exception:  # noqa: BLE001 — in doubt, do not remember
        return False


def _store(key: tuple[str, ...], entry: Hashable, value: Any) -> None:
    with _lock:
        memo = _memos.get(key)
        if memo is None:
            # A new snapshot of a root replaces that root's previous memo at once:
            # its key is never asked again, and memory stays at one per root.
            for old in [k for k in _memos if k[1] == key[1]]:
                del _memos[old]
                _stats["dropped_snapshots"] += 1
            memo = {_OWNER: key}
            _memos[key] = memo
            while len(_memos) > MAX_SNAPSHOTS:
                _memos.popitem(last=False)
                _stats["dropped_snapshots"] += 1
        if len(memo) > MAX_ENTRIES:
            return
        memo[entry] = value
        _memos.move_to_end(key)
        _stats["stored"] += 1


def stats() -> dict[str, int]:
    with _lock:
        out = dict(_stats)
        out["snapshots"] = len(_memos)
        out["entries"] = sum(len(memo) - 1 for memo in _memos.values())
        return out


def keys() -> list[tuple[str, ...]]:
    """Snapshot keys that hold a memo (tests and the status report)."""
    with _lock:
        return list(_memos)


def clear() -> None:
    """Forget every memo (tests; memory pressure)."""
    with _lock:
        _memos.clear()
        for name in _stats:
            _stats[name] = 0


__all__ = ["cached", "clear", "copy_value", "keys", "snapshot_key", "stats"]
