"""RFC-0032 slice 5（#1554）：自定义路径原地数据库的协作式修订号 CAS（schema 18）。

rfcs/evidence/0032-feasibility E1/E1b（2026-10-13）：自定义 ``db_path`` 上，旧候选重放
或暂停后恢复的写入者删除更新的 b.py、``ast_call_graph_state`` built→unbuilt、进程 exit 0。
所有交错都以事件或直接注入确定地制造，不用 sleep 竞速。
"""

from __future__ import annotations

import multiprocessing
import os
import sqlite3
import threading
from pathlib import Path

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.cache.admission import (
    INDEX_CANDIDATE_SUPERSEDED,
    INDEX_RECOVERY_REQUIRED,
    Superseded,
    admission_failure_of,
)
from tree_sitter_analyzer.cache.writer_state import (
    REVISION_SUPERSEDED,
    STATE_MISSING,
    WriterRevision,
)
from tree_sitter_analyzer.incremental_sync import IncrementalSync

_A = "def alpha():\n    return 1\n"
_A_CHANGED = "def alpha():\n    return 2\n"
_B = "def beta():\n    return alpha()\n"
_C = "def gamma():\n    return 3\n"
_EVENT_WAIT_S = 30


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "a.py").write_text(_A, encoding="utf-8")
    return root, tmp_path / "custom" / "index.db"


def _scope():
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor

    return make_source_scope_descriptor()


def _capture(root, cache=None):
    """捕获候选；给出缓存时先绑定其写入修订（RFC-0032 slice 5 的调用顺序）。"""
    from tree_sitter_analyzer.constants import EXCLUDE_DIRS
    from tree_sitter_analyzer.indexing_snapshot import (
        build_index_candidate_snapshot,
        walk_index_candidate_entries,
    )
    from tree_sitter_analyzer.project_graph import _language_from_ext

    revision = cache.writer_revision() if cache is not None else None
    scope = _scope()
    return build_index_candidate_snapshot(
        str(root),
        max_files=scope.certification_max_files,
        exclude_patterns=scope.effective_excludes,
        walk_fn=lambda path: walk_index_candidate_entries(
            path, excluded_dir_names=frozenset(EXCLUDE_DIRS)
        ),
        language_fn=_language_from_ext,
        writer_revision=revision,
    )


def _sync(cache, candidate=None, sync=None):
    scope = _scope()
    return (sync or IncrementalSync(cache)).sync(
        max_files=scope.certification_max_files,
        exclude_patterns=scope.effective_excludes,
        candidate_snapshot=candidate,
        source_scope=scope,
    )


def _sync_path(root, db, candidate=None):
    cache = ASTCache(str(root), str(db))
    try:
        return _sync(cache, candidate)
    finally:
        cache.close()


def _dump(db) -> tuple[str, ...]:
    connection = sqlite3.connect(db)
    try:
        return tuple(connection.iterdump())
    finally:
        connection.close()


def _files(db) -> list[str]:
    connection = sqlite3.connect(db)
    try:
        return [r[0] for r in connection.execute("SELECT file_path FROM ast_index")]
    finally:
        connection.close()


def _revision(db) -> int:
    connection = sqlite3.connect(db)
    try:
        return int(
            connection.execute("SELECT revision FROM ast_writer_state").fetchone()[0]
        )
    finally:
        connection.close()


def _assert_no_writer_holds_lock(db) -> None:
    """被拒绝的写入者不能留下持有写锁、日后可能提交的事务。"""
    connection = sqlite3.connect(db, timeout=0)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.rollback()
    finally:
        connection.close()


def _assert_superseded(excinfo, cause=REVISION_SUPERSEDED) -> None:
    failure = admission_failure_of(excinfo.value)
    assert failure is not None
    assert (failure.code, failure.cause_code) == (INDEX_CANDIDATE_SUPERSEDED, cause)


# --- schema 18 迁移 ---------------------------------------------------------------


