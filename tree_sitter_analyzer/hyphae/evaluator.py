"""Hyphae evaluator — turns a parsed selector into symbol-graph queries.

Mirrors mycelium-hyphae/src/evaluator.rs semantics over a TSA ``ASTCache``:

Base selectors:
- ``#name``  → exact symbol lookup (search_symbols_cascade)
- ``.function`` / ``.method`` → functions (method = function with a class)
- ``.class`` / ``.struct`` / ``.interface`` → class symbols (get_symbols_by_kind)
- ``*``      → all functions + classes

Edge pseudo-classes (reverse-driven via the unified ``edges`` table):
- ``:calls(#X)``      → candidates that call X
- ``:callees(#X)``    → candidates that X calls
- ``:extends(#X)`` / ``:implements(#X)`` → candidates that extend/implement X
- ``:subclasses(#X)`` → candidates that X is a base of
- ``:imports(mod)``   → candidates whose file imports module ``mod``

Structural pseudo-classes:
- ``:has(#X)``        → containers of a member X (via the ``contains`` edge)
- ``:not(sel)``       → candidates minus eval(sel)
- ``:in(path)``       → candidates whose file is under path
- ``:first-child`` / ``:only-child`` / ``:nth-child(n)`` → position within the
  containing class (ordered by line)

Attributes & combinators:
- ``[file=p]`` / ``[language=l]`` / ``[class=C]`` / ``[kind=k]``
- ``A > B`` / ``A B`` (descendant) / ``A ~ B`` (sibling) via the ``class`` field

Edge filters are reverse-driven (one ``query_edges`` per target rather than one
per candidate) so ``.method:calls(#Hub)`` stays a couple of queries even on a
16k-symbol index. An unknown pseudo-class raises ``HyphaeSyntaxError`` rather
than silently passing candidates through.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .ast import Combined, PseudoClass, SelectorList, SimpleSelector
from .parser import HyphaeSyntaxError

# .kind alias → TSA symbol kind. TSA stores Java methods as functions with a
# populated ``class`` field, so we discriminate methods on that.
_FUNCTIONISH = frozenset({"function", "method", "func", "fn"})
_CLASSISH = frozenset({"class", "struct", "interface", "trait", "enum"})

# Edge pseudo-classes → (edge_kinds, target_match_column, returned_column).
# Reverse-driven: match the target name on one endpoint, keep candidates whose
# name appears on the other endpoint. Inheritance pseudo-classes span BOTH the
# ``extends`` and ``implements`` edge kinds, because some indexers store class
# inheritance and interface implementation separately while others (e.g. Java)
# fold both into ``extends`` (per edge_store's inheritance-tree readers).
_INHERIT_KINDS = ("extends", "implements")
_EDGE_PSEUDOS: dict[str, tuple[tuple[str, ...], str, str]] = {
    "calls": (("calls",), "callee_name", "caller_name"),
    "callees": (("calls",), "caller_name", "callee_name"),
    "called-by": (("calls",), "caller_name", "callee_name"),
    # candidate extends/implements the target → candidate is the caller (child),
    # target is the callee (parent/interface).
    "extends": (_INHERIT_KINDS, "callee_name", "caller_name"),
    "implements": (_INHERIT_KINDS, "callee_name", "caller_name"),
    # target's subclasses → also children of the target, same direction.
    "subclasses": (_INHERIT_KINDS, "callee_name", "caller_name"),
}
_POSITION_PSEUDOS = frozenset({"nth-child", "first-child", "only-child"})


def _key(sym: dict[str, Any]) -> tuple[Any, Any, Any]:
    return (sym.get("name"), sym.get("file"), sym.get("line"))


class Evaluator:
    """Evaluate a parsed Hyphae selector against an ``ASTCache``."""

    def __init__(self, cache: Any, max_results: int = 500) -> None:
        self._cache = cache
        self._max = max_results

    # -- public --------------------------------------------------------------
    def eval(self, selector_list: SelectorList) -> list[dict[str, Any]]:
        seen: set[tuple[Any, Any, Any]] = set()
        out: list[dict[str, Any]] = []
        for sel in selector_list.selectors:
            for sym in self._eval_selector(sel):
                k = _key(sym)
                if k in seen:
                    continue
                seen.add(k)
                out.append(sym)
                if len(out) >= self._max:
                    return out
        return out

    # -- dispatch ------------------------------------------------------------
    def _eval_selector(self, sel: Any) -> list[dict[str, Any]]:
        if isinstance(sel, Combined):
            return self._eval_combined(sel)
        return self._eval_simple(sel)

    def _eval_simple(self, simple: SimpleSelector) -> list[dict[str, Any]]:
        cands = self._eval_base(simple.base)
        for attr in simple.attributes:
            cands = self._apply_attribute(cands, attr.name, attr.value)
        for pc in simple.pseudo_classes:
            cands = self._apply_pseudo(cands, pc)
        return cands

    # -- base ----------------------------------------------------------------
    def _eval_base(self, base: tuple[str, str]) -> list[dict[str, Any]]:
        kind, val = base
        if kind == "universal":
            return self._all_functions() + self._symbols_of_kind("class")
        if kind == "name":
            hits = self._cache.search_symbols_cascade(val, limit=self._max) or []
            return [h for h in hits if h.get("name") == val]
        if kind == "kind":
            if val in _FUNCTIONISH:
                funcs = self._all_functions()
                if val == "method":
                    return [f for f in funcs if f.get("class")]
                return funcs
            if val in _CLASSISH:
                return self._symbols_of_kind("class")
            # variable / field / other → flat symbol-rows lookup.
            return self._symbols_of_kind(val)
        return []

    def _all_functions(self) -> list[dict[str, Any]]:
        return list(self._cache.get_functions() or [])

    def _symbols_of_kind(self, kind: str) -> list[dict[str, Any]]:
        getter = getattr(self._cache, "get_symbols_by_kind", None)
        if not callable(getter):
            return []
        return list(getter(kind) or [])

    # -- attribute filters ---------------------------------------------------
    def _apply_attribute(
        self, cands: list[dict[str, Any]], name: str, value: str
    ) -> list[dict[str, Any]]:
        if name == "file":
            return [c for c in cands if value in (c.get("file") or "")]
        if name == "language":
            return [c for c in cands if (c.get("language") or "") == value]
        if name == "class":
            return [c for c in cands if (c.get("class") or "") == value]
        if name == "kind":
            return [c for c in cands if (c.get("kind") or "function") == value]
        return []

    # -- pseudo-classes ------------------------------------------------------
    def _apply_pseudo(
        self, cands: list[dict[str, Any]], pc: PseudoClass
    ) -> list[dict[str, Any]]:
        name = pc.name
        if name in _EDGE_PSEUDOS:
            return self._filter_edge(cands, pc.arg, *_EDGE_PSEUDOS[name])
        if name == "imports":
            return self._filter_imports(cands, pc.arg)
        if name == "has":
            return self._filter_has(cands, pc.arg)
        if name == "not":
            if not isinstance(pc.arg, SelectorList):
                raise HyphaeSyntaxError(":not requires a selector argument")
            excluded = {_key(s) for s in self.eval(pc.arg)}
            return [c for c in cands if _key(c) not in excluded]
        if name == "in":
            if not isinstance(pc.arg, str):
                raise HyphaeSyntaxError(":in requires a path argument")
            return [c for c in cands if (c.get("file") or "").startswith(pc.arg)]
        if name in _POSITION_PSEUDOS:
            return self._filter_position(cands, name, pc.arg)
        raise HyphaeSyntaxError(f"unknown pseudo-class ':{name}'")

    def _filter_edge(
        self,
        cands: list[dict[str, Any]],
        arg: Any,
        edge_kinds: tuple[str, ...],
        target_col: str,
        return_col: str,
    ) -> list[dict[str, Any]]:
        """Keep candidates joined to the target selector by any ``edge_kinds`` edge.

        Reverse-driven: match each target name on ``target_col`` and collect the
        ``return_col`` endpoint with its file, so candidates are matched on
        (name, file) — not name alone. This avoids false positives when two
        symbols share a name across different files (overloads / duplicate
        names). When the edge row lacks a resolved file, the endpoint falls back
        to name-only matching so recall is preserved.
        """
        if not isinstance(arg, SelectorList):
            raise HyphaeSyntaxError("edge pseudo-class requires a selector argument")
        # The returned endpoint's file lives in a different column depending on
        # whether we return the caller (source = file_path) or the callee
        # (target = callee_resolved_file).
        file_col = (
            "file_path" if return_col == "caller_name" else "callee_resolved_file"
        )
        names = self._target_names(arg)
        related_nf: set[tuple[Any, Any]] = set()
        related_name_only: set[Any] = set()
        for tname in names:
            for kind in edge_kinds:
                rows = self._cache.query_edges(kind, **{target_col: tname}) or []
                for r in rows:
                    nm = r.get(return_col)
                    if not nm:
                        continue
                    f = r.get(file_col)
                    if f:
                        related_nf.add((nm, f))
                    else:
                        related_name_only.add(nm)
        return [
            c
            for c in cands
            if (c.get("name"), c.get("file")) in related_nf
            or c.get("name") in related_name_only
        ]

    def _filter_imports(
        self, cands: list[dict[str, Any]], arg: Any
    ) -> list[dict[str, Any]]:
        """Keep candidates whose file imports a module matching the target.

        Imports are file-level (the ``imports`` edge has an empty caller), so a
        candidate matches when its file carries an import whose module path
        contains one of the target names.
        """
        if isinstance(arg, str):
            names: set[Any] = {arg}
        elif isinstance(arg, SelectorList):
            names = self._target_names(arg)
        else:
            raise HyphaeSyntaxError(":imports requires a module path or selector")
        rows = self._cache.query_edges("imports") or []
        files = {
            r.get("file_path")
            for r in rows
            if any(n in (r.get("callee_name") or "") for n in names)
        }
        return [c for c in cands if c.get("file") in files]

    def _filter_has(
        self, cands: list[dict[str, Any]], arg: Any
    ) -> list[dict[str, Any]]:
        """Keep candidates that contain a member matching the target selector.

        Uses the ``contains`` edge (caller=container, callee=member): a candidate
        survives when it is the container of a member named by the target.
        """
        if not isinstance(arg, SelectorList):
            raise HyphaeSyntaxError(":has requires a selector argument")
        names = self._target_names(arg)
        containers: set[Any] = set()
        for mname in names:
            rows = self._cache.query_edges("contains", callee_name=mname) or []
            containers.update(
                r.get("caller_name") for r in rows if r.get("caller_name")
            )
        return [c for c in cands if c.get("name") in containers]

    def _filter_position(
        self, cands: list[dict[str, Any]], name: str, arg: Any
    ) -> list[dict[str, Any]]:
        """Position filters within each containing class (ordered by line).

        Candidates are grouped by their ``class`` field and ordered by line;
        ``:first-child`` keeps the first of each group, ``:only-child`` keeps
        sole members, ``:nth-child(n)`` keeps the 1-based n-th.
        """
        groups: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        for c in cands:
            groups[c.get("class")].append(c)
        out: list[dict[str, Any]] = []
        nth_index: int | None = None
        if name == "nth-child":
            if not isinstance(arg, int):
                raise HyphaeSyntaxError(":nth-child requires a number argument")
            nth_index = arg - 1
        for members in groups.values():
            ordered = sorted(members, key=lambda c: c.get("line") or 0)
            if name == "first-child":
                out.append(ordered[0])
            elif name == "only-child":
                if len(ordered) == 1:
                    out.append(ordered[0])
            elif name == "nth-child" and nth_index is not None:
                if 0 <= nth_index < len(ordered):
                    out.append(ordered[nth_index])
        return out

    def _target_names(self, arg: SelectorList) -> set[Any]:
        """Extract target symbol names from a pseudo-class argument selector.

        ``#name`` bases contribute their literal name directly; richer selectors
        are evaluated and contribute the names of their matches.
        """
        names: set[Any] = set()
        for sel in arg.selectors:
            if isinstance(sel, SimpleSelector) and sel.base[0] == "name":
                names.add(sel.base[1])
            else:
                names.update(s.get("name") for s in self._eval_selector(sel))
        return {n for n in names if n}

    # -- combinators ---------------------------------------------------------
    def _eval_combined(self, combined: Combined) -> list[dict[str, Any]]:
        left = self._eval_selector(combined.left)
        right = self._eval_selector(combined.right)
        left_names = {sym.get("name") for sym in left}
        # Child / descendant: keep right symbols whose containing class is a
        # left symbol. TSA exposes containment via the ``class`` field.
        if combined.combinator in (">", " "):
            return [r for r in right if (r.get("class") or None) in left_names]
        # Sibling (~): same containing class as a left symbol.
        if combined.combinator == "~":
            left_classes = {sym.get("class") for sym in left if sym.get("class")}
            return [r for r in right if (r.get("class") or None) in left_classes]
        return right
