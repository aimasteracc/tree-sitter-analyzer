"""``self.m()`` 的绑定：静态目标是外围类自己的方法，覆写只是可能目标（#1635）。

dogfood 第 6 轮：``Base.run`` 调用 ``self.hook()``，同文件的 ``Sub`` 覆写 ``hook``。
持久化解析把这条边指向 ``base.py``，文件里有两个 ``hook``，接收者 ``self`` 又不是
类名，于是两者都只是 ``possible``——``Base.hook`` 得到 0 个调用方（召回缺口）。
同时，另一个文件里的覆写（``class Leaf(Base)``）根本不在候选里，``Leaf.hook``
答 ``complete, 0``——这是一个假的 complete。

规则（只会更保守）：

1. 接收者为 ``self`` / ``cls`` / ``this`` 且外围类恰有一个同名方法时，该方法是
   确定目标；``super`` 不在此列（它恰恰不指向外围类自己的方法）。
2. 外围类的每个子类（按索引中 ``extends`` 边、按类名传递闭包，跨文件）里的同名
   覆写都是可能目标：动态分派可能落到它们，因此它们不得凭调用边宣称 complete。
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .call_graph import FunctionRef

#: 指向调用者自身实例 / 类的接收者（不含 ``super``）。
OWN_INSTANCE_QUALIFIERS = frozenset({"self", "cls", "this"})
#: 子类闭包最多访问的类数，防止异常索引拖慢构图。
_MAX_SUBCLASSES = 256


def own_class_target(
    candidates: list[FunctionRef], qualifier: str, caller_class: str | None
) -> FunctionRef | None:
    """``self.m()`` 在外围类恰有一个同名方法时的确定目标；否则 None。"""
    if qualifier not in OWN_INSTANCE_QUALIFIERS or not caller_class:
        return None
    own = [ref for ref in candidates if ref.receiver == caller_class]
    return own[0] if len(own) == 1 else None


class SubclassIndex:
    """惰性读取 ``extends`` 边，按类名给出传递子类；读库失败则没有子类证据。"""

    def __init__(self, cache: Any) -> None:
        self._cache = cache
        self._children: dict[str, set[str]] | None = None

    def _load(self) -> dict[str, set[str]]:
        if self._children is None:
            children: dict[str, set[str]] = defaultdict(set)
            try:
                rows = self._cache.get_conn().execute(
                    "SELECT source_node_id, target_node_id FROM edges "
                    "WHERE kind = 'extends'"
                )
                for source, target in rows:
                    child, parent = _class_name(source), _class_name(target)
                    if child and parent and child != parent:
                        children[parent].add(child)
            except Exception:  # nosec B110 — 缺表 / 旧索引：没有子类证据。
                children = defaultdict(set)
            self._children = children
        return self._children

    def subclasses(self, class_name: str) -> set[str]:
        """``class_name`` 的全部传递子类名（不含自身）。"""
        children = self._load()
        found: set[str] = set()
        queue = deque([class_name])
        while queue and len(found) < _MAX_SUBCLASSES:
            for child in children.get(queue.popleft(), ()):
                if child not in found and child != class_name:
                    found.add(child)
                    queue.append(child)
        return found


def override_candidates(
    subclasses: SubclassIndex,
    functions_by_name: dict[str, list[FunctionRef]],
    base_name: str,
    qualifier: str,
    caller_class: str | None,
) -> list[FunctionRef]:
    """``self.base_name()`` 可能分派到的子类覆写（跨文件）。"""
    if qualifier not in OWN_INSTANCE_QUALIFIERS or not caller_class:
        return []
    names = subclasses.subclasses(caller_class)
    if not names:
        return []
    return [
        ref for ref in functions_by_name.get(base_name, []) if ref.receiver in names
    ]


def _class_name(node_id: Any) -> str:
    """``path:Class:line`` 形式节点 id 中的类名；无法解析时为空串。"""
    parts = str(node_id).rsplit(":", 2)
    return parts[1] if len(parts) == 3 and parts[0] and parts[1] else ""
