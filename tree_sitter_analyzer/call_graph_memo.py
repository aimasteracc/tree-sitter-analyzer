"""按构图输入的内容摘要复用已构建的内存调用图（#1657）。

#1651 之后，刷新索引后的第一次 ``nav callers`` 仍需 5–11 s：``index_identity``
随新 generation 变化，内存调用图被丢弃，``CachedCallGraph._build_from_cache``
重新解析约 18.5 万条边。无变化的刷新会发布一个内容完全相同的新 generation，
这正是最常见、也最该省掉的情形。

复用规则（RFC-0030：路径与 generation 都不是新鲜度证据）：

1. 键是本次构图**实际消费的数据**的摘要：``get_call_edges`` / ``get_functions`` /
   ``get_imports`` 返回的行，以及包再导出绑定与子类索引加载到的证据。构图是这些
   输入的确定性函数，输入逐字节相同则构出的图相同。
2. generation id、库路径、``indexed_at`` 都不进入键：内容相同的新 generation
   命中，内容不同的同一 generation 不命中。
3. 摘要按读取顺序计算，顺序不同即视为不同输入（列表顺序影响答案顺序）。
   序列化的偶然差异只会造成未命中（多一次重建），不会造成误命中。
4. 只保存每个项目根最近一次构图的状态，并限制项目根数量，内存上限约为一张图。

这里只负责摘要与存取；身份绑定（``index_bound_graph`` 与 relation mixin，
#1564 / #1610 / #1611 / #1613）照旧决定何时新建图对象，新建的图在构建时才查询
本记忆。
"""

from __future__ import annotations

import hashlib
import marshal
import pickle  # nosec B403 — 只序列化本进程读出的数据用于摘要，从不反序列化。
import threading
from collections import OrderedDict
from typing import Any

#: marshal 格式版本：0 不含引用 / 驻留标记（版本 ≥3 会按引用计数写引用标记）。
_MARSHAL_VERSION = 0
#: 大列表每块的行数（调用边约 18.7 万行，分块后每块的字节副本只有数 MB）。
_CHUNK_ROWS = 8192
#: 记忆保存的项目根个数上限（每个根只保留最近一次构图）。
_MAX_ROOTS = 4

_LOCK = threading.Lock()
#: 项目根 -> (输入摘要, 构建完成的图状态)。
_MEMO: OrderedDict[str, tuple[str, dict[str, Any]]] = OrderedDict()


def input_digest(*parts: Any) -> str | None:
    """构图输入的内容摘要；无法序列化时返回 None（不记忆、照常构建）。

    每个部分单独序列化并带上长度与序列化器标记，拼接无二义。``marshal`` 只接受
    内建类型，比 pickle 快约 3 倍（18.7 万条边约 0.2 s）；含数据类的部分（包再导出
    绑定证据）退回 pickle。两者都可无损还原，所以字节相同即内容相同；同一内容
    偶然序列化出不同字节只会造成未命中。
    """
    hasher = hashlib.blake2b(digest_size=32)
    for part in parts:
        if isinstance(part, list) and len(part) > _CHUNK_ROWS:
            # 大列表分块序列化：峰值内存只多一个块，而不是整份边数据的字节副本。
            hasher.update(b"L" + len(part).to_bytes(8, "big"))
            for start in range(0, len(part), _CHUNK_ROWS):
                if not _feed(hasher, part[start : start + _CHUNK_ROWS]):
                    return None
        elif not _feed(hasher, part):
            return None
    return hasher.hexdigest()


def _feed(hasher: Any, part: Any) -> bool:
    """写入 ``标记 + 长度 + 字节``；标记决定结构，前缀无二义。"""
    encoded = _encode(part)
    if encoded is None:
        return False
    tag, payload = encoded
    hasher.update(tag + len(payload).to_bytes(8, "big"))
    hasher.update(payload)
    return True


def _encode(part: Any) -> tuple[bytes, bytes] | None:
    try:
        # 版本 0：不写对象引用标记与驻留标记，字节只取决于值，不取决于引用计数。
        return b"m", marshal.dumps(part, _MARSHAL_VERSION)
    except ValueError:
        pass
    try:
        return b"p", pickle.dumps(part, protocol=pickle.HIGHEST_PROTOCOL)
    except (pickle.PicklingError, TypeError, AttributeError, RecursionError):
        return None


def lookup(root: str, digest: str) -> dict[str, Any] | None:
    """摘要相同时返回已构建的图状态，否则 None。"""
    with _LOCK:
        entry = _MEMO.get(root)
        if entry is None or entry[0] != digest:
            return None
        _MEMO.move_to_end(root)
        return entry[1]


def store(root: str, digest: str, state: dict[str, Any]) -> None:
    """记录 ``root`` 最近一次构图；同根的旧状态被替换。"""
    with _LOCK:
        _MEMO[root] = (digest, state)
        _MEMO.move_to_end(root)
        while len(_MEMO) > _MAX_ROOTS:
            _MEMO.popitem(last=False)


def discard(root: str) -> None:
    """丢弃 ``root`` 的记忆（输入已变、即将重建时调用）。"""
    with _LOCK:
        _MEMO.pop(root, None)


def clear() -> None:
    """清空记忆（测试与项目根切换后的显式释放）。"""
    with _LOCK:
        _MEMO.clear()
