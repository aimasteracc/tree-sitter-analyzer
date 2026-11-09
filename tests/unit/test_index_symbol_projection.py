"""Fail-closed boundary tests for the index snapshot owner."""

from __future__ import annotations

import json
import os
import sqlite3

import pytest

from tests.unit._ast_cache_helpers import legacy_cache

requires_posix_fd = pytest.mark.skipif(os.name != "posix", reason="GH-1253")


def _fd_is_closed(fd: int) -> bool:
    try:
        os.fstat(fd)
    except OSError:
        return True
    return False


def _untyped_legacy_connection(file_path="a.py", language="python", symbols_json="{}"):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index(file_path, language, symbols_json)")
    conn.execute(
        "INSERT INTO ast_index VALUES (?, ?, ?)", (file_path, language, symbols_json)
    )
    return conn


class _MigrationRaceConnection:
    def __init__(self, conn, before_materialize):
        self.conn = conn
        self.before_materialize = before_materialize

    def __getattr__(self, name):
        return getattr(self.conn, name)

    def execute(self, query, params=()):
        if query.startswith("SELECT file_path, language, symbols_json"):
            self.before_materialize(self.conn)
        return self.conn.execute(query, params)


class _QueryResult:
    def __init__(self, rows):
        self._rows = iter(rows)

    def fetchone(self):
        return next(self._rows, None)


class _MigrationQueryOverride:
    def __init__(self, conn, override):
        self.conn = conn
        self.override = override

    def __getattr__(self, name):
        return getattr(self.conn, name)

    def execute(self, query, params=()):
        replacement = self.override(query, self.conn)
        if replacement is not None:
            return replacement
        return self.conn.execute(query, params)


def test_symbol_upgrade_rejects_indeterminate_ordinary_count():
    # PR #1253: an indeterminate ordinary-row budget count fails closed.
    from tree_sitter_analyzer.index_snapshot_symbols import (
        ensure_symbol_rows_backfilled,
    )

    conn = _untyped_legacy_connection()
    raced = _MigrationQueryOverride(
        conn,
        lambda query, _raw: (
            _QueryResult([])
            if query == "SELECT COUNT(*) FROM ast_symbol_rows"
            else None
        ),
    )
    with pytest.raises(
        sqlite3.OperationalError, match="LEGACY_SYMBOL_MIGRATION_BUDGET"
    ):
        ensure_symbol_rows_backfilled(raced)  # type: ignore[arg-type]
    conn.close()


def test_symbol_upgrade_rejects_malformed_ordinary_row():
    # PR #1253: ordinary scalar types are validated before comparison.
    from tree_sitter_analyzer.index_snapshot_symbols import (
        ensure_symbol_rows_backfilled,
    )

    conn = _untyped_legacy_connection()
    conn.execute(
        "CREATE TABLE ast_symbol_rows(id INTEGER PRIMARY KEY, name, kind, "
        "file_path, language, line, end_line)"
    )
    conn.execute(
        "INSERT INTO ast_symbol_rows VALUES(1, 'x', 'k', 'a.py', 'python', '1', 1)"
    )
    with pytest.raises(ValueError, match="invalid ordinary symbol row"):
        ensure_symbol_rows_backfilled(conn)
    conn.close()


def test_symbol_upgrade_rejects_ordinary_rows_appearing_after_count():
    # PR #1253: ordinary-row preflight must equal its bounded COUNT result.
    from tree_sitter_analyzer.index_snapshot_symbols import (
        ensure_symbol_rows_backfilled,
    )

    conn = _untyped_legacy_connection()
    conn.execute(
        "CREATE TABLE ast_symbol_rows(id INTEGER PRIMARY KEY, name, kind, "
        "file_path, language, line, end_line)"
    )
    conn.execute(
        "INSERT INTO ast_symbol_rows VALUES(1, 'x', 'k', 'a.py', 'python', 1, 1)"
    )

    def add_row(query, raw):
        if query.startswith("SELECT length(CAST(name AS BLOB))"):
            raw.execute(
                "INSERT INTO ast_symbol_rows VALUES(2, 'y', 'k', 'a.py', 'python', 2, 2)"
            )
        return None

    raced = _MigrationQueryOverride(conn, add_row)
    with pytest.raises(
        sqlite3.OperationalError, match="LEGACY_SYMBOL_MIGRATION_BUDGET"
    ):
        ensure_symbol_rows_backfilled(raced)  # type: ignore[arg-type]
    conn.close()


