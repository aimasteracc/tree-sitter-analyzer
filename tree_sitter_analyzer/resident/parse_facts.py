"""RFC-0043: facts derived from parsing one source text, kept per content digest.

The RFC-0040 review gates of ``nav callers`` read the declaring file (and, for
the supertype gates, the files of a class chain) on every request and parsed it
again: on zod that was about 0.7 s per review-gated query. The results they
need from a parse are small immutable tables (the decorators on each
declaration, the definitions and their header lines, the classes of a Python
file). This module keeps those tables, keyed by::

    (kind, language, extra, blake2b-128(content))

Trust (RFC-0042 R0/R1, RFC-0043 §1):

* The content is read live on every request by the caller, through the
  stamp-validated evidence file cache. A memo entry is found only for
  byte-identical content, so an edited file has a new digest and is parsed
  again. Nothing here is freshness evidence and no key is a path stamp.
* ``compute`` must be a pure function of ``(content, language, extra)`` and
  return an immutable value (tuples, frozensets, strings, numbers, frozen
  dataclasses of those). No syntax tree is kept.
* Off switch: ``TSA_RESIDENT_PARSE_MEMO=0`` (or ``off`` / ``false`` / ``no``),
  or the RFC-0042 kill switch ``TSA_RESIDENT=off``. Off means every call
  computes, exactly as before the memo existed.

Bounds: at most :data:`MAX_ENTRIES` entries and :data:`MAX_BYTES` estimated
bytes, least recently used first out.
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
import sys
import threading
from collections import OrderedDict
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")

#: Environment switch; default on (RFC-0043 §6: identity proven on every stored gate answer).
ENV_VAR = "TSA_RESIDENT_PARSE_MEMO"
_OFF_VALUES = frozenset({"0", "off", "false", "no"})
#: Entry bound of the process-wide memo.
MAX_ENTRIES = 4096
#: Estimated byte bound of the process-wide memo.
MAX_BYTES = 64 * 1024 * 1024

_lock = threading.Lock()
#: key -> (value, estimated bytes)
_memo: OrderedDict[tuple[Any, ...], tuple[Any, int]] = OrderedDict()
_bytes = 0
_hits = 0
_misses = 0


def enabled() -> bool:
    """Whether the memo is on (default) for this process right now."""
    if os.environ.get(ENV_VAR, "").strip().lower() in _OFF_VALUES:
        return False
    from . import loader

    return loader.mode() != "off"


def digest(content: str | bytes) -> bytes:
    """Content digest of a text (UTF-8) or raw bytes."""
    data = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.blake2b(data, digest_size=16).digest()


def facts(
    kind: str,
    language: str,
    content: str | bytes,
    compute: Callable[[], T],
    extra: tuple[Any, ...] = (),
) -> T:
    """``compute()`` for this exact content, reused while the content is byte-identical."""
    if not enabled():
        return compute()
    key = (kind, language, extra, type(content).__name__, digest(content))
    return _lookup(key, compute)


def facts_for_digest(
    kind: str,
    language: str,
    content_digest: bytes,
    compute: Callable[[], T],
    extra: tuple[Any, ...] = (),
) -> T:
    """:func:`facts` for raw bytes whose :func:`digest` the caller already holds.

    RFC-0043 Phase C: the Python supertype reader parses a file once per stat
    stamp and keeps its digest; ``compute`` derives the facts from that parse.
    The entry is the one :func:`facts` would use for the same bytes.
    """
    if not enabled():
        return compute()
    return _lookup((kind, language, extra, "bytes", content_digest), compute)


def _lookup(key: tuple[Any, ...], compute: Callable[[], T]) -> T:
    global _hits, _misses
    with _lock:
        hit = _memo.get(key)
        if hit is not None:
            _memo.move_to_end(key)
            _hits += 1
            return hit[0]  # type: ignore[no-any-return]
        _misses += 1
    value = compute()
    _store(key, value)
    return value


def _store(key: tuple[Any, ...], value: Any) -> None:
    global _bytes
    size = estimate_bytes(value) + estimate_bytes(key)
    if size > MAX_BYTES:
        return
    with _lock:
        old = _memo.pop(key, None)
        if old is not None:
            _bytes -= old[1]
        _memo[key] = (value, size)
        _bytes += size
        while _memo and (len(_memo) > MAX_ENTRIES or _bytes > MAX_BYTES):
            _evicted, (_value, evicted_size) = _memo.popitem(last=False)
            _bytes -= evicted_size


def estimate_bytes(value: Any, _depth: int = 0) -> int:
    """Rough deep size of an immutable value (containers, strings, frozen dataclasses)."""
    size = sys.getsizeof(value)
    if _depth > 8:
        return size
    if isinstance(value, tuple | list | frozenset | set):
        return size + sum(estimate_bytes(item, _depth + 1) for item in value)
    if isinstance(value, dict):
        return size + sum(
            estimate_bytes(k, _depth + 1) + estimate_bytes(v, _depth + 1)
            for k, v in value.items()
        )
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return size + sum(
            estimate_bytes(getattr(value, field.name), _depth + 1)
            for field in dataclasses.fields(value)
        )
    return size


def stats() -> dict[str, int]:
    """Entries, estimated bytes, hits and misses (diagnostics, tests)."""
    with _lock:
        return {
            "entries": len(_memo),
            "bytes": _bytes,
            "hits": _hits,
            "misses": _misses,
        }


def clear() -> None:
    """Forget every entry (tests; memory pressure)."""
    global _bytes, _hits, _misses
    with _lock:
        _memo.clear()
        _bytes = 0
        _hits = 0
        _misses = 0


__all__ = [
    "ENV_VAR",
    "clear",
    "digest",
    "enabled",
    "estimate_bytes",
    "facts",
    "facts_for_digest",
    "stats",
]
