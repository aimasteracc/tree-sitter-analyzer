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


class TestSnapshotFailureContracts:
    @staticmethod
    def _certified_cache(root):
        from tree_sitter_analyzer.ast_cache import ASTCache
        from tree_sitter_analyzer.index_snapshot import stamp_full_index_manifest

        source = root / "sample.py"
        source.write_text("value = 1\n")
        cache = ASTCache(str(root))
        cache.index_file(str(source))
        stamp_full_index_manifest(cache.get_conn(), str(root))
        cache.close()

    @pytest.fixture(autouse=True)
    def _close_registry(self):
        yield
        from tree_sitter_analyzer.index_snapshot import REGISTRY

        REGISTRY.close_all()

    def test_no_fts_schema_still_creates_ordinary_symbol_rows(self):
        from tree_sitter_analyzer.cache import schema

        conn = sqlite3.connect(":memory:")
        available = schema.init_db(conn, None, lambda _conn: False, [])
        tables = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        conn.close()
        assert available is False
        assert "ast_symbol_rows" in tables
        assert "ast_symbols_fts" not in tables

    @staticmethod
    def _legacy_symbol_connection(raw_symbols: str) -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE ast_index (file_path TEXT, language TEXT, symbols_json TEXT)"
        )
        conn.execute(
            "INSERT INTO ast_index VALUES ('a.py', 'python', ?)", (raw_symbols,)
        )
        return conn

    @staticmethod
    def _symbol_table_count(conn: sqlite3.Connection) -> int:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE type='table' AND name='ast_symbol_rows'"
            ).fetchone()[0]
        )

    def test_legacy_symbol_migration_row_budget_rolls_back(self, monkeypatch):
        import tree_sitter_analyzer.index_snapshot_symbols as schema

        conn = self._legacy_symbol_connection('{"symbols": []}')
        monkeypatch.setattr(schema, "_LEGACY_SYMBOL_MIGRATION_ROW_BUDGET", 0)
        with pytest.raises(
            sqlite3.OperationalError, match="^LEGACY_SYMBOL_MIGRATION_BUDGET$"
        ):
            schema.ensure_symbol_rows_backfilled(conn)
        assert self._symbol_table_count(conn) == 0
        conn.close()

    def test_legacy_symbol_migration_input_budget_rolls_back(self, monkeypatch):
        import tree_sitter_analyzer.index_snapshot_symbols as schema

        conn = self._legacy_symbol_connection('{"symbols": []}')
        monkeypatch.setattr(schema, "_LEGACY_SYMBOL_MIGRATION_INPUT_BYTE_BUDGET", 1)
        with pytest.raises(
            sqlite3.OperationalError, match="^LEGACY_SYMBOL_MIGRATION_BUDGET$"
        ):
            schema.ensure_symbol_rows_backfilled(conn)
        assert self._symbol_table_count(conn) == 0
        conn.close()

    def test_legacy_symbol_migration_cell_budget_precedes_json(self, monkeypatch):
        import tree_sitter_analyzer.index_snapshot_symbols as schema

        conn = self._legacy_symbol_connection("not-json")
        monkeypatch.setattr(schema, "_LEGACY_SYMBOL_MIGRATION_CELL_BYTE_BUDGET", 1)
        with pytest.raises(
            sqlite3.OperationalError, match="^LEGACY_SYMBOL_MIGRATION_BUDGET$"
        ):
            schema.ensure_symbol_rows_backfilled(conn)
        assert self._symbol_table_count(conn) == 0
        conn.close()

    def test_legacy_symbol_migration_symbol_budget_rolls_back(self, monkeypatch):
        import tree_sitter_analyzer.index_snapshot_symbols as schema

        conn = self._legacy_symbol_connection('{"symbols": [{"name": "x"}]}')
        monkeypatch.setattr(schema, "_LEGACY_SYMBOL_MIGRATION_SYMBOL_BUDGET", 0)
        with pytest.raises(
            sqlite3.OperationalError, match="^LEGACY_SYMBOL_MIGRATION_BUDGET$"
        ):
            schema.ensure_symbol_rows_backfilled(conn)
        assert self._symbol_table_count(conn) == 0
        conn.close()

    def test_legacy_symbol_migration_deadline_rolls_back(self, monkeypatch):
        import tree_sitter_analyzer.index_snapshot_symbols as schema

        conn = self._legacy_symbol_connection('{"symbols": []}')
        monkeypatch.setattr(schema, "_LEGACY_SYMBOL_MIGRATION_SECONDS", -1.0)
        with pytest.raises(
            sqlite3.OperationalError, match="^LEGACY_SYMBOL_MIGRATION_BUDGET$"
        ):
            schema.ensure_symbol_rows_backfilled(conn)
        assert self._symbol_table_count(conn) == 0
        conn.close()

    def test_legacy_symbol_migration_byte_cell_budget_rolls_back(self, monkeypatch):
        import tree_sitter_analyzer.index_snapshot_symbols as schema

        conn = self._legacy_symbol_connection('{"symbols": []}')
        conn.execute("UPDATE ast_index SET symbols_json = ?", (b"{}",))
        monkeypatch.setattr(schema, "_LEGACY_SYMBOL_MIGRATION_CELL_BYTE_BUDGET", 1)
        with pytest.raises(
            sqlite3.OperationalError, match="^LEGACY_SYMBOL_MIGRATION_BUDGET$"
        ):
            schema.ensure_symbol_rows_backfilled(conn)
        assert self._symbol_table_count(conn) == 0
        conn.close()

    def test_legacy_symbol_migration_rejects_non_text_cell(self):
        import tree_sitter_analyzer.index_snapshot_symbols as schema

        conn = self._legacy_symbol_connection('{"symbols": []}')
        conn.execute("UPDATE ast_index SET symbols_json = NULL")
        with pytest.raises(ValueError, match="^invalid legacy symbols_json$"):
            schema.ensure_symbol_rows_backfilled(conn)
        assert self._symbol_table_count(conn) == 0
        conn.close()

    def test_legacy_symbol_migration_rejects_oversized_metadata_schema_before_pragma(
        self,
    ):
        # PR #1253 review 3755736540: malformed setup is bounded before column decode.
        import tree_sitter_analyzer.index_snapshot_symbols as schema

        conn = self._legacy_symbol_connection('{"symbols": []}')
        conn.execute(
            "CREATE TABLE ast_cache_metadata (key TEXT, value TEXT, "
            f"extra TEXT CHECK (extra != '{'x' * 5000}'))"
        )
        statements = []
        conn.set_trace_callback(statements.append)
        with pytest.raises(ValueError, match="invalid ast_cache_metadata schema"):
            schema.ensure_symbol_rows_backfilled(conn)
        conn.close()

        assert not any("table_info" in statement for statement in statements)

    def test_legacy_symbol_migration_rejects_wrong_metadata_columns(self):
        # PR #1253 review 3755736540: marker lookup requires validated columns.
        import tree_sitter_analyzer.index_snapshot_symbols as schema

        conn = self._legacy_symbol_connection('{"symbols": []}')
        conn.execute("CREATE TABLE ast_cache_metadata (key TEXT, other TEXT)")
        with pytest.raises(ValueError, match="invalid ast_cache_metadata schema"):
            schema.ensure_symbol_rows_backfilled(conn)
        conn.close()

    def test_legacy_symbol_migration_does_not_materialize_wrong_huge_marker(self):
        # PR #1253 review 3755736540: marker evidence selects only bounded existence.
        import tree_sitter_analyzer.index_snapshot_symbols as schema

        conn = self._legacy_symbol_connection('{"symbols": []}')
        conn.execute(
            "CREATE TABLE ast_cache_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO ast_cache_metadata VALUES (?, ?)",
            (schema._LEGACY_SYMBOL_MIGRATION_MARKER, "x" * 4096),
        )
        statements = []
        conn.set_trace_callback(statements.append)
        schema.ensure_symbol_rows_backfilled(conn)
        marker = conn.execute(
            "SELECT value FROM ast_cache_metadata WHERE key = ?",
            (schema._LEGACY_SYMBOL_MIGRATION_MARKER,),
        ).fetchone()
        conn.close()

        assert marker == ("complete",)
        marker_queries = [
            statement
            for statement in statements
            if statement.startswith("SELECT 1, typeof(value)")
        ]
        assert len(marker_queries) == 1
        assert "FROM ast_cache_metadata" in marker_queries[0]

    def test_zero_symbol_migration_writes_global_marker_and_does_not_reparse(
        self, monkeypatch
    ):
        # PR #1253 review thread 3888: empty projections still complete migration.
        import tree_sitter_analyzer.index_snapshot_symbols as schema

        conn = self._legacy_symbol_connection('{"symbols": []}')
        schema.ensure_symbol_rows_backfilled(conn)
        marker = conn.execute(
            "SELECT value FROM ast_cache_metadata WHERE key = ?",
            (schema._LEGACY_SYMBOL_MIGRATION_MARKER,),
        ).fetchone()
        monkeypatch.setattr(
            schema.json,
            "loads",
            lambda _raw: pytest.fail("completed legacy migration reparsed JSON"),
        )
        schema.ensure_symbol_rows_backfilled(conn)
        conn.close()

        assert marker == ("complete",)


