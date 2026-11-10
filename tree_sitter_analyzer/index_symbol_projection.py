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


def _fts_terms_are_exact(conn: sqlite3.Connection) -> bool:
    """Run FTS5's official external-content integrity check without persisting writes."""
    savepoint = "ast_symbols_fts_integrity"
    started = False
    try:
        conn.execute(f"SAVEPOINT {savepoint}")
        started = True
        # FTS5 rank=1 also compares the indexed terms with external content.
        conn.execute(
            "INSERT INTO ast_symbols_fts(ast_symbols_fts, rank) "
            "VALUES('integrity-check', 1)"
        )
        return True
    except sqlite3.DatabaseError:
        return False
    finally:
        if started:
            try:
                conn.execute(f"ROLLBACK TO {savepoint}")
            finally:
                conn.execute(f"RELEASE {savepoint}")


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


def _payload_symbol_count(symbols_json: Any) -> int | None:
    """``symbols_json`` 里声明的符号数；读不懂时返回 None（不猜）。

    Codex review P2（2026-11-09）：缺少投影状态时不能「拿现有行盖章」——
    行可能是解析中途留下的部分集合。只有行数与 payload 声明一致时，
    制造出来的证书才代表 payload 本身。
    """
    if not isinstance(symbols_json, str):
        return None
    try:
        import json

        payload = json.loads(symbols_json or "{}")
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    symbols = payload.get("symbols")
    if not isinstance(symbols, list):
        return None
    return len(symbols)


def _projection_matches_payload(conn: sqlite3.Connection, rel_path: str) -> bool:
    """文件缺少投影状态时，现有行是否就是 payload 声明的完整集合。

    无 payload 列或 payload 形状未知（更老的 schema / 空 ``{}``）时返回 True：
    没有声明可以反驳，保持原有的迁移快速路径；只有 payload 明确声明了符号集合、
    而现有行数是它的真子集/超集时才拒绝盖章。
    """
    try:
        source = conn.execute(
            "SELECT symbols_json FROM ast_index WHERE file_path = ?", (rel_path,)
        ).fetchone()
    except sqlite3.OperationalError:
        return True
    if source is None:
        return False
    expected = _payload_symbol_count(source[0])
    if expected is None:
        return True
    actual = conn.execute(
        "SELECT COUNT(*) FROM ast_symbol_rows WHERE file_path = ?", (rel_path,)
    ).fetchone()
    return int(actual[0] if actual else -1) == expected


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


