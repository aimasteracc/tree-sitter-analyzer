"""函数作用域：参数、局部赋值、闭包与 ``self`` 的绑定。"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING, Any

from scripts.wrong_complete.py_model import UNKNOWN, Binding, ClassInfo, ModuleInfo

if TYPE_CHECKING:
    from scripts.wrong_complete.py_model import FuncNode, Project


def _decorator_names(func: FuncNode) -> set[str]:
    names: set[str] = set()
    for deco in func.decorator_list:
        node = deco.func if isinstance(deco, ast.Call) else deco
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


class FunctionScope:
    """一个函数（或 lambda / 推导式）的局部名字表。

    ``lookup(name)`` 返回本作用域或外层函数作用域的绑定；返回 ``None`` 表示
    应回落到模块作用域。同一名字的多个赋值互相矛盾时为 ``UNKNOWN``。
    """

    def __init__(
        self,
        project: Project,
        mod: ModuleInfo,
        func: FuncNode | ast.Lambda | None,
        owner: ClassInfo | None,
        parent: FunctionScope | None,
        unknown_names: tuple[str, ...] = (),
    ) -> None:
        self.project = project
        self.mod = mod
        self.parent = parent
        self.specs: dict[str, list[tuple[Any, ...]]] = {}
        self._busy: set[str] = set()
        for name in unknown_names:
            self.specs.setdefault(name, []).append(("unknown",))
        if func is not None:
            self._collect_params(func, owner)
            if not isinstance(func, ast.Lambda):
                self._collect_body(func.body)

    def _add(self, name: str, spec: tuple[Any, ...]) -> None:
        self.specs.setdefault(name, []).append(spec)

    def _collect_params(
        self, func: FuncNode | ast.Lambda, owner: ClassInfo | None
    ) -> None:
        args = func.args
        positional = [*args.posonlyargs, *args.args]
        first_is_self = False
        if owner is not None and positional and not isinstance(func, ast.Lambda):
            first_is_self = "staticmethod" not in _decorator_names(func)
        for index, arg in enumerate([*positional, *args.kwonlyargs]):
            if index == 0 and first_is_self and owner is not None:
                self._add(arg.arg, ("self", owner))
            elif arg.annotation is not None:
                self._add(arg.arg, ("annot", arg.annotation))
            else:
                self._add(arg.arg, ("unknown",))
        for extra in (args.vararg, args.kwarg):
            if extra is not None:
                self._add(extra.arg, ("unknown",))

    def _collect_body(self, body: list[ast.stmt]) -> None:
        stack: list[ast.AST] = list(body)
        while stack:
            node = stack.pop()
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                self._add(node.name, ("localfunc", node))
                continue
            if isinstance(node, ast.ClassDef):
                info = next((c for c in self.project.classes if c.node is node), None)
                self._add(node.name, ("class", info) if info else ("unknown",))
                continue
            if isinstance(node, ast.Lambda | ast.ListComp | ast.SetComp | ast.DictComp):
                continue
            if isinstance(node, ast.GeneratorExp):
                continue
            self._collect_statement(node)
            stack.extend(ast.iter_child_nodes(node))

    def _collect_statement(self, node: ast.AST) -> None:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self._add(target.id, ("expr", node.value))
                else:
                    self._store_unknown(target)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            self._add(node.target.id, ("annot", node.annotation))
        elif isinstance(node, ast.NamedExpr):
            self._add(node.target.id, ("expr", node.value))
        elif isinstance(node, ast.AugAssign | ast.For | ast.AsyncFor):
            self._store_unknown(node.target)
        elif isinstance(node, ast.withitem) and node.optional_vars is not None:
            self._store_unknown(node.optional_vars)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            self._add(node.name, ("unknown",))
        elif isinstance(node, ast.Global | ast.Nonlocal):
            for name in node.names:
                self._add(name, ("unknown",))
        elif isinstance(node, ast.Import | ast.ImportFrom):
            self._collect_import(node)

    def _store_unknown(self, target: ast.AST) -> None:
        for sub in ast.walk(target):
            if isinstance(sub, ast.Name):
                self._add(sub.id, ("unknown",))

    def _collect_import(self, node: ast.Import | ast.ImportFrom) -> None:
        from scripts.wrong_complete.py_model import import_base

        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[0]
                target = alias.name if alias.asname else local
                self._add(local, ("module", target))
            return
        base = import_base(self.mod, node.level, node.module)
        for alias in node.names:
            if alias.name != "*":
                self._add(alias.asname or alias.name, ("from", base, alias.name))

    def lookup(self, name: str) -> Binding | None:
        """局部 → 外层函数 → ``None``（交给模块作用域）。"""
        if name in self.specs:
            if name in self._busy:
                return UNKNOWN
            self._busy.add(name)
            try:
                results = {self._eval(spec) for spec in self.specs[name]}
            finally:
                self._busy.discard(name)
            return results.pop() if len(results) == 1 else UNKNOWN
        if self.parent is not None:
            return self.parent.lookup(name)
        return None

    def _eval(self, spec: tuple[Any, ...]) -> Binding:
        kind = spec[0]
        project = self.project
        if kind in ("self", "class", "localfunc"):
            return spec if spec[1] is not None else UNKNOWN
        if kind == "annot":
            cls = project.annotation_class(self.mod, spec[1])
            return ("declared", cls) if cls else UNKNOWN
        if kind == "expr":
            return project.eval_expr(self.mod, spec[1], self.lookup)
        if kind == "module":
            found = project.find_module(spec[1])
            return ("module", found.name) if found else ("external",)
        if kind == "from":
            return project.resolve_from(spec[1], spec[2])
        return UNKNOWN
