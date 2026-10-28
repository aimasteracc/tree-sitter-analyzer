"""Python 独立判定器：找出可能调用目标的全部调用点与非调用引用点。

规则（与 TSA 文档化的语义一致，#1648 / #1677 / #1743 / #1758 / #1772）：

* 接收者类型可证明（``self``、构造得到的局部变量、注解、``Cls.m()``、
  ``super()``、模块属性、导入别名）时按 MRO 静态查找：命中目标即 ``target``；
* 声明类型 ``S`` 的接收者、目标定义在 ``S`` 的子类里 → ``possible``（虚分派）；
* 接收者 MRO 上有 ``Protocol`` → ``possible``（结构实现）；
* 接收者无法证明 → ``possible``（``unresolved_receiver``）；
* 其余可证明调用的是别的定义、内建或外部对象 → ``other``（不必列出）。

非调用引用（``obj.m`` 作为值、``getattr(x, "m")``、函数名作为值）同样按上述
规则判定，``kind == "reference"``：调用可经由它们发生（分派表、回调）。
"""

from __future__ import annotations

import ast
from collections.abc import Sequence

from scripts.wrong_complete.py_model import (
    EXTERNAL,
    UNKNOWN,
    Binding,
    ClassInfo,
    ModuleInfo,
    Project,
)
from scripts.wrong_complete.py_scope import FunctionScope
from scripts.wrong_complete.sites import OTHER, POSSIBLE, TARGET, Site, Target

_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


