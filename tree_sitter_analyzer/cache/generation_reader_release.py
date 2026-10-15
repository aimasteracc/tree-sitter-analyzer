"""长驻读者在调用之间不得无限期钉住已退役版本（#1631，RFC-0032 slice 6）。

dogfood round 6（2026-10-16）：MCP 服务器里读过某版本的工具实例（impact 的
``CachedCallGraph`` 等）调用结束后仍保留线程本地只读连接及其版本钉。之后若不再
被调用，该版本永远不能回收：index + 3 次刷新后磁盘上留下 4 份副本，而不是
active + 2。

调用范围（``generation_read_scope``）内打开的只读连接，其版本由每次调用重新解析；
下一次调用若发现活动版本已变，本就会关闭旧连接并换绑。因此在“没有任何进行中的
调用绑定该版本”时提前关闭它，与下次换绑语义相同，只是不必等到下次调用。

正确性：
- 只释放本线程的连接（SQLite 连接不能跨线程关闭）；其他线程的连接保留钉，回收
  照常跳过它们。
- 任何进行中的调用范围绑定的版本（含同一线程上挂起的其他异步任务）都不释放。
- 调用范围之外直接构造的 ``ASTCache`` 是显式快照读者，从不登记、从不释放。
"""

from __future__ import annotations

import threading
import weakref
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .generation_pins import GENERATION_ID

_IN_FLIGHT: Counter[str] = Counter()
_IN_FLIGHT_LOCK = threading.Lock()
_THREAD = threading.local()


def generation_of(database: object) -> str | None:
    """托管版本库 ``<存储>/generations/<ID>/index.db`` 的 ID；其他路径返回 ``None``。"""
    if not isinstance(database, str | Path):
        return None
    path = Path(database)
    generation = path.parent
    if path.name != "index.db" or generation.parent.name != "generations":
        return None
    return generation.name if GENERATION_ID.fullmatch(generation.name) else None


def bind_in_flight(location: Any) -> None:
    """调用范围绑定了一个已发布版本。"""
    generation = getattr(getattr(location, "selector", None), "generation_id", None)
    if location is not None and getattr(location, "published", False) and generation:
        with _IN_FLIGHT_LOCK:
            _IN_FLIGHT[generation] += 1


def unbind_in_flight(locations: Iterable[Any]) -> None:
    """调用范围结束，逐个撤销它绑定的版本。"""
    with _IN_FLIGHT_LOCK:
        for location in locations:
            generation = getattr(
                getattr(location, "selector", None), "generation_id", None
            )
            if getattr(location, "published", False) and generation:
                _IN_FLIGHT[generation] -= 1
                if _IN_FLIGHT[generation] <= 0:
                    del _IN_FLIGHT[generation]


def track_scoped_reader(cache: Any) -> None:
    """登记本线程上在调用范围内打开过已发布版本连接的缓存（弱引用）。"""
    readers = getattr(_THREAD, "readers", None)
    if readers is None:
        readers = _THREAD.readers = weakref.WeakSet()
    readers.add(cache)


def _active_generation(root: str, memo: dict[str, str | None]) -> str | None:
    if root not in memo:
        from .generation_routing import resolve_index_location

        try:
            location = resolve_index_location(root)
        except (OSError, ValueError):
            memo[root] = None  # 无法确认活动版本时不释放任何连接
        else:
            selector = location.selector if location.published else None
            memo[root] = getattr(selector, "generation_id", None)
    return memo[root]


def release_idle_readers() -> list[str]:
    """关闭本线程上空闲读者对非活动版本的连接与钉，返回被释放的版本 ID。"""
    readers = getattr(_THREAD, "readers", None)
    if not readers:
        return []
    released: list[str] = []
    memo: dict[str, str | None] = {}
    for cache in list(readers):
        local = cache._local
        generation = generation_of(getattr(local, "db_path", None))
        if getattr(local, "conn", None) is None or generation is None:
            readers.discard(cache)
            continue
        active = _active_generation(cache.project_root, memo)
        with _IN_FLIGHT_LOCK:
            busy = _IN_FLIGHT[generation] > 0
        if active is None or generation == active or busy:
            continue
        cache.release_thread_connection()
        readers.discard(cache)
        released.append(generation)
    return released