def _versions(db) -> list[int]:
    connection = sqlite3.connect(db)
    try:
        return [
            r[0] for r in connection.execute("SELECT version FROM ast_schema_version")
        ]
    finally:
        connection.close()


def _downgrade_to_v17(db) -> None:
    """模拟 v17 自定义库：schema 18 只增加 ``ast_writer_state``。"""
    connection = sqlite3.connect(db)
    try:
        connection.execute("DROP TABLE ast_writer_state")
        connection.execute("DELETE FROM ast_schema_version WHERE version = 18")
        connection.commit()
    finally:
        connection.close()


def test_new_custom_database_records_schema_18_writer_state(project):
    root, db = project
    _sync_path(root, db)
    connection = sqlite3.connect(db)
    try:
        cache_uuid, revision = connection.execute(
            "SELECT cache_uuid, revision FROM ast_writer_state WHERE id = 1"
        ).fetchone()
    finally:
        connection.close()
    assert (18 in _versions(db), len(cache_uuid), int(cache_uuid, 16) >= 0) == (
        True,
        32,
        True,
    )
    assert revision > 0  # 同步的每次写入提交都推进修订号


def test_v17_custom_database_is_migrated_without_touching_index_rows(project):
    root, db = project
    _sync_path(root, db)
    _downgrade_to_v17(db)
    before = _dump(db)
    cache = ASTCache(str(root), str(db))
    try:
        revision = cache.writer_revision()
    finally:
        cache.close()
    after = _dump(db)
    assert isinstance(revision, WriterRevision) and revision.revision == 0
    # 迁移只增加控制表与版本凭证：已有行（含认证清单）逐行保留。
    added = set(after) - set(before)
    assert set(before) <= set(after)
    assert all(
        "ast_writer_state" in line or "ast_schema_version" in line for line in added
    )
    assert 18 in _versions(db)


def test_readers_accept_v17_and_v18_indexes(project):
    # 已发布的 v17 版本只读打开、不迁移；读者要求的快照版本仍为 17（18 只增加控制表）。
    from tree_sitter_analyzer.index_snapshot_schema import validate_snapshot_schema

    root, db = project
    _sync_path(root, db)
    for downgrade in (False, True):
        if downgrade:
            _downgrade_to_v17(db)
        connection = sqlite3.connect(Path(db).as_uri() + "?mode=ro", uri=True)
        try:
            assert validate_snapshot_schema(connection) is None
        finally:
            connection.close()


def test_future_schema_19_is_rejected_without_mutating_custom_database(project):
    root, db = project
    _sync_path(root, db)
    connection = sqlite3.connect(db)
    with connection:
        connection.execute("INSERT INTO ast_schema_version VALUES (19, 0, 'future')")
    connection.close()
    before = _dump(db)
    with pytest.raises(ValueError, match="INCOMPATIBLE_SCHEMA"):
        ASTCache(str(root), str(db))
    assert _dump(db) == before


def test_malformed_writer_state_rolls_back_the_whole_upgrade(project):
    root, db = project
    _sync_path(root, db)
    _downgrade_to_v17(db)
    connection = sqlite3.connect(db)
    with connection:
        connection.execute("CREATE TABLE ast_writer_state (id INTEGER PRIMARY KEY)")
    connection.close()
    before = _dump(db)
    with pytest.raises(sqlite3.OperationalError, match="cache_uuid"):
        ASTCache(str(root), str(db))
    assert _dump(db) == before


# --- 每次写入提交推进修订号；修订号不是索引内容 -----------------------------------------


def test_every_write_route_advances_the_revision(project):
    root, db = project
    _sync_path(root, db)
    cache = ASTCache(str(root), str(db))
    try:
        seen = [_revision(db)]
        (root / "a.py").write_text(_A_CHANGED, encoding="utf-8")
        assert cache.index_file(str(root / "a.py"))["status"] == "indexed"
        seen.append(_revision(db))
        cache.invalidate(str(root / "a.py"))
        seen.append(_revision(db))
        assert cache.index_project()["errors"] == 0
        seen.append(_revision(db))
    finally:
        cache.close()
    assert seen == sorted(set(seen))  # 严格递增


