"""统一查询基准测试的独立 ground-truth oracle (RFC-0041)。

只使用标准库 :mod:`ast` 模块，与 tree-sitter-analyzer 不共享任何代码，因此
TSA 的 bug 不可能因 oracle "自己与自己一致" 而被掩盖。调用按*名称*解析：
调用 ``foo(...)`` 或 ``x.foo(...)`` 会连边到所有名为 ``foo`` 的定义。对常见
名称这会过度近似，所以基准问题选用在仓库中名称唯一的目标
(由 ``unique_definition`` 检查)；对这些目标，基于名称的边集合就是真实的
静态调用集合。

测试语义与 ``nav action=test_map`` (RFC-0014 Phase B) 一致：测试是指
可被 pytest 收集的函数 (``test_*``) 或测试文件的模块作用域，它直接调用目标，
或经由测试文件中一个不可收集的辅助函数间接调用目标。
"""

from __future__ import annotations

import ast
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

_SKIP_DIRS = frozenset(
    {".git", ".ast-cache", ".venv", "venv", "node_modules", "__pycache__", ".tox"}
)


@dataclass(frozen=True)
class Definition:
    """一个函数或方法定义。"""

    file: str
    name: str
    cls: str | None
    line: int
    end_line: int

    @property
    def key(self) -> str:
        return f"{self.file}::{self.name}"


def is_test_file(path: str) -> bool:
    parts = path.replace("\\", "/").split("/")
    base = parts[-1]
    return (
        "tests" in parts[:-1]
        or "test" in parts[:-1]
        or base.startswith("test_")
        or base.endswith("_test.py")
        or base == "conftest.py"
    )


def is_test_entry(path: str, name: str) -> bool:
    return is_test_file(path) and (name.startswith("test_") or name == "<module>")


def _stdlib_aliases(tree: ast.Module) -> tuple[frozenset[str], frozenset[str]]:
    """文件里绑定到标准库的名字：(模块名, 从标准库导入的名字)。

    #1814 复核时发现：``time.monotonic()`` / ``os.path.exists()`` 与 rich 的
    ``from html import escape`` 按名字连到了项目里恰好同名的唯一定义，Q8 的 callees
    真值因此多出标准库调用。经标准库模块属性的调用、以及对从标准库导入的名字的
    调用不可能指向项目内定义，不计为边。
    """
    modules: set[str] = set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.partition(".")[0]
                if top in sys.stdlib_module_names:
                    modules.add(alias.asname or top)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            if node.module.partition(".")[0] in sys.stdlib_module_names:
                names.update(alias.asname or alias.name for alias in node.names)
    return frozenset(modules), frozenset(names)


#: 字面量接收者（``"".join(...)``、``[].append(...)``）：方法属于内置类型，不是项目代码。
_LITERAL_RECEIVERS = (
    ast.Constant,
    ast.JoinedStr,
    ast.List,
    ast.Dict,
    ast.Set,
    ast.Tuple,
    ast.ListComp,
    ast.DictComp,
    ast.SetComp,
)


def _receiver_root(expr: ast.expr) -> str | None:
    while isinstance(expr, ast.Attribute):
        expr = expr.value
    return expr.id if isinstance(expr, ast.Name) else None


class _Visitor(ast.NodeVisitor):
    def __init__(
        self,
        file: str,
        stdlib: tuple[frozenset[str], frozenset[str]] = (frozenset(), frozenset()),
    ) -> None:
        self.file = file
        self.defs: list[Definition] = []
        self.calls: list[tuple[str, str, int]] = []  # (被调用者, 调用者, 行号)
        self._stack: list[str] = []
        self._cls: list[str] = []
        self._stdlib_modules, self._stdlib_names = stdlib
        self.classes: set[str] = set()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.classes.add(node.name)
        self._cls.append(node.name)
        self.generic_visit(node)
        self._cls.pop()

    def _visit_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        cls = self._cls[-1] if self._cls and not self._stack else None
        self.defs.append(
            Definition(
                self.file, node.name, cls, node.lineno, node.end_lineno or node.lineno
            )
        )
        self._stack.append(node.name)
        saved_cls = self._cls
        self._cls = []
        self.generic_visit(node)
        self._cls = saved_cls
        self._stack.pop()

    visit_FunctionDef = _visit_func
    visit_AsyncFunctionDef = _visit_func

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        name = (
            func.id
            if isinstance(func, ast.Name)
            else func.attr
            if isinstance(func, ast.Attribute)
            else None
        )
        if isinstance(func, ast.Attribute) and (
            _receiver_root(func.value) in self._stdlib_modules
            or isinstance(func.value, _LITERAL_RECEIVERS)
        ):
            name = None  # 标准库模块 / 字面量的方法调用（见 ``_stdlib_aliases``）
        elif isinstance(func, ast.Name) and func.id in self._stdlib_names:
            name = None  # 从标准库导入的名字
        if name:
            caller = self._stack[-1] if self._stack else "<module>"
            self.calls.append((name, caller, node.lineno))
        self.generic_visit(node)


