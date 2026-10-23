"""RFC-0039 slice 2：增量认证根（脏组跟踪、可证明时才增量、否则完整重算并注明原因）。"""

from __future__ import annotations

import sqlite3
import time

import pytest

from tree_sitter_analyzer import index_certification_tree as tree_mod
from tree_sitter_analyzer.cache import certification_tracking as ct

#: 夹具替换前的真实计划规则。
_real_verify_due = ct._verify_due

ROOT = "/root"


def _deadline() -> float:
    return time.monotonic() + 60


@pytest.fixture
def db(tmp_path):
    """一个已认证的父版本：v3 manifest、存放的叶、刚完成初始化的连接。"""
    path = tmp_path / "index.db"
    seed = sqlite3.connect(path)
    seed.executescript(
        """
        CREATE TABLE edges (file_path TEXT, callee_name TEXT);
        CREATE TABLE ast_symbol_comments (symbol_id INTEGER, text TEXT);
        CREATE TABLE ast_cache_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE ast_index_snapshot_manifest (
            singleton INTEGER PRIMARY KEY, canonical_root TEXT, source_fingerprint TEXT,
            index_fingerprint TEXT, file_count INTEGER, source_scope_descriptor TEXT,
            manifest_version INTEGER);
        INSERT INTO edges VALUES ('a.py', 'f'), ('b.py', 'g'), (NULL, 'n'), ('c.py', 'h');
        INSERT INTO ast_symbol_comments VALUES (1, 'c');
        """
    )
    tree = tree_mod.full_tree(seed, deadline=_deadline())
    tree_mod.store_leaves(seed, tree)
    # 盖章时装上的持久触发器与 stale=0 的状态行。
    ct._ensure_stale_triggers(seed, tree.tables)
    ct._write_state(seed, 0, int(time.time()))
    seed.execute(
        "INSERT INTO ast_index_snapshot_manifest VALUES (1, ?, 's', ?, 3, '{}', 3)",
        (ROOT, tree_mod.fold_root(ROOT, tree, _deadline())),
    )
    seed.commit()
    seed.close()
    conn = sqlite3.connect(path)
    ct.note_initialized(conn, migrated=False)
    yield conn, path
    conn.close()


@pytest.fixture(autouse=True)
def _scheduled_only(monkeypatch):
    # 只在测试显式要求时做完整校验，以便观察增量路径本身。
    monkeypatch.delenv(ct.VERIFY_ENV, raising=False)
    monkeypatch.setattr(ct, "_verify_due", lambda _conn: False)


def _stamp(conn):
    conn.execute("BEGIN IMMEDIATE")
    index, tree = ct.commitment(conn, ROOT, deadline=_deadline())
    conn.commit()
    return index, tree, ct.last_decision(conn)


def _full(conn) -> str:
    return tree_mod.certification_root(conn, ROOT, deadline=_deadline())


def test_a_tracked_refresh_folds_only_the_dirty_groups(db) -> None:
    conn, _path = db
    ct.arm(conn)
    conn.execute("UPDATE edges SET callee_name = 'changed' WHERE file_path = 'b.py'")
    conn.execute("DELETE FROM edges WHERE file_path = 'c.py'")
    conn.execute("INSERT INTO edges VALUES ('d.py', 'new')")
    conn.execute(
        "UPDATE edges SET callee_name = callee_name WHERE file_path = 'a.py'"
    )  # 值不变
    conn.commit()

    index, _tree, decision = _stamp(conn)

    assert decision == {
        "mode": "incremental",
        "reason": "DEPENDENCIES_TRACKED",
        "dirty_groups": 3,
    }
    assert index == _full(conn)


def test_dense_and_ungrouped_tables_are_rescanned_whole(db, monkeypatch) -> None:
    conn, _path = db
    monkeypatch.setattr(ct, "DENSE_FRACTION", 0.0)
    ct.arm(conn)
    conn.execute("UPDATE edges SET callee_name = 'x' WHERE file_path IS NULL")
    conn.execute("UPDATE ast_symbol_comments SET text = 'd'")
    conn.commit()
    index, _tree, decision = _stamp(conn)
    assert decision["mode"] == "incremental"
    assert index == _full(conn)


