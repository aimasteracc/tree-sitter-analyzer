"""RFC-0032 slice 5：``WriterFence`` / ``FencedConnection`` 的边界单元测试。

端到端行为见 ``test_custom_writer_cas.py``；这里用内存库直接驱动围栏的每条失败路径。
"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest

import tree_sitter_analyzer.cache.writer_state as owner
from tree_sitter_analyzer.cache.admission import Superseded
from tree_sitter_analyzer.cache.writer_state import (
    REVISION_SUPERSEDED,
    STATE_MISSING,
    FencedConnection,
    WriterFence,
    WriterRevision,
    bind_writer_revision,
    read_writer_revision,
    seed_writer_state,
    writer_operation,
)


@pytest.fixture
def fenced():
    conn = sqlite3.connect(":memory:", factory=FencedConnection)
    conn.execute("CREATE TABLE data (value INTEGER)")
    seed_writer_state(conn)
    conn.commit()
    fence = WriterFence()
    fence.armed = True
    conn.tsa_fence = fence
    try:
        yield conn, fence
    finally:
        conn.close()


def _rows(conn) -> list[int]:
    return [row[0] for row in conn.execute("SELECT value FROM data ORDER BY value")]


def _bump_elsewhere(conn) -> None:
    """另一个写入者的已提交修订（同一内存库，绕过本围栏）。"""
    conn.tsa_fence, fence = None, conn.tsa_fence
    conn.execute("UPDATE ast_writer_state SET revision = revision + 1")
    conn.commit()
    conn.tsa_fence = fence


@pytest.mark.parametrize(
    "row",
    [("a" * 32, -1), ("short", 0), ("a" * 32, "1")],
    ids=["negative", "uuid", "text-revision"],
)
def test_malformed_writer_state_row_fails_closed(row):
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE TABLE ast_writer_state (id, cache_uuid, revision)")
        conn.execute("INSERT INTO ast_writer_state VALUES (1, ?, ?)", row)
        with pytest.raises(Superseded, match=f"^{STATE_MISSING}$"):
            read_writer_revision(conn)
    finally:
        conn.close()


def test_commit_outside_an_operation_advances_without_binding(fenced):
    conn, _ = fenced
    before = read_writer_revision(conn)
    conn.execute("INSERT INTO data VALUES (1)")
    conn.commit()
    assert read_writer_revision(conn) == WriterRevision(
        before.cache_uuid, before.revision + 1
    )


def test_connection_without_fence_commits_plainly():
    conn = sqlite3.connect(":memory:", factory=FencedConnection)
    try:
        conn.execute("CREATE TABLE data (value INTEGER)")
        conn.execute("INSERT INTO data VALUES (1)")
        conn.commit()  # 无 ast_writer_state 也不经围栏
        assert (conn.in_transaction, _rows(conn)) == (False, [1])
    finally:
        conn.close()


def test_swallowed_rejection_is_still_raised_and_rolled_back(fenced):
    conn, fence = fenced
    with pytest.raises(Superseded, match=f"^{REVISION_SUPERSEDED}$"):
        with fence.operation(conn, None):
            _bump_elsewhere(conn)
            conn.execute("INSERT INTO data VALUES (1)")
            with pytest.raises(Superseded):
                conn.commit()  # 内部代码吞掉拒绝后继续写
            conn.execute("INSERT INTO data VALUES (2)")
            with pytest.raises(Superseded):
                conn.commit()  # 失去写入权后一律拒绝
            conn.execute("INSERT INTO data VALUES (3)")  # 未提交即离开操作
    assert (conn.in_transaction, _rows(conn)) == (False, [])


def test_other_error_after_rejection_surfaces_as_superseded(fenced):
    conn, fence = fenced
    with pytest.raises(Superseded, match=f"^{REVISION_SUPERSEDED}$") as excinfo:
        with fence.operation(conn, None):
            _bump_elsewhere(conn)
            conn.execute("INSERT INTO data VALUES (1)")
            try:
                conn.commit()
            except Superseded:
                pass
            raise ValueError("follow-on failure")
    assert isinstance(excinfo.value.__cause__, ValueError)


def test_base_exception_resets_operation_state(fenced):
    conn, fence = fenced
    with pytest.raises(KeyboardInterrupt):
        with fence.operation(conn, None):
            conn.execute("INSERT INTO data VALUES (1)")
            raise KeyboardInterrupt
    # 操作状态已复位：之后的提交是未绑定提交，照常推进。
    conn.execute("INSERT INTO data VALUES (2)")
    conn.commit()
    assert _rows(conn) == [1, 2]


def test_commit_rolls_back_when_writer_state_disappears(fenced):
    conn, _ = fenced
    conn.execute("INSERT INTO data VALUES (1)")
    conn.execute("DROP TABLE ast_writer_state")
    with pytest.raises(Superseded, match=f"^{STATE_MISSING}$"):
        conn.commit()
    assert (conn.in_transaction, _rows(conn)) == (False, [])


def test_conditional_update_miss_is_rejected(fenced, monkeypatch):
    # 读到的修订与条件更新之间不一致（防御分支）：仍回滚并拒绝。
    conn, _ = fenced
    monkeypatch.setattr(
        owner,
        "_ADVANCE",
        "UPDATE ast_writer_state SET revision = revision + 1 "
        "WHERE id = 2 AND cache_uuid = ? AND revision = ?",
    )
    conn.execute("INSERT INTO data VALUES (1)")
    with pytest.raises(Superseded, match=f"^{REVISION_SUPERSEDED}$"):
        conn.commit()
    assert (conn.in_transaction, _rows(conn)) == (False, [])


def test_binding_helpers_ignore_caches_without_an_armed_fence(fenced):
    conn, fence = fenced
    no_fence = SimpleNamespace()
    unarmed = SimpleNamespace(_writer_fence=WriterFence())
    odd = SimpleNamespace(_writer_fence=fence, writer_revision=lambda: "not a rev")
    assert (
        bind_writer_revision(no_fence),
        bind_writer_revision(unarmed),
        bind_writer_revision(odd),
    ) == (None, None, None)
    with writer_operation(no_fence):
        conn.execute("INSERT INTO data VALUES (1)")
    conn.commit()
    assert _rows(conn) == [1]


def test_ast_cache_writer_revision_is_none_before_the_fence_is_armed(tmp_path):
    from tree_sitter_analyzer.ast_cache import ASTCache

    cache = ASTCache(str(tmp_path), str(tmp_path / "custom.db"))
    try:
        armed = cache.writer_revision()
        cache._writer_fence.armed = False
        assert (isinstance(armed, WriterRevision), cache.writer_revision()) == (
            True,
            None,
        )
    finally:
        cache.close()
