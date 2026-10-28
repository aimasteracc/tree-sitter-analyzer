"""TQL 选择器边界：解析、校验并对谓词分类。

Hyphae 求值器只有在执行到未知伪类时才报错，而对未知的
``[attribute=...]`` 则静默返回空结果 (#RFC-0041 §4 的发现)。本模块在解析阶段
就拒绝这两种情况并给出 did-you-mean 修复，使拼写错误绝不会伪装成空答案。

本模块还按完整性对每个谓词分类 (RFC-0041 §3)：属性、路径、位置与包含类
谓词会在已索引的符号行上穷尽求值；边、时间、规则与分支类谓词读取的关系表或
历史表不带覆盖证明，因此使用它们的选择器永远无法让所在阶段成为
``complete``。关系阶段 (``callers()`` 等) 才是带证明地回答这类问题的方式。
"""

from __future__ import annotations

import difflib

from ..hyphae.ast import Combined, PseudoClass, SelectorList, SimpleSelector
from ..hyphae.parser import HyphaeSyntaxError, parse
from .errors import (
    SELECTOR_SYNTAX,
    UNKNOWN_PSEUDO_CLASS,
    Err,
    Ok,
    QueryError,
    Result,
)

#: 求值器已实现、且结果在索引符号行上是穷尽的伪类。
EXHAUSTIVE_PSEUDOS = frozenset(
    {"in", "not", "has", "nth-child", "first-child", "only-child"}
)
#: 依赖关系表/历史表、没有覆盖证明的伪类。
UNPROVEN_PSEUDOS = frozenset(
    {
        "calls",
        "callees",
        "called-by",
        "extends",
        "implements",
        "subclasses",
        "imports",
        "reaches",
        "hot",
        "recently_modified",
        "stale",
        "hotspot",
        "violates",
        "branch",
    }
)
KNOWN_PSEUDOS = EXHAUSTIVE_PSEUDOS | UNPROVEN_PSEUDOS
KNOWN_ATTRIBUTES = frozenset({"file", "language", "class", "kind"})

#: 能带覆盖证明地回答无证明边伪类的关系阶段。
_RELATION_FOR = {
    "calls": "symbol('X').callers()",
    "reaches": "symbol('X').callers(depth=N)",
    "callees": "symbol('X').callees()",
    "called-by": "symbol('X').callees()",
}


#: 选择器括号嵌套上限：Hyphae 解析器是递归下降，过深的嵌套会耗尽递归栈。
MAX_SELECTOR_NESTING = 32


def _nesting(text: str) -> int:
    depth = deepest = 0
    for ch in text:
        if ch == "(":
            depth += 1
            deepest = max(deepest, depth)
        elif ch == ")":
            depth -= 1
    return deepest


def parse_selector(text: str) -> Result[SelectorList]:
    """解析并校验 TQL 选择器。"""
    if _nesting(text) > MAX_SELECTOR_NESTING:
        return Err(
            QueryError(
                SELECTOR_SYNTAX,
                f"TQL syntax error: selector nesting exceeds {MAX_SELECTOR_NESTING}",
                fragment=text[:200],
                suggestion="Flatten nested :not(...) / :has(...) arguments.",
            )
        )
    try:
        selector = parse(text)
    except (HyphaeSyntaxError, ValueError, RecursionError) as exc:
        return Err(
            QueryError(
                SELECTOR_SYNTAX,
                f"TQL syntax error: {exc}",
                fragment=text[:200],
                suggestion=(
                    "Selectors look like '.function:in(src/)', '#Name', "
                    "'.class:has(#method)'; call search action=tql_schema "
                    "for the grammar."
                ),
            )
        )
    problem = _validate(selector, text)
    if problem is not None:
        return Err(problem)
    return Ok(selector)


def _validate(selector: SelectorList, text: str) -> QueryError | None:
    for simple in _simple_selectors(selector):
        for attr in simple.attributes:
            if attr.name not in KNOWN_ATTRIBUTES:
                return _unknown(
                    f"[{attr.name}=...]",
                    attr.name,
                    KNOWN_ATTRIBUTES,
                    text,
                    kind="attribute",
                )
        for pc in simple.pseudo_classes:
            if pc.name not in KNOWN_PSEUDOS:
                return _unknown(f":{pc.name}", pc.name, KNOWN_PSEUDOS, text)
    return None


def _unknown(
    fragment: str,
    name: str,
    known: frozenset[str],
    text: str,
    *,
    kind: str = "pseudo-class",
) -> QueryError:
    close = difflib.get_close_matches(name, sorted(known), n=1)
    fixed = None
    if close:
        old = f"[{name}=" if kind == "attribute" else f":{name}"
        new = f"[{close[0]}=" if kind == "attribute" else f":{close[0]}"
        fixed = text.replace(old, new, 1)
    known_list = ", ".join(sorted(known))
    return QueryError(
        UNKNOWN_PSEUDO_CLASS if kind == "pseudo-class" else SELECTOR_SYNTAX,
        f"unknown {kind} {fragment!r}; known: {known_list}",
        fragment=fragment,
        suggestion=f"Did you mean {close[0]!r}?" if close else None,
        fixed_query=fixed,
    )


def _simple_selectors(selector: SelectorList) -> list[SimpleSelector]:
    out: list[SimpleSelector] = []

    def walk_selector(node: SimpleSelector | Combined) -> None:
        if isinstance(node, Combined):
            walk_selector(node.left)
            walk_selector(node.right)
            return
        out.append(node)
        for pc in node.pseudo_classes:
            if isinstance(pc.arg, SelectorList):
                for inner in pc.arg.selectors:
                    walk_selector(inner)

    for sel in selector.selectors:
        walk_selector(sel)
    return out


def unproven_predicates(selector: SelectorList) -> tuple[str, ...]:
    """``selector`` 中任意位置用到的无证明伪类名称 (已排序)。"""
    names = {
        pc.name
        for simple in _simple_selectors(selector)
        for pc in simple.pseudo_classes
        if pc.name in UNPROVEN_PSEUDOS
    }
    return tuple(sorted(names))


def relation_hint(names: tuple[str, ...]) -> str | None:
    """第一个边伪类对应的带证明关系阶段提示 (若存在)。"""
    for name in names:
        if name in _RELATION_FOR:
            return (
                f":{name} reads call edges without a coverage proof; "
                f"{_RELATION_FOR[name]} answers the same question with "
                "nav-callers completeness."
            )
    return None


__all__ = [
    "EXHAUSTIVE_PSEUDOS",
    "KNOWN_ATTRIBUTES",
    "KNOWN_PSEUDOS",
    "UNPROVEN_PSEUDOS",
    "PseudoClass",
    "parse_selector",
    "relation_hint",
    "unproven_predicates",
]