@pytest.mark.parametrize("rows_to_keep", [0, 1])
def test_complete_marker_marks_incomplete_ordinary_rows_for_reindex(rows_to_keep):
    # PR #1253 review thread 3756380009: the marker is not projection evidence.
    from tree_sitter_analyzer.index_snapshot_symbols import (
        ensure_symbol_rows_backfilled,
    )

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT PRIMARY KEY, content_hash TEXT, "
        "language TEXT, symbols_json TEXT)"
    )
    payload = json.dumps(
        {
            "symbols": [
                {"name": "first", "kind": "function"},
                {"name": "second", "kind": "class"},
            ]
        }
    )
    conn.execute(
        "INSERT INTO ast_index VALUES ('a.py', 'hash-a', 'python', ?)", (payload,)
    )
    ensure_symbol_rows_backfilled(conn)
    conn.execute(
        "DELETE FROM ast_symbol_rows WHERE id NOT IN "
        "(SELECT id FROM ast_symbol_rows ORDER BY id LIMIT ?)",
        (rows_to_keep,),
    )

    ensure_symbol_rows_backfilled(conn)
    rows = conn.execute("SELECT name FROM ast_symbol_rows ORDER BY name").fetchall()
    state = conn.execute(
        "SELECT content_hash, symbol_count FROM ast_symbol_projection_state"
    ).fetchone()
    conn.close()

    expected_rows = [] if rows_to_keep == 0 else [("first",)]
    assert rows == expected_rows
    assert state is None


