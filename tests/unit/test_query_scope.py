"""RFC-0041: query-scoped memoisation is live outside a scope, shared inside."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from tree_sitter_analyzer.graph.alias_edges import _es_alias_rows
from tree_sitter_analyzer.query_scope import in_scope, query_scope, scoped


def _counter():
    calls: list[int] = []

    def compute() -> int:
        calls.append(1)
        return len(calls)

    return calls, compute


def test_unscoped_calls_compute_every_time() -> None:
    calls, compute = _counter()
    assert (scoped("k", compute), scoped("k", compute), len(calls)) == (1, 2, 2)


def test_scoped_calls_compute_once_per_key() -> None:
    calls, compute = _counter()
    with query_scope():
        values = (scoped("k", compute), scoped("k", compute))
    assert (values, len(calls)) == ((1, 1), 1)


def test_scope_ends_with_the_block() -> None:
    with query_scope():
        inside = in_scope()
    assert (inside, in_scope()) == (True, False)


def _alias_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(
        "CREATE TABLE ast_imports (file_path TEXT, local_name TEXT, language TEXT,"
        " alias_of TEXT, is_star INTEGER);"
        "CREATE TABLE edges (id INTEGER PRIMARY KEY, kind TEXT, callee_name TEXT,"
        " file_path TEXT, metadata TEXT);"
    )
    meta = json.dumps({"import_alias": {"local": "makeSig", "name": "signer"}})
    conn.execute(
        "INSERT INTO ast_imports VALUES ('a.ts', 'makeSig', 'typescript', NULL, 0)"
    )
    conn.execute(
        "INSERT INTO ast_imports VALUES ('b.ts', 'signer', 'typescript', NULL, 0)"
    )
    conn.execute("INSERT INTO edges VALUES (1, 'calls', 'makeSig', 'a.ts', ?)", (meta,))
    conn.execute(
        "INSERT INTO edges VALUES (2, 'calls', 'signer', 'b.ts', ?)",
        (json.dumps({"import_alias": {"local": "signer", "name": "signer"}}),),
    )
    conn.commit()
    return conn


def test_scoped_es_alias_rows_equal_the_per_name_query(tmp_path: Path) -> None:
    # RFC-0041: the bucketed lookup must return exactly the per-name rows.
    conn = _alias_db(tmp_path / "index.db")
    live = [row["id"] for row in _es_alias_rows(conn, "signer")]
    with query_scope():
        bucketed = [row["id"] for row in _es_alias_rows(conn, "signer")]
    assert (live, bucketed) == ([1], [1])
