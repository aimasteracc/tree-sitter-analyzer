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
``X``, an ``x: X`` receiver) runs ``C.m`` on a ``T`` when ``C`` comes first in
the MRO; when ``X`` comes first, ``super().m()`` in ``X`` reaches ``C.m``. The
position is therefore not used. Classes above ``C`` are the override case the
call graph already offers (#1648); classes below ``C`` override it.

The method then passes only when no call edge named like it may dispatch
there. Not such an edge: one outside the project, a plain ``m()`` call (never
a method), one bound to this declaration, and one whose receiver class (the
class around ``self.m()`` / ``cls.m()`` / ``super().m()``, or the class the
edge is bound to) is in no dangerous subclass's ancestry. An unbound receiver
may be anything. Without such an edge the subclasses are not even read.

The subclasses are found from source with the import resolver
(:mod:`.callers_py_class_index`, cached per project state); a subscripted
project class (``A[int]``) is followed as the class. It fails closed when a
file that may declare a subclass cannot be read or parsed, when a base that
may name the class or one of its subclasses (``mix(A)``) cannot be followed,
when the ancestry of a subclass cannot, and past :data:`_MAX_SUBCLASSES`.

Not checked, by design: a mangled ``__m`` (each class has its own); members of
external bases (calls from outside the project are not project callers); and
subclasses outside the project (closed world, as for Java #1894).
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .callers_java_overrides import OVERRIDE_REASON
from .callers_java_subtypes import SUBTYPE_VERB
from .callers_py_class_index import (
    ClassFacts,
    ClassIndex,
    Key,
    Unknown,
    class_key,
    project_index,
)
from .callers_py_supertypes import _declares, _owner_class, _Reader
from .callers_supertypes import SupertypeFinding

#: Subclasses of one class walked before giving up (fail closed).
_MAX_SUBCLASSES = 4096
#: Sites named in the hint.
_SITES_NAMED = 3
_OUTSIDE = frozenset({"external", "stdlib", "builtin"})
_FILE_BOUND = frozenset({"local", "project"})
_Tops = Callable[[], frozenset[str] | None]


def python_subtype_finding(
    project_root: str,
    rel: str,
    line: int,
    bare: str,
    cache: Any,
    tops: _Tops,
) -> SupertypeFinding | None:
    """Why a call through another base of a project subclass may reach ``bare``.

    None when ``rel:line`` holds no class-body member ``bare`` or when no such
    call is possible.
    """
    if bare.startswith("__") and not bare.endswith("__"):
        return None  # mangled: ``self.__m()`` in another class is ``_X__m``
    module = _Reader(project_root, tops).module(rel)
    if module is None:
        return None  # the base walk already reported the unreadable file
    owner = _owner_class(module, line, bare)
    if owner is None:
        return None
    finder = _Finder(project_root, rel, owner, bare, cache, tops)
    if cache is None:
        return finder.fail("?", "the project index could not be read")
    sites = finder.sites(line)
    if isinstance(sites, SupertypeFinding):
        return sites
    if not sites:
        return None
    index = project_index(project_root, cache)
    if isinstance(index, str):
        return finder.fail("?", index)
    return finder.check(index, class_key(rel, owner), sites)


@dataclass(frozen=True)
class _Site:
    file: str
    line: int
    receiver: str
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
        tops: _Tops,
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

    # --- call sites -------------------------------------------------------------

    def sites(self, line: int) -> list[_Site] | SupertypeFinding:
        """Call edges named ``bare`` that may run a method this one stands for."""
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
        sites = [
            _Site(str(file), int(call_line or 0), receiver, symbol)
            for file, call_line, full, resolution, resolved_file, symbol in rows
            for receiver in [str(full or "").rpartition(".")[0]]
            if receiver
            and str(resolution or "") not in _OUTSIDE
            and not (symbol is not None and int(symbol) in own)
            and not (
                str(resolved_file or "") == self.rel
                and str(resolution or "") in _FILE_BOUND
                and same_file == 1
            )
        ]
        return sorted(sites, key=lambda site: (site.file, site.line))

    def _may_reach(self, index: ClassIndex, site: _Site, reach: set[Key]) -> bool:
        """The receiver's class may be an instance of a dangerous subclass."""
        if site.receiver in ("self", "cls") or site.receiver.startswith("super("):
            klass = index.class_at(site.file, site.line)
        elif site.symbol is not None:
            klass = self._bound_class(index, int(site.symbol))
        else:
            return True  # an unbound receiver may be anything
        return klass is None or klass in reach

    def _bound_class(self, index: ClassIndex, symbol: int) -> Key | None:
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

    # --- subclasses -------------------------------------------------------------

    def check(
        self, index: ClassIndex, target: Key, sites: list[_Site]
    ) -> SupertypeFinding | None:
        if index.unreadable:
            return self.fail(
                "?",
                f"{index.unreadable[0]}, which may declare a subclass, could not be read",
            )
        if index.klass(target) is None:
            return self.fail("?", "its class could not be read from its file again")
        subclasses = self._subclasses(index, target)
        if isinstance(subclasses, SupertypeFinding):
            return subclasses
        above = index.ancestors(target, self.tops)
        related = (above if isinstance(above, frozenset) else {target}) | subclasses
        reach: set[Key] = set()
        first: tuple[str, ClassFacts] | None = None
        for sub in sorted(subclasses):
            ancestry = index.ancestors(sub, self.tops)
            if not isinstance(ancestry, frozenset):
                where, base = ancestry
                return self.fail(
                    _name(index, sub),
                    f"whose ancestry cannot be followed: class `{_name(index, where)}` "
                    f"has base `{base.clause}`, {base.why}",
                )
            declaring = sorted(
                (facts.key, facts)
                for key in ancestry - related
                for facts in [index.klass(key)]
                if facts is not None and self.bare in facts.names
            )
            if declaring:
                reach |= ancestry
                if first is None:
                    first = (_name(index, sub), declaring[0][1])
        if first is None:
            return None
        kept = [site for site in sites if self._may_reach(index, site, reach)]
        if not kept:
            return None
        subclass, other = first
        return self.fail(
            subclass,
            f"which also inherits `{other.name}.{self.bare}` ({other.rel}:"
            f"{other.line}), so a call through `{other.name}` may run this "
            "method; call(s) named like it are not bound to this declaration "
            "and may dispatch here: " + _describe(kept),
        )

    def _subclasses(
        self, index: ClassIndex, target: Key
    ) -> set[Key] | SupertypeFinding:
        """Every project subclass of ``target``, from the classes whose bases
        mention it (or a subclass, or a rename of either)."""
        found: set[Key] = set()
        members = {target}
        names: set[str] = set()
        pending = [_name(index, target)]
        checked: set[Key] = set()
        while pending:
            spelled, unparsed = index.spelled(pending)
            if unparsed is not None:
                return self.fail("?", _unparsed(unparsed))
            spelled -= names
            names |= spelled
            pending = []
            candidates: set[Key] = set()
            for rel in index.files_with(spelled):
                facts = index.file(rel)
                if facts is None:
                    return self.fail("?", _unparsed(rel))
                candidates.update(c.key for c in facts.classes if c.mentions & spelled)
            # A candidate checked earlier is checked again: a base may resolve to
            # a subclass found since.
            for key in sorted(candidates | (checked - members)):
                if key in members:
                    continue
                checked.add(key)
                verdict = self._candidate(index, key, members, names)
                if isinstance(verdict, SupertypeFinding):
                    return verdict
                if verdict:
                    members.add(key)
                    found.add(key)
                    if len(found) > _MAX_SUBCLASSES:
                        return self.fail(
                            "?",
                            "it has too many subclasses to check (more than "
                            f"{_MAX_SUBCLASSES})",
                        )
                    pending.append(_name(index, key))
        return found

    def _candidate(
        self, index: ClassIndex, key: Key, members: set[Key], names: set[str]
    ) -> bool | SupertypeFinding:
        """``key`` has a base among ``members``; a failure when it may."""
        for base in index.bases(key, self.tops):
            if isinstance(base, Unknown):
                if not base.keyword and base.mentions & names:
                    return self.fail(
                        _name(index, key),
                        f"which may be one: class `{_name(index, key)}` "
                        f"({key[0]}:{key[1]}) has base `{base.clause}`, {base.why}",
                    )
                continue
            if base in members:
                return True
        return False


def _name(index: ClassIndex, key: Key) -> str:
    facts = index.klass(key)
    return "?" if facts is None else facts.name


def _unparsed(rel: str) -> str:
    return f"{rel}, which may declare a subclass, could not be parsed"


def _first_line(node: Any) -> int:
    lines = [
        int(node.lineno),
        *(int(d.lineno) for d in getattr(node, "decorator_list", ())),
    ]
    return min(lines)


def _describe(sites: list[_Site]) -> str:
    named = [f"{site.file}:{site.line}" for site in sites[:_SITES_NAMED]]
    if len(sites) > _SITES_NAMED:
        named.append(f"and {len(sites) - _SITES_NAMED} more")
    return "; ".join(named)


__all__ = ["python_subtype_finding"]
