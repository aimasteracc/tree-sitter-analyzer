"""RFC-0040：callers 查询的目标集——裸名与限定名在任何检查运行之前归一。

#1740 / #1759 / #1773：裸名与限定名各自做范围查找，三次出现分歧（裸名漏掉
NAME_ONLY 门、限定名跳过声明文件守卫、两者列出的调用方不同）。这里是唯一的
归一处：调用方先把不带范围、项目里唯一定义的名字补上其定义文件
（:func:`sole_definition_file`，#1798），再把唯一方法定义的裸名改写为
``Class.method``（#1759），再由
:func:`target_set` 给出规范名、是否限定、按名计数的成员名与检查范围；之后每道
检查都只读这个目标集，``Checked.scope`` 必须等于 :attr:`TargetSet.scope`。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...module_scope_caller import module_caller_entry
from .callers_outcomes import Scope


@dataclass(frozen=True)
class TargetSet:
    """一次查询的规范目标：``name`` 为规范名（裸名或 ``Class.method``）。"""

    name: str
    file_path: str | None
    qualified: bool
    #: 按名计数的检查（未解析入边、声明文件守卫、同名入边）所用的成员名。
    #: #1559 / #1759：限定名按裸方法名计数——接收者未知的调用可能指向任何同名方法。
    count_name: str

    @property
    def scope(self) -> Scope:
        return (self.name, self.file_path)


def is_qualified_name(name: str) -> bool:
    """``Class.method`` 形式（非路径、非 ``file:name``，且类名部分非空）。"""
    return bool(
        "." in name
        and ":" not in name
        and "/" not in name
        and "\\" not in name
        and name.rpartition(".")[0]
    )


def sole_definition_file(graph: Any, cache: Any, name: str) -> str | None:
    """#1798：项目里唯一定义 ``name`` 的文件；不唯一或读不到时为 ``None``。

    唯一定义的名字，不带 ``file_path`` 与带上其定义文件问的是同一个问题，答案
    必须相同。此前不带范围的裸名走另一条路径：把接收者未被证明的同名调用
    （``", ".join``、``os.path.join``）直接列为调用方（rich：``Text.join`` 48 个，
    带范围时 7 个）。调用方据此把范围补成定义文件，四种问法（裸名 / 限定名 ×
    带 / 不带范围）经同一次 #1759 改写与同一个目标集回答。

    只在可证明唯一时补：调用图里成员名恰有一个函数 / 方法定义（限定名还须接收者
    一致），且索引里声明该名字的文件（含变量等其他定义）只有这一个。
    """
    if graph is None or any(ch in name for ch in ":/\\"):
        return None
    qualified = is_qualified_name(name)
    owner, _, member = name.rpartition(".") if qualified else ("", "", name)
    if not member:
        return None
    try:
        refs = list(graph.resolve_targets(member))
        declaring = cache.symbol_declaring_files(member) if cache is not None else None
    except Exception:  # noqa: BLE001 — unreadable graph or index: keep the question as asked
        return None
    if len(refs) != 1:
        return None
    ref = refs[0]
    if getattr(ref, "name", None) != member:
        return None
    if qualified and getattr(ref, "receiver", None) != owner:
        return None
    file_path = str(getattr(ref, "file_path", "") or "").replace("\\", "/")
    if not file_path or declaring is None:
        return None
    if {str(path).replace("\\", "/") for path in declaring} != {file_path}:
        return None
    return file_path


def target_set(name: str, file_path: str | None) -> TargetSet:
    """规范名 ``name``（已做 #1759 改写）对应的目标集。"""
    qualified = is_qualified_name(name)
    count_name = name.rpartition(".")[2] if qualified else name
    return TargetSet(name, file_path, qualified, count_name)


def unattributed_sites(cache: Any, target: TargetSet) -> int | None:
    """调用图路径上无坐标的模块级调用点数；读不到为 ``None``。

    RFC-0040：调用图由缓存构建时会跳过缺调用行的模块级边（``_edge_caller_ref``），
    此前限定名路径因此把这道检查固定为 0——一道从未运行的检查。这里按与 SQL
    路径相同的规则（``module_caller_entry`` 为 None）从调用边计数；限定名按裸
    成员名计数，只会更保守。
    """
    if cache is None:
        return None
    try:
        rows = cache.query_callers(target.count_name, callee_file=target.file_path)
    except Exception:  # noqa: BLE001 — unreadable edges: the check did not run
        return None
    return sum(
        1
        for edge in rows
        if not edge.get("caller_name") and module_caller_entry(edge) is None
    )


__all__ = [
    "TargetSet",
    "is_qualified_name",
    "sole_definition_file",
    "target_set",
    "unattributed_sites",
]
