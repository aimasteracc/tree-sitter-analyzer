"""Fail-closed boundary tests for the index snapshot owner."""

from __future__ import annotations

import os
import sqlite3

import pytest

requires_posix_fd = pytest.mark.skipif(os.name != "posix", reason="GH-1253")
# 纯 SQLite 校验跨平台执行；需要 POSIX 描述符的用例保留各自的标记。


def _fd_is_closed(fd: int) -> bool:
    try:
        os.fstat(fd)
    except OSError:
        return True
    return False


def _legacy_cache_layout(tmp_path, layout):
    """用截至 v13 的真实迁移构造旧库，再分别附加 canonical 或实验布局。"""
    import json

    from tree_sitter_analyzer import ast_cache
    from tree_sitter_analyzer.cache import schema
    from tree_sitter_analyzer.index_snapshot_schema import apply_snapshot_migration

    root = tmp_path / "project"
    root.mkdir()
    directory = root / ".ast-cache"
    directory.mkdir()
    path = directory / "index.db"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    migrations = [(v, getattr(schema, f"apply_migration_v{v}")) for v in range(3, 13)]
    schema.init_db(
        conn, None, ast_cache._has_fts5, migrations + [(13, apply_snapshot_migration)]
    )
    symbols = [
        {"name": name, "kind": "function", "line": line, "end_line": line + 1}
        for name, line in [("run", 1), ("other", 4)]
    ]
    conn.execute(
        "INSERT INTO ast_index(file_path,content_hash,language,mtime_ns,file_size,indexed_at,symbols_json) VALUES ('a.py','original','python',0,0,'old',?)",
        (json.dumps({"symbols": symbols, "comments": []}),),
    )
    from tree_sitter_analyzer.cache.write import write_fts5_symbols

    write_fts5_symbols(conn, "a.py", "python", {"symbols": symbols})
    assert conn.execute(
        "SELECT id,name FROM ast_symbol_rows ORDER BY id"
    ).fetchall() == [(1, "run"), (2, "other")]
    conn.executemany(
        "INSERT INTO ast_symbol_activation(symbol_id,file_path,mod_count_30d,computed_at,git_state) VALUES (?,'a.py',?,123,'tracked')",
        [(1, 7), (2, 9)],
    )
    conn.execute("CREATE TABLE user_notes(id INTEGER PRIMARY KEY, payload BLOB)")
    conn.execute("INSERT INTO user_notes VALUES (99,?)", ("用户数据\x00保留".encode(),))
    if layout == "canonical15":
        schema.apply_migration_v14(conn, schema.record_schema_version)
        schema.apply_migration_v15(conn, schema.record_schema_version)
        conn.execute("UPDATE ast_index SET certified_at=456")
        conn.execute(
            "UPDATE ast_symbol_activation SET activation_state=CASE symbol_id WHEN 1 THEN 'computed' ELSE 'disabled' END"
        )
    elif layout == "experimental15":
        conn.executescript(schema.SCHEMA_V16_COMMENTS)
        conn.executescript(schema.SCHEMA_V17_LSP_CACHE)
        conn.execute(
            "ALTER TABLE ast_symbol_activation ADD COLUMN last_commit_msg TEXT"
        )
        conn.execute(
            "UPDATE ast_symbol_activation SET last_commit_msg='preserved message' WHERE symbol_id=2"
        )
        conn.execute(
            "INSERT INTO ast_symbol_comments(id,symbol_id,line,text,kind) VALUES (77,1,2,'用户注释','inline')"
        )
        conn.execute(
            "INSERT INTO edges(id,source_node_id,target_node_id,kind) VALUES (88,'source','target','calls')"
        )
        conn.execute(
            "INSERT INTO lsp_resolution_cache(symbol_id,edge_id,resolved_file,resolved_line,lsp_server,cached_at) VALUES (1,88,'target.py',3,'peer',22)"
        )
        schema.record_schema_version(
            conn, 14, "Pulse MVP: ast_symbol_comments + last_commit_msg"
        )
        schema.record_schema_version(conn, 15, "LSP resolution cache")
    conn.commit()
    conn.close()
    return root, path