def test_symbol_upgrade_rejects_indeterminate_projection_state_count():
    # PR #1253: projection-state COUNT must be a bounded integer scalar.
    from tree_sitter_analyzer.index_snapshot_symbols import (
        ensure_symbol_rows_backfilled,
    )

    conn = _untyped_legacy_connection()
    raced = _MigrationQueryOverride(
        conn,
        lambda query, _raw: (
            _QueryResult([])
            if query == "SELECT COUNT(*) FROM ast_symbol_projection_state"
            else None
        ),
    )
    with pytest.raises(
        sqlite3.OperationalError, match="LEGACY_SYMBOL_MIGRATION_BUDGET"
    ):
        ensure_symbol_rows_backfilled(raced)  # type: ignore[arg-type]
    conn.close()


def test_symbol_upgrade_rejects_invalid_symbol_scalar_types():
    # PR #1253: parsed legacy symbol fields retain exact scalar types.
    from tree_sitter_analyzer.index_snapshot_symbols import (
        ensure_symbol_rows_backfilled,
    )

    symbols = json.dumps({"symbols": [{"name": "x", "line": "1"}]})
    conn = _untyped_legacy_connection(symbols_json=symbols)
    with pytest.raises(ValueError, match="invalid legacy symbol row"):
        ensure_symbol_rows_backfilled(conn)
    conn.close()


def test_symbol_upgrade_rejects_rows_disappearing_after_preflight():
    # PR #1253: materialization must equal its bounded preflight row count.
    from tree_sitter_analyzer.index_snapshot_symbols import (
        ensure_symbol_rows_backfilled,
    )

    conn = _untyped_legacy_connection()
    raced = _MigrationRaceConnection(
        conn,
        lambda raw: raw.execute("DELETE FROM ast_index"),
    )
    with pytest.raises(
        sqlite3.OperationalError, match="LEGACY_SYMBOL_MIGRATION_BUDGET"
    ):
        ensure_symbol_rows_backfilled(raced)  # type: ignore[arg-type]
    conn.close()


def test_symbol_upgrade_detects_extra_ordinary_rows_after_comparison():
    # PR #1253: leftover ordinary rows make legacy content non-exact.
    from tree_sitter_analyzer.index_snapshot_symbols import (
        ensure_symbol_rows_backfilled,
    )

    symbols = json.dumps(
        {"symbols": [{"name": "x", "kind": "k", "line": 1, "end_line": 1}]}
    )
    conn = _untyped_legacy_connection(symbols_json=symbols)
    conn.execute(
        "CREATE TABLE ast_symbol_rows(id INTEGER PRIMARY KEY, name, kind, "
        "file_path, language, line, end_line)"
    )
    conn.execute(
        "INSERT INTO ast_symbol_rows VALUES(1, 'x', 'k', 'a.py', 'python', 1, 1)"
    )
    ordinary_rows = _QueryResult(
        [
            ("x", "k", "a.py", "python", 1, 1),
            ("extra", "k", "a.py", "python", 2, 2),
        ]
    )
    raced = _MigrationQueryOverride(
        conn,
        lambda query, _raw: (
            ordinary_rows
            if query.startswith("SELECT name, kind, file_path, language")
            else None
        ),
    )
    result = ensure_symbol_rows_backfilled(raced)  # type: ignore[arg-type]
    conn.close()

    assert result is False


