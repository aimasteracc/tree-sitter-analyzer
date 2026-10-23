"""#1774：认证快照上的构图不再每次重读全部调用边来算输入摘要。

``nav callers`` 的认证路径每次查询都拿到一个新的 ``CertifiedSnapshotCache``，
其连接是注册表持有的**私有只读内存副本**（捕获时 ``BEGIN`` + ``query_only``），
没有可供 ``index_file_facts`` 取证的库文件，于是每次构图都读出全部调用边并重算
#1657 的输入摘要（zod 约 0.36 s + 0.14 s），只为在 ``call_graph_memo`` 中命中
同一张图。

快照 ID 由注册表随机生成、从不复用，它命名的副本在其生命周期内不可变；所以
“这个快照的构图输入摘要”一旦算出，对同一快照永远成立。这里按
``(规范根, 快照 ID, 索引指纹, 源码 generation)`` 记住摘要：

* **只省读行与摘要，不改判定**：命中后仍按摘要向 ``call_graph_memo`` 取图，取不到
  （已被其他输入替换）就照常读行重建，答案与未命中逐字节相同。
* **刷新永远不命中旧图**：刷新或编辑后新的认证读取会捕获新的副本（新快照 ID），
  旧键不再被查询；摘要不同的图也不会被 ``call_graph_memo`` 交出。
* 键中的索引指纹与源码 generation 是捕获时的认证状态，与快照 ID 一起出现只为
  让键自证；任何一项不同都视为不同快照。
* 有上限的 LRU：快照的存活期很短（注册表 TTL 35 s），只需记住最近几个。
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any

#: 记住的快照个数上限。
_MAX_SNAPSHOTS = 16

_LOCK = threading.Lock()
#: 快照键 -> 该快照构图输入的摘要。
_DIGESTS: OrderedDict[tuple[str, ...], str] = OrderedDict()


def snapshot_key(cache: Any) -> tuple[str, ...] | None:
    """``cache`` 绑定的不可变认证快照的键；不是认证快照（或身份不全）时为 None。"""
    identity = getattr(cache, "graph_input_identity", None)
    if not callable(identity):
        return None
    try:
        key = identity()
    except Exception:  # noqa: BLE001 — 取不到身份只是不复用
        return None
    if not isinstance(key, tuple) or not key:
        return None
    if not all(isinstance(part, str) and part for part in key):
        return None
    return key


def digest_for(key: tuple[str, ...] | None) -> str | None:
    """此前为同一快照算出的构图输入摘要；没有时为 None。"""
    if key is None:
        return None
    with _LOCK:
        digest = _DIGESTS.get(key)
        if digest is not None:
            _DIGESTS.move_to_end(key)
        return digest


def remember(key: tuple[str, ...] | None, digest: str | None) -> None:
    """记下 ``key`` 快照的构图输入摘要（由该快照的行算出）。"""
    if key is None or not digest:
        return
    with _LOCK:
        _DIGESTS[key] = digest
        _DIGESTS.move_to_end(key)
        while len(_DIGESTS) > _MAX_SNAPSHOTS:
            _DIGESTS.popitem(last=False)


def clear() -> None:
    """清空记忆（测试用）。"""
    with _LOCK:
        _DIGESTS.clear()


__all__ = ["clear", "digest_for", "remember", "snapshot_key"]
