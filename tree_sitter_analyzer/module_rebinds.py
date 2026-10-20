"""#1721：模块级名字在导入与定义之外的重新绑定，供范围回填的解析面比较。

#1705 在模块重新绑定一个属性时不把 ``owner._f()`` 解析到它的再导出目标。模块级
赋值本身是符号（``variable``），已在解析面里；但函数内的 ``global _f; _f = ...``
与模块级 ``del _f`` 不产生符号，#1696 的范围回填因此看不到这类编辑，别的文件里经
模块属性的调用会保留旧解析。这里列出这些名字，写入 ``symbols_json.module_rebinds``。

* ``global`` 语句中的名字（任意嵌套深度——``global`` 总是指模块作用域）；
* 模块顶层 ``del`` 语句中的简单名字。
``nonlocal`` 指外层函数作用域，不是模块名字，不计入。
"""

from __future__ import annotations

from typing import Any

#: 模块顶层可能包住语句的复合语句（``if`` / ``try`` / ``with`` 等的块仍是模块作用域）。
_SCOPE_NODES = frozenset({"function_definition", "class_definition", "lambda"})


def module_rebinds(root: Any) -> list[str]:
    """``root``（Python 模块的语法树根）中被重新绑定的模块级名字，排序去重。"""
    names: set[str] = set()
    stack: list[tuple[Any, bool]] = [(root, True)]
    while stack:
        node, module_scope = stack.pop()
        if node.type == "global_statement":
            names.update(_identifiers(node))
            continue
        if module_scope and node.type == "delete_statement":
            names.update(_deleted_names(node))
            continue
        inner = module_scope and node.type not in _SCOPE_NODES
        stack.extend((child, inner) for child in node.children)
    return sorted(names)


def _identifiers(node: Any) -> list[str]:
    return [_text(child) for child in node.children if child.type == "identifier"]


def _deleted_names(node: Any) -> list[str]:
    """``del a, b`` / ``del (a)`` 中的简单名字；``del x.y`` / ``del d[k]`` 不是名字绑定。"""
    found: list[str] = []
    stack = list(node.children)
    while stack:
        child = stack.pop()
        if child.type == "identifier":
            found.append(_text(child))
        elif child.type in ("expression_list", "parenthesized_expression", "tuple"):
            stack.extend(child.children)
    return found


def _text(node: Any) -> str:
    return bytes(node.text or b"").decode("utf-8", "replace")


__all__ = ["module_rebinds"]
