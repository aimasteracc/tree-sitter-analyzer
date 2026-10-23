"""Python 项目的独立 ``ast`` 模型：模块、类、导入与名字解析。

只依赖标准库，绝不导入 ``tree_sitter_analyzer``。解析是**保守**的：只有
在源码本身能证明时才给出确定绑定，其余一律 ``UNKNOWN``。判定器据此把
无法证明的接收者当作“可能调用”，因此本模型的不精确只会让判定器更严格，
不会掩盖错误的 ``complete``。

绑定（``Binding``）是一个元组，首元素为种类：

* ``("module", 模块名)``；
* ``("class", ClassInfo)``：类对象本身；
* ``("exact", ClassInfo)``：由构造调用得到、类型确定的实例；
* ``("declared", ClassInfo)``：由注解声明的实例（可能是子类实例）；
* ``("self", ClassInfo)``：方法里的 ``self`` / ``cls``（可能是子类）；
* ``("func", 模块路径, 函数名)``：模块级函数；
* ``("localfunc", FunctionDef)``：函数内嵌套定义的函数；
* ``("external",)``：内建或项目外对象；``("unknown",)``：无法证明。
"""

from __future__ import annotations

import ast
import builtins
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

Binding = tuple[Any, ...]
UNKNOWN: Binding = ("unknown",)
EXTERNAL: Binding = ("external",)
_BUILTIN_NAMES = frozenset(dir(builtins))
_MAX_DEPTH = 12
FuncNode = ast.FunctionDef | ast.AsyncFunctionDef
#: 一个函数作用域里名字的局部查找函数；``None`` 表示本作用域未绑定。
LocalLookup = Callable[[str], "Binding | None"]


@dataclass(eq=False)
class ClassInfo:
    """一个类定义（含嵌套在函数里的类）。以对象身份比较。"""

    module: ModuleInfo
    name: str
    node: ast.ClassDef
    methods: dict[str, list[FuncNode]] = field(default_factory=dict)


@dataclass(eq=False)
class ModuleInfo:
    """一个已解析的 Python 模块。"""

    path: str
    name: str
    is_package: bool
    tree: ast.Module
    top: dict[str, list[tuple[Any, ...]]] = field(default_factory=dict)
    star_imports: list[str] = field(default_factory=list)


def module_name(rel: str) -> tuple[str, bool]:
    """``a/b/c.py`` → ``a.b.c``；``a/b/__init__.py`` → ``(a.b, True)``。"""
    parts = rel[:-3].split("/")
    if parts[-1] == "__init__":
        return ".".join(parts[:-1]), True
    return ".".join(parts), False


def _top_statements(body: list[ast.stmt]) -> Iterator[ast.stmt]:
    """模块顶层语句，展开顶层 ``if`` / ``try`` 分支（条件定义）。"""
    for stmt in body:
        if isinstance(stmt, ast.If):
            yield from _top_statements(stmt.body)
            yield from _top_statements(stmt.orelse)
        elif isinstance(stmt, ast.Try):
            for block in (stmt.body, stmt.orelse, stmt.finalbody):
                yield from _top_statements(block)
            for handler in stmt.handlers:
                yield from _top_statements(handler.body)
        else:
            yield stmt


def import_base(mod: ModuleInfo, level: int, module: str | None) -> str:
    """把 ``from ..x import y`` 的相对模块解析成绝对模块名。"""
    if level == 0:
        return module or ""
    package = mod.name if mod.is_package else mod.name.rpartition(".")[0]
    for _ in range(level - 1):
        package = package.rpartition(".")[0]
    if module:
        return f"{package}.{module}" if package else module
    return package


def _bind_import(mod: ModuleInfo, stmt: ast.Import | ast.ImportFrom) -> None:
    """把一条 import 语句的绑定写进 ``mod.top``。"""
    if isinstance(stmt, ast.Import):
        for alias in stmt.names:
            if alias.asname:
                mod.top.setdefault(alias.asname, []).append(("module", alias.name))
            else:
                head = alias.name.split(".")[0]
                mod.top.setdefault(head, []).append(("module", head))
        return
    base = import_base(mod, stmt.level, stmt.module)
    for alias in stmt.names:
        if alias.name == "*":
            mod.star_imports.append(base)
            continue
        local = alias.asname or alias.name
        mod.top.setdefault(local, []).append(("from", base, alias.name))