def test_projection_digest_rejects_same_count_payload_forgery(tmp_path):
    # PR #1253 thread 3757429365: counts cannot certify changed query payloads.
    from tree_sitter_analyzer.index_symbol_projection import symbol_projection_is_exact

    source = tmp_path / "app.py"
    source.write_text("def target():\n    return 1\n")
    cache = legacy_cache(str(tmp_path))
    cache.index_file(str(source))
    conn = cache.get_conn()
    before = symbol_projection_is_exact(conn)
    conn.execute(
        "UPDATE ast_symbol_rows SET kind = 'forged' WHERE file_path = 'app.py'"
    )
    conn.commit()
    after = symbol_projection_is_exact(conn)
    cache.close()

    assert (before, after) == (True, False)


def test_symbol_migration_preserves_its_progress_handler_during_validation():
    # PR #1253 thread 3757429359: nested validation must not replace the deadline.
    from tree_sitter_analyzer.index_snapshot_symbols import (
        ensure_symbol_rows_backfilled,
    )

    raw = sqlite3.connect(":memory:")
    raw.execute(
        "CREATE TABLE ast_index (file_path TEXT, content_hash TEXT, "
        "language TEXT, symbols_json TEXT)"
    )
    raw.execute("INSERT INTO ast_index VALUES ('a.py', 'h', 'python', '{}')")
    installs = []

    class RecordingConnection:
        def __getattr__(self, name):
            return getattr(raw, name)

        def set_progress_handler(self, handler, steps):
            installs.append(handler)
            return raw.set_progress_handler(handler, steps)

    result = ensure_symbol_rows_backfilled(RecordingConnection())  # type: ignore[arg-type]
    raw.close()

    assert (result, sum(handler is not None for handler in installs)) == (True, 1)


def test_projection_digest_frames_null_scalar():
    # PR #1253 thread 3757429365: canonical frames preserve SQLite NULL type.
    from tree_sitter_analyzer.index_symbol_projection import symbol_rows_digest

    digest = symbol_rows_digest(((None,),))

    assert (
        digest
        == "sha256:9341e618b6e0444481fc01888844bdb8d9c2b092bd917393078c79ab221bc537"
    )


def test_projection_digest_frames_blob_scalar():
    # PR #1253 thread 3757429365: canonical frames preserve SQLite BLOB type.
    from tree_sitter_analyzer.index_symbol_projection import symbol_rows_digest

    digest = symbol_rows_digest(((b"x",),))

    assert (
        digest
        == "sha256:b2ea8094e147336ca6cf3359184d9f32d518f9ca5af67180ae3445ccc718dce5"
    )


def test_projection_digest_frames_float_scalar():
    # PR #1253 thread 3757429365: canonical frames preserve SQLite REAL type.
    from tree_sitter_analyzer.index_symbol_projection import symbol_rows_digest

    digest = symbol_rows_digest(((1.5,),))

    assert (
        digest
        == "sha256:b81c87f201095f1f3f84950ae64551bfbbb82de2b70390188a66df7831bcda98"
    )


def test_projection_digest_rejects_unsupported_scalar():
    # PR #1253 thread 3757429365: non-SQLite objects are never string-coerced.
    from tree_sitter_analyzer.index_symbol_projection import symbol_rows_digest

    with pytest.raises(ValueError, match="invalid ordinary symbol scalar"):
        symbol_rows_digest(((object(),),))


def test_symbol_upgrade_adds_digest_to_legacy_state_schema():
    # PR #1253 thread 3757429365: v1 projection state upgrades in place.
    from tree_sitter_analyzer.index_snapshot_symbols import (
        ensure_symbol_rows_backfilled,
    )

    conn = _untyped_legacy_connection()
    conn.execute(
        "CREATE TABLE ast_symbol_projection_state("
        "file_path TEXT PRIMARY KEY, content_hash TEXT NOT NULL, "
        "symbol_count INTEGER NOT NULL)"
    )

    result = ensure_symbol_rows_backfilled(conn)
    columns = tuple(
        row[1] for row in conn.execute("PRAGMA table_info(ast_symbol_projection_state)")
    )
    conn.close()

    assert (result, columns) == (
        True,
        ("file_path", "content_hash", "symbol_count", "projection_digest"),
    )