def test_complete_marker_repairs_projection_hash_mismatch():
    # PR #1253 review thread 3756380009: state must bind the ast_index generation.
    from tree_sitter_analyzer.index_snapshot_symbols import (
        ensure_symbol_rows_backfilled,
    )

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT PRIMARY KEY, content_hash TEXT, "
        "language TEXT, symbols_json TEXT)"
    )
    conn.execute(
        "INSERT INTO ast_index VALUES (?, ?, ?, ?)",
        ("a.py", "hash-a", "python", json.dumps({"symbols": []})),
    )
    ensure_symbol_rows_backfilled(conn)
    conn.execute("UPDATE ast_index SET content_hash = 'hash-b'")

    ensure_symbol_rows_backfilled(conn)
    state = conn.execute(
        "SELECT content_hash, symbol_count FROM ast_symbol_projection_state"
    ).fetchone()
    conn.close()

    assert state == ("hash-b", 0)


def test_symbol_row_upgrade_failure_rolls_back_table_creation():
    # PR #1253: malformed legacy state cannot leave an empty shadow table.
    from tree_sitter_analyzer.index_snapshot_symbols import (
        ensure_symbol_rows_backfilled,
    )

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT, language TEXT, symbols_json TEXT)"
    )
    conn.execute("INSERT INTO ast_index VALUES ('bad.py', 'python', '{')")

    with pytest.raises(json.JSONDecodeError):
        ensure_symbol_rows_backfilled(conn)
    table = conn.execute(
        "SELECT name FROM sqlite_master WHERE name = 'ast_symbol_rows'"
    ).fetchone()
    conn.close()

    assert table is None


