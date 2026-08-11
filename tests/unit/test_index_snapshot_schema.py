"""Fail-closed boundary tests for the index snapshot owner."""

from __future__ import annotations

import os
import sqlite3
import threading

import pytest

requires_posix_fd = pytest.mark.skipif(os.name != "posix", reason="GH-1253")
pytestmark = requires_posix_fd


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

    def test_schema_validation_rejects_missing_tables(self):
        from tree_sitter_analyzer.index_snapshot_schema import validate_snapshot_schema

        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE ast_schema_version(version INTEGER)")
        conn.execute("INSERT INTO ast_schema_version VALUES(13)")
        with pytest.raises(ValueError, match="INCOMPATIBLE_SCHEMA"):
            validate_snapshot_schema(conn)
        conn.close()

    def test_schema_validation_rejects_missing_columns(self):
        from tree_sitter_analyzer.index_snapshot_schema import validate_snapshot_schema

        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE ast_schema_version(version INTEGER)")
        conn.execute("INSERT INTO ast_schema_version VALUES(13)")
        for table in (
            "ast_index",
            "ast_symbol_rows",
            "ast_imports",
            "edges",
            "ast_index_snapshot_manifest",
        ):
            conn.execute(f'CREATE TABLE "{table}"(wrong INTEGER)')
        with pytest.raises(ValueError, match="INCOMPATIBLE_SCHEMA"):
            validate_snapshot_schema(conn)
        conn.close()

    def test_fingerprint_row_budget_is_bounded(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.index_snapshot_schema as schema

        self._certified_cache(tmp_path)
        conn = sqlite3.connect(tmp_path / ".ast-cache" / "index.db")
        monkeypatch.setattr(schema, "_FINGERPRINT_ROW_BUDGET", -1)
        with pytest.raises(RuntimeError, match="INDEX_FINGERPRINT_BUDGET"):
            schema.index_fingerprint(conn, str(tmp_path.resolve()))
        conn.close()

    def test_fingerprint_byte_budget_is_bounded(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.index_snapshot_schema as schema

        self._certified_cache(tmp_path)
        conn = sqlite3.connect(tmp_path / ".ast-cache" / "index.db")
        monkeypatch.setattr(schema, "_FINGERPRINT_BYTE_BUDGET", -1)
        with pytest.raises(RuntimeError, match="INDEX_FINGERPRINT_BUDGET"):
            schema.index_fingerprint(conn, str(tmp_path.resolve()))
        conn.close()

    def test_snapshot_migration_ignores_unsupported_database(self):
        from tree_sitter_analyzer.index_snapshot_schema import apply_snapshot_migration

        class Broken:
            def executescript(self, _sql):
                raise sqlite3.OperationalError("unsupported")

        apply_snapshot_migration(Broken(), lambda *_args: None)

    def test_index_fingerprint_deadline_is_enforced(self, monkeypatch):
        from types import SimpleNamespace

        import tree_sitter_analyzer.index_snapshot_schema as schema

        monkeypatch.setattr(schema, "time", SimpleNamespace(monotonic=lambda: 2.0))
        with pytest.raises(RuntimeError, match="INDEX_FINGERPRINT_DEADLINE"):
            schema._check_deadline(1.0)

    def test_manifest_stamp_rejects_nonbuilt_marker(self, tmp_path):
        from tree_sitter_analyzer.ast_cache import ASTCache
        from tree_sitter_analyzer.index_snapshot_schema import stamp_full_index_manifest

        cache = ASTCache(str(tmp_path))
        try:
            conn = cache.get_conn()
            conn.execute(
                "CREATE TABLE ast_call_graph_state "
                "(id INTEGER PRIMARY KEY, built INTEGER, built_at REAL)"
            )
            conn.execute("INSERT INTO ast_call_graph_state VALUES (1, 0, 0)")
            with pytest.raises(
                sqlite3.OperationalError, match="^CALL_GRAPH_INCOMPLETE$"
            ):
                stamp_full_index_manifest(conn, str(tmp_path))
        finally:
            cache.close()

    def test_typed_fingerprint_frames_float_exactly(self):
        import struct

        from tree_sitter_analyzer.index_snapshot_schema import _typed

        raw = struct.pack(">d", 1.5)
        assert _typed((1.5,)) == b"f" + len(raw).to_bytes(8, "big") + raw

    def test_fingerprint_preflight_rejects_oversize_cell_before_typed_encoding(
        self, monkeypatch
    ):
        # PR #1253 review thread 3883: immutable rows are bounded in SQLite first.
        import tree_sitter_analyzer.index_snapshot_schema as schema

        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE payload(value TEXT)")
        conn.execute("INSERT INTO payload VALUES ('xx')")
        monkeypatch.setattr(schema, "_FINGERPRINT_CELL_BYTE_BUDGET", 1)
        with pytest.raises(RuntimeError, match="INDEX_FINGERPRINT_CELL_BUDGET"):
            schema.index_fingerprint(conn, ".")
        conn.close()

    def test_resolve_state_is_excluded_from_index_fingerprint(self):
        # PR #1253 review thread 3886: mutable control state is not graph evidence.
        import tree_sitter_analyzer.index_snapshot_schema as schema

        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE graph(value TEXT)")
        conn.execute("INSERT INTO graph VALUES ('stable')")
        conn.execute("CREATE TABLE ast_resolve_state(value TEXT)")
        conn.execute("INSERT INTO ast_resolve_state VALUES ('one')")
        before = schema.index_fingerprint(conn, ".")
        conn.execute("UPDATE ast_resolve_state SET value = 'two'")
        after = schema.index_fingerprint(conn, ".")
        conn.close()

        assert after == before

    def test_fingerprint_preflight_rejects_oversize_row(self, monkeypatch):
        # PR #1253 review thread 3883: aggregate row materialization is bounded.
        import tree_sitter_analyzer.index_snapshot_schema as schema

        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE payload(left_value TEXT, right_value TEXT)")
        conn.execute("INSERT INTO payload VALUES ('a', 'b')")
        monkeypatch.setattr(schema, "_FINGERPRINT_ROW_BYTE_BUDGET", 1)
        with pytest.raises(RuntimeError, match="INDEX_FINGERPRINT_ROW_BUDGET"):
            schema.index_fingerprint(conn, ".")
        conn.close()

    def test_fingerprint_preflight_enforces_global_byte_budget(self, monkeypatch):
        # PR #1253 review thread 3883: preflight contributes to the global budget.
        import tree_sitter_analyzer.index_snapshot_schema as schema

        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE payload(value TEXT)")
        conn.execute("INSERT INTO payload VALUES ('a')")
        monkeypatch.setattr(schema, "_FINGERPRINT_BYTE_BUDGET", 0)
        with pytest.raises(RuntimeError, match="INDEX_FINGERPRINT_BUDGET"):
            schema._preflight_table_rows(conn, "payload", ('"value"',), float("inf"))
        conn.close()

    def test_fingerprint_sqlite_data_error_has_stable_reason(self):
        # PR #1253 review thread 3883: driver conversion faults map to unknown safely.
        import tree_sitter_analyzer.index_snapshot_schema as schema

        class DataErrorConnection:
            def set_progress_handler(self, _handler, _steps):
                return None

            def execute(self, _query):
                raise sqlite3.DataError("hostile conversion")

        with pytest.raises(RuntimeError, match="INDEX_FINGERPRINT_INVALID"):
            tuple(
                schema._deadline_ordered_rows(
                    DataErrorConnection(), "SELECT hostile", float("inf")
                )
            )


class TestPostEncodingFingerprintBudgets:
    def test_row_budget_is_enforced_after_encoding(self, monkeypatch):
        import tree_sitter_analyzer.index_snapshot_schema as schema

        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE sample (value TEXT)")
        conn.execute("INSERT INTO sample VALUES ('x')")
        monkeypatch.setattr(schema, "_preflight_table_rows", lambda *args: (0, 0))
        monkeypatch.setattr(schema, "_FINGERPRINT_ROW_BUDGET", 0)
        with pytest.raises(RuntimeError, match="INDEX_FINGERPRINT_BUDGET"):
            schema.index_fingerprint(conn, ".")
        conn.close()

    def test_byte_budget_is_enforced_after_encoding(self, monkeypatch):
        import tree_sitter_analyzer.index_snapshot_schema as schema

        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE sample (value TEXT)")
        conn.execute("INSERT INTO sample VALUES ('x')")
        monkeypatch.setattr(schema, "_preflight_table_rows", lambda *args: (0, 0))
        monkeypatch.setattr(schema, "_FINGERPRINT_BYTE_BUDGET", 0)
        with pytest.raises(RuntimeError, match="INDEX_FINGERPRINT_BUDGET"):
            schema.index_fingerprint(conn, ".")
        conn.close()


def test_schema_inventory_cell_is_bounded_before_text_decode():
    # PR #1253 review thread 2074: sqlite_master text is length-checked in SQLite.
    import tree_sitter_analyzer.index_snapshot_schema as schema

    class HostileSchemaConnection:
        def set_progress_handler(self, _handler, _steps):
            return None

        def execute(self, query):
            assert "length(CAST(name AS BLOB))" in query
            return [(schema._SCHEMA_CELL_BYTE_BUDGET + 1, 0)]

    with pytest.raises(RuntimeError, match="INDEX_FINGERPRINT_SCHEMA_CELL_BUDGET"):
        schema.index_fingerprint(HostileSchemaConnection(), ".")


def test_schema_inventory_table_count_is_bounded(monkeypatch):
    # PR #1253 review thread 2074: table inventory cannot grow without bound.
    import tree_sitter_analyzer.index_snapshot_schema as schema

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE sample(value TEXT)")
    monkeypatch.setattr(schema, "_SCHEMA_TABLE_BUDGET", 0)
    with pytest.raises(RuntimeError, match="INDEX_FINGERPRINT_SCHEMA_BUDGET"):
        schema.index_fingerprint(conn, ".")
    conn.close()


def test_manifest_stamp_blocks_concurrent_sqlite_epoch_mutation(tmp_path, monkeypatch):
    # PR #1253 review 3755216340: fingerprints and manifest share one writer lock.
    import tree_sitter_analyzer.index_snapshot_schema as schema
    from tree_sitter_analyzer.ast_cache import ASTCache

    source = tmp_path / "sample.py"
    source.write_text("value = 1\n")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(source))
    schema.stamp_full_index_manifest(cache.get_conn(), str(tmp_path))
    db_path = cache.db_path
    cache.close()
    entered = threading.Event()
    release = threading.Event()
    original_capture = schema.capture_current_source_snapshot

    def blocked_capture(*args, **kwargs):
        entered.set()
        assert release.wait(2.0) is True
        return original_capture(*args, **kwargs)

    monkeypatch.setattr(schema, "capture_current_source_snapshot", blocked_capture)
    errors: list[BaseException] = []

    def certify() -> None:
        conn = sqlite3.connect(db_path, timeout=2.0)
        try:
            schema.stamp_full_index_manifest(conn, str(tmp_path))
        except BaseException as exc:
            errors.append(exc)
        finally:
            conn.close()

    thread = threading.Thread(target=certify)
    thread.start()
    assert entered.wait(2.0) is True
    writer = sqlite3.connect(db_path, timeout=0.05)
    try:
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            writer.execute("UPDATE ast_index SET language = 'mutated'")
            writer.commit()
    finally:
        writer.close()
        release.set()
        thread.join(2.0)
    assert (thread.is_alive(), errors) == (False, [])
    conn = sqlite3.connect(db_path)
    manifest = conn.execute(
        "SELECT index_fingerprint FROM ast_index_snapshot_manifest"
    ).fetchone()[0]
    assert manifest == schema.index_fingerprint(conn, os.path.realpath(str(tmp_path)))
    conn.close()


def test_failed_stamp_rolls_back_without_deleting_an_unowned_manifest_epoch():
    # PR #1253 thread 3756001890: failed stamps never own cleanup rights.
    from tree_sitter_analyzer.index_snapshot_schema import stamp_full_index_manifest

    class FailingStampConnection:
        def __init__(self):
            self.events: list[str] = []
            self.in_transaction = False

        def commit(self):
            self.events.append("COMMIT")
            self.in_transaction = False

        def rollback(self):
            self.events.append("ROLLBACK")
            self.in_transaction = False

        def execute(self, query, _params=()):
            operation = " ".join(query.split())
            self.events.append(operation)
            if operation == "BEGIN IMMEDIATE":
                self.in_transaction = True
                return self
            if operation.startswith("SELECT COUNT(*) FROM ast_call_graph_state"):
                raise sqlite3.OperationalError("broken marker")
            return self

    conn = FailingStampConnection()
    with pytest.raises(sqlite3.OperationalError, match="CALL_GRAPH_INCOMPLETE"):
        stamp_full_index_manifest(conn, ".")  # type: ignore[arg-type]

    assert conn.events == [
        "COMMIT",
        "BEGIN IMMEDIATE",
        "SELECT COUNT(*) FROM ast_call_graph_state WHERE id IN (1, 2)",
        "ROLLBACK",
    ]


def test_begin_failure_does_not_attempt_manifest_cleanup():
    # PR #1253 review 3755386842: no lock means cleanup would race a later epoch.
    from tree_sitter_analyzer.index_snapshot_schema import stamp_full_index_manifest

    class BusyConnection:
        in_transaction = False

        def __init__(self):
            self.events: list[str] = []

        def commit(self):
            self.events.append("COMMIT")

        def rollback(self):
            self.events.append("ROLLBACK")

        def execute(self, query, _params=()):
            self.events.append(query)
            raise sqlite3.OperationalError("database is locked")

    conn = BusyConnection()
    with pytest.raises(sqlite3.OperationalError, match="database is locked"):
        stamp_full_index_manifest(conn, ".")  # type: ignore[arg-type]

    assert conn.events == ["COMMIT", "BEGIN IMMEDIATE"]


def test_generated_column_is_rejected_before_expression_evaluation() -> None:
    # PR #1253 review 3757662081: generated values must never bypass preflight.
    import tree_sitter_analyzer.index_snapshot_schema as schema

    calls = 0

    def huge_value() -> bytes:
        nonlocal calls
        calls += 1
        return b"x" * 1_000_000

    conn = sqlite3.connect(":memory:")
    conn.create_function("huge_value", 0, huge_value, deterministic=True)
    conn.execute(
        "CREATE TABLE payload(seed INTEGER, value BLOB "
        "GENERATED ALWAYS AS (huge_value()) VIRTUAL)"
    )
    conn.execute("INSERT INTO payload(seed) VALUES (1)")
    calls = 0

    with pytest.raises(RuntimeError, match="^INDEX_FINGERPRINT_UNSUPPORTED_SCHEMA$"):
        schema.index_fingerprint(conn, ".")
    conn.close()

    assert calls == 0


def test_generated_column_snapshot_status_is_stable_unknown(tmp_path) -> None:
    # PR #1253 review 3757662081: hostile schemas degrade to a stable status.
    from tree_sitter_analyzer.index_snapshot import read_existing_snapshot

    TestSnapshotFailureContracts._certified_cache(tmp_path)
    db_path = tmp_path / ".ast-cache" / "index.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE payload(seed INTEGER, value BLOB "
        "GENERATED ALWAYS AS (zeroblob(1000000000)) VIRTUAL)"
    )
    conn.commit()
    conn.close()

    snapshot = read_existing_snapshot(str(tmp_path))

    assert snapshot.completeness == "unknown"
    assert snapshot.reason == "INDEX_FINGERPRINT_UNSUPPORTED_SCHEMA"