class Oracle:
    """针对一个仓库检出、基于名称的静态调用 oracle。"""

    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.defs: list[Definition] = []
        # 被调用者名称 -> (文件, 调用者名称) 的集合
        self.callers_by_name: dict[str, set[tuple[str, str]]] = defaultdict(set)
        # (文件, 调用者名称) -> 被调用者名称的集合
        self.callees_of: dict[tuple[str, str], set[str]] = defaultdict(set)
        self.sites_by_name: dict[str, set[tuple[str, int]]] = defaultdict(set)
        #: 项目内定义的类名（callees 把直接调用类——构造——计为调用项目代码）。
        self.classes: set[str] = set()
        self._scan()

    def _scan(self) -> None:
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for filename in filenames:
                if not filename.endswith(".py"):
                    continue
                full = Path(dirpath) / filename
                rel = full.relative_to(self.root).as_posix()
                try:
                    tree = ast.parse(full.read_text(encoding="utf-8"))
                except (SyntaxError, UnicodeDecodeError):
                    continue
                visitor = _Visitor(rel, _stdlib_aliases(tree))
                visitor.visit(tree)
                self.defs.extend(visitor.defs)
                self.classes |= visitor.classes
                for callee, caller, line in visitor.calls:
                    self.callers_by_name[callee].add((rel, caller))
                    self.callees_of[(rel, caller)].add(callee)
                    self.sites_by_name[callee].add((rel, line))

    # -- 问题 ----------------------------------------------------------------
    def definitions(self, name: str) -> list[Definition]:
        return [d for d in self.defs if d.name == name]

    def unique_definition(self, name: str) -> bool:
        return len(self.definitions(name)) == 1

    def callers(self, name: str) -> set[str]:
        return {f"{f}::{c}" for f, c in self.callers_by_name.get(name, set())}

    def tests_of(self, name: str) -> set[str]:
        """直接或经由一个测试文件辅助函数到达 ``name`` 的测试入口。"""
        out: set[str] = set()
        for file, caller in self.callers_by_name.get(name, set()):
            if not is_test_file(file):
                continue
            if is_test_entry(file, caller):
                out.add(f"{file}::{caller}")
                continue
            for pfile, parent in self.callers_by_name.get(caller, set()):
                if is_test_entry(pfile, parent):
                    out.add(f"{pfile}::{parent}")
        return out

    def callers_within(self, name: str, depth: int, prefix: str) -> set[str]:
        """最多 ``depth`` 跳的调用者，只保留 ``prefix`` 下的文件。"""
        frontier = {name}
        seen: set[str] = set()
        out: set[str] = set()
        for _ in range(depth):
            nxt: set[str] = set()
            for target in frontier:
                for file, caller in self.callers_by_name.get(target, set()):
                    key = f"{file}::{caller}"
                    if file.startswith(prefix) and caller != "<module>":
                        out.add(key)
                    if caller not in seen and caller != "<module>":
                        seen.add(caller)
                        nxt.add(caller)
            frontier = nxt
        return out

    def transitive_callers(self, name: str, max_depth: int = 50) -> set[str]:
        frontier = {name}
        seen: set[str] = {name}
        out: set[str] = set()
        for _ in range(max_depth):
            nxt: set[str] = set()
            for target in frontier:
                for file, caller in self.callers_by_name.get(target, set()):
                    out.add(f"{file}::{caller}")
                    if caller not in seen and caller != "<module>":
                        seen.add(caller)
                        nxt.add(caller)
            if not nxt:
                break
            frontier = nxt
        return out

    def module_funcs_calling_without_tests(self, module: str, callee: str) -> set[str]:
        out: set[str] = set()
        for file, caller in self.callers_by_name.get(callee, set()):
            if file != module or caller == "<module>":
                continue
            if not self.tests_of(caller):
                out.add(f"{file}::{caller}")
        return out

    def implementers(self, method: str) -> set[str]:
        return {f"{d.file}::{d.cls}" for d in self.definitions(method) if d.cls}

    def call_sites(self, name: str) -> set[str]:
        return {f"{f}:{line}" for f, line in self.sites_by_name.get(name, set())}

    def callees(self, file: str, func: str) -> set[str]:
        """``file::func`` 调用的、在项目内定义的被调用者名称。

        #1814 复核：直接调用项目内的类（构造，如 ``CurrentSourceSnapshot(...)``）同样
        执行项目代码，``nav callees`` 也把它列为被调方，因此计入。
        """
        defined = {d.name for d in self.defs} | self.classes
        return {c for c in self.callees_of.get((file, func), set()) if c in defined}
