"""查询作用域内的记忆化：缓存在一次回答内不变的计算。

RFC-0041：一次统一查询会针对同一索引状态，就许多符号反复调用同一批产出方
(``nav callers``)。其中一些子步骤读取的数据与符号无关 (例如索引中所有 ES
别名边)。在 :func:`query_scope` 内这类步骤只需计算一次；作用域之外每次调用
都实时计算，因此普通单次调用的行为不变。

作用域保存在 :class:`contextvars.ContextVar` 中，因此随所等待的 task 传递，
不会泄漏到并发请求。
"""

from __future__ import annotations

import os
from collections.abc import Callable, Hashable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, TypeVar

T = TypeVar("T")

_SCOPE: ContextVar[dict[Hashable, Any] | None] = ContextVar(
    "tsa_query_scope", default=None
)


@contextmanager
def query_scope() -> Iterator[None]:
    """在代码块退出前记忆化 :func:`scoped` 的计算结果。"""
    token = _SCOPE.set({})
    try:
        yield
    finally:
        _SCOPE.reset(token)


def scoped(key: Hashable, compute: Callable[[], T]) -> T:
    """每个活动作用域与 ``key`` 只执行一次 ``compute()``；无作用域时实时计算。"""
    memo = _SCOPE.get()
    if memo is None:
        return compute()
    if key not in memo:
        memo[key] = compute()
    return memo[key]  # type: ignore[no-any-return]


def in_scope() -> bool:
    return _SCOPE.get() is not None


#: 文件数达到此值才并行 stat；更少时线程开销大于收益。
_PARALLEL_STAT_MIN = 64
#: 并行 stat 的线程数（``os.stat`` 释放 GIL）。
_STAT_WORKERS = 8


def _stat_or_none(path: str) -> os.stat_result | None:
    try:
        return os.stat(path)
    except OSError:
        return None


def scoped_stats(paths: Sequence[str]) -> list[os.stat_result | None]:
    """每个路径的 ``os.stat`` 结果（不可 stat 为 None）；作用域内每个路径只 stat 一次。

    RFC-0041 跨名批量：一次回答里新鲜度复核（``relation_freshness``）与非调用引用的
    词表核对（``reference_vocab``）各自对同一批已索引文件逐名重复 stat。作用域内一个
    答案只对应一个源码时刻，两处共用这里的记忆；尚未 stat 的路径多时并行完成。
    作用域外每次实时 stat，行为不变。
    """
    memo: dict[str, os.stat_result | None] | None = (
        scoped(("query_scope.stat",), dict) if in_scope() else None
    )
    if memo is None:
        return [_stat_or_none(path) for path in paths]
    missing = [path for path in dict.fromkeys(paths) if path not in memo]
    if len(missing) >= _PARALLEL_STAT_MIN:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=_STAT_WORKERS) as executor:
            results = list(executor.map(_stat_or_none, missing, chunksize=64))
    else:
        results = [_stat_or_none(path) for path in missing]
    memo.update(zip(missing, results, strict=True))
    return [memo[path] for path in paths]
