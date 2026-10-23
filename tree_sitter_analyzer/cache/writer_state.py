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

import re
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


_SAVEPOINT_SQL = re.compile(
    r"\s*(SAVEPOINT|RELEASE(?:\s+SAVEPOINT)?|ROLLBACK\s+TO(?:\s+SAVEPOINT)?)"
    r"\s+(\"?)(\w+)\2\s*;?\s*\Z",
    re.IGNORECASE,
)


class FencedConnection(sqlite3.Connection):
    """所有提交都先经修订号围栏；无围栏或未武装时与普通连接相同。

    除显式 ``commit()`` 外，SQLite 还会自行提交（#1664）：

    * 无事务时 ``SAVEPOINT`` 自己开启事务，释放最外层保存点即提交。武装后改为先
      ``BEGIN``，最外层 ``RELEASE`` 再交给 :meth:`commit`（经 CAS）；
    * ``executescript`` 先隐式提交挂起事务，再以自动提交逐句执行。武装后先经
      :meth:`commit` 提交挂起事务，脚本在 ``BEGIN`` 开启的事务内执行后同样经 CAS。

    没有行变化的事务（只读保存点、回滚到起点、只有 DDL 的脚本）不发布任何索引
    内容，直接结束而不推进修订号：读者不取写锁，也不使已绑定的候选失效。
    """

    tsa_fence: WriterFence | None = None
    # 本连接为最外层保存点自动开启的事务：保存点名栈与开启时的 total_changes。
    _tsa_savepoints: list[str] | None = None
    _tsa_changes_at_begin = 0

    def _fence_armed(self) -> bool:
        fence = self.tsa_fence
        return fence is not None and fence.armed

    def commit(self) -> None:
        self._tsa_savepoints = None
        fence = self.tsa_fence
        if fence is None:
            super().commit()
            return
        fence.commit(self, super().commit)

    def rollback(self) -> None:
        self._tsa_savepoints = None
        super().rollback()

    def execute(self, sql: str, parameters: Any = (), /) -> sqlite3.Cursor:
        match = _SAVEPOINT_SQL.match(sql) if self._fence_armed() else None
        if match is None:
            return super().execute(sql, parameters)
        return self._savepoint(match.group(1).split()[0].upper(), match.group(3), sql)

    def _savepoint(self, verb: str, name: str, sql: str) -> sqlite3.Cursor:
        """跟踪本连接自动开启的事务里的保存点；调用方自己的事务不受影响。"""
        stack = self._tsa_savepoints if self.in_transaction else None
        name = name.lower()
        if verb == "SAVEPOINT":
            if self.in_transaction:
                cursor = super().execute(sql)
            else:
                super().execute("BEGIN")
                stack = []
                self._tsa_changes_at_begin = self.total_changes
                try:
                    cursor = super().execute(sql)
                except BaseException:
                    self.rollback()  # 不留下没有保存点的自动事务
                    raise
            if stack is not None:
                stack.append(name)
            self._tsa_savepoints = stack
            return cursor
        cursor = super().execute(sql)
        if stack is None or name not in stack:
            return cursor  # 调用方自己事务内的保存点：释放它不会提交
        # SQLite 按名字匹配最近的同名保存点。
        depth = len(stack) - 1 - stack[::-1].index(name)
        if verb == "ROLLBACK":
            del stack[depth + 1 :]
            if depth == 0:
                # 回到自动事务的起点：此前的行变化都已撤销。
                self._tsa_changes_at_begin = self.total_changes
            return cursor
        del stack[depth:]
        if not stack:
            self._end_auto_transaction()
        return cursor

    def _end_auto_transaction(self) -> None:
        """最外层保存点已释放：SQLite 原本在此隐式提交，现在经围栏提交。"""
        try:
            if self.total_changes == self._tsa_changes_at_begin:
                self._tsa_savepoints = None
                super().commit()  # 无行变化：不发布内容，不推进修订号
            else:
                self.commit()
        except BaseException:
            # 与原先 RELEASE 失败不同，保存点已不存在：回滚，不留可能日后提交的事务。
            if self.in_transaction:
                self.rollback()
            raise

    def executescript(self, sql_script: str, /) -> sqlite3.Cursor:
        if not self._fence_armed():
            return super().executescript(sql_script)
        if self.in_transaction:
            self.commit()  # 代替 executescript 自己的隐式 COMMIT
        changes = self.total_changes
        try:
            cursor = super().executescript("BEGIN;\n" + sql_script)
        except BaseException:
            if self.in_transaction:
                self.rollback()
            raise
        if not self.in_transaction:
            return cursor
        if self.total_changes == changes:
            super().commit()  # 只有 DDL 或只读语句
        else:
            self.commit()
        return cursor


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