def converge_symbol_projection(
    conn: sqlite3.Connection,
    *,
    require_fts: bool = False,
) -> bool:
    """收敛投影的三类内部残余，返回是否做了改动（幂等，可重复调用）。

    只修复 *内部* 不一致，不重写任何参考行——行内容与源码的一致性由增量遍历
    负责：

    1. ``ast_symbol_rows`` 里已不在 ``ast_index`` 的文件（陈旧行）；
    2. ``ast_index`` 里缺少投影状态的文件（解析失败或空文件）；
    3. 外部内容 FTS 的孤儿 docsize 行（参考行被重写时遗留）。

    dogfood 2026-11-09：旧版缓存迁移后这三类残余会让
    :func:`symbol_projection_is_exact` 永远为假，于是每次 ``index`` 都把每个
    文件重写一遍（本仓库 2917 文件实测：增量 0.6 s 退化成全量 57 s）。收敛后
    既有认证器可以补发 marker，下一次索引恢复增量。
    """
    tables = {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    if not {"ast_index", "ast_symbol_rows", "ast_symbol_projection_state"} <= tables:
        return False
    changed = False
    deleted = conn.execute(
        "DELETE FROM ast_symbol_rows WHERE file_path NOT IN "
        "(SELECT file_path FROM ast_index)"
    ).rowcount
    changed = changed or deleted > 0
    missing = conn.execute(
        "SELECT source.file_path FROM ast_index AS source "
        "LEFT JOIN ast_symbol_projection_state AS state "
        "ON state.file_path = source.file_path WHERE state.file_path IS NULL"
    ).fetchall()
    for row in missing:
        rel_path = str(row[0])
        if not _projection_matches_payload(conn, rel_path):
            # 行集合与 payload 不符（解析中断/部分回填）：不盖章，留给
            # 全量修复路径；盖章会让「部分行」冒充完整投影。
            continue
        upsert_symbol_projection_state(conn, rel_path)
        changed = True
    orphan_states = conn.execute(
        "DELETE FROM ast_symbol_projection_state WHERE file_path NOT IN "
        "(SELECT file_path FROM ast_index)"
    ).rowcount
    changed = changed or orphan_states > 0
    if require_fts and not _fts_terms_are_exact(conn):
        # 行数一致也不代表词条一致：原地 UPDATE 参考行会留下过期的 FTS 词条。
        # FTS5 官方的 integrity-check(rank=1) 是唯一权威判据，重建后即精确。
        conn.execute("INSERT INTO ast_symbols_fts(ast_symbols_fts) VALUES('rebuild')")
        changed = True
    return changed


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
            )
            if any(conn.execute(query).fetchone() is not None for query in fts_checks):
                return False

        # Preflight every potentially large cell using integer-only projections.
        # No TEXT payload reaches Python until every cell, row, and total budget
        # has passed; payload rows are then fetched individually by integer ID.
        state_preflight = conn.execute(
            "SELECT rowid, "
            "CASE WHEN typeof(file_path)='text' THEN length(CAST(file_path AS BLOB)) ELSE -1 END, "
            "CASE WHEN typeof(projection_digest)='text' THEN length(CAST(projection_digest AS BLOB)) ELSE -1 END "
            "FROM ast_symbol_projection_state ORDER BY rowid"
        )
        state_count = 0
        for state_lengths in state_preflight:
            check_budget()
            if (
                len(state_lengths) != 3
                or any(type(value) is not int for value in state_lengths)
                or state_lengths[0] < 1
                or any(
                    value < 0 or value > _PROJECTION_CELL_BYTE_BUDGET
                    for value in state_lengths[1:]
                )
            ):
                return False
            state_count += 1
            if state_count > max_symbols:
                return False
            bytes_seen += sum(state_lengths[1:])
            check_budget()

        row_preflight = conn.execute(
            "SELECT id, "
            "CASE WHEN typeof(name)='text' THEN length(CAST(name AS BLOB)) ELSE -1 END, "
            "CASE WHEN typeof(kind)='text' THEN length(CAST(kind AS BLOB)) ELSE -1 END, "
            "CASE WHEN typeof(file_path)='text' THEN length(CAST(file_path AS BLOB)) ELSE -1 END, "
            "CASE WHEN typeof(language)='text' THEN length(CAST(language AS BLOB)) ELSE -1 END, "
            "CASE WHEN typeof(line)='integer' THEN length(CAST(line AS BLOB)) ELSE -1 END, "
            "CASE WHEN typeof(end_line)='integer' THEN length(CAST(end_line AS BLOB)) ELSE -1 END "
            "FROM ast_symbol_rows ORDER BY id"
        )
        for row_lengths in row_preflight:
            if (
                len(row_lengths) != 7
                or any(type(value) is not int for value in row_lengths)
                or row_lengths[0] < 1
                or any(
                    value < 0 or value > _PROJECTION_CELL_BYTE_BUDGET
                    for value in row_lengths[1:]
                )
            ):
                return False
            rows_seen += 1
            bytes_seen += sum(row_lengths[1:])
            check_budget()

        state_ids = conn.execute(
            "SELECT rowid FROM ast_symbol_projection_state ORDER BY file_path"
        )
        materialized_states = 0
        for (state_id,) in state_ids:
            check_budget()
            if type(state_id) is not int:
                return False
            state = conn.execute(
                "SELECT file_path, symbol_count, projection_digest "
                "FROM ast_symbol_projection_state WHERE rowid = ?",
                (state_id,),
            ).fetchone()
            if state is None:
                return False
            file_path, expected_count, expected_digest = state
            if (
                type(file_path) is not str
                or type(expected_count) is not int
                or type(expected_digest) is not str
            ):
                return False
            materialized_states += 1
            digest = hashlib.sha256(b"tsa-symbol-projection-v1\0")
            file_count = 0
            row_ids = conn.execute(
                "SELECT id FROM ast_symbol_rows WHERE file_path = ? ORDER BY id",
                (file_path,),
            )
            for (row_id,) in row_ids:
                check_budget()
                if type(row_id) is not int:
                    return False
                values = conn.execute(
                    "SELECT id, name, kind, file_path, language, line, end_line "
                    "FROM ast_symbol_rows WHERE id = ?",
                    (row_id,),
                ).fetchone()
                if (
                    values is None
                    or type(values[0]) is not int
                    or any(type(value) is not str for value in values[1:5])
                    or type(values[5]) is not int
                    or type(values[6]) is not int
                ):
                    return False
                encoded = _typed(values)
                file_count += 1
                digest.update(len(encoded).to_bytes(8, "big"))
                digest.update(encoded)
            if (
                file_count != expected_count
                or "sha256:" + digest.hexdigest() != expected_digest
            ):
                return False
        if materialized_states != state_count:
            return False
        return not require_fts or _fts_terms_are_exact(conn)
    except (sqlite3.DatabaseError, UnicodeError, ValueError, OverflowError):
        return False
    finally:
        if install_progress:
            conn.set_progress_handler(None, 0)
