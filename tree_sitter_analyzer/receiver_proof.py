"""接收者是否被证明：按名字解析的各条路径共用的判定（#1669）。

``x.m()`` 只有在接收者被证明时才能确定地绑定到项目里的 ``m``：
``self`` / ``cls`` / ``super()``、导入的模块或类、类名本身、注解或构造得到的类型。
后几种由 Synapse 的 import / 类名 / 注解规则在索引时带着证据解析；到达按名字
兜底的路径（第二遍解析、跨文件回填）时仍未解析的带接收者调用，接收者类型未知——
项目里只有一个 ``append`` 并不说明 ``xs.append()`` 调用的就是它。
"""

from __future__ import annotations

import re

#: 指向调用方自身实例 / 类的接收者：按名字解析仍然可以绑定（mixin 方法等）。
OWN_RECEIVERS = frozenset({"self", "cls", "super", "super()"})
#: ``Name(`` / ``pkg.Name(``：构造调用接收者的被调名前缀。
_CALLED_NAME = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*(?=\()")


def has_unproven_receiver(callee_full: str) -> bool:
    """调用带有接收者，且接收者不是 ``self`` / ``cls`` / ``super()``。"""
    if "." not in callee_full:
        return False
    return split_receiver(callee_full)[0] not in OWN_RECEIVERS


def is_own_instance_call(callee_full: str) -> bool:
    """``self.m`` / ``cls.m``：接收者恰是调用方自身的实例或类（#1739）。

    这样的调用只能经外围类的 MRO 确定（Synapse 的 self 规则与
    ``inherited_self_calls``）；按名字挑候选的路径不得绑定它。
    """
    return split_receiver(callee_full)[0] in ("self", "cls")


def split_receiver(callee_full: str) -> tuple[str, str]:
    """``Foo(a.b).m`` -> ``("Foo(a.b)", "m")``：括号内的点不参与拆分。"""
    depth = 0
    for index in range(len(callee_full) - 1, -1, -1):
        char = callee_full[index]
        if char == ")":
            depth += 1
        elif char == "(":
            depth -= 1
        elif char == "." and depth == 0:
            return callee_full[:index], callee_full[index + 1 :]
    return "", callee_full


def constructed_class(qualifier: str) -> str | None:
    """接收者恰是一次调用 ``T(...)`` 时返回被调名 ``T``（可带模块前缀），否则 None。

    ``Foo().bar()`` 的接收者由构造调用给出类型（与 ``x = Foo(); x.bar()`` 同理）；
    被调名是否真是类由调用方按类表判定——``get_foo().bar()`` 查不到类即不绑定。
    """
    match = _CALLED_NAME.match(qualifier)
    if match is None or not qualifier.endswith(")"):
        return None
    depth = 0
    for index in range(match.end(), len(qualifier)):
        char = qualifier[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0 and index != len(qualifier) - 1:
                return None
    return match.group(0) if depth == 0 else None


def receiver_type_name(qualifier: str) -> str:
    """用于与候选所属类比较的接收者名：``mod.Foo(3)`` -> ``Foo``，``a.b`` -> ``b``。"""
    constructed = constructed_class(qualifier)
    if constructed is not None:
        return constructed.rsplit(".", 1)[-1]
    return split_receiver(qualifier)[1] if "." in qualifier else qualifier


__all__ = [
    "OWN_RECEIVERS",
    "constructed_class",
    "has_unproven_receiver",
    "is_own_instance_call",
    "receiver_type_name",
    "split_receiver",
]
