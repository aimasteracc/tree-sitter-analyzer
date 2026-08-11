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
_ORDINARY_DEADLINE_SECONDS = 5.0
_ORDINARY_ROW_BUDGET = 2_000_000
_ORDINARY_GROUP_BUDGET = 4096
_ORDINARY_CELL_BYTE_BUDGET = 1024 * 1024
_ORDINARY_OUTPUT_BYTE_BUDGET = 4 * 1024 * 1024


def has_ordinary_symbol_projection(conn: sqlite3.Connection, tables: set[str]) -> bool:
    """Return whether canonical symbol rows contain the status query columns."""
    if "ast_symbol_rows" not in tables:
        return False
    columns = {
        str(row[1]) for row in conn.execute("PRAGMA table_info(ast_symbol_rows)")
    }
    return {"name", "kind", "language", "file_path"}.issubset(columns)


def ordinary_symbol_counts(
    conn: sqlite3.Connection,
) -> tuple[int, dict[str, int], dict[str, int]]:
    """Aggregate canonical rows within fixed SQLite and output budgets."""
    deadline = time.monotonic() + _ORDINARY_DEADLINE_SECONDS
    output_bytes = 0

    def check_deadline() -> None:
        if time.monotonic() > deadline:
            raise RuntimeError("SNAPSHOT_READ_FAILED")

    def expired() -> int:
        return int(time.monotonic() > deadline)

    def grouped(column: str) -> dict[str, int]:
        nonlocal output_bytes
        result: dict[str, int] = {}
        groups = 0
        # CASE prevents an oversized key from crossing the SQLite/Python boundary.
        cursor = conn.execute(
            f"SELECT length(CAST({column} AS BLOB)), "
            f"CASE WHEN length(CAST({column} AS BLOB)) <= ? THEN {column} END, "
            f"COUNT(*) FROM ast_symbol_rows GROUP BY {column} ORDER BY {column}",
            (_ORDINARY_CELL_BYTE_BUDGET,),
        )
        while True:
            check_deadline()
            row = cursor.fetchone()
            if row is None:
                break
            groups += 1
            if groups > _ORDINARY_GROUP_BUDGET:
                raise RuntimeError("SNAPSHOT_READ_FAILED")
            cell_bytes, key, count = row
            if (
                not isinstance(cell_bytes, int)
                or cell_bytes > _ORDINARY_CELL_BYTE_BUDGET
                or not isinstance(key, str)
                or not isinstance(count, int)
                or count < 0
                or count > _ORDINARY_ROW_BUDGET
            ):
                raise RuntimeError("SNAPSHOT_READ_FAILED")
            output_bytes += cell_bytes + len(str(count).encode("ascii"))
            if output_bytes > _ORDINARY_OUTPUT_BYTE_BUDGET:
                raise RuntimeError("SNAPSHOT_READ_FAILED")
            result[key] = count
        return result

    conn.set_progress_handler(expired, 1_000)
    try:
        check_deadline()
        row = conn.execute("SELECT COUNT(*) FROM ast_symbol_rows").fetchone()
        check_deadline()
        if (
            row is None
            or not isinstance(row[0], int)
            or row[0] < 0
            or row[0] > _ORDINARY_ROW_BUDGET
        ):
            raise RuntimeError("SNAPSHOT_READ_FAILED")
        return row[0], grouped("kind"), grouped("language")
    except sqlite3.OperationalError as exc:
        raise RuntimeError("SNAPSHOT_READ_FAILED") from exc
    finally:
        conn.set_progress_handler(None, 0)


