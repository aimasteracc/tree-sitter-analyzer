"""RFC-0042 P3-lite: whole-snapshot lookup tables for the graph-layer readers.

Some edge-layer readers cannot be made cheap per name: the ES alias rows
(:mod:`.alias_edges`) are found only by testing every call edge's metadata,
about 30 ms on hono and 100 ms on zod for each name asked. Grouped once over
the whole index, the same rows cost one scan, and every later name is a dict
lookup. The readers here take only a SQLite connection, so they cannot know
which certified snapshot they read. The snapshot adapter
(``index_snapshot_query.CertifiedSnapshotCache``) therefore binds its
connection to a *provider* for the duration of a read (:func:`bound`), and the
provider keeps each table in the per-snapshot memo
(:mod:`tree_sitter_analyzer.resident.snapshot_memo`), keyed by the certified
snapshot identity.

Trust (RFC-0042 R0): a table is used only for the exact connection object it
was bound with, inside the binding (a :class:`~contextvars.ContextVar`, so it
never leaks to another request or thread). Any other connection, the live
index, ``TSA_RESIDENT=off`` and threads outside the binding get ``None`` here
and read per name, as before. The readers derive each name's answer from the
table with the per-name query's own conditions (differential tests compare
both on real indexes), so a table changes the cost of a read, never its result.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, TypeVar

T = TypeVar("T")

#: ``(conn, provider)`` while a snapshot adapter reads; ``provider(name, compute)``.
_BOUND: ContextVar[tuple[Any, Callable[[str, Callable[[], Any]], Any]] | None] = (
    ContextVar("tsa_snapshot_tables", default=None)
)


@contextmanager
def bound(
    conn: Any, provider: Callable[[str, Callable[[], Any]], Any]
) -> Iterator[None]:
    """Serve :func:`table` for ``conn`` through ``provider`` until the block exits."""
    token = _BOUND.set((conn, provider))
    try:
        yield
    finally:
        _BOUND.reset(token)


def table(conn: Any, name: str, compute: Callable[[], T]) -> T | None:
    """The snapshot's table ``name`` (``compute()`` once per snapshot), or ``None``.

    ``None`` means "no table for this connection here": the caller reads per
    name. ``compute`` errors propagate (an interrupted read is not a table).
    """
    entry = _BOUND.get()
    if entry is None or entry[0] is not conn:
        return None
    return entry[1](name, compute)  # type: ignore[no-any-return]


def is_bound(conn: Any) -> bool:
    entry = _BOUND.get()
    return entry is not None and entry[0] is conn


__all__ = ["bound", "is_bound", "table"]
