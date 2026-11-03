"""#1883: a Python method whose class has a base the index cannot follow.

The index records a Python base only when it is written as a name or a dotted
name (``Proc``, ``a.Proc``); ``class V1(mix(Proc))``, ``class V3(*bases)``,
``class V8(Alias)`` with ``Alias = Proc`` and ``class V9(GProc[int])`` get no
inheritance edge. ``self.get_query()`` in ``Proc.run`` is then never offered
``V1.get_query``, and the override answered ``complete`` with 0 callers.

The walk reads every base of the declaring class, and of every project class
above it, from source with :mod:`ast` (never from inheritance edges), and fails
closed on the first one it cannot follow:

* followed: a class bound once in the scope that evaluates the ``class``
  statement (an enclosing function, the enclosing class body, the module); a
  name imported from a project module, relative or absolute (``src`` layout and
  the importing file's own directories are tried), through ``__init__``
  re-exports and ``import *``; ``mod.Cls`` and ``Outer.Inner`` dotted paths;
* known external, the walk stops there: a module that is not a project file and
  is in the standard library, or whose top-level name is not a project
  directory or module (a third-party package); a builtin class (``object``,
  ``Exception``) the module does not rebind; a subscript of such a class
  (``Generic[T]``, ``typing.Protocol[T]``);
* anything else is ``DYNAMIC_SUPERTYPE``, named by its clause: a call, a
  starred argument, a conditional, a subscripted project class (the index
  records no edge for it), a name bound to a value or bound more than once, a
  name no scope binds, an import that does not resolve to one project file, a
  ``**`` class keyword, a ``metaclass=`` that is not external or whose
  ``__new__`` may rebind the bases (or that defines ``mro``), a cycle or a
  walk longer than :data:`_CLASSES_MAX` classes.

No member is exempt. The JS/TS gate exempts constructors (reached only by
``new``) and ``#private`` members (never reached through a subclass); Python has
no such member: ``self.__init__()`` in a base dispatches to the subclass's
``__init__``, and a mangled ``__m`` is reached from any base class that has the
same simple name.
"""

from __future__ import annotations

import ast
import builtins
import os
import posixpath
import sys
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

from .callers_supertypes import SupertypeFinding
from .evidence_file_cache import FILE_CACHE, StatKey

PY_SUFFIX = ".py"
#: Project classes visited in one walk (bases of bases included).
_CLASSES_MAX = 64
#: Import hops followed for one name (re-exports, star imports).
_HOPS_MAX = 32
#: Builtin classes: external, like a package, unless the module rebinds them.
BUILTIN_CLASSES = frozenset(
    name for name, value in vars(builtins).items() if isinstance(value, type)
)
_STDLIB = frozenset(getattr(sys, "stdlib_module_names", ()))
_PARSED_MAX = 128
_PARSED: OrderedDict[tuple[str, StatKey], _Module | None] = OrderedDict()
_PARSED_LOCK = threading.Lock()
_SCOPES = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


def clear_parsed() -> None:
    """Forget the memoized parses (tests)."""
    with _PARSED_LOCK:
        _PARSED.clear()


