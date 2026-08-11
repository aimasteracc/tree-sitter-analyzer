"""Fail-closed boundary tests for the index snapshot owner."""

from __future__ import annotations

import os
import sqlite3

import pytest

requires_posix_fd = pytest.mark.skipif(os.name != "posix", reason="GH-1253")
pytestmark = requires_posix_fd


def _fd_is_closed(fd: int) -> bool:
    try:
        os.fstat(fd)
    except OSError:
        return True
    return False


def test_schema_version_rejects_unknown_row_immediately():
    # PR #1253 review thread 3755297945: unknown versions fail while streaming.
    from tree_sitter_analyzer.index_snapshot_schema import validate_snapshot_schema

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_schema_version(version)")
    conn.executemany("INSERT INTO ast_schema_version VALUES(?)", [(14,), (13,)])
    with pytest.raises(ValueError, match="INCOMPATIBLE_SCHEMA"):
        validate_snapshot_schema(conn)
    conn.close()


def test_schema_version_row_cap_precedes_table_inventory(monkeypatch):
    # PR #1253 review thread 3755297945: version history has an absolute cap.
    import tree_sitter_analyzer.index_snapshot_schema as schema

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_schema_version(version)")
    conn.executemany("INSERT INTO ast_schema_version VALUES(13)", [()] * 3)
    monkeypatch.setattr(schema, "_SCHEMA_VALIDATION_ROW_BUDGET", 2)
    with pytest.raises(ValueError, match="INCOMPATIBLE_SCHEMA"):
        schema.validate_snapshot_schema(conn)
    conn.close()


def test_schema_table_cap_precedes_required_table_materialization(monkeypatch):
    # PR #1253 review thread 3755297945: sqlite_master enumeration is capped.
    import tree_sitter_analyzer.index_snapshot_schema as schema

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_schema_version(version)")
    conn.execute("INSERT INTO ast_schema_version VALUES(13)")
    monkeypatch.setattr(schema, "_SCHEMA_TABLE_BUDGET", 0)
    with pytest.raises(ValueError, match="INCOMPATIBLE_SCHEMA"):
        schema.validate_snapshot_schema(conn)
    conn.close()


def test_schema_column_cap_is_checked_per_required_table(monkeypatch):
    # PR #1253 review thread 3755297945: table_info enumeration is capped.
    import tree_sitter_analyzer.index_snapshot_schema as schema

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_schema_version(version)")
    conn.execute("INSERT INTO ast_schema_version VALUES(13)")
    conn.execute("CREATE TABLE ast_index(file_path)")
    monkeypatch.setattr(schema, "_SCHEMA_VALIDATION_COLUMN_BUDGET", 0)
    with pytest.raises(ValueError, match="INCOMPATIBLE_SCHEMA"):
        schema.validate_snapshot_schema(conn)
    conn.close()


def test_stamp_rejects_new_source_and_preserves_old_manifest(tmp_path):
    # PR #1253 review thread 2083: post-build additions prevent certification.
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.index_snapshot_schema import stamp_full_index_manifest

    source = tmp_path / "sample.py"
    source.write_text("value = 1\n")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(source))
    stamp_full_index_manifest(cache.get_conn(), str(tmp_path))
    (tmp_path / "late.py").write_text("late = True\n")

    with pytest.raises(sqlite3.OperationalError, match="^SOURCE_CHANGED$"):
        stamp_full_index_manifest(cache.get_conn(), str(tmp_path))
    count = (
        cache.get_conn()
        .execute("SELECT COUNT(*) FROM ast_index_snapshot_manifest")
        .fetchone()[0]
    )
    cache.close()
    assert count == 1


def test_fingerprint_ordering_interrupts_expired_sqlite_sort(monkeypatch):
    # PR #1253: SQLite's internal ORDER BY cannot run past the deadline.

    import tree_sitter_analyzer.index_snapshot_schema as schema

    class InterruptedConnection:
        def set_progress_handler(self, callback, _steps):
            self.callback = callback

        def execute(self, _query):
            assert self.callback() == 1
            raise sqlite3.OperationalError("interrupted")

    monkeypatch.setattr(schema.time, "monotonic", lambda: 2.0)
    with pytest.raises(RuntimeError, match="INDEX_FINGERPRINT_DEADLINE"):
        list(schema._deadline_ordered_rows(InterruptedConnection(), "SELECT 1", 1.0))


def test_fingerprint_ordering_maps_sqlite_interrupt_before_deadline(monkeypatch):
    # PR #1253: an interrupt is exposed through the same stable budget reason.

    import tree_sitter_analyzer.index_snapshot_schema as schema

    class InterruptedConnection:
        def set_progress_handler(self, callback, _steps):
            self.callback = callback

        def execute(self, _query):
            raise sqlite3.OperationalError("interrupted")

    monkeypatch.setattr(schema.time, "monotonic", lambda: 0.0)
    with pytest.raises(RuntimeError, match="INDEX_FINGERPRINT_DEADLINE"):
        list(schema._deadline_ordered_rows(InterruptedConnection(), "SELECT 1", 1.0))


def test_fingerprint_ordering_preserves_non_budget_sqlite_error(monkeypatch):
    # PR #1253: unrelated database faults are not mislabeled as deadlines.

    import tree_sitter_analyzer.index_snapshot_schema as schema

    class BrokenConnection:
        def set_progress_handler(self, callback, _steps):
            self.callback = callback

        def execute(self, _query):
            raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(schema.time, "monotonic", lambda: 0.0)
    with pytest.raises(sqlite3.OperationalError, match="disk I/O error"):
        list(schema._deadline_ordered_rows(BrokenConnection(), "SELECT 1", 1.0))