def test_revision_is_excluded_from_index_fingerprint(project):
    from tree_sitter_analyzer.index_snapshot_schema import index_fingerprint

    root, db = project
    _sync_path(root, db)
    connection = sqlite3.connect(db)
    try:
        before = index_fingerprint(connection, str(root))
        connection.execute("UPDATE ast_writer_state SET revision = revision + 7")
        connection.commit()
        assert index_fingerprint(connection, str(root)) == before
    finally:
        connection.close()


def test_default_locator_cache_has_no_writer_revision(project):
    # 默认定位符由版本选择器 CAS 防护（slice 1），候选不需要修订号绑定。
    root, _ = project
    cache = ASTCache(str(root))
    try:
        assert cache.writer_revision() is None
    finally:
        cache.close()


# --- E1：顺序重放过时的已绑定候选 ------------------------------------------------------


@pytest.mark.parametrize("route", ["sync", "index_project"])
def test_bound_obsolete_replay_is_superseded_and_preserves_dump(project, route):
    root, db = project
    _sync_path(root, db)
    capture_cache = ASTCache(str(root), str(db))
    try:
        old = _capture(root, capture_cache)
    finally:
        capture_cache.close()
    (root / "b.py").write_text(_B, encoding="utf-8")
    assert _sync_path(root, db).errors == 0
    before = _dump(db)
    cache = ASTCache(str(root), str(db))
    try:
        with pytest.raises(Superseded) as excinfo:
            if route == "sync":
                _sync(cache, old)
            else:
                cache.index_project(candidate_snapshot=old, source_scope=_scope())
        assert cache.get_conn().in_transaction is False
    finally:
        cache.close()
    _assert_superseded(excinfo)
    assert (_dump(db), sorted(_files(db))) == (before, ["a.py", "b.py"])
    _assert_no_writer_holds_lock(db)


def test_identical_bytes_replay_is_still_superseded(project):
    # E1 ABA（2026-10-13）：内容与 mtime 回到原值也不能复用旧候选。
    root, db = project
    source = root / "a.py"
    _sync_path(root, db)
    original = os.stat(source)
    cache = ASTCache(str(root), str(db))
    try:
        old = _capture(root, cache)
    finally:
        cache.close()
    source.write_text(_A_CHANGED, encoding="utf-8")
    assert _sync_path(root, db).errors == 0
    source.write_text(_A, encoding="utf-8")
    os.utime(source, ns=(original.st_atime_ns, original.st_mtime_ns))
    assert _sync_path(root, db).errors == 0
    before = _dump(db)
    with pytest.raises(Superseded) as excinfo:
        _sync_path(root, db, old)
    _assert_superseded(excinfo)
    assert _dump(db) == before


def test_replaced_custom_database_rejects_candidate_of_old_incarnation(project):
    from tree_sitter_analyzer.cache.writer_state import CACHE_REPLACED

    root, db = project
    _sync_path(root, db)
    cache = ASTCache(str(root), str(db))
    try:
        old = _capture(root, cache)
    finally:
        cache.close()
    for suffix in ("", "-wal", "-shm"):
        Path(f"{db}{suffix}").unlink(missing_ok=True)
    _sync_path(root, db)  # 新的数据库实体：新的 cache_uuid
    with pytest.raises(Superseded) as excinfo:
        _sync_path(root, db, old)
    _assert_superseded(excinfo, CACHE_REPLACED)


def test_unbound_candidate_stays_accepted_on_custom_path(project):
    # 所有者决定（2026-10-14）：自定义路径的未绑定候选在主版本之前仍被接受。
    root, db = project
    _sync_path(root, db)
    unbound = _capture(root)
    assert unbound.writer_revision is None
    assert _sync_path(root, db, unbound).errors == 0


