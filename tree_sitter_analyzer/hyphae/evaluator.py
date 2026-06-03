"""Hyphae evaluator — turns a parsed selector into symbol-graph queries.

Mirrors mycelium-hyphae/src/evaluator.rs semantics over a TSA ``ASTCache``:

- ``#name``  → exact symbol lookup (search_symbols_cascade)
- ``.kind``  → all functions/methods of that kind (get_functions)
- ``*``      → all functions/methods
- ``:calls(#X)``   → candidates that call X  (reverse-driven via query_callers)
- ``:callees(#X)`` → candidates that X calls (reverse-driven via query_callees)
- ``:not(sel)``    → candidates minus eval(sel)
- ``:in(path)``    → candidates whose file is under path
- ``[file=p]`` / ``[language=l]`` / ``[class=C]`` → attribute filters
- ``A > B`` / ``A B`` (descendant) → B whose containing class is A (via ``class`` field)

The ``:calls`` filter is reverse-driven (one ``query_callers`` per target rather
than one ``query_callees`` per candidate) so ``.method:calls(#Hub)`` stays a
couple of queries even on a 16k-symbol index.
"""

from __future__ import annotations

from typing import Any

from .ast import Combined, PseudoClass, SelectorList, SimpleSelector

# .kind alias → TSA function/method discrimination. TSA stores Java methods as
# functions with a populated ``class`` field, so we discriminate on that.
_FUNCTIONISH = frozenset({"function", "method", "func", "fn"})


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
            return self._all_functions()
        if kind == "name":
            hits = self._cache.search_symbols_cascade(val, limit=self._max) or []
            return [h for h in hits if h.get("name") == val]
        if kind == "kind":
            funcs = self._all_functions()
            if val in _FUNCTIONISH:
                if val == "method":
                    return [f for f in funcs if f.get("class")]
                if val == "function":
                    return funcs
            # Fall back to matching the symbol's own kind field when present.
            return [f for f in funcs if (f.get("kind") or "function") == val]
        return []

    def _all_functions(self) -> list[dict[str, Any]]:
        return list(self._cache.get_functions() or [])

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
        if name == "calls":
            return self._filter_calls(cands, pc.arg, direction="calls")
        if name in ("callees", "called-by"):
            return self._filter_calls(cands, pc.arg, direction="callees")
        if name == "not":
            if isinstance(pc.arg, SelectorList):
                excluded = {_key(s) for s in self.eval(pc.arg)}
                return [c for c in cands if _key(c) not in excluded]
            return cands
        if name == "in":
            path = pc.arg if isinstance(pc.arg, str) else ""
            return [c for c in cands if (c.get("file") or "").startswith(path)]
        # Unknown pseudo-class: be conservative and keep candidates.
        return cands

    def _filter_calls(
        self, cands: list[dict[str, Any]], arg: Any, direction: str
    ) -> list[dict[str, Any]]:
        """Keep candidates that call (or are called by) the target selector.

        ``direction='calls'``  → candidate calls target  (target's callers)
        ``direction='callees'``→ target calls candidate  (target's callees)

        Target names are taken directly from ``#name`` bases so the target need
        not itself be an indexed symbol (e.g. an external class), matching the
        edge-name semantics of the underlying call graph.
        """
        if not isinstance(arg, SelectorList):
            return []
        names = self._target_names(arg)
        related_names: set[Any] = set()
        for tname in names:
            if direction == "calls":
                rows = self._cache.query_callers(tname, None) or []
                related_names.update(
                    r.get("caller_name") for r in rows if r.get("caller_name")
                )
            else:
                rows = self._cache.query_callees(tname, None) or []
                related_names.update(
                    r.get("callee_name") for r in rows if r.get("callee_name")
                )
        return [c for c in cands if c.get("name") in related_names]

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