@dataclass(eq=False)
class _Module:
    """One parsed Python file: its tree, parents and per-scope bindings."""

    rel: str
    tree: ast.Module
    parents: dict[int, ast.AST]
    #: Names a function declares ``global``: an extra module-level binding.
    globals_declared: frozenset[str]
    has_getattr: bool
    _bindings: dict[int, dict[str, list[ast.AST]]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def bindings(self, scope: ast.AST) -> dict[str, list[ast.AST]]:
        with self._lock:
            found = self._bindings.get(id(scope))
            if found is None:
                found = _scope_bindings(scope)
                self._bindings[id(scope)] = found
            return found

    def stars(self) -> list[ast.ImportFrom]:
        return [
            node
            for node in _scope_nodes(self.tree)
            if isinstance(node, ast.ImportFrom)
            and any(alias.name == "*" for alias in node.names)
        ]


def _parse(rel: str, data: bytes) -> _Module | None:
    try:
        tree = ast.parse(data.decode("utf-8-sig"))
    except (SyntaxError, ValueError, UnicodeDecodeError, RecursionError):
        return None
    parents: dict[int, ast.AST] = {}
    declared: set[str] = set()
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
        if isinstance(node, ast.Global):
            declared.update(node.names)
    has_getattr = any(
        isinstance(node, _FUNCTIONS) and node.name == "__getattr__"
        for node in tree.body
    )
    return _Module(rel, tree, parents, frozenset(declared), has_getattr)


def _scope_nodes(scope: ast.AST) -> list[ast.AST]:
    """Every node evaluated in ``scope``'s own namespace (nested bodies pruned)."""
    body: list[ast.AST] = (
        [scope.body] if isinstance(scope, ast.Lambda) else list(scope.body)  # type: ignore[attr-defined]
    )
    found: list[ast.AST] = []
    stack = list(reversed(body))
    while stack:
        node = stack.pop()
        found.append(node)
        if isinstance(node, (*_FUNCTIONS, ast.ClassDef, ast.Lambda)):
            continue  # its name binds here; its body is another scope
        stack.extend(reversed(list(ast.iter_child_nodes(node))))
    return found


def _scope_bindings(scope: ast.AST) -> dict[str, list[ast.AST]]:
    """name -> binding nodes in ``scope``: defs, classes, imports (aliases), stores."""
    found: dict[str, list[ast.AST]] = {}
    if isinstance(scope, (*_FUNCTIONS, ast.Lambda)):
        args = scope.args
        for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs]:
            found.setdefault(arg.arg, []).append(arg)
        for extra in (args.vararg, args.kwarg):
            if extra is not None:
                found.setdefault(extra.arg, []).append(extra)
    for node in _scope_nodes(scope):
        for name, binding in _bound(node):
            found.setdefault(name, []).append(binding)
    return found


def _bound(node: ast.AST) -> list[tuple[str, ast.AST]]:
    if isinstance(node, (*_FUNCTIONS, ast.ClassDef)):
        return [(node.name, node)]
    if isinstance(node, ast.Import | ast.ImportFrom):
        return [
            (alias.asname or alias.name.split(".", 1)[0], alias)
            for alias in node.names
            if alias.name != "*"
        ]
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store | ast.Del):
        return [(node.id, node)]
    if isinstance(node, ast.Global | ast.Nonlocal):
        return [(name, node) for name in node.names]
    name = getattr(node, "name", None)
    if isinstance(node, ast.ExceptHandler | ast.MatchAs | ast.MatchStar) and name:
        return [(str(name), node)]
    if isinstance(node, ast.MatchMapping) and node.rest:
        return [(node.rest, node)]
    return []


# --- values -------------------------------------------------------------------


@dataclass(frozen=True)
class _Class:
    module: _Module
    node: ast.ClassDef


@dataclass(frozen=True)
class _ModuleRef:
    """A module named by an import: ``level`` dots plus ``dotted``, from ``from_rel``."""

    from_rel: str
    level: int
    dotted: str


#: What an expression evaluates to: a project class, a module, ``None`` for a
#: known external class (or module), or why it cannot be followed.
_Value = _Class | _ModuleRef | str | None
_MISSING = object()
_UNDECLARED = "a name not bound in any scope of its module"
_TWICE = "a name bound more than once in its scope"
_AMBIGUOUS = "an import that resolves to more than one project file"
_UNRESOLVED = "an import that does not resolve to one project file"
_UNPARSED = "an import whose file could not be read or parsed"
_EXPRESSION_KINDS = {
    "Call": "a call (a mixin or class factory)",
    "Starred": "a starred argument",
    "IfExp": "a conditional",
    "BoolOp": "a boolean expression",
    "NamedExpr": "an assignment expression",
    "Lambda": "a lambda",
}