def test_failed_manifest_invalidation_rolls_back_locked_transaction():
    # PR #1253 review 3755386842: cleanup failure releases the original lock.
    from tree_sitter_analyzer.index_snapshot_schema import stamp_full_index_manifest

    class CleanupFailureConnection:
        in_transaction = False
        rolled_back = False

        def commit(self):
            self.in_transaction = False

        def rollback(self):
            self.rolled_back = True
            self.in_transaction = False

        def execute(self, query, _params=()):
            if query == "BEGIN IMMEDIATE":
                self.in_transaction = True
            elif query.startswith("SELECT COUNT(*) FROM ast_call_graph_state"):
                raise sqlite3.OperationalError("marker failure")
            elif query.startswith("DELETE FROM ast_index_snapshot_manifest"):
                raise sqlite3.OperationalError("delete failure")
            return self

    conn = CleanupFailureConnection()
    with pytest.raises(sqlite3.OperationalError, match="CALL_GRAPH_INCOMPLETE"):
        stamp_full_index_manifest(conn, ".")  # type: ignore[arg-type]
    assert (conn.rolled_back, conn.in_transaction) == (True, False)


def test_schema_version_rejects_huge_blob_without_fetching_value():
    # PR #1253 thread 3756228865: only typeof/length/booleans cross the boundary.
    from tree_sitter_analyzer.index_snapshot_schema import validate_snapshot_schema

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_schema_version(version)")
    conn.execute("INSERT INTO ast_schema_version VALUES(zeroblob(1048576))")
    with pytest.raises(ValueError, match="INCOMPATIBLE_SCHEMA"):
        validate_snapshot_schema(conn)
    conn.close()


def test_schema_version_rejects_text_version():
    # PR #1253: schema versions are strictly typed SQLite integers.
    from tree_sitter_analyzer.index_snapshot_schema import validate_snapshot_schema

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_schema_version(version)")
    conn.execute("INSERT INTO ast_schema_version VALUES ('13')")
    with pytest.raises(ValueError, match="INCOMPATIBLE_SCHEMA"):
        validate_snapshot_schema(conn)
    conn.close()


def test_schema_column_name_budget_rejects_first_column(monkeypatch):
    # PR #1253: required-table column metadata has an absolute byte cap.
    import tree_sitter_analyzer.index_snapshot_schema as schema

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_schema_version(version)")
    conn.execute("INSERT INTO ast_schema_version VALUES (13)")
    conn.execute("CREATE TABLE ast_index(file_path)")
    monkeypatch.setattr(schema, "_SCHEMA_CELL_BYTE_BUDGET", 0)
    with pytest.raises(ValueError, match="INCOMPATIBLE_SCHEMA"):
        schema.validate_snapshot_schema(conn)
    conn.close()


def test_schema_validation_normalizes_sqlite_interrupt(monkeypatch):
    # PR #1253: progress-handler interruption is a stable deadline failure.
    import tree_sitter_analyzer.index_snapshot_schema as schema

    class InterruptedConnection:
        def set_progress_handler(self, handler, _steps):
            if handler is not None:
                assert handler() == 1

        def execute(self, _query, _params=()):
            raise sqlite3.OperationalError("interrupted")

    monkeypatch.setattr(schema, "_FINGERPRINT_DEADLINE_SECONDS", -1.0)
    with pytest.raises(RuntimeError, match="INDEX_FINGERPRINT_DEADLINE"):
        schema.validate_snapshot_schema(InterruptedConnection())  # type: ignore[arg-type]


def test_schema_rejects_nontext_pragma_column_name():
    # PR #1253: hostile schema metadata cannot be decoded implicitly.
    from tree_sitter_analyzer.index_snapshot_schema import validate_snapshot_schema

    class Cursor:
        def __init__(self, rows):
            self.rows = iter(rows)

        def fetchone(self):
            return next(self.rows, None)

    class HostileConnection:
        def set_progress_handler(self, _handler, _steps):
            return None

        def execute(self, query, _params=()):
            if query.startswith("SELECT typeof(version)"):
                return Cursor([("integer", 2, 1, 1)])
            if query.startswith("SELECT count"):
                return Cursor([(1,)])
            if query.startswith("SELECT 1"):
                return Cursor([(1,)])
            return Cursor([(0, b"not-text")])

    with pytest.raises(ValueError, match="INCOMPATIBLE_SCHEMA"):
        validate_snapshot_schema(HostileConnection())  # type: ignore[arg-type]


def test_manifest_stamp_rejects_old_call_graph_pipeline_marker(tmp_path):
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.index_snapshot_schema import stamp_full_index_manifest

    source = tmp_path / "sample.py"
    source.write_text("value = 1\n")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(source))
    conn = cache.get_conn()
    conn.execute("UPDATE ast_call_graph_state SET pipeline_version = 1 WHERE id = 1")
    conn.commit()

    try:
        with pytest.raises(sqlite3.OperationalError, match="CALL_GRAPH_INCOMPLETE"):
            stamp_full_index_manifest(conn, str(tmp_path))
    finally:
        cache.close()


def test_module_exports_exact_focused_surface() -> None:
    from tree_sitter_analyzer import index_snapshot_schema_validation

    assert index_snapshot_schema_validation.__all__ == ["validate_snapshot_schema"]
