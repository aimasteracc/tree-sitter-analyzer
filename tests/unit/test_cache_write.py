"""Unit tests for lazy write_activation_for_file and _flush_pending_activations (REQ-U-305)."""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_activation_conn():
    """In-memory DB with ast_symbol_activation and ast_symbol_rows tables."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """CREATE TABLE ast_symbol_activation (
            symbol_id INTEGER PRIMARY KEY,
            file_path TEXT NOT NULL,
            last_modified_commit TEXT,
            last_modified_at INTEGER,
            mod_count_30d INTEGER NOT NULL DEFAULT 0,
            mod_count_90d INTEGER NOT NULL DEFAULT 0,
            mod_count_all INTEGER NOT NULL DEFAULT 0,
            computed_at INTEGER NOT NULL DEFAULT 0,
            git_state TEXT,
            activation_state TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE ast_symbol_rows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            file_path TEXT NOT NULL,
            language TEXT NOT NULL,
            line INTEGER NOT NULL DEFAULT 0,
            end_line INTEGER NOT NULL DEFAULT 0
        )"""
    )
    conn.commit()
    return conn


def _insert_symbol(conn, file_path, name="func", kind="function", line=1, end_line=3):
    cur = conn.execute(
        "INSERT INTO ast_symbol_rows (name, kind, file_path, language, line, end_line)"
        " VALUES (?, ?, ?, 'python', ?, ?)",
        (name, kind, file_path, line, end_line),
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# Case (a): write_activation_for_file writes pending state, NOT subprocess.run
# ---------------------------------------------------------------------------

class TestWriteActivationLazy:
    """REQ-U-305(a): write_activation_for_file must not call subprocess.run."""

    def test_writes_pending_state_without_subprocess(self):
        """Placeholder rows are written with activation_state='pending'."""
        from tree_sitter_analyzer.cache.write import write_activation_for_file

        conn = _make_activation_conn()
        symbol_id = _insert_symbol(conn, "src/a.py")
        symbol_rows = [{"id": symbol_id}]

        with patch("subprocess.run") as mock_run:
            with patch(
                "tree_sitter_analyzer.git_activation._activation_disabled",
                return_value=False,
            ):
                write_activation_for_file(conn, "src/a.py", symbol_rows, "/repo")

        mock_run.assert_not_called()

        row = conn.execute(
            "SELECT activation_state FROM ast_symbol_activation"
            " WHERE file_path = 'src/a.py'"
        ).fetchone()
        assert row is not None
        assert row[0] == "pending"

    def test_empty_symbol_rows_deletes_activation(self):
        """Empty inserted_symbol_rows removes existing activation rows."""
        from tree_sitter_analyzer.cache.write import write_activation_for_file

        conn = _make_activation_conn()
        # Pre-populate an activation row
        conn.execute(
            "INSERT INTO ast_symbol_activation (symbol_id, file_path,"
            " mod_count_30d, mod_count_90d, mod_count_all, computed_at)"
            " VALUES (99, 'src/a.py', 0, 0, 0, 0)"
        )
        conn.commit()

        write_activation_for_file(conn, "src/a.py", [], "/repo")

        row = conn.execute(
            "SELECT * FROM ast_symbol_activation WHERE file_path = 'src/a.py'"
        ).fetchone()
        assert row is None


# ---------------------------------------------------------------------------
# Case (c): TSA_INDEX_ACTIVATION=0 → activation_state='disabled'
# ---------------------------------------------------------------------------

class TestWriteActivationDisabled:
    """REQ-U-305(c): disabled activation writes 'disabled' rows, not 'pending'."""

    def test_disabled_writes_disabled_state(self):
        from tree_sitter_analyzer.cache.write import write_activation_for_file

        conn = _make_activation_conn()
        symbol_id = _insert_symbol(conn, "src/b.py")
        symbol_rows = [{"id": symbol_id}]

        with patch(
            "tree_sitter_analyzer.git_activation._activation_disabled",
            return_value=True,
        ):
            write_activation_for_file(conn, "src/b.py", symbol_rows, "/repo")

        row = conn.execute(
            "SELECT activation_state FROM ast_symbol_activation"
            " WHERE file_path = 'src/b.py'"
        ).fetchone()
        assert row is not None
        assert row[0] == "disabled"


# ---------------------------------------------------------------------------
# Case (b): _flush_pending_activations transitions pending → computed
# ---------------------------------------------------------------------------

class TestFlushPendingActivations:
    """REQ-U-305(b): _flush_pending_activations transitions pending→computed."""

    def _seed_pending(self, conn, file_path="src/c.py", symbol_id=1):
        """Insert a pending activation row."""
        conn.execute(
            "INSERT OR REPLACE INTO ast_symbol_activation"
            " (symbol_id, file_path, mod_count_30d, mod_count_90d,"
            "  mod_count_all, computed_at, activation_state)"
            " VALUES (?, ?, 0, 0, 0, 0, 'pending')",
            (symbol_id, file_path),
        )
        conn.execute(
            "INSERT OR REPLACE INTO ast_symbol_rows"
            " (id, name, kind, file_path, language, line, end_line)"
            " VALUES (?, 'fn', 'function', ?, 'python', 1, 5)",
            (symbol_id, file_path),
        )
        conn.commit()

    def test_pending_transitions_to_computed(self):
        """After flush, activation_state changes from 'pending' to 'computed'."""
        from tree_sitter_analyzer.cache.write import _flush_pending_activations

        conn = _make_activation_conn()
        self._seed_pending(conn)

        fake_row = MagicMock()
        fake_row.symbol_id = 1
        fake_row.last_modified_commit = "abc123"
        fake_row.last_modified_at = 1000
        fake_row.mod_count_30d = 5
        fake_row.mod_count_90d = 10
        fake_row.mod_count_all = 20
        fake_row.computed_at = 9999
        fake_row.git_state = "tracked"

        with patch(
            "tree_sitter_analyzer.git_activation.compute_symbol_activation",
            return_value=[fake_row],
        ):
            result = _flush_pending_activations(conn, "/repo")

        assert result["flushed"] == 1
        assert result["errors"] == 0

        row = conn.execute(
            "SELECT activation_state FROM ast_symbol_activation WHERE file_path = 'src/c.py'"
        ).fetchone()
        assert row is not None
        assert row[0] == "computed"

    def test_git_error_degrades_to_computed_zero(self):
        """Git failure marks rows 'computed' with zero counts (REQ-E-304(d))."""
        from tree_sitter_analyzer.cache.write import _flush_pending_activations

        conn = _make_activation_conn()
        self._seed_pending(conn, "src/d.py", symbol_id=2)

        with patch(
            "tree_sitter_analyzer.git_activation.compute_symbol_activation",
            side_effect=RuntimeError("git failure"),
        ):
            result = _flush_pending_activations(conn, "/repo")

        assert result["errors"] == 1

        row = conn.execute(
            "SELECT activation_state, mod_count_30d"
            " FROM ast_symbol_activation WHERE file_path = 'src/d.py'"
        ).fetchone()
        assert row is not None
        # After degradation: state is 'computed', counts remain 0
        assert row[0] == "computed"
        assert row[1] == 0

    def test_absent_activation_state_column_returns_empty(self):
        """Pre-v15 DB without activation_state column returns zeros gracefully."""
        from tree_sitter_analyzer.cache.write import _flush_pending_activations

        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE ast_symbol_activation"
            " (symbol_id INTEGER PRIMARY KEY, file_path TEXT NOT NULL,"
            "  mod_count_30d INTEGER NOT NULL DEFAULT 0,"
            "  mod_count_90d INTEGER NOT NULL DEFAULT 0,"
            "  mod_count_all INTEGER NOT NULL DEFAULT 0,"
            "  computed_at INTEGER NOT NULL DEFAULT 0)"
        )
        conn.commit()

        result = _flush_pending_activations(conn, "/repo")
        assert result == {"flushed": 0, "errors": 0}


# ---------------------------------------------------------------------------
# Migration v15 idempotency
# ---------------------------------------------------------------------------

class TestApplyMigrationV15:
    """apply_migration_v15 is idempotent and adds activation_state."""

    def test_adds_activation_state_column(self):
        from tree_sitter_analyzer.cache.schema import apply_migration_v15

        conn = sqlite3.connect(":memory:")
        conn.execute(
            """CREATE TABLE ast_symbol_activation (
                symbol_id INTEGER PRIMARY KEY,
                file_path TEXT NOT NULL,
                mod_count_30d INTEGER NOT NULL DEFAULT 0,
                mod_count_90d INTEGER NOT NULL DEFAULT 0,
                mod_count_all INTEGER NOT NULL DEFAULT 0,
                computed_at INTEGER NOT NULL DEFAULT 0
            )"""
        )
        conn.execute(
            "CREATE TABLE ast_schema_version (version INTEGER PRIMARY KEY, note TEXT)"
        )
        conn.commit()

        record_calls = []

        def record_fn(c, version, note):
            record_calls.append((version, note))

        apply_migration_v15(conn, record_fn)

        cols = {r[1] for r in conn.execute(
            "PRAGMA table_info(ast_symbol_activation)"
        ).fetchall()}
        assert "activation_state" in cols
        assert any(v == 15 for v, _ in record_calls)

    def test_idempotent_when_column_already_exists(self):
        from tree_sitter_analyzer.cache.schema import apply_migration_v15

        conn = sqlite3.connect(":memory:")
        conn.execute(
            """CREATE TABLE ast_symbol_activation (
                symbol_id INTEGER PRIMARY KEY,
                file_path TEXT NOT NULL,
                activation_state TEXT
            )"""
        )
        conn.execute(
            "CREATE TABLE ast_schema_version (version INTEGER PRIMARY KEY, note TEXT)"
        )
        conn.commit()

        # Should not raise even when column already exists
        apply_migration_v15(conn, lambda c, v, n: None)
        apply_migration_v15(conn, lambda c, v, n: None)