def _collect_classes(mod: ModuleInfo) -> list[ClassInfo]:
    """收集模块内全部类（含嵌套类），并登记各类的直接方法。"""
    found: list[ClassInfo] = []
    for node in ast.walk(mod.tree):
        if not isinstance(node, ast.ClassDef):
            continue
        info = ClassInfo(module=mod, name=node.name, node=node)
        for item in node.body:
            if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                info.methods.setdefault(item.name, []).append(item)
        found.append(info)
    return found


class Project:
    """一个小型 Python 项目的只读模型。"""

    def __init__(self, sources: dict[str, str]) -> None:
        self.modules: dict[str, ModuleInfo] = {}
        self.by_path: dict[str, ModuleInfo] = {}
        self.classes: list[ClassInfo] = []
        self._class_of_node: dict[int, ClassInfo] = {}
        for rel in sorted(sources):
            if not rel.endswith(".py"):
                continue
            try:
                tree = ast.parse(sources[rel])
            except (SyntaxError, ValueError):
                continue
            name, is_package = module_name(rel)
            mod = ModuleInfo(path=rel, name=name, is_package=is_package, tree=tree)
            self.modules[name] = mod
            self.by_path[rel] = mod
            for info in _collect_classes(mod):
                self.classes.append(info)
                self._class_of_node[id(info.node)] = info
        for mod in self.by_path.values():
            self._collect_top(mod)
        self._attr_cache: dict[tuple[int, str], Binding] = {}
        self._mro_cache: dict[int, list[ClassInfo]] = {}
        self._in_progress: set[tuple[int, str]] = set()

    # ------------------------------------------------------------ 模块作用域
    def _collect_top(self, mod: ModuleInfo) -> None:
        for stmt in _top_statements(mod.tree.body):
            if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
                mod.top.setdefault(stmt.name, []).append(("func", mod.path, stmt.name))
            elif isinstance(stmt, ast.ClassDef):
                mod.top.setdefault(stmt.name, []).append(
                    ("class", self._class_of_node[id(stmt)])
                )
            elif isinstance(stmt, ast.Import | ast.ImportFrom):
                _bind_import(mod, stmt)
            elif isinstance(stmt, ast.Assign):
                self._bind_assign(mod.top, stmt.targets, stmt.value)
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                spec = (
                    ("annot", stmt.annotation)
                    if stmt.value is None
                    else ("expr", stmt.value)
                )
                mod.top.setdefault(stmt.target.id, []).append(spec)
            else:
                for node in ast.walk(stmt):
                    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                        mod.top.setdefault(node.id, []).append(("unknown",))

    @staticmethod
    def _bind_assign(
        table: dict[str, list[tuple[Any, ...]]],
        targets: list[ast.expr],
        value: ast.expr,
    ) -> None:
        for target in targets:
            if isinstance(target, ast.Name):
                table.setdefault(target.id, []).append(("expr", value))
                continue
            for node in ast.walk(target):
                if isinstance(node, ast.Name):
                    table.setdefault(node.id, []).append(("unknown",))

    def find_module(self, name: str) -> ModuleInfo | None:
        """按模块名找项目模块；找不到时按唯一后缀匹配（``src/`` 布局）。"""
        if name in self.modules:
            return self.modules[name]
        suffix = "." + name
        hits = [m for key, m in self.modules.items() if key.endswith(suffix)]
        return hits[0] if len(hits) == 1 else None

    def resolve_name(self, mod: ModuleInfo, name: str, depth: int = 0) -> Binding:
        """模块作用域里的名字解析；多个互相矛盾的绑定一律 ``UNKNOWN``。"""
        if depth > _MAX_DEPTH:
            return UNKNOWN
        specs = mod.top.get(name)
        if not specs:
            for star in mod.star_imports:
                star_mod = self.find_module(star)
                if star_mod is None:
                    return UNKNOWN
                found = self.resolve_name(star_mod, name, depth + 1)
                if found[0] not in ("unbound",):
                    return found
            return EXTERNAL if name in _BUILTIN_NAMES else ("unbound",)
        results = {self._eval_spec(mod, spec, depth + 1) for spec in specs}
        return results.pop() if len(results) == 1 else UNKNOWN

    def _eval_spec(self, mod: ModuleInfo, spec: tuple[Any, ...], depth: int) -> Binding:
        kind = spec[0]
        if kind in ("func", "class"):
            return spec
        if kind == "module":
            return ("module", spec[1]) if self.find_module(spec[1]) else EXTERNAL
        if kind == "from":
            return self.resolve_from(spec[1], spec[2], depth)
        if kind == "expr":
            return self.eval_expr(mod, spec[1], None, depth)
        if kind == "annot":
            cls = self.annotation_class(mod, spec[1])
            return ("declared", cls) if cls else UNKNOWN
        return UNKNOWN

    def resolve_from(self, base: str, name: str, depth: int = 0) -> Binding:
        """``from base import name`` 的绑定（子模块优先，再查模块属性）。"""
        sub = self.find_module(f"{base}.{name}" if base else name)
        if sub is not None:
            return ("module", sub.name)
        base_mod = self.find_module(base)
        if base_mod is None:
            return EXTERNAL
        found = self.resolve_name(base_mod, name, depth + 1)
        return UNKNOWN if found[0] == "unbound" else found

    def module_attr(self, modname: str, attr: str, depth: int = 0) -> Binding:
        """``模块.attr`` 的绑定。"""
        mod = self.find_module(modname)
        if mod is None:
            return EXTERNAL
        sub = self.find_module(f"{mod.name}.{attr}")
        if sub is not None:
            return ("module", sub.name)
        found = self.resolve_name(mod, attr, depth + 1)
        return UNKNOWN if found[0] == "unbound" else found

    # ------------------------------------------------------------ 表达式求值
    def eval_expr(
        self, mod: ModuleInfo, expr: ast.expr, local: LocalLookup | None, depth: int = 0
    ) -> Binding:
        """求一个表达式的绑定；``local`` 为函数作用域的局部查找。"""
        if depth > _MAX_DEPTH:
            return UNKNOWN
        if isinstance(expr, ast.Name):
            if local is not None:
                found = local(expr.id)
                if found is not None:
                    return found
            result = self.resolve_name(mod, expr.id, depth + 1)
            return UNKNOWN if result[0] == "unbound" else result
        if isinstance(expr, ast.Attribute):
            owner = self.eval_expr(mod, expr.value, local, depth + 1)
            return self.attribute_of(owner, expr.attr, depth + 1)
        if isinstance(expr, ast.Call):
            return self.call_result(mod, expr, local, depth + 1)
        if isinstance(
            expr, ast.Constant | ast.JoinedStr | ast.List | ast.Dict | ast.Set
        ):
            return EXTERNAL
        if isinstance(expr, ast.Tuple | ast.ListComp | ast.DictComp | ast.SetComp):
            return EXTERNAL
        return UNKNOWN

    def call_result(
        self, mod: ModuleInfo, call: ast.Call, local: LocalLookup | None, depth: int
    ) -> Binding:
        """调用表达式的结果：构造调用给出确定实例，带返回注解的函数给出声明实例。"""
        callee = self.eval_expr(mod, call.func, local, depth + 1)
        if callee[0] == "class":
            return ("exact", callee[1])
        if callee[0] == "func":
            node = self.function_node(callee)
            if node is not None and node.returns is not None:
                cls = self.annotation_class(self.by_path[callee[1]], node.returns)
                if cls is not None:
                    return ("declared", cls)
        return EXTERNAL if callee == EXTERNAL else UNKNOWN

    def attribute_of(self, owner: Binding, attr: str, depth: int) -> Binding:
        """``owner.attr`` 的绑定（模块属性或实例属性类型）。"""
        kind = owner[0]
        if kind == "module":
            return self.module_attr(owner[1], attr, depth + 1)
        if kind in ("exact", "declared", "self"):
            return self.instance_attr(owner[1], attr)
        if kind == "external":
            return EXTERNAL
        return UNKNOWN

    def function_node(self, binding: Binding) -> FuncNode | None:
        """``("func", path, name)`` 对应的（最后一个）定义节点。"""
        mod = self.by_path.get(binding[1])
        if mod is None:
            return None
        nodes = [
            stmt
            for stmt in _top_statements(mod.tree.body)
            if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef)
            and stmt.name == binding[2]
        ]
        return nodes[-1] if nodes else None

    def annotation_class(
        self, mod: ModuleInfo, ann: ast.expr | None
    ) -> ClassInfo | None:
        """注解 → 项目类；``Optional[X]`` / ``X | None`` / 字符串注解展开，容器泛型不追踪。"""
        if ann is None:
            return None
        if isinstance(ann, ast.Constant) and isinstance(ann.value, str):
            try:
                return self.annotation_class(
                    mod, ast.parse(ann.value, mode="eval").body
                )
            except SyntaxError:
                return None
        if isinstance(ann, ast.BinOp) and isinstance(ann.op, ast.BitOr):
            sides = [s for s in (ann.left, ann.right) if not _is_none(s)]
            return self.annotation_class(mod, sides[0]) if len(sides) == 1 else None
        if isinstance(ann, ast.Subscript) and dotted(ann.value).endswith("Optional"):
            return self.annotation_class(mod, ann.slice)
        if isinstance(ann, ast.Name | ast.Attribute):
            found = self.eval_expr(mod, ann, None)
            return found[1] if found[0] == "class" else None
        return None

    # ------------------------------------------------------------ 继承
    def bases(self, cls: ClassInfo) -> tuple[list[ClassInfo], bool, bool]:
        """直接基类：``(已解析基类, 是否有无法解析的基类, 是否 Protocol)``。"""
        resolved: list[ClassInfo] = []
        unknown = False
        protocol = False
        for base in cls.node.bases:
            target = base.value if isinstance(base, ast.Subscript) else base
            name = dotted(target)
            if name.endswith("Protocol"):
                protocol = True
                continue
            if name in ("object", "Generic", "typing.Generic"):
                continue
            found = self.eval_expr(cls.module, target, None)
            if found[0] == "class":
                resolved.append(found[1])
            else:
                unknown = True
        return resolved, unknown, protocol

    def mro(self, cls: ClassInfo) -> list[ClassInfo]:
        """深度优先、左优先、去重的近似 MRO（含自身）；按类缓存。"""
        cached = self._mro_cache.get(id(cls))
        if cached is not None:
            return cached
        order: list[ClassInfo] = []
        stack = [cls]
        while stack and len(order) < 64:
            current = stack.pop(0)
            if current in order:
                continue
            order.append(current)
            stack[0:0] = self.bases(current)[0]
        self._mro_cache[id(cls)] = order
        return order

    def lookup(self, cls: ClassInfo, name: str) -> ClassInfo | None:
        """沿 MRO 找第一个声明 ``name`` 的类。"""
        for klass in self.mro(cls):
            if name in klass.methods:
                return klass
        return None

    def has_unknown_base(self, cls: ClassInfo) -> bool:
        """MRO 上是否有无法解析（项目外）的基类。"""
        return any(self.bases(klass)[1] for klass in self.mro(cls))

    def is_protocol(self, cls: ClassInfo) -> bool:
        """MRO 上是否有 ``typing.Protocol``（结构类型：任何同名方法都可能是实现）。"""
        return any(self.bases(klass)[2] for klass in self.mro(cls))

    def is_subclass(self, sub: ClassInfo, sup: ClassInfo) -> bool:
        """``sub`` 是否（传递地）继承 ``sup``（含相等）。"""
        return sup in self.mro(sub)

    # ------------------------------------------------------------ 实例属性
    def instance_attr(self, cls: ClassInfo, attr: str) -> Binding:
        """``self.attr`` 的类型：类体注解、``@property`` 返回注解或各方法里一致的赋值。"""
        from scripts.wrong_complete.py_attrs import own_attr

        key = (id(cls), attr)
        if key in self._attr_cache:
            return self._attr_cache[key]
        if key in self._in_progress:
            return UNKNOWN
        self._in_progress.add(key)
        try:
            result = UNKNOWN
            for klass in self.mro(cls):
                found = own_attr(self, klass, attr)
                if found is not None:
                    result = found
                    break
        finally:
            self._in_progress.discard(key)
        self._attr_cache[key] = result
        return result


def _is_none(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def is_name(node: ast.expr, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def dotted(node: ast.expr) -> str:
    """``a.b.C`` → ``"a.b.C"``；其他表达式返回空串。"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        head = dotted(node.value)
        return f"{head}.{node.attr}" if head else ""
    return ""
