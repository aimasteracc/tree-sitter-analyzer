"""Bounded manifest reader boundary for authoritative snapshots."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import cast

from .index_snapshot_schema import _deadline_ordered_rows


def _read_bounded_manifest_impl(
    connection: sqlite3.Connection,
    deadline: float,
    *,
    clock: Callable[[], float],
    require_budget: Callable[[float], None],
    text_byte_budget: int,
    scope_byte_budget: int,
    total_byte_budget: int,
) -> sqlite3.Row | None:
    """Preflight manifest cell sizes inside SQLite before decoding values."""
    columns = (
        "canonical_root",
        "source_fingerprint",
        "index_fingerprint",
        "file_count",
        "source_scope_descriptor",
        "manifest_version",
    )
    valid_singleton = "typeof(singleton) = 'integer' AND singleton = 1"
    count_rows = _deadline_ordered_rows(
        connection,
        "SELECT COUNT(*), "
        f"CASE WHEN COUNT(CASE WHEN {valid_singleton} THEN 1 END) = COUNT(*) "
        "THEN 1 ELSE 0 END, "
        f"CASE WHEN COUNT(CASE WHEN {valid_singleton} THEN 1 END) = 1 "
        "THEN 1 ELSE 0 END "
        "FROM ast_index_snapshot_manifest",
        deadline,
    )
    count_row = next(count_rows, None)
    if (
        count_row is None
        or len(count_row) != 3
        or not isinstance(count_row[0], int)
        or next(count_rows, None) is not None
    ):
        raise ValueError("INDEX_MANIFEST_INVALID")
    if count_row[0] == 0:
        return None
    if (
        count_row[0] != 1
        or type(count_row[1]) is not int
        or count_row[1] != 1
        or type(count_row[2]) is not int
        or count_row[2] != 1
    ):
        raise ValueError("INDEX_MANIFEST_INVALID")

    length_query = (
        "SELECT "
        + ", ".join(f"length(CAST({column} AS BLOB))" for column in columns)
        + " FROM ast_index_snapshot_manifest WHERE singleton=1"
    )
    length_rows = _deadline_ordered_rows(connection, length_query, deadline)
    first_lengths = next(length_rows, None)
    if first_lengths is None or next(length_rows, None) is not None:
        raise ValueError("INDEX_MANIFEST_INVALID")
    lengths = tuple(0 if value is None else int(value) for value in first_lengths)
    per_cell = (
        text_byte_budget,
        text_byte_budget,
        text_byte_budget,
        text_byte_budget,
        scope_byte_budget,
        text_byte_budget,
    )
    if any(
        length < 0 or length > budget
        for length, budget in zip(lengths, per_cell, strict=True)
    ):
        raise ValueError("INDEX_MANIFEST_INVALID")
    if sum(lengths) > total_byte_budget:
        raise ValueError("INDEX_MANIFEST_INVALID")
    query = (
        "SELECT "
        + ", ".join(columns)
        + " FROM ast_index_snapshot_manifest WHERE singleton=1"
    )

    def expired() -> int:
        return int(clock() >= deadline)

    connection.set_progress_handler(expired, 1_000)
    try:
        require_budget(deadline)
        cursor = connection.execute(query)
        fetchone = getattr(cursor, "fetchone", None)
        if callable(fetchone):
            manifest = fetchone()
            duplicate = fetchone()
        else:
            rows = iter(cursor)
            manifest = next(rows, None)
            duplicate = next(rows, None)
        require_budget(deadline)
    finally:
        connection.set_progress_handler(None, 0)
    if manifest is None or duplicate is not None:
        raise ValueError("INDEX_MANIFEST_INVALID")
    return cast(sqlite3.Row, manifest)


def _read_bounded_manifest(
    connection: sqlite3.Connection, deadline: float
) -> sqlite3.Row | None:
    """Preserve the established import while honoring owner-module seams."""
    from . import index_snapshot

    return index_snapshot._read_bounded_manifest(connection, deadline)


__all__ = ["_read_bounded_manifest"]
