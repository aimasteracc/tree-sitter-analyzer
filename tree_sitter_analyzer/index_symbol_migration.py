"""Non-destructive bounded migration of the ordinary symbol projection."""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable

from .index_symbol_projection import index_content_hash_sql as _index_content_hash_sql
from .index_symbol_projection import (
    projection_schema_columns as _projection_schema_columns,
)
from .index_symbol_projection import (
    symbol_rows_digest as _symbol_rows_digest,
)


def ensure_symbol_rows_backfilled(
    conn: sqlite3.Connection,
    *,
    seconds: float,
    row_budget: int,
    input_byte_budget: int,
    symbol_budget: int,
    cell_byte_budget: int,
    schema_byte_budget: int,
    marker_key: str,
    marker_value: str,
    exact_validator: Callable[..., bool],
    require_fts: bool,
) -> bool:
    """Certify legacy rows without ever replacing a non-empty projection.

    Existing ordinary rows are content-compared with ``symbols_json`` under the
    migration budgets.  Exact rows retain their IDs and every ID-based derived
    reference; partial rows are merely marked incomplete for the next index run.
    """
    deadline = time.monotonic() + seconds
    max_rows = row_budget
    max_input_bytes = input_byte_budget
    max_symbols = symbol_budget
    max_cell_bytes = cell_byte_budget
    rows_seen = input_bytes = symbols_seen = 0

    def check_budget() -> None:
        if (
            time.monotonic() > deadline
            or rows_seen > max_rows
            or input_bytes > max_input_bytes
            or symbols_seen > max_symbols
        ):
            raise sqlite3.OperationalError("LEGACY_SYMBOL_MIGRATION_BUDGET")

    def expired() -> int:
        return int(time.monotonic() > deadline)

    savepoint_started = False
    inserted_legacy_rows = False
    conn.set_progress_handler(expired, 1_000)
    try:
        conn.execute("SAVEPOINT ast_symbol_rows_upgrade")
        savepoint_started = True
        conn.execute(
            "CREATE TABLE IF NOT EXISTS ast_cache_metadata ("
            "key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        metadata_sql_length = conn.execute(
            "SELECT length(CAST(sql AS BLOB)) FROM sqlite_master "
            "WHERE type = 'table' AND name = 'ast_cache_metadata' LIMIT 1"
        ).fetchone()
        check_budget()
        if (
            metadata_sql_length is None
            or type(metadata_sql_length[0]) is not int
            or metadata_sql_length[0] > schema_byte_budget
        ):
            raise ValueError("invalid ast_cache_metadata schema")
        if _projection_schema_columns(conn, "ast_cache_metadata") != ("key", "value"):
            raise ValueError("invalid ast_cache_metadata schema")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS ast_symbol_rows ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, "
            "kind TEXT NOT NULL, file_path TEXT NOT NULL, language TEXT NOT NULL, "
            "line INTEGER NOT NULL DEFAULT 0, end_line INTEGER NOT NULL DEFAULT 0)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sym_rows_file_path "
            "ON ast_symbol_rows(file_path)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS ast_symbol_projection_state ("
            "file_path TEXT PRIMARY KEY, content_hash TEXT NOT NULL, "
            "symbol_count INTEGER NOT NULL CHECK(symbol_count >= 0), "
            "projection_digest TEXT NOT NULL)"
        )
        state_columns = _projection_schema_columns(conn, "ast_symbol_projection_state")
        if "projection_digest" not in state_columns:
            conn.execute(
                "ALTER TABLE ast_symbol_projection_state ADD COLUMN "
                "projection_digest TEXT NOT NULL DEFAULT ''"
            )
        marker_row = conn.execute(
            "SELECT 1, typeof(value)='text' AND value = ? "
            "FROM ast_cache_metadata WHERE key = ? LIMIT 1",
            (marker_value, marker_key),
        ).fetchone()
        check_budget()
        marker_key_present = marker_row is not None
        marker = (
            marker_row
            if marker_row is not None and tuple(marker_row) == (1, 1)
            else None
        )
        if marker is not None and exact_validator(
            conn,
            max_symbols,
            deadline=deadline,
            install_progress=False,
            require_fts=require_fts,
        ):
            conn.execute("RELEASE ast_symbol_rows_upgrade")
            savepoint_started = False
            return True

        hash_sql = _index_content_hash_sql(conn)
        hash_column = "content_hash" if hash_sql != "''" else "''"
        preflight = conn.execute(
            "SELECT length(CAST(file_path AS BLOB)), "
            "length(CAST(language AS BLOB)), length(CAST(symbols_json AS BLOB)), "
            f"length(CAST({hash_column} AS BLOB)) FROM ast_index"
        )
        while True:
            check_budget()
            length_row = preflight.fetchone()
            if length_row is None:
                break
            rows_seen += 1
            cell_lengths = tuple(length_row)
            if cell_lengths[2] is None:
                raise ValueError("invalid legacy symbols_json")
            if any(
                value is None
                for value in (cell_lengths[0], cell_lengths[1], cell_lengths[3])
            ):
                raise ValueError("invalid legacy symbol source row")
            if any(
                type(value) is not int or value > max_cell_bytes
                for value in cell_lengths
            ):
                raise sqlite3.OperationalError("LEGACY_SYMBOL_MIGRATION_BUDGET")
            input_bytes += sum(cell_lengths)
            check_budget()

        ordinary_count_row = conn.execute(
            "SELECT COUNT(*) FROM ast_symbol_rows"
        ).fetchone()
        if (
            ordinary_count_row is None
            or type(ordinary_count_row[0]) is not int
            or ordinary_count_row[0] < 0
            or ordinary_count_row[0] > max_symbols
        ):
            raise sqlite3.OperationalError("LEGACY_SYMBOL_MIGRATION_BUDGET")
        ordinary_empty = ordinary_count_row[0] == 0
        ordinary_preflight = conn.execute(
            "SELECT length(CAST(name AS BLOB)), length(CAST(kind AS BLOB)), "
            "length(CAST(file_path AS BLOB)), length(CAST(language AS BLOB)), "
            "typeof(line), typeof(end_line) FROM ast_symbol_rows ORDER BY file_path, id"
        )
        ordinary_seen = 0
        while True:
            check_budget()
            ordinary_lengths = ordinary_preflight.fetchone()
            if ordinary_lengths is None:
                break
            ordinary_seen += 1
            lengths = tuple(ordinary_lengths[:4])
            if any(
                type(value) is not int or value > max_cell_bytes for value in lengths
            ) or tuple(ordinary_lengths[4:]) != ("integer", "integer"):
                raise ValueError("invalid ordinary symbol row")
            input_bytes += sum(lengths)
            check_budget()
        if ordinary_seen != ordinary_count_row[0]:
            raise sqlite3.OperationalError("LEGACY_SYMBOL_MIGRATION_BUDGET")
        state_count_row = conn.execute(
            "SELECT COUNT(*) FROM ast_symbol_projection_state"
        ).fetchone()
        if state_count_row is None or type(state_count_row[0]) is not int:
            raise sqlite3.OperationalError("LEGACY_SYMBOL_MIGRATION_BUDGET")
        allow_legacy_insert = (
            ordinary_empty and not marker_key_present and state_count_row[0] == 0
        )
        ordinary_cursor = (
            None
            if ordinary_empty
            else conn.execute(
                "SELECT name, kind, file_path, language, line, end_line "
                "FROM ast_symbol_rows ORDER BY file_path, id"
            )
        )
        content_exact = not ordinary_empty
        state_rows: list[tuple[str, str, int]] = []
        cursor = conn.execute(
            f"SELECT file_path, language, symbols_json, {hash_column} "
            "FROM ast_index ORDER BY file_path"
        )
        materialized_rows = 0
        while True:
            check_budget()
            row = cursor.fetchone()
            if row is None:
                break
            file_path, language, raw_symbols, content_hash = row
            materialized_rows += 1
            if materialized_rows > rows_seen:
                raise sqlite3.OperationalError("LEGACY_SYMBOL_MIGRATION_BUDGET")
            materialized = (file_path, language, raw_symbols, content_hash)
            if not isinstance(raw_symbols, (bytes, str)):
                raise ValueError("invalid legacy symbols_json")
            if any(
                not isinstance(value, (bytes, str))
                for value in (file_path, language, content_hash)
            ):
                raise ValueError("invalid legacy symbol source row")
            cell_lengths = tuple(
                len(value)
                if isinstance(value, bytes)
                else len(value.encode("utf-8", "surrogatepass"))
                for value in materialized
            )
            if any(length > max_cell_bytes for length in cell_lengths):
                raise sqlite3.OperationalError("LEGACY_SYMBOL_MIGRATION_BUDGET")
            parsed = json.loads(raw_symbols)
            symbols = parsed.get("symbols", []) if isinstance(parsed, dict) else []
            if not isinstance(symbols, list):
                raise ValueError("invalid legacy symbols_json")
            symbols_seen += len(symbols)
            check_budget()
            state_rows.append((file_path, content_hash, len(symbols)))
            for offset in range(0, len(symbols), 512):
                check_budget()
                params: list[tuple[str, str, str, str, int, int]] = []
                for symbol in symbols[offset : offset + 512]:
                    if not isinstance(symbol, dict):
                        raise ValueError("invalid legacy symbol row")
                    expected = (
                        symbol.get("name") or symbol.get("text", ""),
                        symbol.get("kind", "unknown"),
                        file_path,
                        language,
                        symbol.get("line", 0),
                        symbol.get("end_line", 0),
                    )
                    if (
                        any(not isinstance(value, str) for value in expected[:4])
                        or type(expected[4]) is not int
                        or type(expected[5]) is not int
                    ):
                        raise ValueError("invalid legacy symbol row")
                    params.append(expected)
                    if ordinary_cursor is not None:
                        actual = ordinary_cursor.fetchone()
                        if (
                            actual is None
                            or tuple(actual) != expected
                            or any(
                                type(actual[index]) is not type(expected[index])
                                for index in range(6)
                            )
                        ):
                            content_exact = False
                if allow_legacy_insert:
                    conn.executemany(
                        "INSERT INTO ast_symbol_rows "
                        "(name, kind, file_path, language, line, end_line) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        params,
                    )
                check_budget()
        if materialized_rows != rows_seen:
            raise sqlite3.OperationalError("LEGACY_SYMBOL_MIGRATION_BUDGET")
        if ordinary_cursor is not None and ordinary_cursor.fetchone() is not None:
            content_exact = False
        if ordinary_empty:
            content_exact = symbols_seen == 0 or allow_legacy_insert

        if not content_exact:
            # Never delete/reinsert a partial projection: IDs may already be used
            # by activation rows, FTS rowids, and resolved call-edge metadata.
            conn.execute("DELETE FROM ast_symbol_projection_state")
            conn.execute(
                "DELETE FROM ast_cache_metadata WHERE key = ?",
                (marker_key,),
            )
            conn.execute("RELEASE ast_symbol_rows_upgrade")
            savepoint_started = False
            return False

        inserted_legacy_rows = allow_legacy_insert and symbols_seen > 0
        if allow_legacy_insert:
            fts = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='ast_symbols_fts'"
            ).fetchone()
            if fts is not None:
                conn.execute(
                    "INSERT INTO ast_symbols_fts(ast_symbols_fts) VALUES('delete-all')"
                )
                conn.execute(
                    "INSERT INTO ast_symbols_fts(rowid, name, kind, file_path, language) "
                    "SELECT id, name, kind, file_path, language "
                    "FROM ast_symbol_rows ORDER BY id"
                )
        conn.execute("DELETE FROM ast_symbol_projection_state")
        for file_path, content_hash, symbol_count in state_rows:
            check_budget()
            digest_rows = conn.execute(
                "SELECT id, name, kind, file_path, language, line, end_line "
                "FROM ast_symbol_rows WHERE file_path = ? ORDER BY id",
                (file_path,),
            )
            projection_digest = _symbol_rows_digest(digest_rows, check_budget)
            check_budget()
            conn.execute(
                "INSERT INTO ast_symbol_projection_state "
                "(file_path, content_hash, symbol_count, projection_digest) "
                "VALUES (?, ?, ?, ?)",
                (file_path, content_hash, symbol_count, projection_digest),
            )
        conn.execute(
            "INSERT INTO ast_cache_metadata (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (marker_key, marker_value),
        )
        if not exact_validator(
            conn,
            max_symbols,
            deadline=deadline,
            install_progress=False,
            require_fts=require_fts,
        ):
            raise sqlite3.OperationalError("LEGACY_SYMBOL_PROJECTION_INVALID")
        conn.execute("RELEASE ast_symbol_rows_upgrade")
        savepoint_started = False
        if inserted_legacy_rows:
            from .cache.callgraph_state import clear_call_graph_built_strict

            clear_call_graph_built_strict(conn)
        return True
    except Exception as exc:
        conn.set_progress_handler(None, 0)
        if savepoint_started:
            conn.execute("ROLLBACK TO ast_symbol_rows_upgrade")
            conn.execute("RELEASE ast_symbol_rows_upgrade")
        if isinstance(exc, sqlite3.OperationalError) and (
            time.monotonic() > deadline or "interrupt" in str(exc).lower()
        ):
            raise sqlite3.OperationalError("LEGACY_SYMBOL_MIGRATION_BUDGET") from exc
        raise
    finally:
        conn.set_progress_handler(None, 0)
