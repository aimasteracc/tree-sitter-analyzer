"""#1873: an interrupted SQL read is "not read", never "no rows".

The certified snapshot's connection interrupts any statement that runs past the
request deadline (SQLite progress handler, ``OperationalError: interrupted``).
A reader that turned that error into ``[]`` (or another default) handed the
rest of the request a value it cannot tell from "read, found nothing": an
RFC-0040 check would then count 0 and could take part in a ``complete``.

Readers that keep a default for a *damaged* index (missing table or column)
call :func:`raise_if_interrupted` first: an interrupt propagates as
:class:`ReadInterrupted`, every other error keeps today's default, so an answer
read without a deadline firing is unchanged.
"""

from __future__ import annotations

import sqlite3


class ReadInterrupted(sqlite3.OperationalError):
    """A read cut off by the connection's deadline: its result was not read.

    A subclass of ``sqlite3.OperationalError``, so code that already treats any
    SQL error on the snapshot as a failed read (the certified answer falls back,
    the uncertified cache reports ``None``) treats it the same way.
    """


def is_interrupted(exc: BaseException) -> bool:
    """Whether ``exc`` is SQLite's interrupt (progress handler or ``interrupt()``)."""
    return isinstance(exc, sqlite3.OperationalError) and (
        isinstance(exc, ReadInterrupted) or "interrupt" in str(exc).lower()
    )


def raise_if_interrupted(exc: BaseException) -> None:
    """Re-raise an interrupt as :class:`ReadInterrupted`; return for anything else."""
    if isinstance(exc, ReadInterrupted):
        raise exc
    if is_interrupted(exc):
        raise ReadInterrupted(str(exc)) from exc


__all__ = ["ReadInterrupted", "is_interrupted", "raise_if_interrupted"]