@pytest.mark.parametrize("layout", ["v13", "canonical15", "experimental15"])
def test_legacy_layout_upgrade_preserves_data_and_is_idempotent(tmp_path, layout):
    """PR #1350/#1352：三种真实旧布局统一升级，不因相同版本号漏列或丢失用户投影。"""
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.index_snapshot_schema import validate_snapshot_schema

    root, path = _legacy_cache_layout(tmp_path, layout)
    cache = ASTCache(str(root), db_path=str(path))
    try:
        db = cache.get_conn()
        assert [
            r[0]
            for r in db.execute(
                "SELECT version FROM ast_schema_version WHERE version>=13 ORDER BY version"
            )
        ] == [13, 14, 15, 16, 17]
        assert validate_snapshot_schema(db) is None
        assert db.execute("SELECT certified_at FROM ast_index").fetchone()[0] == (
            456 if layout == "canonical15" else None
        )
        expected_states = [
            (1, 7, "pending"),
            (
                2,
                9,
                "disabled" if layout == "canonical15" else "pending",
            ),
        ]
        assert [
            tuple(r)
            for r in db.execute(
                "SELECT symbol_id,mod_count_30d,activation_state FROM ast_symbol_activation ORDER BY symbol_id"
            )
        ] == expected_states
        assert (
            db.execute("SELECT payload FROM user_notes WHERE id=99").fetchone()[0]
            == "用户数据\x00保留".encode()
        )
        assert (
            db.execute("SELECT content_hash FROM ast_index").fetchone()[0] == "original"
        )
        if layout == "experimental15":
            assert tuple(
                db.execute(
                    "SELECT id,symbol_id,text FROM ast_symbol_comments"
                ).fetchone()
            ) == (77, 1, "用户注释")
            assert tuple(
                db.execute(
                    "SELECT edge_id,resolved_file,resolved_line,cached_at FROM lsp_resolution_cache"
                ).fetchone()
            ) == (88, "target.py", 3, 22)
            assert (
                db.execute(
                    "SELECT last_commit_msg FROM ast_symbol_activation WHERE symbol_id=2"
                ).fetchone()[0]
                == "preserved message"
            )
        before = tuple(db.iterdump())
    finally:
        cache.close()
    reopened = ASTCache(str(root), db_path=str(path))
    try:
        assert tuple(reopened.get_conn().iterdump()) == before
    finally:
        reopened.close()


@pytest.mark.parametrize("layout", ["v13", "canonical15", "experimental15"])
@pytest.mark.parametrize("fault", ["record", "interrupt", "release"])
def test_entire_extension_upgrade_rolls_back_and_retries(tmp_path, layout, fault):
    """PR #1350/#1352：末次迁移的真实记录失败或 SQLite 中断必须回滚整次扩展升级。"""
    from tree_sitter_analyzer.cache import schema
    from tree_sitter_analyzer.index_snapshot_schema import (
        apply_snapshot_migration,
        validate_snapshot_schema,
    )

    _, path = _legacy_cache_layout(tmp_path, layout)
    db = sqlite3.connect(path)
    migrations = [(13, apply_snapshot_migration)] + [
        (v, getattr(schema, f"apply_migration_v{v}")) for v in range(14, 18)
    ]
    try:
        if fault == "record":
            db.execute(
                "CREATE TEMP TRIGGER deny_record BEFORE INSERT ON ast_schema_version WHEN NEW.version=17 BEGIN SELECT RAISE(ABORT,'record denied'); END"
            )
        elif fault == "interrupt":

            def interrupt(sql):
                if (
                    sql.startswith("INSERT OR IGNORE INTO ast_schema_version")
                    and "LSP resolution cache" in sql
                ):
                    db.interrupt()

            db.set_trace_callback(interrupt)
        else:
            denied = []

            def deny_release(action, operation, *_):
                if (
                    action == sqlite3.SQLITE_SAVEPOINT
                    and operation == "RELEASE"
                    and not denied
                ):
                    denied.append(True)
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK

            db.set_authorizer(deny_release)
        before = tuple(db.iterdump())
        with pytest.raises(
            sqlite3.DatabaseError, match="record denied|interrupted|not authorized"
        ):
            schema.init_db(db, False, None, migrations)
        db.set_trace_callback(None)
        db.set_authorizer(None)
        assert db.in_transaction is False
        assert tuple(db.iterdump()) == before
        db.execute("DROP TRIGGER IF EXISTS deny_record")
        schema.init_db(db, False, None, migrations)
        assert validate_snapshot_schema(db) is None
    finally:
        db.close()


