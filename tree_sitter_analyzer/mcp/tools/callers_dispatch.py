"""#1596：声明文件中的未解析调用点何时可能指向目标（RFC-0028 §1.2 守卫按名收窄）。

§1.2 的作用域守卫曾把声明文件里任意一个未解析调用都当作“可能指向本文件声明的
任何符号”，于是 ``"\\n".join``、``header.get`` 这类调用让模块级函数永远答不出
``complete``（dogfood 第 3 轮 18/18、第 4 轮 12/12 为 ``unknown``）。

收窄依据：一个调用点要调用目标，要么调用文本以目标名结尾（``target()``、
``x.target()``），要么名字在运行时计算（``getattr(x, name)``、``HANDLERS[name]``、
``globals()[...]``）。名字不同的调用点只能经由别名、回调或容器到达目标，而这些
都需要一次按名引用——0 调用方时由非调用引用门（#1593）扫描。因此收窄只在该门
会运行的情况下使用（见 ``callers_tool``），计算式分发始终保留守卫。
"""

from __future__ import annotations

import os
import re
from typing import Any

#: 排除原因码：调用点的属性名 / 裸名与目标不同，无法点名目标。
NAMES_OTHER_REASON = "names_other_symbol"
#: completeness 原因：目标带有可能登记它的装饰器（注册表分发不产生调用边）。
DECORATED_REASON = "DECORATOR_MAY_REGISTER"
#: 只包装或标注、不把函数登记到别处的装饰器（按最后一段名字比较）。
_PASSIVE_DECORATORS = frozenset(
    {
        "abstractmethod",
        "cache",
        "classmethod",
        "contextmanager",
        "asynccontextmanager",
        "deprecated",
        "final",
        "lru_cache",
        "overload",
        "override",
        "Override",
        "staticmethod",
        "wraps",
    }
)

#: 名字在运行时计算的构造；出现在调用文本任意位置即保留守卫（只会更保守）。
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
#: 调用文本末尾的名字：整个文本是标识符，或 ``.`` 之后的标识符。
_TRAILING_NAME = re.compile(r"(?:^|\.)\s*([A-Za-z_$][\w$]*)$")


def could_name_target(callee_full: str, target: str) -> bool:
    """调用文本是否可能点名 ``target``：同名，或名字在运行时计算。

    无法判定的形状（空文本、``make()()``）一律返回 True——多计只会让答案停在
    ``incomplete`` / ``unknown``，少计才会在真实调用边上宣称不存在。
    """
    text = (callee_full or "").strip()
    literal = _LITERAL_GETATTR.match(text)
    if literal is not None:
        return literal.group(2) == target
    if not text or any(marker in text for marker in _COMPUTED_MARKERS):
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


def registering_decorator(
    project_root: str, declarations: list[tuple[str, int, str]]
) -> str | None:
    """声明上第一个可能登记目标的装饰器文本；没有则为 None。

    ``@app.route`` / ``@register`` 把函数存进注册表，之后以 ``f()`` 之类的名字
    不同的调用点分发——按名收窄后，这类分发不再由声明文件守卫兜底，因此 0 调用方
    不能凭调用边宣称 ``complete``。已知只包装、不登记的装饰器除外。读取失败的
    声明跳过：与访问器判定一致，后续各门仍然适用。
    """
    for rel_path, line, _language in declarations:
        try:
            with open(
                os.path.join(project_root, rel_path), encoding="utf-8", errors="replace"
            ) as handle:
                source = handle.read().splitlines()
        except OSError:
            continue
        for decorator in _decorators_at(source, line):
            name = decorator[1:].split("(", 1)[0].strip().rpartition(".")[2]
            if name not in _PASSIVE_DECORATORS:
                return decorator
    return None


def registered_hint(func_name: str, decorator: str) -> str:
    """装饰器登记门的 next_step。"""
    return (
        f"No resolved caller for {func_name!r}, but it is decorated with "
        f"`{decorator}`, which may register it for dispatch the call graph does "
        "not record, so this is not evidence of absence."
    )


def _decorators_at(source: list[str], line: int) -> list[str]:
    """声明行起（及其上方）连续的装饰器行，已去除缩进。"""
    found: list[str] = []
    index = line - 1
    while 0 <= index < len(source) and source[index].lstrip().startswith("@"):
        found.append(source[index].strip())
        index += 1
    index = line - 2
    while 0 <= index < len(source) and source[index].lstrip().startswith("@"):
        found.append(source[index].strip())
        index -= 1
    return found


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
