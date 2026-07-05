"""Persisted "full rebuild in progress" marker for the AST cache (#578).

A ``--full-index --full-index-mode full`` rebuild does ``DELETE FROM ast_index``
+ ``commit`` up front, then re-populates in bounded 500-file batches (the "A4"
RSS guard in :func:`_ast_cache_helpers._commit_index_results`). Those batched
re-inserts commit incrementally over the ~70 s rebuild, so a reader on another
connection — or another process — sees the committed-but-empty / half-filled
table and returns ``success: true`` with phantom-empty data.

A single big transaction wrapping the whole rebuild would remove the window but
revive the exact OOM that A4's bounded-batch commit exists to prevent, so it is
not an option. Instead the rebuild stamps a single sqlite meta row before the
DELETE and clears it after re-population; readers consult it and warn rather
than trusting a half-built table.

The marker is persisted (visible to every connection, including other
processes) and self-expiring: a rebuild that crashes without clearing the row
leaves a marker that goes *stale* after ``ttl_seconds`` so readers are never
wedged into permanent "rebuilding" warnings.

This mirrors the ``ast_resolve_state`` single-row idiom in
:mod:`tree_sitter_analyzer._ast_cache_unresolved`.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time

logger = logging.getLogger(__name__)

# Liveness is decided primarily by the recorded rebuilder pid (below); this TTL
# is only a backstop for the cases pid-liveness can't cover — pid reuse, or a
# (non-default) cache shared across machines. Set well above any plausible
# single rebuild so it never expires a genuinely-running one: a 20k-file repo on
# a slow/contended host can take many minutes (the ~70 s in #578 was a small
# repo). Kept finite so a wedged marker still self-heals eventually.
_DEFAULT_TTL_SECONDS = 3600.0

# Tolerance for a marker timestamp that sits slightly in the future (minor clock
# skew). Beyond this the clock stepped backward (NTP) and the marker is bogus.
_CLOCK_SKEW_GRACE_SECONDS = 60.0

_CREATE_DDL = (
    "CREATE TABLE IF NOT EXISTS ast_build_state ("
    "id INTEGER PRIMARY KEY, "
    "building INTEGER NOT NULL, "
    "started_at REAL NOT NULL, "
    "pid INTEGER NOT NULL)"
)


def _pid_alive(pid: int) -> bool:
    """Best-effort: is a process with this pid running on THIS machine?

    The ``.ast-cache`` db is local to the checkout, so the rebuilder and any
    concurrent reader share a machine — a dead pid means the rebuild crashed,
    and the marker is stale *immediately* (no waiting for the TTL backstop).
    Signal 0 probes existence without delivering anything.
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, just owned by another user
    except OSError:  # pragma: no cover — be conservative, assume alive
        return True
    return True


def mark_build_in_progress(conn: sqlite3.Connection) -> None:
    """Stamp the single-row marker that a full rebuild has started.

    Best-effort: on write failure (lock contention, transient I/O) this logs and
    returns rather than raising — the marker must never become a *new* failure
    source. The caller then proceeds without a marker, degrading to the pre-#578
    behaviour (readers may see the transient empty window) rather than aborting
    the rebuild outright, which would be a worse "can't rebuild under
    contention" failure mode.
    """
    try:
        conn.execute(_CREATE_DDL)
        conn.execute(
            "INSERT INTO ast_build_state (id, building, started_at, pid) "
            "VALUES (1, 1, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "building = excluded.building, "
            "started_at = excluded.started_at, "
            "pid = excluded.pid",
            (time.time(), os.getpid()),
        )
        conn.commit()
    except sqlite3.OperationalError:
        logger.debug("could not mark build-in-progress", exc_info=True)


def clear_build_in_progress(conn: sqlite3.Connection) -> None:
    """Clear the marker after a rebuild finishes (or aborts cleanly)."""
    try:
        conn.execute("UPDATE ast_build_state SET building = 0 WHERE id = 1")
        conn.commit()
    except sqlite3.OperationalError:
        logger.debug("could not clear build-in-progress", exc_info=True)


def build_in_progress(
    conn: sqlite3.Connection, *, ttl_seconds: float = _DEFAULT_TTL_SECONDS
) -> bool:
    """True iff a full rebuild is actively in progress.

    Returns ``False`` when the marker table/row is absent, when the flag is off,
    or when the marker is *stale*. Staleness is decided by, in order:

    * **clock skew** — a ``started_at`` more than ``_CLOCK_SKEW_GRACE_SECONDS``
      in the future means the wall clock stepped backward (NTP); the marker is
      bogus, not fresh-forever.
    * **TTL backstop** — older than ``ttl_seconds`` (covers pid reuse and the
      non-default cross-machine cache case).
    * **pid liveness** — the recorded rebuilder pid is no longer running, so the
      rebuild crashed; stale immediately rather than after the full TTL.

    Never raises.
    """
    try:
        row = conn.execute(
            "SELECT building, started_at, pid FROM ast_build_state WHERE id = 1"
        ).fetchone()
    except sqlite3.OperationalError:
        return False
    if row is None:
        return False
    if isinstance(row, sqlite3.Row):
        building, started_at, pid = row["building"], row["started_at"], row["pid"]
    else:
        building, started_at, pid = row[0], row[1], row[2]
    if not building:
        return False
    now = time.time()
    started = float(started_at)
    if started > now + _CLOCK_SKEW_GRACE_SECONDS:
        return False  # clock stepped backward — bogus future timestamp
    if (now - started) >= ttl_seconds:
        return False  # TTL backstop for a wedged/crashed marker
    if not _pid_alive(int(pid)):
        return False  # rebuilder process gone — crashed, stale now
    return True