@pytest.mark.parametrize(
    "symbols_json",
    [json.dumps({"symbols": {"name": "bad"}}), json.dumps({"symbols": ["bad"]})],
)
def test_symbol_row_upgrade_rejects_malformed_legacy_shapes(symbols_json):
    # PR #1253: malformed legacy symbol shapes roll back instead of shadowing JSON.
    from tree_sitter_analyzer.index_snapshot_symbols import (
        ensure_symbol_rows_backfilled,
    )

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT, language TEXT, symbols_json TEXT)"
    )
    conn.execute(
        "INSERT INTO ast_index VALUES ('bad.py', 'python', ?)", (symbols_json,)
    )

    with pytest.raises(ValueError, match="invalid legacy"):
        ensure_symbol_rows_backfilled(conn)
    table = conn.execute(
        "SELECT name FROM sqlite_master WHERE name = 'ast_symbol_rows'"
    ).fetchone()
    conn.close()

    assert table is None


def _untyped_legacy_connection(file_path="a.py", language="python", symbols_json="{}"):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index(file_path, language, symbols_json)")
    conn.execute(
        "INSERT INTO ast_index VALUES (?, ?, ?)", (file_path, language, symbols_json)
    )
    return conn


def test_symbol_upgrade_rejects_null_source_identity():
    # PR #1253: migration requires text file and language identities.
    from tree_sitter_analyzer.index_snapshot_symbols import (
        ensure_symbol_rows_backfilled,
    )

    conn = _untyped_legacy_connection(None, "python", "{}")
    with pytest.raises(ValueError, match="invalid legacy symbol source row"):
        ensure_symbol_rows_backfilled(conn)
    conn.close()


def test_symbol_upgrade_rejects_nontext_json_value():
    # PR #1253: materialized JSON must remain bytes or text.
    from tree_sitter_analyzer.index_snapshot_symbols import (
        ensure_symbol_rows_backfilled,
    )

    conn = _untyped_legacy_connection("a.py", "python", 7)
    with pytest.raises(ValueError, match="invalid legacy symbols_json"):
        ensure_symbol_rows_backfilled(conn)
    conn.close()


def test_symbol_upgrade_rejects_nontext_materialized_identity():
    # PR #1253: materialized identities are revalidated after preflight.
    from tree_sitter_analyzer.index_snapshot_symbols import (
        ensure_symbol_rows_backfilled,
    )

    conn = _untyped_legacy_connection(7, "python", "{}")
    with pytest.raises(ValueError, match="invalid legacy symbol source row"):
        ensure_symbol_rows_backfilled(conn)
    conn.close()


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


def test_symbol_upgrade_rejects_rows_appearing_after_preflight():
    # PR #1253: materialization cannot exceed its preflight row count.
    from tree_sitter_analyzer.index_snapshot_symbols import (
        ensure_symbol_rows_backfilled,
    )

    conn = _untyped_legacy_connection()
    conn.execute(
        "CREATE TABLE ast_symbol_rows(id INTEGER PRIMARY KEY, name TEXT, kind TEXT, "
        "file_path TEXT, language TEXT, line INTEGER, end_line INTEGER)"
    )
    conn.execute("INSERT INTO ast_symbol_rows VALUES (1, '', '', 'a.py', '', 0, 0)")
    raced = _MigrationRaceConnection(
        conn,
        lambda raw: raw.execute(
            "INSERT INTO ast_index VALUES ('b.py', 'python', '{}')"
        ),
    )
    with pytest.raises(
        sqlite3.OperationalError, match="LEGACY_SYMBOL_MIGRATION_BUDGET"
    ):
        ensure_symbol_rows_backfilled(raced)  # type: ignore[arg-type]
    conn.close()