class _Reader:
    """One walk: parsed modules, module resolution and the project's top names."""

    def __init__(
        self, project_root: str, tops: Callable[[], frozenset[str] | None]
    ) -> None:
        self.root = project_root
        self._tops = tops
        self._tops_value: frozenset[str] | None = None
        self._tops_read = False
        self._modules: dict[str, _Module | None] = {}
        self._files: dict[str, bool] = {}
        self.visiting: set[tuple[str, str]] = set()

    def module(self, rel: str) -> _Module | None:
        if rel not in self._modules:
            self._modules[rel] = self._load(rel)
        return self._modules[rel]

    def _load(self, rel: str) -> _Module | None:
        found = FILE_CACHE.read_stamped(os.path.join(self.root, *rel.split("/")))
        if found is None:
            return None
        data, stamp = found
        key = (rel, stamp) if stamp is not None else None
        if key is not None:
            with _PARSED_LOCK:
                if key in _PARSED:
                    _PARSED.move_to_end(key)
                    return _PARSED[key]
        parsed = _parse(rel, data)
        if key is not None:
            with _PARSED_LOCK:
                _PARSED[key] = parsed
                while len(_PARSED) > _PARSED_MAX:
                    _PARSED.popitem(last=False)
        return parsed

    def is_file(self, rel: str) -> bool:
        if rel not in self._files:
            self._files[rel] = os.path.isfile(os.path.join(self.root, *rel.split("/")))
        return self._files[rel]

    def is_dir(self, rel: str) -> bool:
        return os.path.isdir(os.path.join(self.root, *rel.split("/")))

    def tops(self) -> frozenset[str] | None:
        if not self._tops_read:
            self._tops_read = True
            self._tops_value = self._tops()
        return self._tops_value

    def find(self, ref: _ModuleRef) -> str | None:
        """The one project file ``ref`` names; ``""`` when none; None if ambiguous."""
        parts = [p for p in ref.dotted.split(".") if p]
        if ref.level:
            base = posixpath.dirname(ref.from_rel)
            for _ in range(ref.level - 1):
                if not base:
                    return ""
                base = posixpath.dirname(base)
            roots = [base]
        else:
            roots = _absolute_roots(ref.from_rel)
        found = {
            path
            for root in roots
            for path in _candidates(root, parts)
            if self.is_file(path)
        }
        if len(found) > 1:
            return None
        return next(iter(found), "")


def _absolute_roots(from_rel: str) -> list[str]:
    """Import roots for an absolute module: the project, ``src`` and the file's dirs."""
    roots = ["", "src"]
    current = posixpath.dirname(from_rel)
    while current:
        roots.append(current)
        current = posixpath.dirname(current)
    return roots


def _candidates(root: str, parts: list[str]) -> list[str]:
    if not parts:
        return [posixpath.join(root, "__init__.py")] if root else []
    stem = posixpath.join(root, *parts)
    return [stem + PY_SUFFIX, posixpath.join(stem, "__init__.py")]


# --- the walk -----------------------------------------------------------------


def python_dynamic_base(
    project_root: str,
    rel: str,
    line: int,
    bare: str,
    tops: Callable[[], frozenset[str] | None],
) -> tuple[str | None, SupertypeFinding | None]:
    """The declaring class's name and the first unfollowable base above ``bare``.

    The name is None when ``rel:line`` holds no class-body member ``bare``.
    """
    reader = _Reader(project_root, tops)
    module = reader.module(rel)
    if module is None:
        return None, _unchecked(rel, "the declaring file could not be read or parsed")
    owner = _owner_class(module, line, bare)
    if owner is None:
        return None, None
    return owner.name, _walk(reader, _Class(module, owner))


def _owner_class(module: _Module, line: int, bare: str) -> ast.ClassDef | None:
    """The class whose body directly declares ``bare`` on ``line`` (innermost)."""
    best: Any = None
    node: Any
    for node in ast.walk(module.tree):
        if not _declares(node, bare):
            continue
        first = min(
            [node.lineno, *(d.lineno for d in getattr(node, "decorator_list", ()))]
        )
        if not first <= line <= (node.end_lineno or node.lineno):
            continue
        if best is None or node.lineno >= best.lineno:
            best = node
    parent = None if best is None else module.parents.get(id(best))
    return parent if isinstance(parent, ast.ClassDef) else None


def _declares(node: ast.AST, bare: str) -> bool:
    if isinstance(node, _FUNCTIONS):
        return node.name == bare
    if isinstance(node, ast.Assign):
        return any(isinstance(t, ast.Name) and t.id == bare for t in node.targets)
    if isinstance(node, ast.AnnAssign):
        return isinstance(node.target, ast.Name) and node.target.id == bare
    return False


