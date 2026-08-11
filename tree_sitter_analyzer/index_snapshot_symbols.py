"""Bounded legacy symbol aggregation for index snapshot readers."""

from __future__ import annotations

import json
import sqlite3
import time

_FALLBACK_BYTE_BUDGET = 256 * 1024 * 1024
_FALLBACK_SYMBOL_BUDGET = 2_000_000
_FALLBACK_INPUT_ROW_BUDGET = 250_000
_FALLBACK_CELL_BYTE_BUDGET = 1024 * 1024
_FALLBACK_DEADLINE_SECONDS = 5.0


def has_ordinary_symbol_projection(conn: sqlite3.Connection, tables: set[str]) -> bool:
    """Return whether canonical symbol rows contain the status query columns."""
    if "ast_symbol_rows" not in tables:
        return False
    columns = {
        str(row[1]) for row in conn.execute("PRAGMA table_info(ast_symbol_rows)")
    }
    return {"name", "kind", "language", "file_path"}.issubset(columns)


def fallback_symbol_counts(
    conn: sqlite3.Connection,
) -> tuple[int, dict[str, int], dict[str, int]]:
    """Count legacy symbols without materializing an unbounded JSON cell."""
    byte_budget = _FALLBACK_BYTE_BUDGET
    symbol_budget = _FALLBACK_SYMBOL_BUDGET
    input_row_budget = _FALLBACK_INPUT_ROW_BUDGET
    cell_byte_budget = _FALLBACK_CELL_BYTE_BUDGET
    deadline_seconds = _FALLBACK_DEADLINE_SECONDS
    deadline = time.monotonic() + deadline_seconds
    rows_seen = bytes_seen = total = 0
    by_kind: dict[str, int] = {}
    by_language: dict[str, int] = {}

    def check_budget() -> None:
        if (
            time.monotonic() > deadline
            or rows_seen > input_row_budget
            or bytes_seen > byte_budget
            or total > symbol_budget
        ):
            raise RuntimeError("INDEX_SYMBOL_FALLBACK_BUDGET")

    def expired() -> int:
        return int(time.monotonic() > deadline)

    conn.set_progress_handler(expired, 1_000)
    try:
        # SQLite computes BLOB lengths without transferring the potentially large
        # values into Python.  Reject every oversized cell before json.loads.
        preflight = conn.execute(
            "SELECT length(CAST(symbols_json AS BLOB)), "
            "length(CAST(language AS BLOB)) FROM ast_index ORDER BY file_path"
        )
        while True:
            check_budget()
            length_row = preflight.fetchone()
            if length_row is None:
                break
            rows_seen += 1
            lengths = tuple(length_row)
            if any(value is None or not isinstance(value, int) for value in lengths):
                raise ValueError("CORRUPT_INDEX")
            if any(value > cell_byte_budget for value in lengths):
                raise RuntimeError("INDEX_SYMBOL_FALLBACK_BUDGET")
            bytes_seen += sum(lengths)
            check_budget()

        cursor = conn.execute(
            "SELECT symbols_json, language FROM ast_index ORDER BY file_path"
        )
        while True:
            check_budget()
            row = cursor.fetchone()
            if row is None:
                break
            raw, language_value = row
            if not isinstance(raw, (bytes, str)) or not isinstance(
                language_value, (bytes, str)
            ):
                raise ValueError("CORRUPT_INDEX")
            payload = json.loads(raw)
            check_budget()
            symbols = payload.get("symbols", []) if isinstance(payload, dict) else []
            if not isinstance(symbols, list):
                raise ValueError("CORRUPT_INDEX")
            language = (
                language_value.decode("utf-8", errors="replace")
                if isinstance(language_value, bytes)
                else language_value
            )
            total += len(symbols)
            check_budget()
            for index, symbol in enumerate(symbols):
                if index % 512 == 0:
                    check_budget()
                kind = (
                    str(symbol.get("kind", "unknown"))
                    if isinstance(symbol, dict)
                    else "unknown"
                )
                by_kind[kind] = by_kind.get(kind, 0) + 1
                by_language[language] = by_language.get(language, 0) + 1
        return total, dict(sorted(by_kind.items())), dict(sorted(by_language.items()))
    except sqlite3.OperationalError as exc:
        if time.monotonic() > deadline or "interrupt" in str(exc).lower():
            raise RuntimeError("INDEX_SYMBOL_FALLBACK_BUDGET") from exc
        raise
    finally:
        conn.set_progress_handler(None, 0)


_LEGACY_SYMBOL_MIGRATION_SECONDS = 5.0
_LEGACY_SYMBOL_MIGRATION_ROW_BUDGET = 250_000
_LEGACY_SYMBOL_MIGRATION_INPUT_BYTE_BUDGET = 256 * 1024 * 1024
_LEGACY_SYMBOL_MIGRATION_SYMBOL_BUDGET = 2_000_000
_LEGACY_SYMBOL_MIGRATION_CELL_BYTE_BUDGET = 1024 * 1024
_LEGACY_SYMBOL_MIGRATION_MARKER = "symbol_rows_projection_v1"


