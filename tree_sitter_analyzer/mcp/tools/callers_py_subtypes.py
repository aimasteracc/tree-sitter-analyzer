"""#1896: a Python method a subclass inherits as another base's method.

.. code-block:: python

    class A:                        # pkg/a.py
        def m(self): ...
    class I:                        # pkg/i.py
        def m(self): raise NotImplementedError
        def run(self): return self.m()
    class B(A, I): ...              # pkg/b.py; MRO: B, A, I

``B().run()`` runs ``A.m``, but the call edge of ``self.m()`` in ``I.run`` is
bound to ``I.m`` (and ``A`` has no base), so ``A.m`` answered ``complete``
with 0 callers. In one file the call was already a name-only site.

:func:`python_subtype_finding` walks the project subclasses of the declaring
class ``C`` (transitively). A subclass ``T`` is *dangerous* when its ancestry
holds a class ``X`` that declares the same name and is unrelated to ``C`` (not
``C``, not above it, not below it): a call bound to ``X.m`` (``self.m()`` in
``X``, an ``x: X`` receiver) runs ``C.m`` on a ``T``, when ``C`` comes first in
the MRO; when ``X`` comes first, ``super().m()`` in ``X`` reaches ``C.m``. The
position is not used: either way a call that does not name ``C.m`` may run it.
Classes above ``C`` are the override case, which the call graph already offers
(#1648); classes below ``C`` override it.

The method then passes only when no call edge named like it may dispatch
there: an edge outside the project, a plain ``m()`` call (never a method), an
edge bound to this declaration, and an edge whose receiver class (the class
enclosing ``self.m()`` / ``cls.m()`` / ``super().m()``, or the class the edge
is bound to) is in no dangerous subclass's ancestry, are not. An unbound
receiver may be anything.

The subclasses are found from source, never from inheritance edges, with the
import resolver of :mod:`.callers_py_supertypes`. Every class of every indexed
Python file is read once into an index cached per project state (the index
snapshot and the stat of every file); a subscripted project class
(``A[int]``) is followed as the class. It fails closed when a file that may
declare a subclass cannot be read or parsed, when a base that may name the
class or one of its subclasses (``mix(A)``) cannot be followed, when the
ancestry of a subclass cannot, and past :data:`_MAX_SUBCLASSES` subclasses.

Not checked, by design: a mangled ``__m`` (each class has its own); members of
external bases (calls from outside the project are not project callers); and
subclasses outside the project (closed world, as for Java #1894).
"""

from __future__ import annotations

import ast
import os
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from .callers_java_overrides import OVERRIDE_REASON
from .callers_java_subtypes import SUBTYPE_VERB
from .callers_py_supertypes import (
    _Class,
    _declares,
    _eval,
    _keyword_problem,
    _Module,
    _owner_class,
    _Reader,
    _scopes_for,
)
from .callers_supertypes import SupertypeFinding
from .evidence_file_cache import FILE_CACHE

#: Subclasses of one class walked before giving up (fail closed).
_MAX_SUBCLASSES = 4096
#: Sites named in the hint.
_SITES_NAMED = 3
#: Project states (roots) whose class index is kept.
_INDEXES_MAX = 4
#: A file modified this recently may change again within its stat granularity.
_RACY_NS = 5_000_000_000
_OUTSIDE = frozenset({"external", "stdlib", "builtin"})
_FILE_BOUND = frozenset({"local", "project"})

#: ``(file, line, column)`` of a ``class`` statement.
_Key = tuple[str, int, int]


@dataclass(frozen=True)
class _Unknown:
    """A base (or class keyword) the resolver cannot follow."""

    clause: str
    why: str
    #: Names the clause mentions (and the names they are bound to).
    mentions: frozenset[str]


#: A base: a project class, ``None`` for an external one, or an unknown one.
_Base = _Key | _Unknown | None


@dataclass(frozen=True)
class _ClassFacts:
    name: str
    rel: str
    line: int
    end: int
    bases: tuple[_Base, ...]
    #: Names bound in the class body.
    names: frozenset[str]