# --- E1b：两个写入者交错，失败者得到类型化错误且不留下写入 --------------------------------


def _paused_sync(cache, pause_after, entered, release, outcome, candidate=None):
    """在 ``pause_after`` 给出的注入点暂停一个写入者；结果写入 ``outcome``。"""
    sync = IncrementalSync(cache)
    pause_after(sync, cache, entered, release)

    def run():
        try:
            outcome["result"] = _sync(cache, candidate, sync)
        except BaseException as exc:  # 线程边界：交给主线程断言
            outcome["error"] = exc
        finally:
            outcome["in_transaction"] = cache.get_conn().in_transaction

    return threading.Thread(target=run, name="tsa-paused-writer")


def _pause_before_first_write(sync, cache, entered, release):
    original = sync._load_indexed_rows

    def load_then_pause(conn):
        rows = original(conn)
        entered.set()
        assert release.wait(_EVENT_WAIT_S)
        return rows

    sync._load_indexed_rows = load_then_pause


def _pause_after_first_commit(sync, cache, entered, release):
    original = cache.index_file

    def index_then_pause(*args, **kwargs):
        result = original(*args, **kwargs)
        if not entered.is_set():
            # 暂停点在一次已提交写入之后，不持有写锁，胜者不会被阻塞。
            assert cache.get_conn().in_transaction is False
            entered.set()
            assert release.wait(_EVENT_WAIT_S)
        return result

    cache.index_file = index_then_pause


@pytest.mark.parametrize(
    "pause",
    [_pause_before_first_write, _pause_after_first_commit],
    ids=["before", "mid"],
)
def test_two_writers_on_one_custom_path_only_one_publishes(project, pause):
    root, db = project
    (root / "b.py").write_text(_B, encoding="utf-8")
    _sync_path(root, db)
    (root / "a.py").write_text(_A_CHANGED, encoding="utf-8")
    (root / "c.py").write_text(_C, encoding="utf-8")
    entered, release = threading.Event(), threading.Event()
    outcome: dict = {}
    loser_cache = ASTCache(str(root), str(db))
    loser = _paused_sync(loser_cache, pause, entered, release, outcome)
    try:
        loser.start()
        assert entered.wait(_EVENT_WAIT_S)
        # 失败者暂停期间，另一个写入者完成一次完整同步并认证。
        winner = _sync_path(root, db, _capture(root))
        assert (winner.errors, winner.scope_complete) == (0, True)
        after_winner = _dump(db)
    finally:
        release.set()
        loser.join(_EVENT_WAIT_S)
        loser_cache.close()
    assert loser.is_alive() is False
    assert isinstance(outcome.get("error"), Superseded), outcome
    failure = admission_failure_of(outcome["error"])
    assert failure is not None and failure.code == INDEX_CANDIDATE_SUPERSEDED
    assert outcome["in_transaction"] is False
    # 胜者的完整结果（含认证清单与调用图标记）逐行保留，失败者没有留下任何写入。
    assert _dump(db) == after_winner
    assert sorted(_files(db)) == ["a.py", "b.py", "c.py"]
    _assert_no_writer_holds_lock(db)


def _replay_in_child(root, db, captured, resume, queue):
    """子进程：绑定并捕获候选，等父进程完成更新的同步后重放（E1b）。"""
    cache = ASTCache(root, db)
    try:
        old = _capture(Path(root), cache)
        captured.set()
        if not resume.wait(_EVENT_WAIT_S):
            queue.put(("timeout", None))
            return
        try:
            _sync(cache, old)
        except Superseded as exc:
            failure = admission_failure_of(exc)
            queue.put(("superseded", failure.code if failure else None))
        else:
            queue.put(("written", None))
    finally:
        cache.close()