def _walk(reader: _Reader, start: _Class) -> SupertypeFinding | None:
    """Depth-first over every base; a class on the current path again is a cycle."""
    done: set[tuple[str, int]] = set()
    path: set[tuple[str, int]] = set()
    stack: list[tuple[_Class, bool]] = [(start, False)]
    while stack:
        cls, leaving = stack.pop()
        key = (cls.module.rel, id(cls.node))
        if leaving:
            path.discard(key)
            done.add(key)
            continue
        if key in path:
            return _finding(cls, None, "whose bases form a cycle")
        if key in done:
            continue
        if len(done) + len(path) >= _CLASSES_MAX:
            return _finding(cls, None, "whose bases are too many to follow")
        path.add(key)
        stack.append((cls, True))
        found, bases = _class_bases(reader, cls)
        if found is not None:
            return found
        stack.extend((base, False) for base in reversed(bases))
    return None


def _class_bases(
    reader: _Reader, cls: _Class
) -> tuple[SupertypeFinding | None, list[_Class]]:
    scopes = _scopes_for(cls.module, cls.node)
    bases: list[_Class] = []
    for expr in cls.node.bases:
        value = _base_value(reader, cls.module, scopes, expr)
        if isinstance(value, str):
            return _finding(cls, expr, value), []
        if isinstance(value, _ModuleRef):
            return _finding(cls, expr, "a module, not a class"), []
        if isinstance(value, _Class):
            bases.append(value)
    for keyword in cls.node.keywords:
        why = _keyword_problem(reader, cls.module, scopes, keyword)
        if why is not None:
            return _finding(cls, keyword, why, verb="has class keyword"), []
    return None, bases


def _keyword_problem(
    reader: _Reader, module: _Module, scopes: list[ast.AST], keyword: ast.keyword
) -> str | None:
    """Why a class keyword may inject bases; None for a plain ``__init_subclass__`` one."""
    if keyword.arg is None:
        return "a `**` keyword that may pass a metaclass"
    if keyword.arg != "metaclass":
        return None
    value = _eval(reader, module, scopes, keyword.value, 0)
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, _ModuleRef):
        return "a module, not a metaclass"
    return _metaclass_problem(reader, value)


def _metaclass_problem(reader: _Reader, meta: _Class) -> str | None:
    """A project metaclass may rebind the bases in ``__new__`` or replace ``mro``."""
    chain = _project_chain(reader, meta)
    if isinstance(chain, str):
        return f"a metaclass whose bases cannot be followed ({chain})"
    for cls in chain:
        for node in cls.node.body:
            if isinstance(node, _FUNCTIONS) and node.name == "mro":
                return f"a metaclass `{cls.node.name}` that defines `mro`"
            if isinstance(node, _FUNCTIONS) and node.name == "__new__":
                if not _passes_bases(node):
                    return (
                        f"a metaclass `{cls.node.name}` whose `__new__` rebinds "
                        "its bases"
                    )
    return None


def _project_chain(reader: _Reader, start: _Class) -> list[_Class] | str:
    found: list[_Class] = []
    stack = [start]
    seen: set[tuple[str, int]] = set()
    while stack:
        cls = stack.pop()
        key = (cls.module.rel, id(cls.node))
        if key in seen:
            continue
        if len(seen) >= _CLASSES_MAX:
            return "too many classes"
        seen.add(key)
        found.append(cls)
        scopes = _scopes_for(cls.module, cls.node)
        for expr in cls.node.bases:
            value = _base_value(reader, cls.module, scopes, expr)
            if isinstance(value, str | _ModuleRef):
                return f"`{ast.unparse(expr)}`"
            if isinstance(value, _Class):
                stack.append(value)
    return found