@dataclass
class _Index:
    """Every class of the project's Python files, from source."""

    classes: dict[_Key, _ClassFacts]
    children: dict[_Key, list[_Key]]
    #: Classes with a base that cannot be followed.
    unknown: list[tuple[_Key, _Unknown]]
    by_file: dict[str, list[_Key]]
    unreadable: list[str]
    unparsed: list[str]
    _ancestors: dict[_Key, frozenset[_Key] | tuple[_Key, _Unknown]] = field(
        default_factory=dict
    )
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def ancestors(self, key: _Key) -> frozenset[_Key] | tuple[_Key, _Unknown]:
        """``key`` and every class above it, or the first base that cannot be followed."""
        with self._lock:
            found = self._ancestors.get(key)
        if found is not None:
            return found
        found = self._walk_up(key)
        with self._lock:
            self._ancestors[key] = found
        return found

    def _walk_up(self, key: _Key) -> frozenset[_Key] | tuple[_Key, _Unknown]:
        seen = {key}
        stack = [key]
        while stack:
            current = stack.pop()
            for base in self.classes[current].bases:
                if isinstance(base, _Unknown):
                    return current, base
                if base is not None and base not in seen:
                    seen.add(base)
                    stack.append(base)
        return frozenset(seen)

    def class_at(self, rel: str, line: int, name: str = "") -> _Key | None:
        """The innermost class of ``rel`` spanning ``line`` (binding ``name``)."""
        best: _Key | None = None
        for key in self.by_file.get(rel, ()):
            facts = self.classes[key]
            if not facts.line <= line <= facts.end:
                continue
            if name and name not in facts.names:
                continue
            if best is None or facts.line >= self.classes[best].line:
                best = key
        return best


_INDEXES: OrderedDict[str, tuple[Any, _Index]] = OrderedDict()
_INDEXES_LOCK = threading.Lock()


def clear_indexes() -> None:
    """Forget the cached class indexes (tests)."""
    with _INDEXES_LOCK:
        _INDEXES.clear()


# --- the finding ----------------------------------------------------------------


def python_subtype_finding(
    project_root: str,
    rel: str,
    line: int,
    bare: str,
    cache: Any,
    tops: Callable[[], frozenset[str] | None],
) -> SupertypeFinding | None:
    """Why a call through another base of a project subclass may reach ``bare``.

    None when ``rel:line`` holds no class-body member ``bare`` or when no such
    call is possible.
    """
    if bare.startswith("__") and not bare.endswith("__"):
        return None  # mangled: ``self.__m()`` in another class is ``_X__m``
    reader = _Reader(project_root, tops)
    module = reader.module(rel)
    if module is None:
        return None  # the base walk already reported the unreadable file
    owner = _owner_class(module, line, bare)
    if owner is None:
        return None
    target = _key(rel, owner)
    finding = _Finder(project_root, rel, owner, bare, cache, tops)
    sites = finding.coarse_sites(module, line)
    if isinstance(sites, SupertypeFinding):
        return sites
    if not sites:
        return None
    index = _project_index(project_root, cache, tops)
    if isinstance(index, str):
        return finding.fail("?", index)
    return finding.check(index, target, sites)


def _key(rel: str, node: ast.ClassDef) -> _Key:
    return (rel, node.lineno, node.col_offset)


@dataclass
class _Site:
    file: str
    line: int
    receiver: str
    resolution: str
    resolved_file: str
    symbol: int | None