@pytest.mark.parametrize(
    ("prepare", "reason"),
    [
        (lambda conn, path: None, "NOT_ARMED"),
        (lambda conn, path: ct._INIT.pop(id(conn)) and ct.arm(conn), "NOT_INITIALIZED"),
        (
            lambda conn, path: (ct.note_initialized(conn, migrated=True), ct.arm(conn)),
            "MIGRATED",
        ),
        (
            lambda conn, path: (
                conn.execute("INSERT INTO edges VALUES ('e.py', 'x')"),
                ct.arm(conn),
            ),
            "WRITES_BEFORE_ARMING",
        ),
        (
            lambda conn, path: (ct.arm(conn), _commit_elsewhere(path)),
            "OTHER_CONNECTION_COMMITTED",
        ),
        # 上次盖章后别的连接（或盖章失败的运行、单文件写入）写过：持久触发器留下标记。
        (
            lambda conn, path: (_commit_elsewhere(path), ct.arm(conn)),
            "WRITTEN_SINCE_STAMP",
        ),
        (
            lambda conn, path: (
                conn.execute(
                    "DROP TRIGGER " + ct._stale_trigger_name("edges", "UPDATE")
                ),
                ct.note_initialized(conn, migrated=False),
                ct.arm(conn),
            ),
            "NO_STALE_TRACKING",
        ),
        (
            lambda conn, path: (
                ct.arm(conn),
                conn.execute("ALTER TABLE edges ADD COLUMN z TEXT"),
            ),
            "TABLES_CHANGED",
        ),
        (
            lambda conn, path: (
                ct.arm(conn),
                conn.execute(
                    "UPDATE ast_index_snapshot_manifest SET manifest_version = 2"
                ),
            ),
            "PARENT_NOT_V3",
        ),
        (
            lambda conn, path: (
                ct.arm(conn),
                conn.execute(f"UPDATE {tree_mod.LEAF_TABLE} SET leaf = x'00'"),
            ),
            "LEAVES_DO_NOT_FOLD",
        ),
    ],
)
def test_unprovable_refreshes_recompute_in_full_and_say_why(
    db, prepare, reason
) -> None:
    conn, path = db
    prepare(conn, path)
    conn.commit()
    index, _tree, decision = _stamp(conn)
    assert decision["mode"] == "full" and decision["reason"] == reason
    assert index == _full(conn)


def _commit_elsewhere(path) -> None:
    other = sqlite3.connect(path)
    other.execute("INSERT INTO edges VALUES ('z.py', 'other')")
    other.commit()
    other.close()


def test_a_missed_write_fails_closed_under_verification(db, monkeypatch) -> None:
    conn, _path = db
    monkeypatch.setattr(ct, "_verify_due", lambda _conn: True)
    ct.clear_mismatches()
    ct.arm(conn)
    conn.execute("UPDATE edges SET callee_name = 'changed' WHERE file_path = 'b.py'")
    conn.execute(f"DELETE FROM temp.{ct._DIRTY}")  # 模拟漏记的写入
    conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    with pytest.raises(sqlite3.OperationalError, match=ct.MISMATCH):
        ct.commitment(conn, ROOT, deadline=_deadline())
    conn.rollback()
    assert len(ct.mismatches()) == 1
    ct.clear_mismatches()


def test_verification_schedule_counts_incremental_stamps(db, monkeypatch) -> None:
    # 夹具替换了 `_verify_due`；这里直接检查真实的计划规则。
    conn, _path = db
    conn.execute(f"DELETE FROM {ct.STATE_TABLE}")
    assert ct._read_state(conn) is None
    assert _real_verify_due(conn) is True  # 没有计划状态：先完整校验
    ct._write_state(conn, ct.VERIFY_EVERY - 1, int(time.time()))
    assert _real_verify_due(conn) is True
    ct._write_state(conn, 0, int(time.time()))
    assert _real_verify_due(conn) is False
    ct._write_state(conn, 0, int(time.time()) - ct.VERIFY_MAX_AGE_SECONDS - 1)
    assert _real_verify_due(conn) is True
    monkeypatch.setenv(ct.VERIFY_ENV, "full")
    ct._write_state(conn, 0, int(time.time()))
    assert _real_verify_due(conn) is True


def test_incremental_and_full_stamps_advance_the_schedule(db) -> None:
    conn, _path = db
    ct.arm(conn)
    conn.execute("INSERT INTO edges VALUES ('e.py', 'x')")
    conn.commit()
    _stamp(conn)
    assert ct._read_state(conn)[0] == 1
    _stamp(conn)  # 未武装：完整重算，计数归零
    assert ct._read_state(conn)[0] == 0


@pytest.mark.parametrize(
    ("literal", "value"),
    [
        ("NULL", None),
        ("'a''b.py'", "a'b.py"),
        ("12", 12),
        ("1.5", 1.5),
        ("X'00ff'", b"\x00\xff"),
    ],
)
def test_quoted_group_values_round_trip(literal, value) -> None:
    assert ct._unquote(literal) == value


def test_disarm_removes_every_trigger(db) -> None:
    conn, _path = db
    ct.arm(conn)
    # 两张根内表（edges、ast_symbol_comments），各有 INSERT / UPDATE / DELETE 三个触发器。
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM sqlite_temp_master WHERE type='trigger'"
        ).fetchone()[0]
        == 6
    )
    ct.disarm(conn)
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM sqlite_temp_master WHERE type='trigger'"
        ).fetchone()[0]
        == 0
    )
    assert ct.last_decision(conn) is None


def test_arming_failures_never_raise(db) -> None:
    conn, _path = db
    closed = sqlite3.connect(":memory:")
    closed.close()
    ct.note_initialized(closed, migrated=False)
    ct.arm(closed)
    ct.disarm(closed)
    assert ct._token(closed, "arm") is None


