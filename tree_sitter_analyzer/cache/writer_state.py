"""自定义路径原地数据库的协作式修订号 CAS（RFC-0032 slice 5，schema 18，#1554）。

默认定位符由版本选择器 CAS 防护；自定义 ``db_path`` 仍原地写入。在那里，旧候选重放
或并发写入者会删除更新的行（rfcs/evidence/0032-feasibility E1/E1b：b.py 被删、
``ast_call_graph_state`` built→unbuilt、进程 exit 0）。

所有者决定（2026-10-14）：现在采用协作式修订号 CAS，迁移自定义存储留待主版本。

* ``ast_writer_state(id=1, cache_uuid, revision)`` 是唯一写入权威。
* 每个经 ``ASTCache.get_conn()`` 提交的写事务，在同一事务内以
  ``UPDATE ... WHERE revision=?`` 推进修订号（:class:`FencedConnection`）。
* 一次写入操作（:func:`writer_operation`）在开始时绑定修订号：候选已绑定时取其捕获
  时的修订号，否则取开始时的当前值。之后本操作的每次提交都要求修订号仍是自己上次
  看到的值；否则回滚该事务并抛 :class:`Superseded`（``INDEX_CANDIDATE_SUPERSEDED``），
  本操作后续提交一律拒绝，被拒绝的事务不留下任何行。
* 未绑定修订号的候选仍被接受（所有者决定，直至主版本），但并发写入照样被防护。

只防护同版本 TSA 写入者：旧版本进程或绕过 ``ASTCache`` 自开连接的原始 SQL 不推进
修订号，不在边界内。修订号是写入权威元数据，不进入 ``index_fingerprint``，也不替代
源码/索引指纹；它从不依赖时钟、mtime、哈希或可复用的行 ID。
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from .admission import Superseded

REVISION_SUPERSEDED = "INDEX_WRITER_REVISION_SUPERSEDED"
CACHE_REPLACED = "INDEX_WRITER_CACHE_REPLACED"
STATE_MISSING = "INDEX_WRITER_STATE_MISSING"

SCHEMA_V18_WRITER_STATE = """
CREATE TABLE IF NOT EXISTS ast_writer_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    cache_uuid TEXT NOT NULL CHECK (length(cache_uuid) = 32),
    revision INTEGER NOT NULL CHECK (revision >= 0)
)
"""
_SELECT_STATE = "SELECT cache_uuid, revision FROM ast_writer_state WHERE id = 1"
_ADVANCE = (
    "UPDATE ast_writer_state SET revision = revision + 1 "
    "WHERE id = 1 AND cache_uuid = ? AND revision = ?"
)


@dataclass(frozen=True)
class WriterRevision:
    """一个缓存实体（``cache_uuid``）中的一次写入修订。"""

    cache_uuid: str
    revision: int


def seed_writer_state(conn: sqlite3.Connection) -> None:
    """建表并写入初始行；已有合法行保持不变（迁移可重入）。"""
    conn.execute(SCHEMA_V18_WRITER_STATE)
    conn.execute(
        "INSERT OR IGNORE INTO ast_writer_state (id, cache_uuid, revision) "
        "VALUES (1, ?, 0)",
        (uuid.uuid4().hex,),
    )
    read_writer_revision(conn)


def read_writer_revision(conn: sqlite3.Connection) -> WriterRevision:
    """读取当前修订；表或行缺失、类型不符都失败关闭（``INDEX_WRITER_STATE_MISSING``）。"""
    try:
        cursor = conn.execute(_SELECT_STATE)
        try:
            rows = cursor.fetchall()  # 读完并关闭，不留下活动语句
        finally:
            cursor.close()
    except sqlite3.OperationalError as exc:
        raise Superseded(STATE_MISSING) from exc
    row = rows[0] if len(rows) == 1 else None
    if (
        row is None
        or not isinstance(row[0], str)
        or len(row[0]) != 32
        or type(row[1]) is not int
        or row[1] < 0
    ):
        raise Superseded(STATE_MISSING)
    return WriterRevision(row[0], row[1])


class _OperationState(threading.local):
    depth = 0
    expected: WriterRevision | None = None
    lost: str | None = None


class WriterFence:
    """一个 ``ASTCache`` 的修订号围栏；操作状态按线程区分。

    ``armed`` 在 schema 初始化完成后才置位：迁移本身的提交不推进修订号。
    """

    def __init__(self) -> None:
        self.armed = False
        self._state = _OperationState()

    @contextmanager
    def operation(
        self, conn: sqlite3.Connection, bound: WriterRevision | None
    ) -> Iterator[None]:
        """绑定本线程的一次写入操作；嵌套调用沿用最外层的绑定。"""
        state = self._state
        if state.depth == 0:
            current = read_writer_revision(conn)
            if bound is not None and bound != current:
                # 首次写入之前即拒绝过时候选：不读不写，逻辑转储不变。
                raise Superseded(_mismatch(bound, current))
            state.expected, state.lost = current, None
        state.depth += 1
        try:
            yield
        except Exception as exc:
            lost = self._finish(conn)
            if lost is not None and not isinstance(exc, Superseded):
                raise Superseded(lost) from exc
            raise
        except BaseException:
            self._finish(conn)
            raise
        lost = self._finish(conn)
        if lost is not None:
            # 操作内部吞掉了被拒绝的提交（例如记为 errors 后继续），仍须类型化抛出。
            raise Superseded(lost)

    def _finish(self, conn: sqlite3.Connection) -> str | None:
        state = self._state
        state.depth -= 1
        if state.depth:
            return None
        lost, state.expected, state.lost = state.lost, None, None
        if lost is not None and conn.in_transaction:
            conn.rollback()  # 失去写入权后未提交的语句也不得保留
        return lost

    def commit(self, conn: sqlite3.Connection, base_commit: Callable[[], None]) -> None:
        """在待提交事务内 CAS 推进修订号，然后提交；失配时回滚并抛出。"""
        if not self.armed or not conn.in_transaction:
            base_commit()
            return
        state = self._state
        if state.lost is not None:
            conn.rollback()
            raise Superseded(state.lost)
        try:
            current = read_writer_revision(conn)
        except Superseded:
            conn.rollback()
            raise
        expected = state.expected if state.depth else None
        if expected is not None and expected != current:
            self._reject(conn, _mismatch(expected, current))
        # 本事务已持有写锁，读到的是最新提交；条件更新再确认一次。
        advanced = conn.execute(_ADVANCE, (current.cache_uuid, current.revision))
        if advanced.rowcount != 1:
            self._reject(conn, REVISION_SUPERSEDED)
        base_commit()
        if state.depth:
            state.expected = WriterRevision(current.cache_uuid, current.revision + 1)

    def _reject(self, conn: sqlite3.Connection, code: str) -> None:
        conn.rollback()
        if self._state.depth:
            self._state.lost = code
        raise Superseded(code)


def _mismatch(expected: WriterRevision, current: WriterRevision) -> str:
    if expected.cache_uuid != current.cache_uuid:
        return CACHE_REPLACED
    return REVISION_SUPERSEDED


class FencedConnection(sqlite3.Connection):
    """``commit()`` 先经修订号围栏；无围栏时与普通连接相同。"""

    tsa_fence: WriterFence | None = None

    def commit(self) -> None:
        fence = self.tsa_fence
        if fence is None:
            super().commit()
            return
        fence.commit(self, super().commit)


def _armed_fence(cache: Any) -> WriterFence | None:
    fence = getattr(cache, "_writer_fence", None)
    return fence if isinstance(fence, WriterFence) and fence.armed else None


def bind_writer_revision(cache: Any) -> WriterRevision | None:
    """捕获候选之前调用：自定义路径缓存返回当前修订，其余（默认定位符等）返回 None。"""
    if _armed_fence(cache) is None:
        return None
    revision = cache.writer_revision()
    return revision if isinstance(revision, WriterRevision) else None


@contextmanager
def writer_operation(cache: Any, candidate: Any = None) -> Iterator[None]:
    """原地写入操作的边界；无围栏或未初始化的缓存不受影响。"""
    fence = _armed_fence(cache)
    if fence is None:
        yield
        return
    bound = getattr(candidate, "writer_revision", None)
    with fence.operation(
        cache.get_conn(), bound if isinstance(bound, WriterRevision) else None
    ):
        yield
