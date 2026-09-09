"""一次工具调用固定读版本；下一次调用重新解析选择器。"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from .generation_routing import (
    _WRITERS,
    IndexLocation,
    logical_index_path,
    resolve_index_location,
)

_READERS: ContextVar[dict[str, IndexLocation] | None] = ContextVar(
    "tsa_generation_readers", default=None
)


@contextmanager
def generation_read_scope() -> Iterator[None]:
    """嵌套 facade 共用外层调用的版本绑定，退出后不向下次调用泄漏。"""
    if _READERS.get() is not None:
        yield
        return
    token = _READERS.set({})
    try:
        yield
    finally:
        _READERS.reset(token)


def current_read_location(root: str) -> IndexLocation | None:
    scope = _READERS.get()
    if scope is None:
        return None
    key = str(logical_index_path(root))
    private = (_WRITERS.get() or {}).get(key)
    if private is not None:
        return private
    if key not in scope:
        scope.setdefault(key, resolve_index_location(root))
    return scope[key]