def test_tracking_never_breaks_a_writers_conflict_clause(db) -> None:
    # 外层 INSERT OR REPLACE 覆盖触发器体内的冲突策略：同一组被写两次不得报错。
    conn, _path = db
    conn.execute(
        "CREATE TABLE IF NOT EXISTS keyed (file_path TEXT PRIMARY KEY, v TEXT)"
    )
    conn.commit()
    ct.note_initialized(conn, migrated=False)
    ct.arm(conn)
    conn.execute("INSERT OR REPLACE INTO keyed VALUES ('a.py', '1')")
    conn.execute("INSERT OR REPLACE INTO keyed VALUES ('a.py', '2')")
    conn.execute("UPDATE edges SET callee_name = 'x' WHERE file_path = 'a.py'")
    conn.execute("UPDATE edges SET callee_name = 'y' WHERE file_path = 'a.py'")
    conn.commit()
    index, _tree, _decision = _stamp(conn)
    # 新表不在父版本的叶里：完整重算；关键是写入语句没有因跟踪而失败。
    assert index == _full(conn)


def test_a_missing_stale_flag_is_not_trusted(db) -> None:
    conn, _path = db
    conn.execute("DELETE FROM ast_cache_metadata WHERE key = ?", (ct.STALE_KEY,))
    conn.commit()
    ct.note_initialized(conn, migrated=False)
    ct.arm(conn)
    _index, _tree, decision = _stamp(conn)
    assert (decision["mode"], decision["reason"]) == ("full", "NO_STALE_TRACKING")
    # 完整重算的盖章重新装上标记：下一轮可增量。
    flag = conn.execute(
        "SELECT value FROM ast_cache_metadata WHERE key = ?", (ct.STALE_KEY,)
    ).fetchone()
    assert flag == ("0",)


def test_an_old_format_state_table_is_rebuilt(db) -> None:
    conn, _path = db
    conn.execute(f"DROP TABLE {ct.STATE_TABLE}")
    conn.execute(f"CREATE TABLE {ct.STATE_TABLE} (id INTEGER PRIMARY KEY, extra TEXT)")
    ct._write_state(conn, 3, 7)
    assert ct._read_state(conn) == (3, 7)


def test_a_file_whose_rows_all_go_drops_its_leaf(db, monkeypatch) -> None:
    conn, _path = db
    monkeypatch.setattr(ct, "DENSE_FRACTION", 1.0)  # 逐组重算
    ct.arm(conn)
    conn.execute("DELETE FROM edges WHERE file_path = 'c.py'")
    conn.commit()
    index, tree, decision = _stamp(conn)
    assert decision["mode"] == "incremental"
    assert tree_mod.group_key("c.py") not in tree.leaves["edges"]
    assert index == _full(conn)


def test_reads_on_a_bare_connection_degrade_to_full() -> None:
    bare = sqlite3.connect(":memory:")
    try:
        assert ct._parent_root(bare, ROOT) is None
        assert ct._stored_leaves(bare, ()) is None
        assert ct._read_state(bare) is None
        assert ct._stale_blocker(bare, ()) == "NO_STALE_TRACKING"
        # 两个同类令牌表：无法确定，视为没有令牌。
        bare.execute(f"CREATE TEMP TABLE {ct._TOKENS}_arm_a (x)")
        bare.execute(f"CREATE TEMP TABLE {ct._TOKENS}_arm_b (x)")
        assert ct._token(bare, "arm") is None
    finally:
        bare.close()


def test_leaves_of_an_unknown_table_are_not_trusted(db) -> None:
    conn, _path = db
    conn.execute(f"INSERT INTO {tree_mod.LEAF_TABLE} VALUES ('gone', x'00', x'00')")
    tables = tree_mod.rooted_tables(conn, _deadline())
    assert ct._stored_leaves(conn, tables) is None


def test_sync_result_reports_the_certification_decision() -> None:
    from tree_sitter_analyzer.incremental_sync_support import SyncResult

    decision = {
        "mode": "incremental",
        "reason": "DEPENDENCIES_TRACKED",
        "dirty_groups": 2,
    }
    assert SyncResult(certification=decision).to_dict()["certification"] == decision
    assert "certification" not in SyncResult().to_dict()


def test_a_verified_incremental_stamp_resets_the_schedule(db, monkeypatch) -> None:
    conn, _path = db
    monkeypatch.setattr(ct, "_verify_due", lambda _conn: True)
    ct._write_state(conn, 5, int(time.time()))
    conn.commit()
    ct.note_initialized(conn, migrated=False)  # 上面的准备写入之后的新基线
    ct.arm(conn)
    conn.execute("UPDATE edges SET callee_name = 'v' WHERE file_path = 'a.py'")
    conn.commit()
    index, _tree, decision = _stamp(conn)
    assert decision["mode"] == "incremental"
    assert index == _full(conn)
    assert ct._read_state(conn)[0] == 0
