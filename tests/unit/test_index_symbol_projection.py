"""Fail-closed boundary tests for the index snapshot owner."""

from __future__ import annotations

import json
import os
import sqlite3

import pytest

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
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.index_symbol_projection import symbol_projection_is_exact

    source = tmp_path / "app.py"
    source.write_text("def target():\n    return 1\n")
    cache = ASTCache(str(tmp_path))
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


def test_missing_fts_row_forces_full_projection_reindex(tmp_path):
    # PR #1253 thread 3759606810: removed FTS evidence cannot retain an exact stamp.
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.index_symbol_projection import symbol_projection_is_exact

    source = tmp_path / "app.py"
    source.write_text("def target():\n    return 1\n")
    cache = ASTCache(str(tmp_path))
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

    assert (before, stats["indexed"], stats["cached"], after) == (False, 1, 0, True)


def test_extra_fts_rowid_rejects_exact_projection(tmp_path):
    # PR #1253 thread 3759606810: an FTS-only rowid is stale projection evidence.
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.index_symbol_projection import symbol_projection_is_exact

    source = tmp_path / "app.py"
    source.write_text("def target():\n    return 1\n")
    cache = ASTCache(str(tmp_path))
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


def test_stale_external_fts_terms_force_rebuild(tmp_path):
    # PR #1253 thread 3760178960: external payload columns are not indexed terms.
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.index_symbol_projection import (
        symbol_projection_is_exact,
        upsert_symbol_projection_state,
    )

    source = tmp_path / "app.py"
    source.write_text("def alpha():\n    return 1\n")
    cache = ASTCache(str(tmp_path))
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

    assert (before, stale_matches, stats["indexed"], after, repaired_matches) == (
        False,
        (1, 0),
        1,
        True,
        (1, 0),
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
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.index_symbol_projection import symbol_projection_is_exact

    source = tmp_path / "app.py"
    source.write_text("value = 1\n")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(source))
    conn = cache.get_conn()
    conn.execute("UPDATE ast_index SET content_hash='different'")

    result = symbol_projection_is_exact(conn)
    cache.close()

    assert result is False
