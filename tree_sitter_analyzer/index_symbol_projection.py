"""Bounded SQL verification for the ordinary symbol projection."""

from __future__ import annotations

import hashlib
import sqlite3
import struct
import time
from collections.abc import Iterable
from typing import Any

_PROJECTION_SECONDS = 5.0
_PROJECTION_CELL_BYTE_BUDGET = 1024 * 1024
_PROJECTION_TOTAL_BYTE_BUDGET = 256 * 1024 * 1024


def projection_schema_columns(conn: sqlite3.Connection, table: str) -> tuple[str, ...]:
    """Read one small, trusted projection schema under the caller's deadline."""
    return tuple(str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})"))


def sqlite_compile_supports_fts5(conn: sqlite3.Connection) -> bool | None:
    """Read the connection's compile capability without probing or writing."""
    try:
        row = conn.execute("SELECT sqlite_compileoption_used('ENABLE_FTS5')").fetchone()
    except sqlite3.DatabaseError:
        return None
    if row is None or len(row) != 1 or type(row[0]) is not int or row[0] not in (0, 1):
        return None
    return bool(row[0])


def index_content_hash_sql(conn: sqlite3.Connection) -> str:
    """Return the generation expression, supporting pre-hash test fixtures."""
    try:
        conn.execute("SELECT content_hash FROM ast_index LIMIT 0")
    except sqlite3.OperationalError as exc:
        if "no such column" not in str(exc).lower():
            raise
        return "''"
    return "source.content_hash"


def delete_projection_state_if_present(conn: sqlite3.Connection, rel_path: str) -> None:
    """Delete state while tolerating pre-projection compatibility fixtures."""
    try:
        conn.execute(
            "DELETE FROM ast_symbol_projection_state WHERE file_path = ?", (rel_path,)
        )
    except sqlite3.OperationalError as exc:
        if "no such table" not in str(exc).lower():
            raise


def delete_fts_rows(
    conn: sqlite3.Connection,
    rel_path: str,
) -> None:
    """Delete one externally backed FTS generation using its old payload."""
    schema = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='ast_symbols_fts'"
    ).fetchone()
    externally_backed = bool(
        schema is not None
        and isinstance(schema[0], str)
        and "content='ast_symbol_rows'" in schema[0]
    )
    if not externally_backed:
        conn.execute("DELETE FROM ast_symbols_fts WHERE file_path = ?", (rel_path,))
        return
    old_rows = conn.execute(
        "SELECT id, name, kind, file_path, language FROM ast_symbol_rows "
        "WHERE file_path = ? ORDER BY id",
        (rel_path,),
    ).fetchall()
    try:
        for row in old_rows:
            conn.execute(
                "INSERT INTO ast_symbols_fts"
                "(ast_symbols_fts, rowid, name, kind, file_path, language) "
                "VALUES('delete', ?, ?, ?, ?, ?)",
                tuple(row),
            )
    except sqlite3.DatabaseError as exc:
        # A missing/corrupt FTS row is precisely what projection repair is
        # replacing.  Ordinary rows remain authoritative and the full repair
        # rebuilds FTS from them before certification.
        if "malformed" not in str(exc).lower():
            raise


def _typed(values: Iterable[Any]) -> bytes:
    """Encode SQLite scalars without ambiguous concatenation or Python hash()."""
    result = bytearray()
    for value in values:
        if value is None:
            tag, raw = b"n", b""
        elif isinstance(value, bytes):
            tag, raw = b"b", value
        elif type(value) is int:
            tag, raw = b"i", str(value).encode("ascii")
        elif isinstance(value, float):
            tag, raw = b"f", struct.pack(">d", value)
        elif isinstance(value, str):
            tag, raw = b"t", value.encode("utf-8", "surrogatepass")
        else:
            raise ValueError("invalid ordinary symbol scalar")
        result.extend(tag)
        result.extend(len(raw).to_bytes(8, "big"))
        result.extend(raw)
    return bytes(result)


def symbol_rows_digest(rows: Iterable[Iterable[Any]], check: Any | None = None) -> str:
    """Digest complete query-visible ordinary rows in their canonical ID order."""
    digest = hashlib.sha256(b"tsa-symbol-projection-v1\0")
    for row in rows:
        if check is not None:
            check()
        encoded = _typed(row)
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return "sha256:" + digest.hexdigest()


