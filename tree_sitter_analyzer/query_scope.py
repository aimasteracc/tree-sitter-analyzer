"""查询作用域内的记忆化：缓存在一次回答内不变的计算。

RFC-0041：一次统一查询会针对同一索引状态，就许多符号反复调用同一批产出方
(``nav callers``)。其中一些子步骤读取的数据与符号无关 (例如索引中所有 ES
别名边)。在 :func:`query_scope` 内这类步骤只需计算一次；作用域之外每次调用
都实时计算，因此普通单次调用的行为不变。

作用域保存在 :class:`contextvars.ContextVar` 中，因此随所等待的 task 传递，
不会泄漏到并发请求。
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterator
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
