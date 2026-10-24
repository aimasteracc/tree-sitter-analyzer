"""Independent ground-truth oracle for the unified-query benchmark (RFC-0041).

Uses only the standard-library :mod:`ast` module: it shares no code with
tree-sitter-analyzer, so a TSA bug cannot hide behind the oracle agreeing with
itself. Call resolution is by *name*: a call ``foo(...)`` or ``x.foo(...)`` is
an edge to every definition named ``foo``. That over-approximates for common
names, so the benchmark questions use targets whose names are unique in the
repository (``unique_definition`` checks this); for those, the name-based edge
set is the true static call set.

Test semantics match ``nav action=test_map`` (RFC-0014 Phase B): a test is a
pytest-collectible function (``test_*``) or the module scope of a test file
that calls the target directly, or through one non-collectible helper in a
test file.
"""

from __future__ import annotations

import ast
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

_SKIP_DIRS = frozenset(
    {".git", ".ast-cache", ".venv", "venv", "node_modules", "__pycache__", ".tox"}
)


@dataclass(frozen=True)
class Definition:
    """One function or method definition."""

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


class _Visitor(ast.NodeVisitor):
    def __init__(self, file: str) -> None:
        self.file = file
        self.defs: list[Definition] = []
        self.calls: list[tuple[str, str, int]] = []  # (callee, caller, line)
        self._stack: list[str] = []
        self._cls: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
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
        if name:
            caller = self._stack[-1] if self._stack else "<module>"
            self.calls.append((name, caller, node.lineno))
        self.generic_visit(node)


class Oracle:
    """Name-based static call oracle over one repository checkout."""

    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.defs: list[Definition] = []
        # callee name -> set of (file, caller name)
        self.callers_by_name: dict[str, set[tuple[str, str]]] = defaultdict(set)
        # (file, caller name) -> set of callee names
        self.callees_of: dict[tuple[str, str], set[str]] = defaultdict(set)
        self.sites_by_name: dict[str, set[tuple[str, int]]] = defaultdict(set)
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
                visitor = _Visitor(rel)
                visitor.visit(tree)
                self.defs.extend(visitor.defs)
                for callee, caller, line in visitor.calls:
                    self.callers_by_name[callee].add((rel, caller))
                    self.callees_of[(rel, caller)].add(callee)
                    self.sites_by_name[callee].add((rel, line))

    # -- questions -----------------------------------------------------------
    def definitions(self, name: str) -> list[Definition]:
        return [d for d in self.defs if d.name == name]

    def unique_definition(self, name: str) -> bool:
        return len(self.definitions(name)) == 1

    def callers(self, name: str) -> set[str]:
        return {f"{f}::{c}" for f, c in self.callers_by_name.get(name, set())}

    def tests_of(self, name: str) -> set[str]:
        """Test entries reaching ``name`` directly or via one test-file helper."""
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
        """Callers up to ``depth`` hops, keeping only files under ``prefix``."""
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
        """Project-defined callee names called from ``file::func``."""
        defined = {d.name for d in self.defs}
        return {c for c in self.callees_of.get((file, func), set()) if c in defined}