def test_projection_validator_enforces_total_payload_budget(tmp_path, monkeypatch):
    # PR #1253 thread 3757429365: ordinary payload bytes have an absolute cap.
    import tree_sitter_analyzer.index_symbol_projection as projection
    from tree_sitter_analyzer.ast_cache import ASTCache

    source = tmp_path / "app.py"
    source.write_text("value = 1\n")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(source))
    monkeypatch.setattr(projection, "_PROJECTION_TOTAL_BYTE_BUDGET", -1)

    result = projection.symbol_projection_is_exact(cache.get_conn())
    cache.close()

    assert result is False


class _ProjectionCursor:
    def __init__(self, rows):
        self._rows = iter(rows)

    def fetchone(self):
        return next(self._rows, None)

    def __iter__(self):
        return self

    def __next__(self):
        return next(self._rows)


class _ProjectionConnection:
    row_columns = ("id", "name", "kind", "file_path", "language", "line", "end_line")
    state_columns = ("file_path", "content_hash", "symbol_count", "projection_digest")
    metadata_columns = ("key", "value")

    def __init__(self, *, states=(), symbol_rows=()):
        self.states = states
        self.symbol_rows = symbol_rows

    def set_progress_handler(self, callback, _steps):
        if callback is not None:
            assert callback() == 0

    def execute(self, query, _params=()):
        if query.startswith("PRAGMA table_info"):
            table = query.removeprefix("PRAGMA table_info(").removesuffix(")")
            columns = {
                "ast_symbol_rows": self.row_columns,
                "ast_symbol_projection_state": self.state_columns,
                "ast_cache_metadata": self.metadata_columns,
            }[table]
            return _ProjectionCursor(
                [(index, name) for index, name in enumerate(columns)]
            )
        if "COUNT(*) FILTER" in query:
            return _ProjectionCursor([(1, 1)])
        if query.startswith("SELECT content_hash FROM ast_index"):
            return _ProjectionCursor([])
        if query.startswith("SELECT 1 FROM"):
            return _ProjectionCursor([])
        if query.startswith("SELECT rowid, "):
            return _ProjectionCursor(
                [
                    (
                        index,
                        len(state[0].encode()) if isinstance(state[0], str) else -1,
                        len(state[2].encode()) if isinstance(state[2], str) else -1,
                    )
                    for index, state in enumerate(self.states, 1)
                ]
            )
        if query.startswith("SELECT id, CASE"):
            return _ProjectionCursor(
                [
                    (
                        row[0],
                        *(row[7:11]),
                        len(str(row[5]).encode()) if type(row[5]) is int else -1,
                        len(str(row[6]).encode()) if type(row[6]) is int else -1,
                    )
                    for row in self.symbol_rows
                ]
            )
        if query.startswith("SELECT rowid FROM"):
            return _ProjectionCursor(
                [(index,) for index in range(1, len(self.states) + 1)]
            )
        if query.startswith("SELECT file_path, symbol_count"):
            index = int(_params[0]) - 1
            return _ProjectionCursor([self.states[index]])
        if query.startswith("SELECT id FROM ast_symbol_rows"):
            return _ProjectionCursor(
                [(row[0],) for row in self.symbol_rows if row[3] == _params[0]]
            )
        if query.startswith("SELECT id, name, kind"):
            return _ProjectionCursor(
                [tuple(row[:7]) for row in self.symbol_rows if row[0] == _params[0]]
            )
        return _ProjectionCursor([])


class _ProjectionMaterializationOverride(_ProjectionConnection):
    def __init__(self, *, prefix: str, rows, **kwargs):
        super().__init__(**kwargs)
        self.prefix = prefix
        self.rows = rows

    def execute(self, query, params=()):
        if query.startswith(self.prefix):
            return _ProjectionCursor(self.rows)
        return super().execute(query, params)


def _valid_projection_values():
    from tree_sitter_analyzer.index_symbol_projection import symbol_rows_digest

    row = (1, "name", "kind", "a.py", "python", 1, 1, 4, 4, 4, 6)
    digest = symbol_rows_digest((row[:7],))
    return row, ("a.py", 1, digest)


