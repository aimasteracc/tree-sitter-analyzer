"""#1833：行循环被中断时，持有游标的读取方不得继续锁住索引库。

#1832 的模式：游标存放在局部变量里，两行之间抛出异常；保留该异常（pytest 日志
捕获、带 ``exc_info`` 的日志记录）的任何人都让持有游标的帧存活，未读完的语句
继续持有读事务。连接关闭后成为僵尸，写入方或封存方的 ``wal_checkpoint`` /
切回回滚日志一直忙。每个用例在“异常仍被保留”时断言锁已释放。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.constraints.schema import Constraint


def _wal_database(path: Path, statements: list[tuple[str, list[tuple[Any, ...]]]]):
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        for ddl, rows in statements:
            conn.execute(ddl)
            if rows:
                marks = ",".join("?" * len(rows[0]))
                table = ddl.split()[2].split("(")[0]
                conn.executemany(f"INSERT INTO {table} VALUES ({marks})", rows)
        conn.commit()
    finally:
        conn.close()


def _interrupted_read_releases_lock(
    database: Path,
    read: Callable[[sqlite3.Connection], object],
    error: type[BaseException],
) -> None:
    reader = sqlite3.connect(database)
    kept: list[BaseException] = []
    try:
        read(reader)
    except error as exc:
        kept.append(exc)  # 与日志记录保留 exc_info 相同：traceback 与帧都存活
    finally:
        reader.close()
    assert kept, "the read must be interrupted mid-iteration"

    sealer = sqlite3.connect(database, timeout=0)
    try:
        assert sealer.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] == 0
        assert sealer.execute("PRAGMA journal_mode=DELETE").fetchone()[0] == "delete"
    finally:
        sealer.close()


def test_constraint_evaluation_deadline_mid_read_leaves_no_lock(tmp_path):
    from tree_sitter_analyzer.constraints.evaluator import evaluate

    database = tmp_path / "index.db"
    _wal_database(
        database,
        [
            (
                "CREATE TABLE edges (kind, caller_name, caller_file, caller_line,"
                " callee_name, callee_resolved_file, file_path)",
                [
                    ("calls", "a", "mcp/a.py", 1, "b", "cli/b.py", "mcp/a.py"),
                    ("calls", "c", "mcp/c.py", 2, "d", "cli/d.py", "mcp/c.py"),
                    ("calls", "e", "mcp/e.py", 3, "f", "cli/f.py", "mcp/e.py"),
                ],
            )
        ],
    )
    constraint = Constraint(
        id="no-cli",
        severity="error",
        rule="forbid",
        from_glob="mcp/**",
        to_glob="cli/**",
        reason="layering",
    )
    calls = iter(range(1_000))

    def deadline_on_second_check() -> None:
        if next(calls) == 1:
            raise TimeoutError

    _interrupted_read_releases_lock(
        database,
        lambda conn: evaluate(
            [constraint], conn, check_callback=deadline_on_second_check
        ),
        TimeoutError,
    )


def test_snapshot_get_imports_corrupt_row_leaves_no_lock(tmp_path):
    from tree_sitter_analyzer.index_snapshot_query import CertifiedSnapshotCache

    database = tmp_path / "index.db"
    _wal_database(
        database,
        [
            (
                "CREATE TABLE ast_index (file_path, imports_json)",
                [("a.py", json.dumps(["os"])), ("b.py", "not-json"), ("c.py", "[]")],
            )
        ],
    )

    class Owner:
        class snapshot:  # noqa: N801 - minimal stand-in for the owner contract
            canonical_root = tmp_path

        def __init__(self, conn: sqlite3.Connection) -> None:
            self.connection = conn

        def require_active(self) -> None:
            return None

    def read(conn: sqlite3.Connection) -> object:
        conn.row_factory = sqlite3.Row
        return CertifiedSnapshotCache(Owner(conn)).get_imports()

    _interrupted_read_releases_lock(database, read, ValueError)


def test_ordinary_symbol_counts_invalid_group_leaves_no_lock(tmp_path):
    from tree_sitter_analyzer.index_snapshot_symbols import ordinary_symbol_counts

    database = tmp_path / "index.db"
    _wal_database(
        database,
        [
            (
                "CREATE TABLE ast_symbol_rows (kind, language)",
                [
                    ("class", "python"),
                    (None, "python"),
                    ("function", "python"),
                ],  # NULL 组排在最前
            )
        ],
    )
    _interrupted_read_releases_lock(database, ordinary_symbol_counts, RuntimeError)


def test_ordinary_edge_counts_invalid_group_leaves_no_lock(tmp_path):
    from tree_sitter_analyzer.index_snapshot_symbols import ordinary_edge_counts

    database = tmp_path / "index.db"
    _wal_database(
        database,
        [("CREATE TABLE edges (kind)", [("calls",), (None,), ("extends",)])],
    )
    _interrupted_read_releases_lock(database, ordinary_edge_counts, RuntimeError)


def test_fallback_symbol_counts_corrupt_row_leaves_no_lock(tmp_path):
    from tree_sitter_analyzer.index_snapshot_symbols import fallback_symbol_counts

    database = tmp_path / "index.db"
    _wal_database(
        database,
        [
            (
                "CREATE TABLE ast_index (file_path, language, symbols_json)",
                [
                    ("a.py", "python", json.dumps({"symbols": []})),
                    ("b.py", "python", "not-json"),
                    ("c.py", "python", json.dumps({"symbols": []})),
                ],
            )
        ],
    )
    _interrupted_read_releases_lock(database, fallback_symbol_counts, ValueError)


def test_legacy_symbol_migration_corrupt_row_leaves_no_lock(tmp_path):
    from tree_sitter_analyzer.index_snapshot_symbols import (
        ensure_symbol_rows_backfilled,
    )

    database = tmp_path / "index.db"
    _wal_database(
        database,
        [
            (
                "CREATE TABLE ast_index (file_path, language, symbols_json)",
                [
                    ("a.py", "python", json.dumps({"symbols": []})),
                    ("b.py", "python", "not-json"),
                    ("c.py", "python", json.dumps({"symbols": []})),
                ],
            )
        ],
    )
    _interrupted_read_releases_lock(database, ensure_symbol_rows_backfilled, ValueError)


def test_unnamed_cursor_loop_is_already_safe(tmp_path):
    """守卫：``for row in conn.execute(...)`` 的游标只在求值栈上，异常展开时即释放。

    因此不命名游标的行循环（如 ``_candidate_caller_files``）无需额外处理；只有把
    游标存入局部变量的读取方才会成为僵尸（#1833 审计的判据）。
    """
    from tree_sitter_analyzer.constraints.evaluator_import_resolution import (
        _build_import_index,
    )

    database = tmp_path / "index.db"
    _wal_database(
        database,
        [
            (
                "CREATE TABLE ast_imports (file_path, module_path)",
                [("a.py", "x"), ("b.py", "y"), ("c.py", "z")],
            )
        ],
    )
    calls = iter(range(1_000))

    def deadline_on_second_check() -> None:
        if next(calls) == 1:
            raise TimeoutError

    _interrupted_read_releases_lock(
        database,
        lambda conn: _build_import_index(conn, check_callback=deadline_on_second_check),
        TimeoutError,
    )