class _Finder:
    """One target: its call sites and the verdict over its subclasses."""

    def __init__(
        self,
        root: str,
        rel: str,
        owner: ast.ClassDef,
        bare: str,
        cache: Any,
        tops: Callable[[], frozenset[str] | None],
    ) -> None:
        self.root = root
        self.rel = rel
        self.owner = owner
        self.bare = bare
        self.cache = cache
        self.tops = tops

    def fail(self, subclass: str, why: str) -> SupertypeFinding:
        return SupertypeFinding(
            subclass,
            self.rel,
            self.owner.lineno,
            self.owner.name,
            why,
            verb=SUBTYPE_VERB,
            reason=OVERRIDE_REASON,
        )

    def coarse_sites(self, module: _Module, line: int) -> list[_Site] | SupertypeFinding:
        """Call edges named ``bare`` that may dispatch to a method not named here."""
        member = next(
            (
                node
                for node in self.owner.body
                if _declares(node, self.bare)
                and _first_line(node) <= line <= (getattr(node, "end_lineno", 0) or 0)
            ),
            None,
        )
        first = line if member is None else _first_line(member)
        last = line if member is None else member.lineno
        try:
            conn = self.cache.get_conn()
            own = {
                int(row[0])
                for row in conn.execute(
                    "SELECT id FROM ast_symbol_rows WHERE file_path = ? AND name = ? "
                    "AND kind IN ('method', 'function') AND line BETWEEN ? AND ?",
                    (self.rel, self.bare, first, last),
                )
            }
            same_file = int(
                conn.execute(
                    "SELECT count(*) FROM ast_symbol_rows WHERE file_path = ? "
                    "AND name = ? AND kind IN ('method', 'function')",
                    (self.rel, self.bare),
                ).fetchone()[0]
            )
            rows = conn.execute(
                "SELECT file_path, line, callee_full, callee_resolution, "
                "callee_resolved_file, callee_symbol_id FROM edges "
                "WHERE kind = 'calls' AND callee_name = ? AND language = 'python'",
                (self.bare,),
            ).fetchall()
        except Exception:  # noqa: BLE001 — unreadable: cannot prove
            return self.fail("?", "the call edges named like it could not be read")
        sites: list[_Site] = []
        for file, call_line, full, resolution, resolved_file, symbol in rows:
            receiver, dot, _name = str(full or "").rpartition(".")
            resolution = str(resolution or "")
            if not dot or resolution in _OUTSIDE:
                continue  # a plain call is never a method; an outside one is not ours
            if symbol is not None and int(symbol) in own:
                continue
            if (
                str(resolved_file or "") == self.rel
                and resolution in _FILE_BOUND
                and same_file == 1
            ):
                continue
            sites.append(
                _Site(
                    str(file),
                    int(call_line or 0),
                    receiver,
                    resolution,
                    str(resolved_file or ""),
                    None if symbol is None else int(symbol),
                )
            )
        sites.sort(key=lambda site: (site.file, site.line))
        return sites

    def check(
        self, index: _Index, target: _Key, sites: list[_Site]
    ) -> SupertypeFinding | None:
        subclasses = _subclasses(index, target)
        if isinstance(subclasses, str):
            return self.fail("?", subclasses)
        blocked = _possible_subclass(self.root, index, target, subclasses)
        if blocked is not None:
            return self.fail(*blocked)
        above = index.ancestors(target)
        related = (above if isinstance(above, frozenset) else {target}) | subclasses
        reach: set[_Key] = set()
        first: tuple[str, _Key] | None = None
        for sub in sorted(subclasses):
            ancestry = index.ancestors(sub)
            if not isinstance(ancestry, frozenset):
                where, base = ancestry
                return self.fail(
                    index.classes[sub].name,
                    f"whose ancestry cannot be followed: class "
                    f"`{index.classes[where].name}` has base `{base.clause}`, "
                    f"{base.why}",
                )
            declaring = sorted(
                key
                for key in ancestry - related
                if self.bare in index.classes[key].names
            )
            if declaring:
                reach |= ancestry
                if first is None:
                    first = (index.classes[sub].name, declaring[0])
        if first is None:
            return None
        kept = [site for site in sites if self._may_reach(index, site, reach)]
        if not kept:
            return None
        subclass, other = first
        facts = index.classes[other]
        return self.fail(
            subclass,
            f"which also inherits `{facts.name}.{self.bare}` ({facts.rel}:"
            f"{facts.line}), so a call through `{facts.name}` may run this "
            "method; call(s) named like it are not bound to this declaration "
            "and may dispatch here: " + _describe(kept),
        )

    def _may_reach(self, index: _Index, site: _Site, reach: set[_Key]) -> bool:
        """The receiver's class may be an instance of a dangerous subclass."""
        if site.receiver in ("self", "cls") or site.receiver.startswith("super("):
            klass = index.class_at(site.file, site.line)
        elif site.symbol is not None:
            klass = self._bound_class(index, site.symbol)
        else:
            return True  # an unbound receiver may be anything
        return klass is None or klass in reach

    def _bound_class(self, index: _Index, symbol: int) -> _Key | None:
        try:
            row = (
                self.cache.get_conn()
                .execute(
                    "SELECT file_path, line FROM ast_symbol_rows WHERE id = ?",
                    (symbol,),
                )
                .fetchone()
            )
        except Exception:  # noqa: BLE001 — unknown binding: may reach
            return None
        if row is None:
            return None
        return index.class_at(str(row[0]), int(row[1] or 0), self.bare)