def test_projection_rejects_noninteger_materialized_state_id() -> None:
    from tree_sitter_analyzer.index_symbol_projection import symbol_projection_is_exact

    _row, state = _valid_projection_values()
    conn = _ProjectionMaterializationOverride(
        prefix="SELECT rowid FROM", rows=(("bad",),), states=(state,)
    )

    assert symbol_projection_is_exact(conn) is False


def test_projection_rejects_state_removed_after_preflight() -> None:
    from tree_sitter_analyzer.index_symbol_projection import symbol_projection_is_exact

    _row, state = _valid_projection_values()
    conn = _ProjectionMaterializationOverride(
        prefix="SELECT file_path, symbol_count", rows=(), states=(state,)
    )

    assert symbol_projection_is_exact(conn) is False


def test_projection_rejects_state_type_changed_after_preflight() -> None:
    from tree_sitter_analyzer.index_symbol_projection import symbol_projection_is_exact

    _row, state = _valid_projection_values()
    conn = _ProjectionMaterializationOverride(
        prefix="SELECT file_path, symbol_count",
        rows=(("a.py", "1", state[2]),),
        states=(state,),
    )

    assert symbol_projection_is_exact(conn) is False


def test_projection_rejects_noninteger_materialized_symbol_id() -> None:
    from tree_sitter_analyzer.index_symbol_projection import symbol_projection_is_exact

    row, state = _valid_projection_values()
    conn = _ProjectionMaterializationOverride(
        prefix="SELECT id FROM ast_symbol_rows",
        rows=(("bad",),),
        states=(state,),
        symbol_rows=(row,),
    )

    assert symbol_projection_is_exact(conn) is False


def test_projection_rejects_symbol_removed_after_preflight() -> None:
    from tree_sitter_analyzer.index_symbol_projection import symbol_projection_is_exact

    row, state = _valid_projection_values()
    conn = _ProjectionMaterializationOverride(
        prefix="SELECT id, name, kind", rows=(), states=(state,), symbol_rows=(row,)
    )

    assert symbol_projection_is_exact(conn) is False


def test_projection_rejects_materialized_digest_mismatch() -> None:
    from tree_sitter_analyzer.index_symbol_projection import symbol_projection_is_exact

    row, state = _valid_projection_values()
    wrong_state = (state[0], state[1], "sha256:" + "0" * 64)
    conn = _ProjectionConnection(states=(wrong_state,), symbol_rows=(row,))

    assert symbol_projection_is_exact(conn) is False


def test_projection_rejects_state_added_after_preflight() -> None:
    from tree_sitter_analyzer.index_symbol_projection import symbol_projection_is_exact

    row, state = _valid_projection_values()
    conn = _ProjectionMaterializationOverride(
        prefix="SELECT rowid, ", rows=(), states=(state,), symbol_rows=(row,)
    )

    assert symbol_projection_is_exact(conn) is False


def test_symbol_projection_rejects_wrong_state_schema() -> None:
    from tree_sitter_analyzer.index_symbol_projection import symbol_projection_is_exact

    conn = _ProjectionConnection()
    conn.state_columns = ("wrong",)

    assert symbol_projection_is_exact(conn) is False


def test_symbol_projection_rejects_wrong_metadata_schema() -> None:
    from tree_sitter_analyzer.index_symbol_projection import symbol_projection_is_exact

    conn = _ProjectionConnection()
    conn.metadata_columns = ("wrong",)

    assert symbol_projection_is_exact(conn) is False


def test_symbol_projection_rejects_malformed_state_scalar() -> None:
    from tree_sitter_analyzer.index_symbol_projection import symbol_projection_is_exact

    conn = _ProjectionConnection(states=((1, 0, "sha256:" + "0" * 64),))

    assert symbol_projection_is_exact(conn) is False


def test_symbol_projection_rejects_malformed_symbol_scalar() -> None:
    from tree_sitter_analyzer.index_symbol_projection import symbol_projection_is_exact

    conn = _ProjectionConnection(
        states=(("a.py", 1, "sha256:" + "0" * 64),),
        symbol_rows=(("bad", "name", "kind", "a.py", "python", 1, 1, 4, 4, 4, 6),),
    )

    assert symbol_projection_is_exact(conn) is False