def ensure_symbol_rows_backfilled(conn: sqlite3.Connection) -> None:
    """Create symbol storage and migrate legacy JSON within absolute budgets."""
    deadline = time.monotonic() + _LEGACY_SYMBOL_MIGRATION_SECONDS
    max_rows = _LEGACY_SYMBOL_MIGRATION_ROW_BUDGET
    max_input_bytes = _LEGACY_SYMBOL_MIGRATION_INPUT_BYTE_BUDGET
    max_symbols = _LEGACY_SYMBOL_MIGRATION_SYMBOL_BUDGET
    max_cell_bytes = _LEGACY_SYMBOL_MIGRATION_CELL_BYTE_BUDGET
    rows_seen = input_bytes = symbols_seen = 0

    def check_budget() -> None:
        if (
            time.monotonic() > deadline
            or rows_seen > max_rows
            or input_bytes > max_input_bytes
            or symbols_seen > max_symbols
        ):
            raise sqlite3.OperationalError("LEGACY_SYMBOL_MIGRATION_BUDGET")

    conn.execute("SAVEPOINT ast_symbol_rows_upgrade")
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS ast_cache_metadata ("
            "key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        marker = conn.execute(
            "SELECT value FROM ast_cache_metadata WHERE key = ?",
            (_LEGACY_SYMBOL_MIGRATION_MARKER,),
        ).fetchone()
        if marker is not None:
            conn.execute("RELEASE ast_symbol_rows_upgrade")
            return
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
        missing_rows = (
            " FROM ast_index AS source WHERE NOT EXISTS "
            "(SELECT 1 FROM ast_symbol_rows AS symbols "
            "WHERE symbols.file_path = source.file_path)"
        )

        def expired() -> int:
            return int(time.monotonic() > deadline)

        conn.set_progress_handler(expired, 1_000)
        preflight = conn.execute(
            "SELECT length(CAST(file_path AS BLOB)), "
            "length(CAST(language AS BLOB)), "
            "length(CAST(symbols_json AS BLOB))" + missing_rows
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
            if any(value is None for value in cell_lengths[:2]):
                raise ValueError("invalid legacy symbol source row")
            if any(
                not isinstance(value, int) or value > max_cell_bytes
                for value in cell_lengths
            ):
                raise sqlite3.OperationalError("LEGACY_SYMBOL_MIGRATION_BUDGET")
            input_bytes += sum(cell_lengths)
            check_budget()

        cursor = conn.execute("SELECT file_path, language, symbols_json" + missing_rows)
        materialized_rows = 0
        while True:
            check_budget()
            row = cursor.fetchone()
            if row is None:
                break
            file_path, language, raw_symbols = row
            materialized_rows += 1
            if materialized_rows > rows_seen:
                raise sqlite3.OperationalError("LEGACY_SYMBOL_MIGRATION_BUDGET")
            materialized = (file_path, language, raw_symbols)
            if not isinstance(raw_symbols, (bytes, str)):
                raise ValueError("invalid legacy symbols_json")
            if any(not isinstance(value, (bytes, str)) for value in materialized[:2]):
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
            check_budget()
            symbols = parsed.get("symbols", []) if isinstance(parsed, dict) else []
            if not isinstance(symbols, list):
                raise ValueError("invalid legacy symbols_json")
            symbols_seen += len(symbols)
            check_budget()
            for offset in range(0, len(symbols), 512):
                check_budget()
                params = []
                for symbol in symbols[offset : offset + 512]:
                    if not isinstance(symbol, dict):
                        raise ValueError("invalid legacy symbol row")
                    params.append(
                        (
                            symbol.get("name") or symbol.get("text", ""),
                            symbol.get("kind", "unknown"),
                            file_path,
                            language,
                            symbol.get("line", 0),
                            symbol.get("end_line", 0),
                        )
                    )
                conn.executemany(
                    "INSERT INTO ast_symbol_rows "
                    "(name, kind, file_path, language, line, end_line) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    params,
                )
                check_budget()
        conn.execute(
            "INSERT INTO ast_cache_metadata (key, value) VALUES (?, ?)",
            (_LEGACY_SYMBOL_MIGRATION_MARKER, "complete"),
        )
        conn.set_progress_handler(None, 0)
        conn.execute("RELEASE ast_symbol_rows_upgrade")
    except Exception as exc:
        conn.set_progress_handler(None, 0)
        conn.execute("ROLLBACK TO ast_symbol_rows_upgrade")
        conn.execute("RELEASE ast_symbol_rows_upgrade")
        if isinstance(exc, sqlite3.OperationalError) and (
            time.monotonic() > deadline or "interrupt" in str(exc).lower()
        ):
            raise sqlite3.OperationalError("LEGACY_SYMBOL_MIGRATION_BUDGET") from exc
        raise
