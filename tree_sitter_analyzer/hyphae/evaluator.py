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

import time
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
        self._was_truncated = False
        self._total_count = 0

    # -- public --------------------------------------------------------------
    def eval(self, selector_list: SelectorList) -> list[dict[str, Any]]:
        """Evaluate the selector and return capped results.

        Returns the list of matching symbols (capped at self._max).
        Call total_matches() and was_truncated() after eval() to get metadata.
        """
        # ALL counting is kept in locals and written to the instance only at
        # the very end: ``:not(...)`` re-enters eval() (line ~213), and any
        # mid-loop instance mutation would be clobbered by the nested call
        # (Codex P2 on #489 — reentrancy). The outer frame's final assignment
        # always wins because it happens after every nested eval returns.
        seen: set[tuple[Any, Any, Any]] = set()
        out: list[dict[str, Any]] = []
        total_count = 0
        hit_cap = False
        sel_with_cap = None

        for sel in selector_list.selectors:
            for sym in self._eval_selector(sel):
                k = _key(sym)
                if k in seen:
                    continue
                seen.add(k)
                out.append(sym)
                total_count += 1
                if len(out) >= self._max:
                    hit_cap = True
                    sel_with_cap = sel
                    break
            if hit_cap:
                break

        # If we hit the cap, count the rest to get the true total.
        if hit_cap and sel_with_cap is not None:
            # Count remaining from current selector
            for sym in self._eval_selector(sel_with_cap):
                k = _key(sym)
                if k not in seen:
                    seen.add(k)
                    total_count += 1
            # Count remaining selectors
            sel_idx = selector_list.selectors.index(sel_with_cap)
            for rem_sel in selector_list.selectors[sel_idx + 1 :]:
                for sym in self._eval_selector(rem_sel):
                    k = _key(sym)
                    if k not in seen:
                        seen.add(k)
                        total_count += 1

        self._total_count = total_count
        # Truncated only if matches were actually LOST: exactly max_results
        # unique matches is a complete result, not a capped one (Codex P2).
        self._was_truncated = total_count > len(out)
        return out

    def total_matches(self) -> int:
        """Return the total number of matches (before cap, if truncated)."""
        return self._total_count

    def was_truncated(self) -> bool:
        """Return whether the results were capped at max_results."""
        return self._was_truncated

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

    # -- depth BFS (recursive CTE) ------------------------------------------

    def _eval_depth_bfs(
        self,
        seed_ids: list[int],
        direction: str,
        depth_min: int,
        depth_max: int,
    ) -> set[int]:
        """Return symbol IDs reachable from ``seed_ids`` within depth range.

        ``direction`` is ``"callee"`` (forward) or ``"caller"`` (reverse).
        Edges where callee_symbol_id IS NULL are skipped by the CTE condition.
        """
        conn = getattr(self._cache, "get_conn", None)
        if conn is None:
            return set()
        try:
            db = conn()
        except Exception:
            return set()

        if direction == "callee":
            source_col = "caller_name"
            target_col = "callee_symbol_id"
        else:
            source_col = "callee_symbol_id"
            target_col = "source_node_id"

        if not seed_ids:
            return set()

        placeholders = ",".join("?" * len(seed_ids))

        if direction == "callee":
            # Forward BFS: follow edges from seed symbols to their callees (INTEGER IDs).
            # Recursive step joins ast_symbol_rows to convert callee_symbol_id back to
            # caller_name for the next hop, staying entirely in the integer domain.
            sql = f"""
WITH RECURSIVE reachable(id, hop) AS (
    SELECT e.callee_symbol_id, 1
    FROM   edges e
    JOIN   ast_symbol_rows sr ON sr.id IN ({placeholders})
                              AND sr.name = e.caller_name
    WHERE  e.kind = 'calls'
    AND    e.callee_symbol_id IS NOT NULL
    UNION ALL
    SELECT e.callee_symbol_id, r.hop + 1
    FROM   edges e
    JOIN   ast_symbol_rows sr2 ON sr2.id = r.id AND sr2.name = e.caller_name
    WHERE  r.hop < ?
    AND    e.kind = 'calls'
    AND    e.callee_symbol_id IS NOT NULL
)
SELECT DISTINCT id FROM reachable
WHERE hop >= ? AND hop <= ?
"""
        else:
            # Reverse BFS: find callers of seeds (and their callers, etc.)
            # edges.caller_name is TEXT; convert to integer via ast_symbol_rows at each hop.
            sql = f"""
WITH RECURSIVE reachable(id, hop) AS (
    SELECT sr2.id, 1
    FROM   edges e
    JOIN   ast_symbol_rows sr  ON sr.id IN ({placeholders})
                              AND e.callee_symbol_id = sr.id
    JOIN   ast_symbol_rows sr2 ON sr2.name = e.caller_name
    WHERE  e.kind = 'calls'
    UNION ALL
    SELECT sr2.id, r.hop + 1
    FROM   edges e
    JOIN   reachable r          ON e.callee_symbol_id = r.id
    JOIN   ast_symbol_rows sr2  ON sr2.name = e.caller_name
    WHERE  r.hop < ?
    AND    e.kind = 'calls'
)
SELECT DISTINCT id FROM reachable
WHERE hop >= ? AND hop <= ?
"""

        try:
            params = list(seed_ids) + [depth_max, depth_min, depth_max]
            rows = db.execute(sql, params).fetchall()
            return {int(r[0]) for r in rows}
        except Exception:
            return set()

    # -- temporal pseudo-classes --------------------------------------------

    def _filter_temporal(
        self, cands: list[dict[str, Any]], name: str, arg: Any
    ) -> list[dict[str, Any]]:
        """Apply :hot/:hot(N)/:recently_modified/:stale/:hotspot filters."""
        conn_fn = getattr(self._cache, "get_conn", None)
        if conn_fn is None:
            return cands
        try:
            db = conn_fn()
        except Exception:
            return cands

        if name == "hot":
            threshold = int(arg) if isinstance(arg, int) else 5
            try:
                hot_ids = {
                    r[0] for r in db.execute(
                        "SELECT symbol_id FROM ast_symbol_activation "
                        "WHERE mod_count_30d > ?",
                        (threshold,),
                    )
                }
                return [c for c in cands if c.get("id") in hot_ids]
            except Exception:
                return cands

        if name == "recently_modified":
            cutoff = int(time.time()) - 30 * 86400
            try:
                recent_ids = {
                    r[0] for r in db.execute(
                        "SELECT symbol_id FROM ast_symbol_activation "
                        "WHERE last_modified_at > ?",
                        (cutoff,),
                    )
                }
                return [c for c in cands if c.get("id") in recent_ids]
            except Exception:
                return cands

        if name == "stale":
            cutoff = int(time.time()) - 180 * 86400
            try:
                stale_ids = {
                    r[0] for r in db.execute(
                        "SELECT symbol_id FROM ast_symbol_activation "
                        "WHERE last_modified_at < ? AND mod_count_30d = 0",
                        (cutoff,),
                    )
                }
                return [c for c in cands if c.get("id") in stale_ids]
            except Exception:
                return cands

        if name == "hotspot":
            # Python-side top-10% per file rank (SQLite version-independent).
            from collections import defaultdict as _dd
            try:
                act_rows = db.execute(
                    "SELECT symbol_id, file_path, mod_count_30d "
                    "FROM ast_symbol_activation"
                ).fetchall()
            except Exception:
                return cands

            by_file: dict[str, list[tuple[int, int]]] = _dd(list)
            for r in act_rows:
                by_file[r[1]].append((r[0], r[2] or 0))

            hotspot_ids: set[int] = set()
            for file_syms in by_file.values():
                sorted_syms = sorted(file_syms, key=lambda x: x[1], reverse=True)
                cutoff_n = max(1, len(sorted_syms) // 10)
                hotspot_ids.update(sym_id for sym_id, _ in sorted_syms[:cutoff_n])

            return [c for c in cands if c.get("id") in hotspot_ids]

        return cands

    # -- pseudo-classes ------------------------------------------------------
    def _apply_pseudo(
        self, cands: list[dict[str, Any]], pc: PseudoClass
    ) -> list[dict[str, Any]]:
        name = pc.name
        if name in _EDGE_PSEUDOS:
            # Check for DepthQuantifier — use BFS CTE when depth_min is set.
            if pc.depth_min is not None:
                return self._filter_edge_depth(cands, pc)
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
        # Temporal pseudo-classes (H-5).
        if name in ("hot", "recently_modified", "stale", "hotspot"):
            return self._filter_temporal(cands, name, pc.arg)
        # :violates(rule_id) (H-6).
        if name == "violates":
            return self._filter_violates(cands, pc.arg)
        # :reaches(#target){n,m} (H-7).
        if name == "reaches":
            return self._filter_reaches(cands, pc)
        # :branch(kind) (H-8).
        if name == "branch":
            return self._filter_branch(cands, pc.arg)
        raise HyphaeSyntaxError(f"unknown pseudo-class ':{name}'")

    def _filter_edge_depth(
        self,
        cands: list[dict[str, Any]],
        pc: PseudoClass,
    ) -> list[dict[str, Any]]:
        """Apply depth-bounded BFS for :calls{n,m} and :called-by{n,m}."""
        depth_min = pc.depth_min or 1
        depth_max = pc.depth_max if pc.depth_max is not None else depth_min

        # Resolve seed symbol IDs from the argument selector.
        if not isinstance(pc.arg, SelectorList):
            raise HyphaeSyntaxError("depth pseudo-class requires a selector argument")
        names = self._target_names(pc.arg)

        conn_fn = getattr(self._cache, "get_conn", None)
        if conn_fn is None:
            return cands
        try:
            db = conn_fn()
        except Exception:
            return cands

        try:
            seed_rows = db.execute(
                "SELECT id FROM ast_symbol_rows WHERE name IN ({})".format(
                    ",".join("?" * len(names))
                ),
                list(names),
            ).fetchall()
        except Exception:
            return cands

        seed_ids = [int(r[0]) for r in seed_rows]

        # Direction: "calls(#X){n,m}" = find who calls X (reverse BFS from X).
        # "callees"/"called-by" = find what X calls (forward BFS from X).
        direction = "callee" if pc.name in ("called-by", "callees") else "caller"
        reachable_ids = self._eval_depth_bfs(seed_ids, direction, depth_min, depth_max)

        try:
            id_rows = db.execute(
                "SELECT id, name, file_path FROM ast_symbol_rows "
                "WHERE id IN ({})".format(",".join("?" * len(reachable_ids))),
                list(reachable_ids),
            ).fetchall() if reachable_ids else []
        except Exception:
            return cands

        reachable_nf: set[tuple[Any, Any]] = {(r[1], r[2]) for r in id_rows}
        return [
            c for c in cands
            if (c.get("name"), c.get("file")) in reachable_nf
        ]

    def _filter_violates(
        self,
        cands: list[dict[str, Any]],
        arg: Any,
    ) -> list[dict[str, Any]]:
        """Keep candidates that have a violation registered for ``rule_id``."""
        rule_id = str(arg) if arg is not None else ""
        conn_fn = getattr(self._cache, "get_conn", None)
        if conn_fn is None:
            return cands
        try:
            db = conn_fn()
            violated = {
                (r[0], r[1]) for r in db.execute(
                    "SELECT caller_file, caller_name FROM ast_constraint_violations "
                    "WHERE rule_id = ?",
                    (rule_id,),
                )
            }
            return [
                c for c in cands
                if (c.get("file"), c.get("name")) in violated
            ]
        except Exception:
            return cands

    def _filter_reaches(
        self,
        cands: list[dict[str, Any]],
        pc: PseudoClass,
    ) -> list[dict[str, Any]]:
        """:reaches(#target){n,m} — candidates that can reach ``target`` in n-m hops."""
        depth_min = pc.depth_min or 1
        depth_max = pc.depth_max if pc.depth_max is not None else depth_min

        if not isinstance(pc.arg, SelectorList):
            raise HyphaeSyntaxError(":reaches requires a selector argument")
        target_names = self._target_names(pc.arg)

        conn_fn = getattr(self._cache, "get_conn", None)
        if conn_fn is None:
            return cands
        try:
            db = conn_fn()
        except Exception:
            return cands

        try:
            target_rows = db.execute(
                "SELECT id FROM ast_symbol_rows WHERE name IN ({})".format(
                    ",".join("?" * len(target_names))
                ),
                list(target_names),
            ).fetchall() if target_names else []
        except Exception:
            return cands

        target_ids = [int(r[0]) for r in target_rows]
        # BFS in caller direction from target to find who can reach target.
        reachable_ids = self._eval_depth_bfs(target_ids, "caller", depth_min, depth_max)

        try:
            id_rows = db.execute(
                "SELECT id, name, file_path FROM ast_symbol_rows "
                "WHERE id IN ({})".format(",".join("?" * len(reachable_ids))),
                list(reachable_ids),
            ).fetchall() if reachable_ids else []
        except Exception:
            return cands

        reachable_nf: set[tuple[Any, Any]] = {(r[1], r[2]) for r in id_rows}
        return [
            c for c in cands
            if (c.get("name"), c.get("file")) in reachable_nf
        ]

    def _filter_branch(
        self,
        cands: list[dict[str, Any]],
        arg: Any,
    ) -> list[dict[str, Any]]:
        """:branch(kind) — keep candidates called inside the given branch kind."""
        branch_kind = str(arg) if arg is not None else ""
        conn_fn = getattr(self._cache, "get_conn", None)
        if conn_fn is None:
            return cands
        try:
            db = conn_fn()
            matched = {
                r[0] for r in db.execute(
                    "SELECT callee_name FROM edges "
                    "WHERE kind = 'calls' "
                    "AND json_extract(metadata, '$.branch.kind') = ?",
                    (branch_kind,),
                )
            }
            return [c for c in cands if c.get("name") in matched]
        except Exception:
            return cands

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
