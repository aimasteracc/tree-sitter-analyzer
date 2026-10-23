"""实例属性 ``self.attr`` 的类型推断（只用类体与方法体里可见的证据）。"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from typing import TYPE_CHECKING

from scripts.wrong_complete.py_model import (
    UNKNOWN,
    Binding,
    ClassInfo,
    FuncNode,
    dotted,
    is_name,
)
from scripts.wrong_complete.py_scope import FunctionScope

if TYPE_CHECKING:
    from scripts.wrong_complete.py_model import Project

_PROPERTY_DECORATORS = frozenset(
    {"property", "functools.cached_property", "cached_property"}
)


def own_attr(project: Project, cls: ClassInfo, attr: str) -> Binding | None:
    """``cls`` 自身（不看基类）对 ``attr`` 的证据；全部一致才给出绑定，没有证据为 ``None``。"""
    mod = cls.module
    specs: set[Binding] = set()
    for item in cls.node.body:
        if isinstance(item, ast.AnnAssign) and is_name(item.target, attr):
            ann_cls = project.annotation_class(mod, item.annotation)
            specs.add(("declared", ann_cls) if ann_cls else UNKNOWN)
        elif isinstance(item, ast.Assign) and any(
            is_name(t, attr) for t in item.targets
        ):
            specs.add(project.eval_expr(mod, item.value, None))
    for funcs in cls.methods.values():
        for func in funcs:
            if func.name == attr and _is_property(func):
                ret = project.annotation_class(mod, func.returns)
                specs.add(("declared", ret) if ret else UNKNOWN)
                continue
            scope = FunctionScope(project, mod, func, cls, None)
            for value, annotation in _self_assignments(func, attr):
                if annotation is not None:
                    ann_cls = project.annotation_class(mod, annotation)
                    specs.add(("declared", ann_cls) if ann_cls else UNKNOWN)
                elif value is not None:
                    specs.add(project.eval_expr(mod, value, scope.lookup))
                else:
                    specs.add(UNKNOWN)
    if not specs:
        return None
    return specs.pop() if len(specs) == 1 else UNKNOWN


def _is_property(func: FuncNode) -> bool:
    return any(dotted(d) in _PROPERTY_DECORATORS for d in func.decorator_list)


def _self_assignments(
    func: FuncNode, attr: str
) -> Iterator[tuple[ast.expr | None, ast.expr | None]]:
    """方法体内对 ``self.attr`` 的赋值 ``(value, annotation)``；不进入嵌套定义。

    元组解包等无法对应到单个值的赋值给出 ``(None, None)``（即未知）。
    """
    if not func.args.args:
        return
    self_name = func.args.args[0].arg
    stack: list[ast.AST] = list(func.body)
    while stack:
        node = stack.pop()
        if isinstance(
            node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Lambda
        ):
            continue
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if _is_self_attr(target, self_name, attr):
                    yield node.value, None
                elif not isinstance(target, ast.Attribute):
                    for sub in ast.walk(target):
                        if _is_self_attr(sub, self_name, attr):
                            yield None, None
        elif isinstance(node, ast.AnnAssign) and _is_self_attr(
            node.target, self_name, attr
        ):
            yield node.value, node.annotation
        elif isinstance(node, ast.AugAssign) and _is_self_attr(
            node.target, self_name, attr
        ):
            yield None, None
        stack.extend(ast.iter_child_nodes(node))


def _is_self_attr(node: ast.AST, self_name: str, attr: str) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == attr
        and isinstance(node.value, ast.Name)
        and node.value.id == self_name
    )
