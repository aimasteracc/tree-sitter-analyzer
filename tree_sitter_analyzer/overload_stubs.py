"""#1773：Python ``@overload`` 存根与实现是同一个可调用对象。

``typing.overload`` 存根只供类型检查：运行时类体（或模块）里最后一个未加
``@overload`` 的同名定义才是该名字绑定的函数。调用图若把存根当作独立的同名定义，
``self.constrain(...)`` 在外围类的多个 ``constrain`` 之间无法区分，只能记为同名匹配，
限定名 ``_Pipeline.constrain`` 于是列出 0 个调用方（dogfood r12，pydantic）。

规则（只会更保守）：

* 索引为装饰器写作 ``@overload`` 或 ``@<任意>.overload`` 的 Python 函数记下
  ``overload: true``；
* 构图时，同一文件、同一外围类、同名的一组定义里恰有一个未标记的实现时，丢弃该组
  的存根，实现代表整个方法；
* 没有实现（``.pyi``、Protocol 里只有存根）或有多个未标记定义（条件定义）时一律
  不动，与改动前相同。
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

#: 符号行 / 函数条目上标记 ``@overload`` 存根的键。
OVERLOAD_KEY = "overload"
_OVERLOAD_NAME = "overload"


def _text(node: Any) -> str:
    raw = getattr(node, "text", None)
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw or "")


def _names_overload(expr: Any) -> bool:
    """装饰器表达式是 ``overload`` 或 ``<x>.overload``（不含调用形式）。"""
    if expr.type == "identifier":
        return _text(expr) == _OVERLOAD_NAME
    if expr.type == "attribute":
        attr = expr.child_by_field_name("attribute")
        return attr is not None and _text(attr) == _OVERLOAD_NAME
    return False


def is_overload_stub(node: Any, language: str) -> bool:
    """Python ``function_definition`` 节点带 ``@overload`` 装饰器时为真。"""
    if language != "python":
        return False
    parent = getattr(node, "parent", None)
    if parent is None or parent.type != "decorated_definition":
        return False
    for child in parent.children:
        if child.type != "decorator":
            continue
        if any(_names_overload(expr) for expr in child.named_children):
            return True
    return False


def _group_key(entry: dict[str, Any]) -> tuple[Any, Any, Any]:
    return (entry.get("file"), entry.get("class"), entry.get("name"))


def drop_overload_stubs(entries: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """去掉有唯一实现的 ``@overload`` 存根；返回新列表，其余条目保持原顺序。"""
    items = list(entries)
    if not any(entry.get(OVERLOAD_KEY) for entry in items):
        return items
    implementations = Counter(
        _group_key(entry) for entry in items if not entry.get(OVERLOAD_KEY)
    )
    return [
        entry
        for entry in items
        if not (entry.get(OVERLOAD_KEY) and implementations[_group_key(entry)] == 1)
    ]
