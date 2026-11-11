"""RFC-0042 P2a: one selector stat per request instead of about ten probes.

Profiling (RFC-0042, ``rich``) puts 35 % of a warm ``nav callers`` in probes
that re-derive the same facts on every request: the index location (each call
reads ``index-generations/active.json`` and runs ``realpath``), the live-index
probe (a SQLite connection and four queries, three times per request: the
certification ruling and twice for ``query_cost``), the rebuild flag (location
plus connection, twice) and the certification-timeout record.

A :class:`ResidentHandle` keeps the facts that are pure functions of the
published generation the selector names:

* the resolved :class:`~tree_sitter_analyzer.cache.generation_routing.IndexLocation`;
* the :class:`~tree_sitter_analyzer.cache.live_index_probe.LiveIndexProbe`
  (row counts, max edge rowid, call-graph marker) of that database.

**Why that is sound.** A handle is kept only for a *sealed* published
generation: the database is a plain file with no write bits (``seal`` clears
them before publication; rollback journal, no sidecars), so its content cannot
change while it stays sealed. Publication replaces the selector by an atomic
rename (a new file ID). Each request first compares the selector's and the
database's ``lstat`` stamps (device, inode, size, mtime, mode, attributes) with
the handle's; any difference, a missing file, or a database that regained a
write bit drops the handle and the request takes today's path, which builds a
new handle from today's functions. The handle is never freshness evidence
(RFC-0030): the location and the probe say which index the request reads, not
whether the source matches it, and the certified snapshot still decides that.

**Not cached: the rebuild flag.** ``is_index_rebuilding`` still runs its query
on every call. Inside a request it uses one read-only connection to the
handle's database, opened on first use and closed when the request ends, so the
two checks of a request cost one connect instead of two location resolutions
and two connects. No connection outlives a request: a connection held across
requests would pin a retired generation on disk (#1631).

**No query scope per request.** The RFC's suggested first step, running each
request inside one RFC-0041 ``query_scope``, was measured on ``rich`` (ABBA,
n = 160 per slot) and made single requests slower: review-gated median
97.5–104.6 ms with the scope against 86.2–87.7 ms without. The scope's batch
paths (joined vocabularies, bucketed alias rows that cannot be memoized on an
in-memory snapshot) pay off across names, not within one. The handle removes
the repeated ``realpath`` calls of the probes instead.

**Scope.** Only code inside :func:`request` (the ``nav callers`` entry point)
reads through a handle; every other caller, the loader thread included, keeps
today's path. ``TSA_RESIDENT=off`` disables handles entirely; ``first-use``
builds one on the first request; ``background`` also builds one at the end of
the loader's load.
"""

from __future__ import annotations

import os
import sqlite3
import stat
import threading
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import loader

#: At most this many project roots keep a handle (the ``call_graph_memo`` bound).
MAX_ROOTS = 4
_WRITE_BITS = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
_REPARSE_POINT = 0x400

_lock = threading.Lock()
#: Project root (as the tool was given it) -> its handle; bounded, oldest first.
_handles: OrderedDict[str, ResidentHandle] = OrderedDict()
#: Counters for tests and the status report.
_stats = {"built": 0, "reused": 0, "dropped": 0}


@dataclass(frozen=True)
class FileStamp:
    """``lstat`` evidence of one file; a rename or any write changes it."""

    device: int
    inode: int
    size: int
    mtime_ns: int
    mode: int
    attributes: int


def file_stamp(path: str | os.PathLike[str]) -> FileStamp | None:
    """The stamp of ``path`` without following links; ``None`` when missing."""
    try:
        info = os.lstat(path)
    except OSError:
        return None
    return FileStamp(
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_mode,
        int(getattr(info, "st_file_attributes", 0) or 0),
    )


def _sealed(stamp: FileStamp | None) -> bool:
    """A plain regular file with no write bit: a sealed generation database."""
    return (
        stamp is not None
        and stat.S_ISREG(stamp.mode)
        and not stamp.mode & _WRITE_BITS
        and not stamp.attributes & _REPARSE_POINT
    )


@dataclass(frozen=True)
class ResidentHandle:
    """The per-root facts of one sealed published generation (see module doc)."""

    root: str
    real_root: str
    selector_path: str
    selector_stamp: FileStamp
    database_stamp: FileStamp
    location: Any
    live_probe: Any

    @property
    def database(self) -> Path:
        return Path(self.location.path)

    def matches(self, project_root: str | None) -> bool:
        return bool(project_root) and project_root in (self.root, self.real_root)

    def current(self) -> bool:
        """Two ``lstat`` calls: the selector and the database are unchanged."""
        return (
            file_stamp(self.selector_path) == self.selector_stamp
            and file_stamp(self.database) == self.database_stamp
        )


