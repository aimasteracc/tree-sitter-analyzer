"""一次工具调用固定读版本；下一次调用重新解析选择器。"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from .generation_reader_release import (
    bind_in_flight,
    release_idle_readers,
    unbind_in_flight,
)
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
    """嵌套 facade 共用外层调用的版本绑定，退出后不向下次调用泄漏。

    #1631：最外层调用结束时撤销其版本绑定，并释放本线程空闲读者对已退役版本的
    连接与钉，使下一次发布（含 watcher 线程的发布）能够回收它们。
    """
    if _READERS.get() is not None:
        yield
        return
    scope: dict[str, IndexLocation] = {}
    token = _READERS.set(scope)
    try:
        yield
    finally:
        _READERS.reset(token)
        unbind_in_flight(scope.values())
        release_idle_readers()


def adopt_read_location(root: str, location: IndexLocation) -> None:
    """本次调用自己发布的版本对同一调用的后续读取可见（读己之写）。

    首次发布前绑定的是旧定位符；若仍沿用它，同一调用在写入后会去打开
    （并创建）旧 ``index.db``（#1554）。其他写者的发布仍不改变当前绑定。
    """
    scope = _READERS.get()
    if scope is not None:
        key = str(logical_index_path(root))
        previous = scope.get(key)
        scope[key] = location
        bind_in_flight(location)
        if previous is not None:
            unbind_in_flight([previous])


def current_read_location(root: str) -> IndexLocation | None:
    scope = _READERS.get()
    if scope is None:
        return None
    key = str(logical_index_path(root))
    private = (_WRITERS.get() or {}).get(key)
    if private is not None:
        return private
    if key not in scope:
        location = resolve_index_location(root)
        scope[key] = location
        bind_in_flight(location)
    return scope[key]