def test_missing_fts_row_is_rebuilt_without_full_projection_reindex(tmp_path):
    # PR #1253 thread 3759606810: removed FTS evidence cannot retain an exact stamp.
    # dogfood 2026-11-09：缺失的 FTS 条目由参考行重建即可（并按完整校验重新签发
    # marker），不再触发整仓重写——修复前这里把 2917 个文件全部重新提取，
    # 一次 1 文件刷新实测 57 s。
    from tree_sitter_analyzer.index_symbol_projection import symbol_projection_is_exact

    source = tmp_path / "app.py"
    source.write_text("def target():\n    return 1\n")
    cache = legacy_cache(str(tmp_path))
    cache.index_file(str(source))
    conn = cache.get_conn()
    row = conn.execute(
        "SELECT id, name, kind, file_path, language FROM ast_symbol_rows"
    ).fetchone()
    conn.execute(
        "INSERT INTO ast_symbols_fts"
        "(ast_symbols_fts, rowid, name, kind, file_path, language) "
        "VALUES('delete', ?, ?, ?, ?, ?)",
        tuple(row),
    )
    conn.commit()

    before = symbol_projection_is_exact(conn, require_fts=True)
    stats = cache.index_project()
    after = symbol_projection_is_exact(conn, require_fts=True)
    cache.close()

    # before=False 仍然固定「移除 FTS 证据后不得保留旧 exact 戳」这一 #1253 语义；
    # 变化的是恢复方式：有界重建并重新认证，而不是全量重索引。
    assert (before, stats["indexed"], stats["cached"], after) == (False, 0, 1, True)


def test_extra_fts_rowid_rejects_exact_projection(tmp_path):
    # PR #1253 thread 3759606810: an FTS-only rowid is stale projection evidence.
    from tree_sitter_analyzer.index_symbol_projection import symbol_projection_is_exact

    source = tmp_path / "app.py"
    source.write_text("def target():\n    return 1\n")
    cache = legacy_cache(str(tmp_path))
    cache.index_file(str(source))
    conn = cache.get_conn()
    conn.execute(
        "INSERT INTO ast_symbols_fts(rowid, name, kind, file_path, language) "
        "VALUES(999, 'stale', 'function', 'gone.py', 'python')"
    )
    conn.commit()

    result = symbol_projection_is_exact(conn, require_fts=True)
    cache.close()

    assert result is False


def test_projection_preflights_lengths_before_payload_fetch(tmp_path, monkeypatch):
    # PR #1253 thread 3760178955: oversized TEXT must never cross into Python.
    import tree_sitter_analyzer.index_symbol_projection as projection
    from tree_sitter_analyzer.ast_cache import ASTCache

    source = tmp_path / "app.py"
    source.write_text("def oversized():\n    return 1\n")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(source))
    raw = cache.get_conn()

    class RecordingConnection:
        def __init__(self, conn):
            self.conn = conn
            self.payload_fetched = False

        def __getattr__(self, name):
            return getattr(self.conn, name)

        def execute(self, query, params=()):
            if query.startswith("SELECT id, name, kind") and "WHERE id" in query:
                self.payload_fetched = True
            return self.conn.execute(query, params)

    wrapped = RecordingConnection(raw)
    monkeypatch.setattr(projection, "_PROJECTION_CELL_BYTE_BUDGET", 3)
    result = projection.symbol_projection_is_exact(wrapped)
    cache.close()

    assert (result, wrapped.payload_fetched) == (False, False)