def test_future_schema_is_rejected_without_mutating_cache(tmp_path):
    """PR #1350/#1352：未来 v18 在任何迁移写入之前被拒绝，原库保持可由新版处理。"""
    from tree_sitter_analyzer.ast_cache import ASTCache

    root, path = _legacy_cache_layout(tmp_path, "experimental15")
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO ast_schema_version VALUES (18,0,'future')")
    with sqlite3.connect(path) as db:
        before = tuple(db.iterdump())
    with pytest.raises(ValueError, match="INCOMPATIBLE_SCHEMA"):
        ASTCache(str(root), db_path=str(path))
    with sqlite3.connect(path) as db:
        assert tuple(db.iterdump()) == before


@pytest.mark.parametrize(
    "table,column",
    [("ast_symbol_comments", "text"), ("lsp_resolution_cache", "resolved_line")],
)
def test_unrecognized_experimental_shape_is_not_certified(tmp_path, table, column):
    """PR #1350/#1352：超出已知旧布局的缺列不能因 CREATE IF NOT EXISTS 被当成升级成功。"""
    from tree_sitter_analyzer.ast_cache import ASTCache

    root, path = _legacy_cache_layout(tmp_path, "experimental15")
    with sqlite3.connect(path) as db:
        db.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
        before = tuple(db.iterdump())
    with pytest.raises(sqlite3.OperationalError, match=column):
        ASTCache(str(root), db_path=str(path))
    with sqlite3.connect(path) as db:
        assert tuple(db.iterdump()) == before


@pytest.mark.parametrize(
    "version,table", [(16, "ast_symbol_comments"), (17, "lsp_resolution_cache")]
)
def test_failed_optional_migration_does_not_certify_schema(tmp_path, version, table):
    """PR #1352：只读存储上的迁移失败不能写入版本凭证，snapshot 校验必须拒绝残缺 schema。"""
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.cache import schema
    from tree_sitter_analyzer.index_snapshot_schema import validate_snapshot_schema

    cache = ASTCache(str(tmp_path))
    try:
        db = cache.get_conn()
        db.execute(f"DROP TABLE {table}")
        db.execute("DELETE FROM ast_schema_version WHERE version >= ?", (version,))
        db.commit()
        before = [
            tuple(r)
            for r in db.execute("SELECT * FROM ast_schema_version ORDER BY version")
        ]
        db.execute("PRAGMA query_only=ON")
        migration = getattr(schema, f"apply_migration_v{version}")
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            migration(db, schema.record_schema_version)
        assert [
            tuple(r)
            for r in db.execute("SELECT * FROM ast_schema_version ORDER BY version")
        ] == before
        with pytest.raises(ValueError, match="INCOMPATIBLE_SCHEMA"):
            validate_snapshot_schema(db)
    finally:
        cache.close()


def test_schema_version_rejects_unknown_row_immediately():
    # PR #1352：未来版本测试必须相对当前版本，不能用已支持的 14。
    from tree_sitter_analyzer.index_snapshot_schema import (
        SNAPSHOT_SCHEMA_VERSION,
        validate_snapshot_schema,
    )

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_schema_version(version)")
    conn.executemany(
        "INSERT INTO ast_schema_version VALUES(?)",
        [(SNAPSHOT_SCHEMA_VERSION + 1,), (SNAPSHOT_SCHEMA_VERSION,)],
    )
    with pytest.raises(ValueError, match="INCOMPATIBLE_SCHEMA"):
        validate_snapshot_schema(conn)
    conn.close()


@pytest.mark.parametrize("future_version", [None, 18])
def test_snapshot_reader_matches_latest_real_migration(tmp_path, future_version):
    # PR #1350/#1352：canonical 14/15 与新 16/17 必须同时存在，未来 18 不可接受。
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.index_snapshot_schema import (
        SNAPSHOT_SCHEMA_VERSION,
        validate_snapshot_schema,
    )

    cache = ASTCache(str(tmp_path))
    try:
        conn = cache.get_conn()
        versions = [
            row[0]
            for row in conn.execute(
                "SELECT version FROM ast_schema_version WHERE version >= 13 ORDER BY version"
            )
        ]
        assert versions == [13, 14, 15, 16, 17]
        assert SNAPSHOT_SCHEMA_VERSION == max(versions) == 17
        assert "certified_at" in {
            row[1] for row in conn.execute("PRAGMA table_info(ast_index)")
        }
        assert "activation_state" in {
            row[1] for row in conn.execute("PRAGMA table_info(ast_symbol_activation)")
        }
        if future_version is None:
            assert validate_snapshot_schema(conn) is None
        else:
            conn.execute(
                "INSERT INTO ast_schema_version(version, applied_at, description) "
                "VALUES (?, 0, 'future')",
                (future_version,),
            )
            with pytest.raises(ValueError, match="^INCOMPATIBLE_SCHEMA$"):
                validate_snapshot_schema(conn)
    finally:
        cache.close()