class PythonOracle:
    """对一个项目、一个目标给出判定器调用点集合。"""

    def __init__(self, project: Project, target: Target) -> None:
        self.project = project
        self.target = target
        self.target_class = self._find_target_class()
        self.alias_names = self._alias_names()
        self.sites: list[Site] = []

    def _alias_names(self) -> frozenset[str]:
        """可能绑定到目标的名字：目标名本身、``import ... as`` 与赋值别名（传递闭包）。

        只是性能上的预筛：不在集合里的裸名不可能解析到目标，跳过其名字解析。
        """
        names = {self.target.name}
        changed = True
        while changed:
            changed = False
            for mod in self.project.by_path.values():
                for node in ast.walk(mod.tree):
                    for alias in _aliases_from(node, names):
                        if alias not in names:
                            names.add(alias)
                            changed = True
        return frozenset(names)

    def _find_target_class(self) -> ClassInfo | None:
        if self.target.owner is None:
            return None
        candidates = [
            cls
            for cls in self.project.classes
            if cls.module.path == self.target.file and cls.name == self.target.owner
        ]
        for cls in candidates:
            if any(
                f.lineno == self.target.line
                for f in cls.methods.get(self.target.name, [])
            ):
                return cls
        return candidates[0] if candidates else None

    # ------------------------------------------------------------ 遍历
    def run(self) -> list[Site]:
        """遍历全部模块，返回按位置排序的判定结果（同一位置只保留一条）。"""
        for mod in self.project.by_path.values():
            self._visit_body(mod, mod.tree.body, None, "<module>", None)
        unique: dict[tuple[str, int, str], Site] = {}
        for site in self.sites:
            key = (site.file, site.line, site.kind)
            current = unique.get(key)
            if current is None or _rank(site.verdict) > _rank(current.verdict):
                unique[key] = site
        return sorted(unique.values(), key=lambda s: (s.file, s.line, s.kind))

    def _visit_body(
        self,
        mod: ModuleInfo,
        nodes: Sequence[ast.AST],
        scope: FunctionScope | None,
        caller: str,
        owner: ClassInfo | None,
    ) -> None:
        for node in nodes:
            self._visit(mod, node, scope, caller, owner)

    def _visit(
        self,
        mod: ModuleInfo,
        node: ast.AST,
        scope: FunctionScope | None,
        caller: str,
        owner: ClassInfo | None,
    ) -> None:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            self._visit_function(mod, node, scope, caller, owner)
        elif isinstance(node, ast.ClassDef):
            self._visit_class(mod, node, scope, caller)
        elif isinstance(node, ast.Lambda):
            child = FunctionScope(self.project, mod, node, None, scope)
            self._visit(mod, node.body, child, caller, None)
        elif isinstance(node, _COMPREHENSIONS):
            names = tuple(
                sub.id
                for gen in node.generators
                for sub in ast.walk(gen.target)
                if isinstance(sub, ast.Name)
            )
            child = FunctionScope(self.project, mod, None, None, scope, names)
            for sub in ast.iter_child_nodes(node):
                self._visit(mod, sub, child, caller, None)
        elif isinstance(node, ast.Call):
            self._visit_call(mod, node, scope, caller)
        elif isinstance(node, ast.Attribute):
            self._visit_attribute(mod, node, scope, caller)
        elif isinstance(node, ast.Name):
            self._visit_name(mod, node, scope, caller)
        else:
            for sub in ast.iter_child_nodes(node):
                self._visit(mod, sub, scope, caller, None)

    def _visit_function(
        self,
        mod: ModuleInfo,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        scope: FunctionScope | None,
        caller: str,
        owner: ClassInfo | None,
    ) -> None:
        outer: list[ast.AST] = [*node.decorator_list, *node.args.defaults]
        outer.extend(d for d in node.args.kw_defaults if d is not None)
        self._visit_body(mod, outer, scope, caller, None)
        child = FunctionScope(self.project, mod, node, owner, scope)
        self._visit_body(mod, node.body, child, node.name, None)

    def _visit_class(
        self,
        mod: ModuleInfo,
        node: ast.ClassDef,
        scope: FunctionScope | None,
        caller: str,
    ) -> None:
        info = next((c for c in self.project.classes if c.node is node), None)
        self._visit_body(mod, [*node.decorator_list, *node.bases], scope, caller, None)
        for item in node.body:
            if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                self._visit_function(mod, item, scope, caller, info)
            else:
                self._visit(mod, item, scope, caller, None)

    # ------------------------------------------------------------ 节点
    def _record(
        self,
        mod: ModuleInfo,
        node: ast.AST,
        kind: str,
        verdict: str,
        reason: str,
        caller: str,
    ) -> None:
        line = getattr(node, "lineno", 0)
        self.sites.append(Site(mod.path, line, kind, verdict, reason, caller))

    def _eval(
        self, mod: ModuleInfo, expr: ast.expr, scope: FunctionScope | None
    ) -> Binding:
        return self.project.eval_expr(mod, expr, scope.lookup if scope else None)

    def _visit_call(
        self, mod: ModuleInfo, node: ast.Call, scope: FunctionScope | None, caller: str
    ) -> None:
        func = node.func
        name = self.target.name
        if isinstance(func, ast.Attribute):
            if func.attr == name:
                verdict, reason = self._classify_member(mod, func.value, scope)
                self._record(mod, node, "call", verdict, reason, caller)
            self._visit(mod, func.value, scope, caller, None)
        elif isinstance(func, ast.Name):
            if func.id in self.alias_names:
                verdict, reason = self._classify_bare(mod, func.id, scope)
                if verdict != OTHER or func.id == name:
                    self._record(mod, node, "call", verdict, reason, caller)
            if func.id == "getattr" and _getattr_names(node, name):
                verdict, reason = self._classify_member(mod, node.args[0], scope)
                self._record(
                    mod, node, "reference", verdict, f"getattr:{reason}", caller
                )
        else:
            self._visit(mod, func, scope, caller, None)
        for arg in [*node.args, *(kw.value for kw in node.keywords)]:
            self._visit(mod, arg, scope, caller, None)

    def _visit_attribute(
        self,
        mod: ModuleInfo,
        node: ast.Attribute,
        scope: FunctionScope | None,
        caller: str,
    ) -> None:
        if node.attr == self.target.name and isinstance(node.ctx, ast.Load):
            verdict, reason = self._classify_member(mod, node.value, scope)
            self._record(mod, node, "reference", verdict, reason, caller)
        self._visit(mod, node.value, scope, caller, None)

    def _visit_name(
        self, mod: ModuleInfo, node: ast.Name, scope: FunctionScope | None, caller: str
    ) -> None:
        if not isinstance(node.ctx, ast.Load) or node.id not in self.alias_names:
            return
        verdict, reason = self._classify_bare(mod, node.id, scope)
        if verdict == TARGET:
            self._record(mod, node, "reference", verdict, reason, caller)

    # ------------------------------------------------------------ 判定
    def _classify_bare(
        self, mod: ModuleInfo, name: str, scope: FunctionScope | None
    ) -> tuple[str, str]:
        """裸名调用 ``name(...)``（名字可能是目标的别名）。"""
        local = scope.lookup(name) if scope else None
        binding = local if local is not None else self.project.resolve_name(mod, name)
        target = self.target
        if binding[0] == "func":
            if (
                target.owner is None
                and binding[1] == target.file
                and binding[2] == target.name
            ):
                return (
                    TARGET,
                    "module_function" if name == target.name else "function_alias",
                )
            return OTHER, "other_function"
        if binding[0] == "localfunc":
            node = binding[1]
            if (
                target.owner is None
                and node.lineno == target.line
                and mod.path == target.file
            ):
                return TARGET, "nested_function"
            return OTHER, "other_function"
        if name != target.name:
            return OTHER, "different_name"
        if binding == UNKNOWN:
            return POSSIBLE, "unknown_callable"
        if binding[0] == "unbound" and mod.star_imports:
            return POSSIBLE, "star_import"
        return OTHER, f"bare_{binding[0]}"

    def _classify_member(
        self, mod: ModuleInfo, receiver: ast.expr, scope: FunctionScope | None
    ) -> tuple[str, str]:
        """``receiver.<name>`` 的判定。"""
        if _is_super_call(receiver):
            return self._classify_super(scope)
        binding = self._eval(mod, receiver, scope)
        kind = binding[0]
        if kind == "module":
            found = self.project.module_attr(binding[1], self.target.name)
            if self.target.owner is None and found == (
                "func",
                self.target.file,
                self.target.name,
            ):
                return TARGET, "module_attribute"
            return (
                (POSSIBLE, "module_attr_unknown")
                if found == UNKNOWN
                else (OTHER, "module_attribute")
            )
        if kind in ("class", "exact"):
            return self._classify_static(
                binding[1], "class_object" if kind == "class" else "constructed"
            )
        if kind in ("declared", "self"):
            return self._classify_dispatch(binding[1], kind)
        if binding == EXTERNAL or kind in ("func", "localfunc"):
            return OTHER, "external_or_function_object"
        return POSSIBLE, "unresolved_receiver"

    def _classify_static(self, cls: ClassInfo, reason: str) -> tuple[str, str]:
        """类型确定（类对象 / 构造实例）：不会分派到子类覆盖。"""
        found = self.project.lookup(cls, self.target.name)
        if found is not None and found is self.target_class:
            return TARGET, reason
        if found is None and self.project.has_unknown_base(cls):
            return POSSIBLE, "unknown_base"
        return OTHER, f"{reason}_other"

    def _classify_dispatch(self, cls: ClassInfo, kind: str) -> tuple[str, str]:
        """声明类型 / ``self``：静态类型或其子类，可能分派到覆盖。"""
        project = self.project
        found = project.lookup(cls, self.target.name)
        tcls = self.target_class
        if found is not None and found is tcls:
            return TARGET, kind
        if tcls is not None and tcls is not cls and project.is_subclass(tcls, cls):
            return POSSIBLE, "override_dispatch"
        if project.is_protocol(cls):
            return POSSIBLE, "protocol_receiver"
        if found is None and project.has_unknown_base(cls):
            return POSSIBLE, "unknown_base"
        if tcls is not None and kind == "self" and self._shared_subclass(cls, tcls):
            return POSSIBLE, "mixin_dispatch"
        return OTHER, f"{kind}_other"

    def _shared_subclass(self, cls: ClassInfo, tcls: ClassInfo) -> bool:
        """是否存在同时继承 ``cls`` 与目标类、且按 MRO 选中目标的类（mixin）。"""
        project = self.project
        return any(
            project.is_subclass(x, cls)
            and project.is_subclass(x, tcls)
            and project.lookup(x, self.target.name) is tcls
            for x in project.classes
        )

    def _classify_super(self, scope: FunctionScope | None) -> tuple[str, str]:
        found = scope.lookup("self") if scope else None
        if found is None or found[0] != "self":
            return POSSIBLE, "super_unknown"
        cls: ClassInfo = found[1]
        for klass in self.project.mro(cls)[1:]:
            if self.target.name in klass.methods:
                return (
                    (TARGET, "super")
                    if klass is self.target_class
                    else (OTHER, "super_other")
                )
        return (
            (POSSIBLE, "super_unknown_base")
            if self.project.has_unknown_base(cls)
            else (OTHER, "super_other")
        )


def _aliases_from(node: ast.AST, names: set[str]) -> list[str]:
    """``node`` 新引入的、指向 ``names`` 之一的别名。"""
    if isinstance(node, ast.ImportFrom):
        return [a.asname for a in node.names if a.asname and a.name in names]
    if isinstance(node, ast.Assign | ast.AnnAssign) and node.value is not None:
        value = node.value
        tail = (
            value.id
            if isinstance(value, ast.Name)
            else value.attr
            if isinstance(value, ast.Attribute)
            else None
        )
        if tail in names:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            return [t.id for t in targets if isinstance(t, ast.Name)]
    return []


def _rank(verdict: str) -> int:
    return {TARGET: 2, POSSIBLE: 1}.get(verdict, 0)


def _is_super_call(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "super"
    )


def _getattr_names(node: ast.Call, name: str) -> bool:
    return (
        len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value == name
    )


def python_sites(sources: dict[str, str], target: Target) -> list[Site]:
    """便捷入口：源码字典 + 目标 → 判定结果。"""
    return PythonOracle(Project(sources), target).run()