def _passes_bases(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """``__new__(mcs, name, bases, ns)`` never rebinds ``bases`` and passes it on as is."""
    params = [*func.args.posonlyargs, *func.args.args]
    if len(params) < 3 or func.args.vararg is not None:
        return False
    bases = params[2].arg
    for node in ast.walk(func):
        if isinstance(node, ast.Name) and node.id == bases:
            if not isinstance(node.ctx, ast.Load):
                return False
        if isinstance(node, ast.Global | ast.Nonlocal) and bases in node.names:
            return False
        if isinstance(node, ast.Call) and _creates_class(node):
            args = node.args
            if len(args) < 3 or not (
                isinstance(args[2], ast.Name) and args[2].id == bases
            ):
                return False
    return True


def _creates_class(call: ast.Call) -> bool:
    """``super().__new__(...)``, ``type.__new__(...)`` or ``type(name, bases, ns)``."""
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr == "__new__":
        return True
    return isinstance(func, ast.Name) and func.id == "type" and len(call.args) == 3


def _scopes_for(module: _Module, node: ast.AST) -> list[ast.AST]:
    """Scopes a ``class`` statement's bases are evaluated in, innermost first.

    The enclosing scope itself (a class body is visible only to statements
    directly in it), then enclosing functions, then the module.
    """
    scopes: list[ast.AST] = []
    current = module.parents.get(id(node))
    while current is not None:
        if isinstance(current, _SCOPES) and (
            not scopes or not isinstance(current, ast.ClassDef)
        ):
            scopes.append(current)
        current = module.parents.get(id(current))
    return scopes if scopes else [module.tree]


def _base_value(
    reader: _Reader, module: _Module, scopes: list[ast.AST], expr: ast.expr
) -> _Value:
    if isinstance(expr, ast.Subscript):
        value = _eval(reader, module, scopes, expr.value, 0)
        if isinstance(value, _Class):
            return (
                "a subscripted project class (the index records no inheritance "
                "edge for it)"
            )
        return value
    return _eval(reader, module, scopes, expr, 0)


def _eval(
    reader: _Reader, module: _Module, scopes: list[ast.AST], expr: ast.expr, hops: int
) -> _Value:
    if isinstance(expr, ast.Name):
        return _resolve_name(reader, module, scopes, expr.id, hops)
    if isinstance(expr, ast.Attribute):
        owner = _eval(reader, module, scopes, expr.value, hops)
        return _attribute(reader, owner, expr.attr, hops)
    kind = _EXPRESSION_KINDS.get(type(expr).__name__, f"a `{type(expr).__name__}`")
    return f"{kind} the index cannot follow"


def _resolve_name(
    reader: _Reader, module: _Module, scopes: list[ast.AST], name: str, hops: int
) -> _Value:
    for scope in scopes:
        if scope is module.tree:
            break
        entries = module.bindings(scope).get(name)
        if entries:
            if len(entries) == 1 and isinstance(entries[0], ast.ClassDef):
                return _Class(module, entries[0])
            if len(entries) == 1 and isinstance(entries[0], ast.alias):
                return _import_value(reader, module, entries[0], hops)
            return "a local value, not a class the index can follow"
    found = _lookup(reader, module, name, hops)
    if found is not _MISSING:
        return cast("_Value", found)
    return None if name in BUILTIN_CLASSES else _UNDECLARED


def _lookup(reader: _Reader, module: _Module, name: str, hops: int) -> Any:
    """``name`` at the module level of ``module``; :data:`_MISSING` if nothing binds it."""
    if hops > _HOPS_MAX:
        return "an import whose re-exports are too deep to follow"
    key = (module.rel, name)
    if key in reader.visiting:
        return "an import cycle"
    reader.visiting.add(key)
    try:
        entries = list(module.bindings(module.tree).get(name, ()))
        if name in module.globals_declared:
            return _TWICE
        if entries:
            return _module_binding(reader, module, entries, hops)
        return _star_lookup(reader, module, name, hops)
    finally:
        reader.visiting.discard(key)


def _module_binding(
    reader: _Reader, module: _Module, entries: list[ast.AST], hops: int
) -> _Value:
    values: list[_Value] = []
    for entry in entries:
        if isinstance(entry, ast.ClassDef):
            values.append(_Class(module, entry))
        elif isinstance(entry, ast.alias):
            values.append(_import_value(reader, module, entry, hops))
        elif len(entries) == 1:
            return "a value, not a class the index can follow"
        else:
            return _TWICE
    if len(values) == 1:
        return values[0]
    # ``try: from typing import X`` / ``except: from typing_extensions import X``.
    return None if all(value is None for value in values) else _TWICE


def _star_lookup(reader: _Reader, module: _Module, name: str, hops: int) -> Any:
    external = False
    found: list[_Value] = []
    for star in module.stars():
        ref = _ModuleRef(module.rel, star.level, star.module or "")
        target = reader.find(ref)
        if target is None:
            return _AMBIGUOUS
        if not target:
            why = _unfound(reader, ref)
            if why is not None:
                return why
            external = True
            continue
        other = reader.module(target)
        if other is None:
            return _UNPARSED
        value = _lookup(reader, other, name, hops + 1)
        if value is not _MISSING:
            found.append(value)
    if len(found) > 1:
        return _TWICE
    if found:
        return found[0]
    return None if external else _MISSING


def _import_value(
    reader: _Reader, module: _Module, alias: ast.alias, hops: int
) -> _Value:
    stmt = module.parents.get(id(alias))
    if isinstance(stmt, ast.Import):
        dotted = alias.name if alias.asname else alias.name.split(".", 1)[0]
        return _ModuleRef(module.rel, 0, dotted)
    if not isinstance(stmt, ast.ImportFrom):
        return "an import the index cannot follow"
    package = _ModuleRef(module.rel, stmt.level, stmt.module or "")
    return _attribute(reader, package, alias.name, hops)


def _attribute(reader: _Reader, owner: _Value, attr: str, hops: int) -> _Value:
    """``owner.attr``: a class nested in a class, or a name / submodule of a module."""
    if owner is None or isinstance(owner, str):
        return owner
    if isinstance(owner, _Class):
        entries = owner.module.bindings(owner.node).get(attr) or []
        if len(entries) == 1 and isinstance(entries[0], ast.ClassDef):
            return _Class(owner.module, entries[0])
        return "a class attribute that is not a class the index can follow"
    target = reader.find(owner)
    if target is None:
        return _AMBIGUOUS
    if target:
        other = reader.module(target)
        if other is None:
            return _UNPARSED
        value = _lookup(reader, other, attr, hops + 1)
        if value is not _MISSING:
            return value  # type: ignore[no-any-return]
    sub = _ModuleRef(owner.from_rel, owner.level, _join(owner.dotted, attr))
    found = reader.find(sub)
    if found is None:
        return _AMBIGUOUS
    if found:
        return sub
    if target:
        if not owner.level and owner.dotted.split(".", 1)[0] in _STDLIB:
            # ``tests/types.py`` next to ``from types import X``: the stdlib
            # module is the one imported first, the project file only shadows it
            # on a path the walk tries for scripts.
            return None
        if target.endswith("/__init__.py") or target == "__init__.py":
            return "a name its package does not bind (nor a submodule)"
        return "a name its module does not bind"
    return _unfound(reader, owner)


def _unfound(reader: _Reader, ref: _ModuleRef) -> str | None:
    """A module that is no project file: external, or why it cannot be followed."""
    if ref.level:
        return _UNRESOLVED
    top = ref.dotted.split(".", 1)[0]
    if top in _STDLIB:
        return None
    if reader.find(_ModuleRef(ref.from_rel, 0, top)) != "" or reader.is_dir(top):
        return _UNRESOLVED  # the top-level package is a project one
    tops = reader.tops()
    if tops is None:
        return "an import whose module cannot be classified (the index is unreadable)"
    return _UNRESOLVED if top in tops else None


def _join(dotted: str, attr: str) -> str:
    return f"{dotted}.{attr}" if dotted else attr


def _finding(
    cls: _Class, expr: ast.AST | None, why: str, *, verb: str = "has base"
) -> SupertypeFinding:
    clause = "?" if expr is None else _clause_text(expr)
    return SupertypeFinding(
        " ".join(clause.split())[:80],
        cls.module.rel,
        cls.node.lineno,
        cls.node.name,
        why,
        verb=verb,
    )


def _clause_text(expr: ast.AST) -> str:
    try:
        return ast.unparse(expr)
    except Exception:  # noqa: BLE001 — a clause we cannot print is still named
        return "?"


def _unchecked(rel: str, why: str) -> SupertypeFinding:
    return SupertypeFinding("", rel, 0, "", why, unchecked=True)


__all__ = ["BUILTIN_CLASSES", "PY_SUFFIX", "clear_parsed", "python_dynamic_base"]