def test_schema_version_row_cap_precedes_table_inventory(monkeypatch):
    # PR #1253 review thread 3755297945: version history has an absolute cap.
    import tree_sitter_analyzer.index_snapshot_schema as schema

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_schema_version(version)")
    conn.executemany(
        "INSERT INTO ast_schema_version VALUES(?)",
        [(schema.SNAPSHOT_SCHEMA_VERSION,)] * 3,
    )
    monkeypatch.setattr(schema, "_SCHEMA_VALIDATION_ROW_BUDGET", 2)
    with pytest.raises(ValueError, match="INCOMPATIBLE_SCHEMA"):
        schema.validate_snapshot_schema(conn)
    conn.close()


def test_schema_table_cap_precedes_required_table_materialization(monkeypatch):
    # PR #1253 review thread 3755297945: sqlite_master enumeration is capped.
    import tree_sitter_analyzer.index_snapshot_schema as schema

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_schema_version(version)")
    conn.execute(
        "INSERT INTO ast_schema_version VALUES(?)", (schema.SNAPSHOT_SCHEMA_VERSION,)
    )
    monkeypatch.setattr(schema, "_SCHEMA_TABLE_BUDGET", 0)
    with pytest.raises(ValueError, match="INCOMPATIBLE_SCHEMA"):
        schema.validate_snapshot_schema(conn)
    conn.close()


def test_schema_column_cap_is_checked_per_required_table(monkeypatch):
    # PR #1253 review thread 3755297945: table_info enumeration is capped.
    import tree_sitter_analyzer.index_snapshot_schema as schema

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_schema_version(version)")
    conn.execute(
        "INSERT INTO ast_schema_version VALUES(?)", (schema.SNAPSHOT_SCHEMA_VERSION,)
    )
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

    # #1364 起错误消息携带诊断后缀(state/reason/行数),锚定前缀即可
    with pytest.raises(
        sqlite3.OperationalError, match=r"^SOURCE_CHANGED:state=[a-z]+:"
    ):
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
    conn.execute("INSERT INTO ast_schema_version VALUES ('15')")
    with pytest.raises(ValueError, match="INCOMPATIBLE_SCHEMA"):
        validate_snapshot_schema(conn)
    conn.close()


def test_schema_requires_current_version_row(monkeypatch):
    import tree_sitter_analyzer.index_snapshot_schema as schema

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_schema_version(version)")
    conn.execute("INSERT INTO ast_schema_version VALUES (15)")
    monkeypatch.setattr(schema, "SNAPSHOT_SCHEMA_VERSION", 99)
    with pytest.raises(ValueError, match="INCOMPATIBLE_SCHEMA"):
        schema.validate_snapshot_schema(conn)
    conn.close()


def test_schema_column_name_budget_rejects_first_column(monkeypatch):
    # PR #1253: required-table column metadata has an absolute byte cap.
    import tree_sitter_analyzer.index_snapshot_schema as schema

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_schema_version(version)")
    conn.execute(
        "INSERT INTO ast_schema_version VALUES (?)", (schema.SNAPSHOT_SCHEMA_VERSION,)
    )
    conn.execute("CREATE TABLE ast_index(file_path)")
    monkeypatch.setattr(schema, "_SCHEMA_CELL_BYTE_BUDGET", 0)
    with pytest.raises(ValueError, match="INCOMPATIBLE_SCHEMA"):
        schema.validate_snapshot_schema(conn)
    conn.close()