def test_stale_external_fts_terms_are_rebuilt_from_rows(tmp_path):
    # PR #1253 thread 3760178960: external payload columns are not indexed terms.
    # dogfood 2026-11-09：过期词条用参考行原地重建 FTS 即可（并按完整校验重签
    # marker），不必把文件重新提取一遍；修复前这里每次索引都全量重写。
    from tree_sitter_analyzer.index_symbol_projection import (
        symbol_projection_is_exact,
        upsert_symbol_projection_state,
    )

    source = tmp_path / "app.py"
    source.write_text("def alpha():\n    return 1\n")
    cache = legacy_cache(str(tmp_path))
    cache.index_file(str(source))
    conn = cache.get_conn()
    conn.execute("UPDATE ast_symbol_rows SET name='beta' WHERE name='alpha'")
    upsert_symbol_projection_state(conn, "app.py")
    conn.commit()

    before = symbol_projection_is_exact(conn, require_fts=True)
    stale_matches = (
        conn.execute(
            "SELECT COUNT(*) FROM ast_symbols_fts WHERE ast_symbols_fts MATCH 'alpha'"
        ).fetchone()[0],
        conn.execute(
            "SELECT COUNT(*) FROM ast_symbols_fts WHERE ast_symbols_fts MATCH 'beta'"
        ).fetchone()[0],
    )
    stats = cache.index_project()
    after = symbol_projection_is_exact(conn, require_fts=True)
    repaired_matches = (
        conn.execute(
            "SELECT COUNT(*) FROM ast_symbols_fts WHERE ast_symbols_fts MATCH 'alpha'"
        ).fetchone()[0],
        conn.execute(
            "SELECT COUNT(*) FROM ast_symbols_fts WHERE ast_symbols_fts MATCH 'beta'"
        ).fetchone()[0],
    )
    cache.close()

    # before=False / stale_matches=(1,0) 仍固定 #1253 的语义：旧戳不可信、过期词条
    # 还在；修复方式变为按参考行重建（索引 0 个文件），重建后 alpha 消失、beta 出现。
    assert (before, stale_matches, stats["indexed"], after, repaired_matches) == (
        False,
        (1, 0),
        0,
        True,
        (0, 1),
    )


def test_projection_state_cap_fails_before_payload_materialization() -> None:
    # PR #1253 thread 3760178955: projection state rows share the row budget.
    from tree_sitter_analyzer.index_symbol_projection import symbol_projection_is_exact

    conn = _ProjectionConnection(states=(("a.py", 0, "sha256:" + "0" * 64),))

    assert symbol_projection_is_exact(conn, max_symbols=0) is False


def test_delete_projection_state_propagates_real_database_errors() -> None:
    # PR #1253: compatibility tolerance is limited to a genuinely missing table.
    from tree_sitter_analyzer.index_symbol_projection import (
        delete_projection_state_if_present,
    )

    class LockedConnection:
        def execute(self, *_args):
            raise sqlite3.OperationalError("database is locked")

    with pytest.raises(sqlite3.OperationalError, match="locked"):
        delete_projection_state_if_present(LockedConnection(), "a.py")  # type: ignore[arg-type]


def test_delete_projection_state_tolerates_missing_legacy_table() -> None:
    # PR #1253: legacy fixtures without projection state remain compatible.
    from tree_sitter_analyzer.index_symbol_projection import (
        delete_projection_state_if_present,
    )

    class LegacyConnection:
        calls = 0

        def execute(self, *_args):
            self.calls += 1
            raise sqlite3.OperationalError("no such table: ast_symbol_projection_state")

    conn = LegacyConnection()
    delete_projection_state_if_present(conn, "a.py")  # type: ignore[arg-type]

    assert conn.calls == 1


def test_projection_rejects_state_generation_mismatch(tmp_path) -> None:
    # PR #1253: authoritative certification binds state to the index generation.
    from tree_sitter_analyzer.index_symbol_projection import symbol_projection_is_exact

    source = tmp_path / "app.py"
    source.write_text("value = 1\n")
    cache = legacy_cache(str(tmp_path))
    cache.index_file(str(source))
    conn = cache.get_conn()
    conn.execute("UPDATE ast_index SET content_hash='different'")

    result = symbol_projection_is_exact(conn)
    cache.close()

    assert result is False