def test_virtual_table_hidden_columns_are_outside_select_scope() -> None:
    # PR #1253 review 3757662081: SELECT * omits virtual-table hidden columns.
    import tree_sitter_analyzer.index_snapshot_schema as schema

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE VIRTUAL TABLE search USING fts5(content)")

    columns = schema._query_visible_columns(conn, "search", float("inf"))
    conn.close()

    assert columns == ("content",)


@pytest.mark.parametrize(
    "row",
    [
        (0,),
        (0, 42, "", 0, None, 0, 0),
        (0, "hidden", "", 0, None, 0, 4),
        (0, "hidden", "", 0, None, 0, 1),
    ],
)
def test_unsupported_table_xinfo_metadata_fails_closed(row: tuple[object, ...]) -> None:
    # PR #1253 review 3757662081: unknown xinfo layouts never reach SELECT.
    import tree_sitter_analyzer.index_snapshot_schema as schema

    class Connection:
        def execute(self, _query: str):
            class Cursor:
                rows = iter((row,))

                def fetchone(self):
                    return next(self.rows, None)

            return Cursor()

    with pytest.raises(RuntimeError, match="^INDEX_FINGERPRINT_UNSUPPORTED_SCHEMA$"):
        schema._query_visible_columns(Connection(), "payload", float("inf"))