def test_symbol_upgrade_rechecks_cell_budget_after_preflight(monkeypatch):
    # PR #1253: a row enlarged between queries cannot bypass the byte cap.
    import tree_sitter_analyzer.index_snapshot_symbols as schema

    conn = _untyped_legacy_connection(symbols_json="{}")
    raced = _MigrationRaceConnection(
        conn,
        lambda raw: raw.execute("UPDATE ast_index SET symbols_json = ?", ("x" * 11,)),
    )
    monkeypatch.setattr(schema, "_LEGACY_SYMBOL_MIGRATION_CELL_BYTE_BUDGET", 10)
    with pytest.raises(
        sqlite3.OperationalError, match="LEGACY_SYMBOL_MIGRATION_BUDGET"
    ):
        schema.ensure_symbol_rows_backfilled(raced)  # type: ignore[arg-type]
    conn.close()


def test_symbol_upgrade_progress_handler_interrupt_is_bounded(monkeypatch):
    # PR #1253: SQLite work is interrupted once the migration deadline expires.
    import tree_sitter_analyzer.index_snapshot_symbols as schema

    conn = _untyped_legacy_connection()
    state = {"query": False, "expired": None}

    class InterruptConnection(_MigrationRaceConnection):
        def set_progress_handler(self, handler, steps):
            if handler is None:
                return self.conn.set_progress_handler(None, steps)
            self.handler = handler
            return self.conn.set_progress_handler(handler, steps)

        def execute(self, query, params=()):
            if query.startswith("SELECT length"):
                state["query"] = True
                state["expired"] = self.handler()
                raise sqlite3.OperationalError("interrupted")
            return self.conn.execute(query, params)

    raced = InterruptConnection(conn, lambda _raw: None)
    monkeypatch.setattr(
        schema.time, "monotonic", lambda: 10.0 if state["query"] else 0.0
    )
    with pytest.raises(
        sqlite3.OperationalError, match="LEGACY_SYMBOL_MIGRATION_BUDGET"
    ):
        schema.ensure_symbol_rows_backfilled(raced)  # type: ignore[arg-type]
    assert state["expired"] == 1
    conn.close()


def test_exact_v12_projection_certification_preserves_all_symbol_references(tmp_path):
    # PR #1253 thread 3756769301: certification must never renumber exact rows.
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.index_snapshot_symbols import (
        ensure_symbol_rows_backfilled,
    )

    source = tmp_path / "app.py"
    source.write_text(
        "def target():\n    return 1\ndef caller():\n    return target()\n"
    )
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(source))
    conn = cache.get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO ast_symbol_activation "
        "(symbol_id, file_path, computed_at, git_state) VALUES (1, 'app.py', 1, 'clean')"
    )
    before = {
        "rows": [
            tuple(row)
            for row in conn.execute("SELECT id, name FROM ast_symbol_rows ORDER BY id")
        ],
        "fts": [
            tuple(row)
            for row in conn.execute("SELECT rowid FROM ast_symbols_fts ORDER BY rowid")
        ],
        "activation": [
            tuple(row)
            for row in conn.execute(
                "SELECT symbol_id, file_path FROM ast_symbol_activation ORDER BY symbol_id"
            )
        ],
        "callees": [
            tuple(row)
            for row in conn.execute(
                "SELECT callee_symbol_id FROM edges WHERE kind='calls' ORDER BY id"
            )
        ],
    }
    conn.execute("DELETE FROM ast_cache_metadata WHERE key='symbol_rows_projection_v1'")
    conn.execute("DELETE FROM ast_symbol_projection_state")
    conn.commit()

    assert ensure_symbol_rows_backfilled(conn) is True
    after = {
        "rows": [
            tuple(row)
            for row in conn.execute("SELECT id, name FROM ast_symbol_rows ORDER BY id")
        ],
        "fts": [
            tuple(row)
            for row in conn.execute("SELECT rowid FROM ast_symbols_fts ORDER BY rowid")
        ],
        "activation": [
            tuple(row)
            for row in conn.execute(
                "SELECT symbol_id, file_path FROM ast_symbol_activation ORDER BY symbol_id"
            )
        ],
        "callees": [
            tuple(row)
            for row in conn.execute(
                "SELECT callee_symbol_id FROM edges WHERE kind='calls' ORDER BY id"
            )
        ],
    }
    cache.close()

    assert after == before


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
        if query.startswith("SELECT file_path, symbol_count"):
            return _ProjectionCursor(self.states)
        if query.startswith("SELECT id, name, kind"):
            return _ProjectionCursor(self.symbol_rows)
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