def build(project_root: str) -> ResidentHandle | None:
    """A handle from today's functions; ``None`` when the facts are not cacheable.

    ``None`` for an unpublished index, an unsealed database, an unreadable
    probe, or a selector or database that changed while the facts were read.
    """
    from ..cache.generation_routing import (
        generation_storage_path,
        resolve_index_location,
    )
    from ..cache.live_index_probe import probe_live_index_uncached

    real_root = os.path.realpath(os.path.abspath(project_root))
    selector_path = str(generation_storage_path(real_root) / "active.json")
    selector_before = file_stamp(selector_path)
    if selector_before is None:
        return None
    try:
        location = resolve_index_location(real_root)
    except (OSError, ValueError):
        return None
    if not location.published:
        return None
    database_before = file_stamp(location.path)
    if not _sealed(database_before):
        return None
    probe = probe_live_index_uncached(project_root)
    if probe is None or not probe.identity or probe.identity[0] != str(location.path):
        return None
    if (
        file_stamp(selector_path) != selector_before
        or file_stamp(location.path) != database_before
    ):
        return None  # a publish raced the reads: take today's path this time
    assert database_before is not None  # narrowed by _sealed
    return ResidentHandle(
        root=project_root,
        real_root=real_root,
        selector_path=selector_path,
        selector_stamp=selector_before,
        database_stamp=database_before,
        location=location,
        live_probe=probe,
    )


def acquire(project_root: str | None) -> ResidentHandle | None:
    """The current handle for ``project_root``: reused when both stamps hold, else rebuilt."""
    if not project_root or loader.mode() == "off":
        return None
    with _lock:
        handle = _handles.get(project_root)
    if handle is not None and handle.current():
        with _lock:
            _stats["reused"] += 1
        return handle
    fresh = build(project_root)
    with _lock:
        if handle is not None and _handles.get(project_root) is handle:
            del _handles[project_root]
            _stats["dropped"] += 1
        if fresh is not None:
            _handles[project_root] = fresh
            _handles.move_to_end(project_root)
            while len(_handles) > MAX_ROOTS:
                _handles.popitem(last=False)
            _stats["built"] += 1
    return fresh


def peek(project_root: str) -> ResidentHandle | None:
    """The stored handle (not validated); for tests and the status report."""
    with _lock:
        return _handles.get(project_root)


def stats() -> dict[str, int]:
    with _lock:
        return dict(_stats)


def reset() -> None:
    """Forget every handle (tests; a new process)."""
    with _lock:
        _handles.clear()
        for key in _stats:
            _stats[key] = 0


# --------------------------------------------------------------------------- #
# Request scope
# --------------------------------------------------------------------------- #


class _Request:
    """One request's validated handle and its lazily opened read-only connection."""

    __slots__ = ("handle", "thread", "connection")

    def __init__(self, handle: ResidentHandle) -> None:
        self.handle = handle
        self.thread = threading.get_ident()
        self.connection: sqlite3.Connection | None = None

    def close(self) -> None:
        if self.connection is not None:
            try:
                self.connection.close()
            except sqlite3.Error:
                pass
            self.connection = None


_REQUEST: ContextVar[_Request | None] = ContextVar("tsa_resident_request", default=None)


@contextmanager
def request(project_root: str | None) -> Iterator[ResidentHandle | None]:
    """Validate the handle once and let the probes of this request read through it.

    Nested use for the same root reuses the outer request. ``None`` (no handle)
    means every probe takes today's path.
    """
    outer = _REQUEST.get()
    if outer is not None and outer.handle.matches(project_root):
        yield outer.handle
        return
    handle = acquire(project_root)
    if handle is None:
        token = _REQUEST.set(None)
        try:
            yield None
        finally:
            _REQUEST.reset(token)
        return
    current = _Request(handle)
    token = _REQUEST.set(current)
    try:
        yield handle
    finally:
        _REQUEST.reset(token)
        current.close()


def _active(project_root: str | None) -> _Request | None:
    current = _REQUEST.get()
    if current is None or not current.handle.matches(project_root):
        return None
    if current.thread != threading.get_ident():
        return None  # another thread with a copied context: today's path
    return current


def current_handle(project_root: str | None) -> ResidentHandle | None:
    """The validated handle of the request running for ``project_root``, if any."""
    active = _active(project_root)
    return None if active is None else active.handle


def live_probe(project_root: str | None) -> Any:
    """The handle's live-index probe for this request, else ``None`` (probe today)."""
    active = _active(project_root)
    return None if active is None else active.handle.live_probe


def rebuilding(project_root: str | None) -> bool | None:
    """The rebuild flag read now on the request's connection; ``None``: read it today's way.

    Same query as ``is_index_rebuilding`` (``build_in_progress`` over a
    read-only connection with a 2 s lock wait). A failure to open the
    connection hands the check back to today's code.
    """
    active = _active(project_root)
    if active is None:
        return None
    from ..cache.build_state import build_in_progress

    if active.connection is None:
        try:
            active.connection = sqlite3.connect(
                active.handle.database.absolute().as_uri() + "?mode=ro",
                uri=True,
                timeout=2,
            )
        except sqlite3.Error:
            return None
    try:
        return bool(build_in_progress(active.connection))
    except Exception:  # noqa: BLE001 — today's reader treats a failure as False
        return False


__all__ = [
    "FileStamp",
    "ResidentHandle",
    "acquire",
    "build",
    "current_handle",
    "file_stamp",
    "live_probe",
    "peek",
    "rebuilding",
    "request",
    "reset",
    "stats",
]