def _projection_db(symbols_json: str, rows: int) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT, content_hash TEXT, "
        "language TEXT, symbols_json TEXT)"
    )
    conn.execute(
        "CREATE TABLE ast_symbol_rows (id INTEGER PRIMARY KEY, name TEXT, kind TEXT, "
        "file_path TEXT, language TEXT, line INTEGER, end_line INTEGER)"
    )
    conn.execute(
        "CREATE TABLE ast_symbol_projection_state (file_path TEXT PRIMARY KEY, "
        "content_hash TEXT, symbol_count INTEGER, projection_digest TEXT)"
    )
    conn.execute(
        "INSERT INTO ast_index VALUES ('a.py', 'h', 'python', ?)", (symbols_json,)
    )
    for index in range(rows):
        conn.execute(
            "INSERT INTO ast_symbol_rows (name, kind, file_path, language, line, end_line) "
            "VALUES (?, 'function', 'a.py', 'python', ?, ?)",
            (f"f{index}", index + 1, index + 2),
        )
    return conn


def test_convergence_does_not_stamp_a_partial_projection() -> None:
    """Codex P2：payload 声明 2 个符号、行只有 1 个 → 不得制造投影证书。"""
    from tree_sitter_analyzer.index_symbol_projection import (
        converge_symbol_projection,
        symbol_projection_is_exact,
    )

    conn = _projection_db('{"symbols": [{"name": "f0"}, {"name": "f1"}]}', rows=1)

    converge_symbol_projection(conn)

    stamped = conn.execute(
        "SELECT COUNT(*) FROM ast_symbol_projection_state"
    ).fetchone()[0]
    assert (stamped, symbol_projection_is_exact(conn)) == (0, False)
    conn.close()


def test_convergence_stamps_a_projection_that_matches_the_payload() -> None:
    """行集合与 payload 一致时才盖章（旧缓存迁移的快速路径仍然可用）。"""
    from tree_sitter_analyzer.index_symbol_projection import (
        converge_symbol_projection,
    )

    conn = _projection_db('{"symbols": [{"name": "f0"}]}', rows=1)

    converge_symbol_projection(conn)

    state = conn.execute(
        "SELECT symbol_count FROM ast_symbol_projection_state"
    ).fetchall()
    # 盖章内容来自 payload：1 个符号；exactness 还需要认证器补 marker，
    # 那是另一道契约（本用例只验证「盖章这一步」）。
    assert [tuple(row) for row in state] == [(1,)]
    conn.close()


def test_projection_payload_check_rejects_a_file_outside_the_index() -> None:
    """防御分支：文件不在 ast_index 时不得声称「行与 payload 一致」。"""
    from tree_sitter_analyzer.index_symbol_projection import (
        _projection_matches_payload,
    )

    conn = _projection_db('{"symbols": []}', rows=0)

    assert _projection_matches_payload(conn, "missing.py") is False
    conn.close()


def test_projection_payload_check_leaves_unverifiable_payloads_stampable() -> None:
    """payload 形状未知（空 ``{}`` / 非 JSON）时没有声明可反驳，保持可盖章。"""
    from tree_sitter_analyzer.index_symbol_projection import (
        _projection_matches_payload,
    )

    assert _projection_matches_payload(_projection_db("{}", rows=0), "a.py") is True
    assert (
        _projection_matches_payload(_projection_db("not json", rows=0), "a.py") is True
    )


def test_upsert_is_a_noop_without_a_state_table_or_source_row() -> None:
    """两条防御分支：没有状态表、或文件不在 ast_index 时都不写错行。"""
    from tree_sitter_analyzer.index_symbol_projection import (
        upsert_symbol_projection_state,
    )

    bare = sqlite3.connect(":memory:")
    bare.execute("CREATE TABLE ast_index(file_path TEXT)")
    upsert_symbol_projection_state(bare, "a.py")
    assert bare.execute("SELECT COUNT(*) FROM ast_index").fetchone() == (0,)
    bare.close()

    conn = _projection_db('{"symbols": []}', rows=0)
    upsert_symbol_projection_state(conn, "missing.py")
    assert (
        conn.execute("SELECT COUNT(*) FROM ast_symbol_projection_state").fetchone()[0]
        == 0
    )
    conn.close()