def _first_line(node: Any) -> int:
    return min([node.lineno, *(d.lineno for d in getattr(node, "decorator_list", ()))])


def _describe(sites: list[_Site]) -> str:
    named = [f"{site.file}:{site.line}" for site in sites[:_SITES_NAMED]]
    if len(sites) > _SITES_NAMED:
        named.append(f"and {len(sites) - _SITES_NAMED} more")
    return "; ".join(named)


def _subclasses(index: _Index, target: _Key) -> set[_Key] | str:
    found: set[_Key] = set()
    stack = [target]
    while stack:
        for child in index.children.get(stack.pop(), ()):
            if child in found or child == target:
                continue
            found.add(child)
            if len(found) > _MAX_SUBCLASSES:
                return (
                    f"it has too many subclasses to check (more than "
                    f"{_MAX_SUBCLASSES})"
                )
            stack.append(child)
    return found


def _possible_subclass(
    root: str, index: _Index, target: _Key, subclasses: set[_Key]
) -> tuple[str, str] | None:
    """A class or file that may subclass the target without the index knowing."""
    names = {index.classes[key].name for key in (target, *subclasses)}
    for key, base in index.unknown:
        if key in subclasses or not base.mentions & names:
            continue
        facts = index.classes[key]
        return facts.name, (
            f"which may be one: class `{facts.name}` ({facts.rel}:{facts.line}) "
            f"has base `{base.clause}`, {base.why}"
        )
    if index.unreadable:
        rel = index.unreadable[0]
        return "?", f"{rel}, which may declare a subclass, could not be read"
    pattern = re.compile(r"\b(?:" + "|".join(map(re.escape, sorted(names))) + r")\b")
    for rel in index.unparsed:
        text = FILE_CACHE.read_text(os.path.join(root, *rel.split("/")))
        if text is None or pattern.search(text):
            return "?", f"{rel}, which may declare a subclass, could not be parsed"
    return None


# --- the project class index ------------------------------------------------------


def _project_index(
    root: str, cache: Any, tops: Callable[[], frozenset[str] | None]
) -> _Index | str:
    """The class index of the project's indexed Python files, cached per state."""
    files = _python_files(cache)
    if files is None:
        return "the project's Python files could not be listed to find its subclasses"
    stamps, racy = _stamps(root, files)
    from ...resident import snapshot_memo

    state = (snapshot_memo.snapshot_key(cache), stamps)
    with _INDEXES_LOCK:
        hit = _INDEXES.get(root)
        if hit is not None and hit[0] == state:
            _INDEXES.move_to_end(root)
            return hit[1]
    index = _build(root, files, tops)
    if not racy:
        with _INDEXES_LOCK:
            _INDEXES[root] = (state, index)
            _INDEXES.move_to_end(root)
            while len(_INDEXES) > _INDEXES_MAX:
                _INDEXES.popitem(last=False)
    return index


def _python_files(cache: Any) -> list[str] | None:
    if cache is None:
        return None
    from ...resident import snapshot_memo

    def read() -> list[str] | None:
        try:
            rows = (
                cache.get_conn()
                .execute("SELECT file_path FROM ast_index WHERE language = 'python'")
                .fetchall()
            )
        except Exception:  # noqa: BLE001 — unreadable: cannot list
            return None
        return sorted({str(row[0]).replace("\\", "/") for row in rows})

    found = snapshot_memo.cached(cache, "py_subtypes.files", (), read)
    return None if found is None else list(found)