def ordinary_edge_counts(conn: sqlite3.Connection) -> tuple[int, dict[str, int]]:
    """Aggregate edge kinds under the ordinary snapshot read budgets."""
    deadline = time.monotonic() + _ORDINARY_DEADLINE_SECONDS
    output_bytes = 0

    def check_deadline() -> None:
        if time.monotonic() > deadline:
            raise RuntimeError("SNAPSHOT_READ_FAILED")

    def expired() -> int:
        return int(time.monotonic() > deadline)

    conn.set_progress_handler(expired, 1_000)
    try:
        check_deadline()
        total_row = conn.execute("SELECT COUNT(*) FROM edges").fetchone()
        check_deadline()
        if (
            total_row is None
            or not isinstance(total_row[0], int)
            or total_row[0] < 0
            or total_row[0] > _ORDINARY_ROW_BUDGET
        ):
            raise RuntimeError("SNAPSHOT_READ_FAILED")

        result: dict[str, int] = {}
        cursor = conn.execute(
            "SELECT length(CAST(kind AS BLOB)), "
            "CASE WHEN length(CAST(kind AS BLOB)) <= ? THEN kind END, "
            "COUNT(*) FROM edges GROUP BY kind ORDER BY kind",
            (_ORDINARY_CELL_BYTE_BUDGET,),
        )
        groups = 0
        while True:
            check_deadline()
            row = cursor.fetchone()
            check_deadline()
            if row is None:
                break
            groups += 1
            if groups > _ORDINARY_GROUP_BUDGET:
                raise RuntimeError("SNAPSHOT_READ_FAILED")
            cell_bytes, key, count = row
            if (
                not isinstance(cell_bytes, int)
                or cell_bytes < 0
                or cell_bytes > _ORDINARY_CELL_BYTE_BUDGET
                or not isinstance(key, str)
                or not isinstance(count, int)
                or count < 0
                or count > _ORDINARY_ROW_BUDGET
            ):
                raise RuntimeError("SNAPSHOT_READ_FAILED")
            output_bytes += cell_bytes + len(str(count).encode("ascii"))
            if output_bytes > _ORDINARY_OUTPUT_BYTE_BUDGET:
                raise RuntimeError("SNAPSHOT_READ_FAILED")
            result[key] = count
        return total_row[0], result
    except (sqlite3.DatabaseError, UnicodeError, ValueError, OverflowError) as exc:
        raise RuntimeError("SNAPSHOT_READ_FAILED") from exc
    finally:
        conn.set_progress_handler(None, 0)


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
    rows_seen = bytes_seen = total = output_bytes = 0
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

    def increment_group(target: dict[str, int], key: str) -> None:
        nonlocal output_bytes
        key_bytes = len(key.encode("utf-8", "surrogatepass"))
        if key_bytes > _ORDINARY_CELL_BYTE_BUDGET:
            raise RuntimeError("INDEX_SYMBOL_FALLBACK_BUDGET")
        previous = target.get(key)
        if previous is None:
            if len(target) >= _ORDINARY_GROUP_BUDGET:
                raise RuntimeError("INDEX_SYMBOL_FALLBACK_BUDGET")
            next_count = 1
            added_bytes = key_bytes + 1
        else:
            next_count = previous + 1
            added_bytes = len(str(next_count)) - len(str(previous))
        if output_bytes + added_bytes > _ORDINARY_OUTPUT_BYTE_BUDGET:
            raise RuntimeError("INDEX_SYMBOL_FALLBACK_BUDGET")
        output_bytes += added_bytes
        target[key] = next_count

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
                increment_group(by_kind, kind)
                increment_group(by_language, language)
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
_LEGACY_SYMBOL_MIGRATION_SCHEMA_BYTE_BUDGET = 4096
_LEGACY_SYMBOL_MIGRATION_MARKER = "symbol_rows_projection_v1"
_LEGACY_SYMBOL_MIGRATION_MARKER_VALUE = "complete"


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

    def expired() -> int:
        return int(time.monotonic() > deadline)

    savepoint_started = False
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
            or not isinstance(metadata_sql_length[0], int)
            or metadata_sql_length[0] > _LEGACY_SYMBOL_MIGRATION_SCHEMA_BYTE_BUDGET
        ):
            raise ValueError("invalid ast_cache_metadata schema")
        metadata_columns = tuple(
            row[1] for row in conn.execute("PRAGMA table_info(ast_cache_metadata)")
        )
        check_budget()
        if metadata_columns != ("key", "value"):
            raise ValueError("invalid ast_cache_metadata schema")
        marker = conn.execute(
            "SELECT 1 FROM ast_cache_metadata WHERE key = ? AND value = ? LIMIT 1",
            (
                _LEGACY_SYMBOL_MIGRATION_MARKER,
                _LEGACY_SYMBOL_MIGRATION_MARKER_VALUE,
            ),
        ).fetchone()
        check_budget()
        if marker is not None:
            conn.execute("RELEASE ast_symbol_rows_upgrade")
            savepoint_started = False
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
            (
                _LEGACY_SYMBOL_MIGRATION_MARKER,
                _LEGACY_SYMBOL_MIGRATION_MARKER_VALUE,
            ),
        )
        conn.execute("RELEASE ast_symbol_rows_upgrade")
        savepoint_started = False
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
