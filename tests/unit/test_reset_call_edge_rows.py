"""reset_call_edge_rows skips edges already in the unresolved form (cold-index perf)."""

from __future__ import annotations

import sqlite3


def _reset_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE edges (id INTEGER PRIMARY KEY, metadata TEXT, "
        "callee_resolution TEXT, callee_resolved_file TEXT, callee_symbol_id INTEGER)"
    )
    conn.executemany(
        "INSERT INTO edges VALUES (?, ?, ?, ?, ?)",
        [
            # Already in reset form: freshly extracted and unresolved.
            (
                1,
                '{"callee_resolution": "unknown", "callee_resolved_file": ""}',
                "unknown",
                "",
                None,
            ),
            # Resolved by the backfill: must be reset.
            (
                2,
                '{"callee_resolution": "import", "callee_resolved_file": "b.py", '
                '"callee_symbol_id": 7, "import_alias": "x"}',
                "import",
                "b.py",
                7,
            ),
            # Columns reset but metadata still carries a binding: must be rewritten.
            (
                3,
                '{"callee_resolution": "unknown", "callee_resolved_file": "", '
                '"receiver_binding": {"type": "T"}}',
                "unknown",
                "",
                None,
            ),
        ],
    )
    return conn


def _reset_contents(conn: sqlite3.Connection) -> list[tuple]:
    return [tuple(r) for r in conn.execute("SELECT * FROM edges ORDER BY id")]


def test_reset_call_edge_rows_skips_rows_already_in_reset_form() -> None:
    from tree_sitter_analyzer.cache.write import reset_call_edge_rows

    columns = "id, metadata, callee_resolution, callee_resolved_file, callee_symbol_id"
    skipping, plain = _reset_db(), _reset_db()
    updates: list[str] = []
    skipping.set_trace_callback(
        lambda sql: updates.append(sql) if sql.startswith("UPDATE") else None
    )
    reset_call_edge_rows(
        skipping, skipping.execute(f"SELECT {columns} FROM edges").fetchall()
    )
    # Rows without the resolution columns are always rewritten (previous behavior).
    reset_call_edge_rows(
        plain, plain.execute("SELECT id, metadata FROM edges").fetchall()
    )

    assert len(updates) == 2
    assert _reset_contents(skipping) == _reset_contents(plain)
    assert _reset_contents(skipping)[1] == (
        2,
        '{"callee_resolution": "unknown", "callee_resolved_file": ""}',
        "unknown",
        "",
        None,
    )
