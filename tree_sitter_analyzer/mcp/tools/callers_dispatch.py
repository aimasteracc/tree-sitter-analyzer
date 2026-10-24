"""#1596：声明文件中的未解析调用点何时可能指向目标（RFC-0028 §1.2 守卫按名收窄）。

§1.2 的作用域守卫曾把声明文件里任意一个未解析调用都当作“可能指向本文件声明的
任何符号”，于是 ``"\\n".join``、``header.get`` 这类调用让模块级函数永远答不出
``complete``（dogfood 第 3 轮 18/18、第 4 轮 12/12 为 ``unknown``）。

收窄依据：一个调用点要调用目标，要么调用文本以目标名结尾（``target()``、
``x.target()``），要么名字在运行时计算（``getattr(x, name)``、``HANDLERS[name]``、
``globals()[...]``）。名字不同的调用点只能经由别名、回调或容器到达目标，而这些
都需要一次按名引用——0 调用方时由非调用引用门（#1593）扫描。因此收窄只在该门
会运行的情况下使用（见 ``callers_tool``），计算式分发始终保留守卫。

#1632：计算式标记只作用于真正被调用的尾段。``received[0].get()`` 调用的是
``.get``，前缀中的 ``[`` 不会改变被调用的名字；``HANDLERS[name]()``、
``getattr(m, name)()`` 的尾段本身就是计算结果，仍保留守卫。
"""

from __future__ import annotations

import re
from typing import Any

#: 排除原因码：调用点的属性名 / 裸名与目标不同，无法点名目标。
NAMES_OTHER_REASON = "names_other_symbol"

#: 名字在运行时计算的构造；出现在被调用的尾段中即保留守卫（#1632）。
_COMPUTED_MARKERS = (
    "getattr(",
    "setattr(",
    "hasattr(",
    "globals(",
    "locals(",
    "vars(",
    "eval(",
    "exec(",
    "__getattribute__",
    "attrgetter(",
    "methodcaller(",
    "[",
)
#: ``getattr(<接收者>, "<字面量>")``：名字是字面量，可直接与目标比较。
_LITERAL_GETATTR = re.compile(
    r"^getattr\(\s*[^,()\[\]]+\s*,\s*([\"'])([A-Za-z_$][\w$]*)\1\s*\)$"
)
#: ``type(<表达式>)``：调用它构造一个实例（#1759）。
_TYPE_CONSTRUCTION = re.compile(r"^type\(\s*[A-Za-z_$][\w$.]*\s*\)$")
#: 构造实例时可能执行的方法。
_CONSTRUCTION_METHODS = frozenset(
    {"__init__", "__new__", "__call__", "__init_subclass__"}
)
#: 调用文本末尾的名字：整个文本是标识符，或 ``.`` 之后的标识符。
_TRAILING_NAME = re.compile(r"(?:^|\.)\s*([A-Za-z_$][\w$]*)$")
#: 把调用转发给前缀对象本身的尾段名（``f.call(...)``、``f.__call__()``）：
#: 被调用的仍是前缀计算出的对象，因此标记看整段文本。
_FORWARDERS = frozenset({"call", "apply", "__call__"})


def trailing_segment(text: str) -> str | None:
    """最后一个顶层 ``.`` 之后的部分，即真正被调用的尾段。

    括号与引号内的 ``.`` 不计（``getattr(x, "a.b").get`` 的尾段是 ``get``）；
    括号或引号不配对时无法切分，返回 None。
    """
    depth = 0
    quote = ""
    last_dot = -1
    index = 0
    while index < len(text):
        char = text[index]
        if quote:
            if char == "\\":
                index += 1
            elif char == quote:
                quote = ""
        elif char in "\"'`":
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
            if depth < 0:
                return None
        elif char == "." and depth == 0:
            last_dot = index
        index += 1
    if depth or quote:
        return None
    return text[last_dot + 1 :]


#: 函数字面量的开头：``function``、``async``、``lambda``，或箭头函数的参数表 + ``=>``。
_FUNCTION_LITERAL_HEAD = re.compile(
    r"^(?:async\s+)?(?:function\b|lambda\b"
    r"|\((?:[^()]|\([^()]*\))*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)"
)


def _strip_wrapping_parens(text: str) -> str | None:
    """去掉包住整段文本的成对括号；括号不配对时为 None。"""
    while text.startswith("("):
        depth = 0
        quote = ""
        close = -1
        escaped = False
        for index, char in enumerate(text):
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = ""
            elif char in "\"'`":
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    close = index
                    break
        if close == -1:
            return None
        if close != len(text) - 1:
            return text
        text = text[1:-1].strip()
    return text


def is_function_literal(callee_full: str) -> bool:
    """调用文本是（被括号包住的）函数字面量：``(() => {…})``、``(function () {…})``。"""
    inner = _strip_wrapping_parens((callee_full or "").strip())
    return bool(inner) and _FUNCTION_LITERAL_HEAD.match(inner or "") is not None


def could_name_target(callee_full: str, target: str) -> bool:
    """调用文本是否可能点名 ``target``：同名，或名字在运行时计算。

    无法判定的形状（空文本、``make()()``）一律返回 True——多计只会让答案停在
    ``incomplete`` / ``unknown``，少计才会在真实调用边上宣称不存在。
    """
    text = (callee_full or "").strip()
    if _TYPE_CONSTRUCTION.match(text):
        # #1759：``type(self)(...)`` 只构造实例：只到达构造相关的方法。
        return target in _CONSTRUCTION_METHODS
    if is_function_literal(text):
        # #1741：立即调用的函数字面量（IIFE / ``(lambda: …)()``）只调用它自己；
        # 体内的调用各有自己的边，不会经由这个调用点到达目标。
        return False
    literal = _LITERAL_GETATTR.match(text)
    if literal is not None:
        return literal.group(2) == target
    # #1632：标记只看被调用的尾段——`received[0].get` 调用的是 `.get`，前缀里的
    # `[` 无法让它点名目标；尾段是转发名或无法切分时退回整段文本（只会更保守）。
    segment = trailing_segment(text)
    scope = text if segment is None or segment.strip() in _FORWARDERS else segment
    if not text or any(marker in scope for marker in _COMPUTED_MARKERS):
        return True
    trailing = _TRAILING_NAME.search(text)
    if trailing is None:
        return True
    return trailing.group(1) == target


def partition_by_target(
    sites: list[dict[str, Any]], target: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """把未解析调用点分为（可能指向目标，被排除）两组；不修改输入。

    被排除的点复制后标为 ``excluded`` 并带上原因码，使守卫计入的点与报告为
    已排除的点仍是同一次扫描的互补两部分（§1.3）。
    """
    kept: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for site in sites:
        if could_name_target(str(site.get("callee") or ""), target):
            kept.append(site)
        else:
            excluded.append(
                {
                    **site,
                    "classification": "excluded",
                    "reason_code": NAMES_OTHER_REASON,
                }
            )
    return kept, excluded


def narrow_to_target(
    unresolved: list[dict[str, Any]] | None,
    excluded: list[dict[str, Any]] | None,
    target: str,
) -> tuple[list[dict[str, Any]] | None, list[dict[str, Any]] | None]:
    """按目标名收窄守卫：返回（仍守卫的点，合并后的已排除点）。

    任一侧读取失败（``None``）时原样返回——无法读取不等于没有，不在此处降级。
    """
    if unresolved is None or excluded is None:
        return unresolved, excluded
    kept, renamed = partition_by_target(unresolved, target)
    merged = sorted([*excluded, *renamed], key=lambda s: (s["file"], s["line"]))
    return kept, merged
