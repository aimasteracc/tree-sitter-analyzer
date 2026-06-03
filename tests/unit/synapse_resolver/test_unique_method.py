"""RFC-0002 Phase 1: unique-method receiver resolution.

When a method call `obj.method()` has a receiver whose type we can't infer,
but `method` is defined on exactly ONE class across the whole project, resolve
to it. If `method` is defined on multiple classes (e.g. `execute`), stay
`unknown` rather than guess.
"""

from __future__ import annotations

from tree_sitter_analyzer.synapse_resolver import resolve_callee
from tree_sitter_analyzer.synapse_resolver._context import ResolverContext


def _ctx(**kw):
    defaults = {
        "project_root": "/repo",
        "cache": None,
        "file_languages": {"caller.py": "python"},
    }
    defaults.update(kw)
    return ResolverContext(**defaults)


def test_unique_method_receiver_resolves_to_project():
    # all_edges defined on exactly one class → pg.all_edges() resolves to it
    ctx = _ctx(
        file_class_methods={"project_graph.py": {"ProjectGraph": {"all_edges": 42}}}
    )
    r = resolve_callee("pg.all_edges", "caller.py", ctx)
    assert r.resolution == "project"
    assert r.callee_symbol_id == 42
    assert r.resolved_file == "project_graph.py"


def test_ambiguous_method_stays_unknown():
    # execute on two classes → don't guess
    ctx = _ctx(
        file_class_methods={
            "a.py": {"A": {"execute": 1}},
            "b.py": {"B": {"execute": 2}},
        }
    )
    r = resolve_callee("obj.execute", "caller.py", ctx)
    assert r.resolution == "unknown"


def test_self_method_not_hijacked():
    # self.X still resolves via _try_self_method (local), not unique-method
    ctx = _ctx(file_class_methods={"caller.py": {"C": {"foo": 5}}})
    r = resolve_callee("self.foo", "caller.py", ctx)
    assert r.resolution == "local"


def test_bare_name_unaffected():
    # no receiver → unique-method rule must not fire
    ctx = _ctx(file_class_methods={"x.py": {"X": {"helper": 9}}})
    r = resolve_callee("helper", "caller.py", ctx)
    # helper is a method here, not a bare global → unique-method needs a qualifier,
    # so this stays unknown (not hijacked into project via the method table)
    assert r.resolution == "unknown"


def test_self_method_via_callee_full_resolves_local():
    """self._x() arrives as callee_name='_x' + callee_full='self._x' — the bare
    name lost the receiver, so resolution must use callee_full to reach
    _try_self_method (the #1 unknown source)."""
    ctx = _ctx(file_class_methods={"caller.py": {"Sync": {"_scan_disk_files": 77}}})
    r = resolve_callee(
        "_scan_disk_files", "caller.py", ctx, callee_full="self._scan_disk_files"
    )
    assert r.resolution == "local"
    assert r.callee_symbol_id == 77


def test_bare_name_without_self_full_unaffected():
    ctx = _ctx(file_class_methods={"caller.py": {"Sync": {"_scan_disk_files": 77}}})
    # no callee_full → bare name, stays unknown (not a self call we can see)
    r = resolve_callee("_scan_disk_files", "caller.py", ctx)
    assert r.resolution == "unknown"


# -- Codex P2 regressions (PR #274) -------------------------------------------
def test_unique_method_via_production_callee_full():
    """P2#1: production rows are callee_name='all_edges' + callee_full='pg.all_edges'.
    Must split callee_full to recover the `pg` receiver so unique-method fires."""
    ctx = _ctx(
        file_class_methods={"project_graph.py": {"ProjectGraph": {"all_edges": 42}}}
    )
    r = resolve_callee("all_edges", "caller.py", ctx, callee_full="pg.all_edges")
    assert r.resolution == "project"
    assert r.callee_symbol_id == 42


def test_self_method_no_cross_class_match():
    """P2#2: A.f calls self.helper(); only B defines helper → must NOT resolve to B."""
    ctx = _ctx(file_class_methods={"caller.py": {"A": {"f": 1}, "B": {"helper": 2}}})
    r = resolve_callee(
        "helper", "caller.py", ctx, callee_full="self.helper", caller_name="f"
    )
    assert r.resolution == "unknown"


def test_self_method_resolves_within_enclosing_class():
    """P2#2: A.f calls self.g(); A defines g → resolve to A.g (not B's anything)."""
    ctx = _ctx(
        file_class_methods={"caller.py": {"A": {"f": 1, "g": 3}, "B": {"helper": 2}}}
    )
    r = resolve_callee("g", "caller.py", ctx, callee_full="self.g", caller_name="f")
    assert r.resolution == "local"
    assert r.callee_symbol_id == 3


# -- RFC-0002: receiver-type-aware (class.method) resolution ------------------
def test_class_method_disambiguates_non_unique():
    """execute defined on A and B; ClassName.execute (receiver type inferred)
    resolves to the right one — what unique-method can't do (it stays unknown)."""
    ctx = _ctx(
        file_class_methods={
            "a.py": {"A": {"execute": 10}},
            "b.py": {"B": {"execute": 20}},
        }
    )
    # extractor inferred receiver type → callee_full='A.execute'
    r = resolve_callee("execute", "caller.py", ctx, callee_full="A.execute")
    assert r.resolution == "project"
    assert r.callee_symbol_id == 10
    assert r.resolved_file == "a.py"
    # the other class
    r2 = resolve_callee("execute", "caller.py", ctx, callee_full="B.execute")
    assert r2.callee_symbol_id == 20


def test_class_method_unknown_class_with_ambiguous_method():
    # NotAClass not known + execute ambiguous (A and B) → neither class-method
    # nor unique-method resolves → unknown (don't guess)
    ctx = _ctx(
        file_class_methods={
            "a.py": {"A": {"execute": 10}},
            "b.py": {"B": {"execute": 20}},
        }
    )
    r = resolve_callee("execute", "caller.py", ctx, callee_full="NotAClass.execute")
    assert r.resolution == "unknown"


def test_class_method_duplicate_class_stays_unknown():
    """P2 (Codex): Client defined in two modules → ambiguous, don't guess a file."""
    ctx = _ctx(
        file_class_methods={
            "a.py": {"Client": {"send": 1}},
            "b.py": {"Client": {"send": 2}},
        }
    )
    r = resolve_callee("send", "caller.py", ctx, callee_full="Client.send")
    assert r.resolution == "unknown"