def test_obsolete_writer_in_another_process_is_superseded(project):
    # E1b（2026-10-13）：两个真实进程；子进程捕获后暂停，父进程完成更新的同步。
    root, db = project
    _sync_path(root, db)
    context = multiprocessing.get_context("spawn")
    captured, resume, queue = context.Event(), context.Event(), context.Queue()
    child = context.Process(
        target=_replay_in_child, args=(str(root), str(db), captured, resume, queue)
    )
    child.start()
    try:
        assert captured.wait(_EVENT_WAIT_S)
        (root / "b.py").write_text(_B, encoding="utf-8")
        assert _sync_path(root, db).errors == 0
        before = _dump(db)
        resume.set()
        assert queue.get(timeout=_EVENT_WAIT_S) == (
            "superseded",
            INDEX_CANDIDATE_SUPERSEDED,
        )
    finally:
        resume.set()
        child.join(_EVENT_WAIT_S)
    assert child.exitcode == 0
    assert (_dump(db), sorted(_files(db))) == (before, ["a.py", "b.py"])


# --- 写入状态缺失失败关闭；watcher 返回类型化答复 -------------------------------------------


def test_missing_writer_state_fails_closed_as_recovery_required(project):
    root, db = project
    _sync_path(root, db)
    cache = ASTCache(str(root), str(db))
    try:
        other = sqlite3.connect(db)
        with other:
            other.execute("DROP TABLE ast_writer_state")
        other.close()
        before = _dump(db)
        (root / "a.py").write_text(_A_CHANGED, encoding="utf-8")
        with pytest.raises(Superseded, match=f"^{STATE_MISSING}$") as excinfo:
            cache.index_file(str(root / "a.py"))
    finally:
        cache.close()
    failure = admission_failure_of(excinfo.value)
    assert failure is not None and failure.code == INDEX_RECOVERY_REQUIRED
    assert _dump(db) == before


def test_custom_path_watcher_reports_superseded_candidate(project, monkeypatch):
    # 注入交错：watcher 绑定修订并捕获候选之后、写入之前，另一写入者提交。
    import tree_sitter_analyzer.indexing_snapshot as snapshot_owner
    from tree_sitter_analyzer.file_watcher import FileWatcherDaemon

    root, db = project
    _sync_path(root, db)
    cache = ASTCache(str(root), str(db))
    watcher = FileWatcherDaemon(cache, debounce=0)
    original = snapshot_owner.build_index_candidate_snapshot
    retries: list[float | None] = []

    def capture_then_other_writer(*args, **kwargs):
        candidate = original(*args, **kwargs)
        # 另一个同版本写入者的一次提交（其提交同样经 CAS 推进修订号）。watcher 此时
        # 持有该库的进程内写锁，因此直接以独立连接模拟，避免同锁重入。
        other = sqlite3.connect(db)
        with other:
            other.execute("UPDATE ast_writer_state SET revision = revision + 1")
        other.close()
        return candidate

    monkeypatch.setattr(
        snapshot_owner, "build_index_candidate_snapshot", capture_then_other_writer
    )
    monkeypatch.setattr(
        watcher,
        "_request_sync",
        lambda *, retry=False, base_delay=None: retries.append(base_delay),
    )
    (root / "a.py").write_text(_A_CHANGED, encoding="utf-8")
    before = (_dump(db), _revision(db))
    try:
        result = watcher.trigger_sync()
    finally:
        watcher.stop()
        cache.close()
    assert (result["error_code"], result["cause_code"], result["retryable"]) == (
        INDEX_CANDIDATE_SUPERSEDED,
        REVISION_SUPERSEDED,
        True,
    )
    assert retries == [5.0]
    # watcher 没有写入：只有模拟写入者推进的修订号不同，其余逐行不变。
    revision_row = 'INSERT INTO "ast_writer_state" VALUES(1,\''
    unchanged = [line for line in before[0] if not line.startswith(revision_row)]
    assert [
        line for line in _dump(db) if not line.startswith(revision_row)
    ] == unchanged
    assert _revision(db) == before[1] + 1