def _stamps(
    root: str, files: list[str]
) -> tuple[tuple[tuple[str, tuple[int, int, int] | None], ...], bool]:
    now = time.time_ns()
    found: list[tuple[str, tuple[int, int, int] | None]] = []
    racy = False
    for rel in files:
        try:
            info = os.stat(os.path.join(root, *rel.split("/")))
        except OSError:
            found.append((rel, None))
            continue
        found.append((rel, (info.st_size, info.st_mtime_ns, info.st_ctime_ns)))
        racy = racy or now - info.st_mtime_ns < _RACY_NS
    return tuple(found), racy


def _build(
    root: str, files: list[str], tops: Callable[[], frozenset[str] | None]
) -> _Index:
    reader = _Reader(root, tops)
    index = _Index({}, {}, [], {}, [], [])
    for rel in files:
        if FILE_CACHE.read_bytes(os.path.join(root, *rel.split("/"))) is None:
            index.unreadable.append(rel)
            continue
        module = reader.module(rel)
        if module is None:
            index.unparsed.append(rel)
            continue
        for node in ast.walk(module.tree):
            if isinstance(node, ast.ClassDef):
                _add_class(reader, module, node, index)
    for key, facts in index.classes.items():
        for base in facts.bases:
            if isinstance(base, tuple):
                index.children.setdefault(base, []).append(key)
    return index


def _add_class(
    reader: _Reader, module: _Module, node: ast.ClassDef, index: _Index
) -> None:
    key = _key(module.rel, node)
    scopes = _scopes_for(module, node)
    bases: list[_Base] = []
    for expr in node.bases:
        bases.append(_base(reader, module, scopes, expr))
    for keyword in node.keywords:
        try:
            why = _keyword_problem(reader, module, scopes, keyword)
        except RecursionError:
            why = "a class keyword the index cannot follow"
        if why is not None:
            clause = ast.unparse(keyword)
            bases.append(_Unknown(clause, why, _mentions(module, [keyword.value])))
    for base in bases:
        if isinstance(base, _Unknown):
            index.unknown.append((key, base))
    index.classes[key] = _ClassFacts(
        node.name,
        module.rel,
        node.lineno,
        node.end_lineno or node.lineno,
        tuple(bases),
        frozenset(module.bindings(node)),
    )
    index.by_file.setdefault(module.rel, []).append(key)


def _base(
    reader: _Reader, module: _Module, scopes: list[ast.AST], expr: ast.expr
) -> _Base:
    """A base class; a subscripted project class (``A[int]``) is the class."""
    try:
        value: Any = _eval(
            reader,
            module,
            scopes,
            expr.value if isinstance(expr, ast.Subscript) else expr,
            0,
        )
    except RecursionError:
        value = "a base too deeply nested to follow"
    if isinstance(value, _Class):
        return _key(value.module.rel, value.node)
    if value is None:
        return None
    why = value if isinstance(value, str) else "a module, not a class"
    return _Unknown(
        " ".join(ast.unparse(expr).split())[:80], why, _mentions(module, [expr])
    )


def _mentions(module: _Module, exprs: Iterable[ast.AST]) -> frozenset[str]:
    """Names in ``exprs``, and what a module-level name among them is bound to."""
    found: set[str] = set()
    for expr in exprs:
        for node in ast.walk(expr):
            if isinstance(node, ast.Attribute):
                found.add(node.attr)
            elif isinstance(node, ast.Name):
                found.add(node.id)
                found |= _bound_to(module, node.id)
    return frozenset(found)


def _bound_to(module: _Module, name: str) -> set[str]:
    found: set[str] = set()
    for entry in module.bindings(module.tree).get(name, ()):
        if isinstance(entry, ast.alias):
            found.add(entry.name.rpartition(".")[2])
            continue
        parent = module.parents.get(id(entry))
        value = getattr(parent, "value", None)
        if isinstance(value, ast.AST):
            for node in ast.walk(value):
                if isinstance(node, ast.Name):
                    found.add(node.id)
                elif isinstance(node, ast.Attribute):
                    found.add(node.attr)
    return found


__all__ = ["clear_indexes", "python_subtype_finding"]