def upsert_symbol_projection_state(conn: sqlite3.Connection, rel_path: str) -> None:
    """Bind ordinary rows and their full payload to the ast_index generation."""
    table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='ast_symbol_projection_state'"
    ).fetchone()
    if table is None:
        return
    source = conn.execute(
        "SELECT content_hash FROM ast_index WHERE file_path = ?", (rel_path,)
    ).fetchone()
    if source is None:
        conn.execute(
            "DELETE FROM ast_symbol_projection_state WHERE file_path = ?", (rel_path,)
        )
        return
    rows = conn.execute(
        "SELECT id, name, kind, file_path, language, line, end_line "
        "FROM ast_symbol_rows WHERE file_path = ? ORDER BY id",
        (rel_path,),
    ).fetchall()
    digest = symbol_rows_digest(rows)
    conn.execute(
        "INSERT INTO ast_symbol_projection_state "
        "(file_path, content_hash, symbol_count, projection_digest) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(file_path) DO UPDATE SET content_hash=excluded.content_hash, "
        "symbol_count=excluded.symbol_count, projection_digest=excluded.projection_digest",
        (rel_path, source[0], len(rows), digest),
    )


def symbol_projection_is_exact(
    conn: sqlite3.Connection,
    max_symbols: int = 2_000_000,
    *,
    deadline: float | None = None,
    install_progress: bool = True,
    require_fts: bool = False,
) -> bool:
    """Boundedly verify ordinary rows and, when required, the exact FTS projection."""
    expires_at = (
        time.monotonic() + _PROJECTION_SECONDS if deadline is None else deadline
    )
    rows_seen = bytes_seen = 0

    def check_budget() -> None:
        if (
            time.monotonic() > expires_at
            or rows_seen > max_symbols
            or bytes_seen > _PROJECTION_TOTAL_BYTE_BUDGET
        ):
            raise sqlite3.OperationalError("SYMBOL_PROJECTION_BUDGET")

    def expired() -> int:
        return int(time.monotonic() > expires_at)

    if install_progress:
        conn.set_progress_handler(expired, 1_000)
    try:
        check_budget()
        conn.execute("SELECT file_path, symbols_json FROM ast_index LIMIT 0")
        row_columns = set(projection_schema_columns(conn, "ast_symbol_rows"))
        state_columns = projection_schema_columns(conn, "ast_symbol_projection_state")
        metadata_columns = projection_schema_columns(conn, "ast_cache_metadata")
        if require_fts:
            fts_columns = projection_schema_columns(conn, "ast_symbols_fts")
            if fts_columns != ("name", "kind", "file_path", "language"):
                return False
            fts_schema = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' "
                "AND name='ast_symbols_fts'"
            ).fetchone()
            if (
                fts_schema is None
                or type(fts_schema[0]) is not str
                or "content='ast_symbol_rows'" not in fts_schema[0]
                or "content_rowid='id'" not in fts_schema[0]
            ):
                return False
        if not {
            "id",
            "file_path",
            "name",
            "kind",
            "language",
            "line",
            "end_line",
        }.issubset(row_columns):
            return False
        if state_columns != (
            "file_path",
            "content_hash",
            "symbol_count",
            "projection_digest",
        ):
            return False
        if metadata_columns != ("key", "value"):
            return False
        marker = conn.execute(
            "SELECT COUNT(*), COUNT(*) FILTER (WHERE typeof(key)='text' "
            "AND typeof(value)='text' AND value='complete') FROM ast_cache_metadata "
            "WHERE key='symbol_rows_projection_v1'"
        ).fetchone()
        if (
            marker is None
            or any(type(v) is not int for v in marker)
            or tuple(marker) != (1, 1)
        ):
            return False
        hash_sql = index_content_hash_sql(conn)
        checks = (
            "SELECT 1 FROM ast_index AS source LEFT JOIN ast_symbol_projection_state "
            "AS state ON state.file_path=source.file_path WHERE "
            f"typeof(source.file_path)!='text' OR state.file_path IS NULL OR state.content_hash IS NOT {hash_sql} LIMIT 1",
            "SELECT 1 FROM ast_symbol_projection_state AS state LEFT JOIN ast_index "
            "AS source ON source.file_path=state.file_path WHERE source.file_path IS NULL LIMIT 1",
            "SELECT 1 FROM ast_symbol_projection_state WHERE typeof(file_path)!='text' "
            "OR typeof(content_hash)!='text' OR typeof(symbol_count)!='integer' "
            f"OR symbol_count < 0 OR symbol_count > {max_symbols} "
            "OR typeof(projection_digest)!='text' OR length(projection_digest)!=71 "
            "OR projection_digest NOT GLOB 'sha256:[0-9a-f]*' LIMIT 1",
            "SELECT 1 FROM ast_symbol_rows AS rows LEFT JOIN ast_symbol_projection_state "
            "AS state ON state.file_path=rows.file_path WHERE state.file_path IS NULL "
            "OR typeof(rows.file_path)!='text' LIMIT 1",
        )
        if any(conn.execute(query).fetchone() is not None for query in checks):
            return False
        if require_fts:
            count_row = conn.execute(
                "SELECT (SELECT COUNT(*) FROM ast_symbol_rows), "
                "(SELECT COUNT(*) FROM ast_symbols_fts_docsize)"
            ).fetchone()
            if (
                count_row is None
                or any(type(value) is not int for value in count_row)
                or count_row[0] != count_row[1]
                or count_row[0] > max_symbols
            ):
                return False
            fts_checks = (
                "SELECT 1 FROM ast_symbol_rows AS rows LEFT JOIN "
                "ast_symbols_fts_docsize AS docs ON docs.id=rows.id "
                "WHERE docs.id IS NULL LIMIT 1",
                "SELECT 1 FROM ast_symbols_fts_docsize AS docs LEFT JOIN "
                "ast_symbol_rows AS rows ON rows.id=docs.id "
                "WHERE rows.id IS NULL LIMIT 1",
                "SELECT 1 FROM ast_symbols_fts AS f JOIN ast_symbol_rows AS rows "
                "ON rows.id=f.rowid WHERE f.name IS NOT rows.name "
                "OR f.kind IS NOT rows.kind OR f.file_path IS NOT rows.file_path "
                "OR f.language IS NOT rows.language LIMIT 1",
            )
            if any(conn.execute(query).fetchone() is not None for query in fts_checks):
                return False
        states = conn.execute(
            "SELECT file_path, symbol_count, projection_digest "
            "FROM ast_symbol_projection_state ORDER BY file_path"
        )
        for state in states:
            check_budget()
            file_path, expected_count, expected_digest = state
            if (
                type(file_path) is not str
                or type(expected_count) is not int
                or type(expected_digest) is not str
            ):
                return False
            cursor = conn.execute(
                "SELECT id, name, kind, file_path, language, line, end_line, "
                "length(CAST(name AS BLOB)), length(CAST(kind AS BLOB)), "
                "length(CAST(file_path AS BLOB)), length(CAST(language AS BLOB)) "
                "FROM ast_symbol_rows WHERE file_path = ? ORDER BY id",
                (file_path,),
            )
            digest = hashlib.sha256(b"tsa-symbol-projection-v1\0")
            file_count = 0
            while True:
                check_budget()
                row = cursor.fetchone()
                if row is None:
                    break
                values, lengths = tuple(row[:7]), tuple(row[7:])
                if (
                    type(values[0]) is not int
                    or any(type(value) is not str for value in values[1:5])
                    or type(values[5]) is not int
                    or type(values[6]) is not int
                    or any(
                        type(length) is not int or length > _PROJECTION_CELL_BYTE_BUDGET
                        for length in lengths
                    )
                ):
                    return False
                encoded = _typed(values)
                file_count += 1
                rows_seen += 1
                bytes_seen += sum(lengths) + len(encoded)
                check_budget()
                digest.update(len(encoded).to_bytes(8, "big"))
                digest.update(encoded)
            if (
                file_count != expected_count
                or "sha256:" + digest.hexdigest() != expected_digest
            ):
                return False
        return True
    except (sqlite3.DatabaseError, UnicodeError, ValueError, OverflowError):
        return False
    finally:
        if install_progress:
            conn.set_progress_handler(None, 0)
