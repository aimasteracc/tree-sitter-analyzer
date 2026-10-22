"""#1739：Python 的 ``self`` / ``cls`` 只有作为方法的第一个参数时才是方法接收者。

dogfood 第 10 轮（pydantic）：``lambda self, v, serializer: list(self.keys())`` 的
``self`` 是 lambda 参数，类型未知，却和方法接收者一样被按 ``self`` 规则解析，
绑定到了项目里唯一的 ``GetterDict.keys``。

规则：从调用点向外找绑定该名字的作用域——

* lambda 或函数的参数列表含该名字时，只有“类体中直接定义的函数、且该名字是
  第一个参数”才是方法接收者；lambda、模块级函数和嵌套函数的同名参数都不是；
* 函数没有绑定该名字（闭包读取外层方法的 ``self``）时继续向外找；
* 到达类体或模块仍未绑定：不是方法接收者。

不是方法接收者时，接收者根写作 ``(self)``：与 ``self`` 语义相同的合法 Python
表达式，但不等于 ``self`` / ``cls``，于是 Synapse、第二遍解析、跨文件回填、
继承调用解析与内存调用图都把它当作普通的未证明接收者（#1669）。
"""

from __future__ import annotations

from typing import Any

#: 方法接收者参数的惯用名。
OWN_PARAMETER_NAMES = ("self", "cls")
_PARAMETER_WRAPPERS = frozenset(
    {"typed_parameter", "default_parameter", "typed_default_parameter"}
)


def mark_unbound_own_receiver(call_node: Any, call_info: dict[str, Any]) -> None:
    """接收者根为 ``self`` / ``cls`` 但不是方法接收者时，改写为 ``(self)`` 形式。"""
    receiver = call_info.get("receiver") or ""
    root, dot, rest = receiver.partition(".")
    if root not in OWN_PARAMETER_NAMES or binds_method_receiver(call_node, root):
        return
    rewritten = f"({root}){dot}{rest}"
    call_info["receiver"] = rewritten
    call_info["full_name"] = f"{rewritten}.{call_info['name']}"


def binds_method_receiver(call_node: Any, name: str) -> bool:
    """调用点上的 ``name`` 是否是外围方法的接收者（第一个参数）。"""
    current = getattr(call_node, "parent", None)
    while current is not None:
        kind = current.type
        if kind == "lambda":
            if name in parameter_names(current.child_by_field_name("parameters")):
                return False
        elif kind == "function_definition":
            params = parameter_names(current.child_by_field_name("parameters"))
            if name in params:
                return params[0] == name and _defined_in_class_body(current)
        elif kind == "class_definition":
            return False
        current = current.parent
    return False


def parameter_names(params: Any) -> list[str]:
    """参数列表（``parameters`` / ``lambda_parameters``）中按顺序的参数名。"""
    if params is None:
        return []
    names: list[str] = []
    for child in params.children:
        if child.type == "identifier":
            names.append(_text(child))
        elif child.type in _PARAMETER_WRAPPERS:
            # 名字是包装节点的第一个子节点（`*args: T` 的第一个子节点不是标识符）。
            names.extend(
                _text(sub) for sub in child.children[:1] if sub.type == "identifier"
            )
    return names


def _defined_in_class_body(func_node: Any) -> bool:
    parent = func_node.parent
    if parent is not None and parent.type == "decorated_definition":
        parent = parent.parent
    owner = None if parent is None else parent.parent
    return (
        parent is not None
        and parent.type == "block"
        and owner is not None
        and owner.type == "class_definition"
    )


def _text(node: Any) -> str:
    return bytes(node.text or b"").decode("utf-8", errors="replace")


__all__ = [
    "OWN_PARAMETER_NAMES",
    "binds_method_receiver",
    "mark_unbound_own_receiver",
    "parameter_names",
]
