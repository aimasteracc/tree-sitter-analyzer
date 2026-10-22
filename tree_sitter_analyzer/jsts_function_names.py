"""#1763：JS/TS 中以常量定义的函数（``const f = (...) => {}``）的名字。

ts1 dogfood（hono）：``export const cors = (options?: CORSOptions) => { ... }``、
``export const getCookie: GetCookie = (c, key?) => { ... }`` 这类箭头函数常量
没有被索引为函数定义，于是：

* 它们的调用方无法被 ``nav callers`` 定位；
* 函数体内的调用没有外围调用方（hono 94% 的 TS 调用边 caller 为空）；
* 同名的内层 ``function cors(c, next)`` 接走了所有 ``cors()`` 调用。

规则：箭头函数或函数表达式恰是 ``variable_declarator`` 的初始值（可带类型注解、
可被括号包裹）时，以声明的标识符命名。命名的函数表达式仍用它自己的名字；其余
匿名箭头函数（回调实参等）没有名字——不再把单参数箭头函数的参数误当作函数名。
"""

from __future__ import annotations

from typing import Any

#: 可作为常量初始值、以声明名命名的函数节点类型。
FUNCTION_VALUE_TYPES = frozenset({"arrow_function", "function_expression"})


def declarator_name(node: Any) -> str | None:
    """``node`` 恰是 ``const name = node`` 的初始值时返回 ``name``，否则 None。"""
    current = node
    parent = getattr(node, "parent", None)
    while parent is not None and parent.type == "parenthesized_expression":
        current, parent = parent, parent.parent
    if parent is None or parent.type != "variable_declarator":
        return None
    if parent.child_by_field_name("value") != current:
        return None
    name = parent.child_by_field_name("name")
    if name is None or name.type != "identifier":
        return None
    return _text(name)


def function_value_name(node: Any) -> str | None:
    """箭头函数 / 函数表达式的名字：自身的名字，否则所属常量声明的名字。"""
    if node.type not in FUNCTION_VALUE_TYPES:
        return None
    own = node.child_by_field_name("name")
    if own is not None:
        return _text(own)
    return declarator_name(node)


def _text(node: Any) -> str:
    return bytes(node.text or b"").decode("utf-8", errors="replace")


__all__ = ["FUNCTION_VALUE_TYPES", "declarator_name", "function_value_name"]