def test_schema_total_column_name_budget_rejects_before_collection(monkeypatch):
    import tree_sitter_analyzer.index_snapshot_schema as schema

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_schema_version(version)")
    conn.execute(
        "INSERT INTO ast_schema_version VALUES (?)", (schema.SNAPSHOT_SCHEMA_VERSION,)
    )
    conn.execute("CREATE TABLE ast_index(file_path)")
    monkeypatch.setattr(schema, "_SCHEMA_TOTAL_BYTE_BUDGET", 0)
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
            return Cursor([("blob", 8, None)])

    with pytest.raises(ValueError, match="INCOMPATIBLE_SCHEMA"):
        validate_snapshot_schema(HostileConnection())  # type: ignore[arg-type]


def test_schema_column_name_is_bounded_inside_sqlite_before_materialization():
    # PR #1253 Codex thread 3763183163: hostile PRAGMA names stay in SQLite.
    import tree_sitter_analyzer.index_snapshot_schema as schema

    class Cursor:
        def __init__(self, rows):
            self.rows = iter(rows)

        def fetchone(self):
            return next(self.rows, None)

    class OversizedNameConnection:
        def set_progress_handler(self, _handler, _steps):
            return None

        def execute(self, query, _params=()):
            if query.startswith("SELECT typeof(version)"):
                return Cursor([("integer", 2, 1, 1)])
            if query.startswith("SELECT count"):
                return Cursor([(1,)])
            if query.startswith("SELECT 1"):
                return Cursor([(1,)])
            assert "length(CAST(name AS BLOB))" in query
            assert "CASE WHEN" in query
            return Cursor([("text", schema._SCHEMA_CELL_BYTE_BUDGET + 1, None)])

    with pytest.raises(ValueError, match="INCOMPATIBLE_SCHEMA"):
        schema.validate_snapshot_schema(OversizedNameConnection())  # type: ignore[arg-type]


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


@requires_posix_fd
def test_read_existing_forces_memory_temp_store_before_fingerprint(
    tmp_path, monkeypatch
):
    # PR #1253 review thread 3757754345: ORDER BY sorters must never spill to disk.
    import tree_sitter_analyzer.index_snapshot as owner
    from tree_sitter_analyzer.ast_cache import ASTCache

    source = tmp_path / "sample.py"
    source.write_text("def sample():\n    return 1\n")
    cache = ASTCache(str(tmp_path))
    cache.index_project(workers=0)
    cache.close()
    sqlite_tmp = tmp_path / "sqlite-tmp"
    sqlite_tmp.mkdir()
    sqlite_tmp.chmod(0o500)
    monkeypatch.setenv("SQLITE_TMPDIR", str(sqlite_tmp))
    observed = []
    real_fingerprint = owner.index_fingerprint

    def fingerprint_with_temp_store_check(connection, root):
        observed.append(connection.execute("PRAGMA temp_store").fetchone()[0])
        return real_fingerprint(connection, root)

    monkeypatch.setattr(owner, "index_fingerprint", fingerprint_with_temp_store_check)
    try:
        snapshot = owner.read_existing_snapshot(str(tmp_path))
        with owner.acquire_index_snapshot(
            snapshot.snapshot_id, str(tmp_path)
        ) as acquired:
            evidence_temp_store = acquired[1].execute("PRAGMA temp_store").fetchone()[0]
        temp_names = sorted(path.name for path in sqlite_tmp.iterdir())
    finally:
        sqlite_tmp.chmod(0o700)

    assert (observed, evidence_temp_store, temp_names) == ([2], 2, [])


def test_memory_temp_store_configuration_failure_is_stable():
    # PR #1253 review thread 3757754345: pragma refusal fails with one stable reason.
    from tree_sitter_analyzer.index_snapshot_capability import require_memory_temp_store

    class RefusingConnection:
        def execute(self, query):
            if query == "PRAGMA temp_store=MEMORY":
                raise sqlite3.OperationalError("refused")
            return self

        def fetchone(self):
            return (1,)

    with pytest.raises(ValueError, match="^INDEX_TEMP_STORE_MEMORY_REQUIRED$"):
        require_memory_temp_store(RefusingConnection())


def test_memory_temp_store_unaccepted_value_is_stable():
    # PR #1253 review thread 3757754345: a silently ignored pragma also fails closed.
    from tree_sitter_analyzer.index_snapshot_capability import require_memory_temp_store

    class IgnoringConnection:
        def execute(self, _query):
            return self

        def fetchone(self):
            return (1,)

    with pytest.raises(ValueError, match="^INDEX_TEMP_STORE_MEMORY_REQUIRED$"):
        require_memory_temp_store(IgnoringConnection())
