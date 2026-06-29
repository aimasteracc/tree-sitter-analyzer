"""RFC-0010 second wave: Ruby per-language callee resolver.

Unit-level tests that drive ``resolve_ruby_callee`` against a hand-built context
(no full index needed). They assert the four guarantees of a SAFE,
self-contained resolver:

* same-file ``local`` resolution from ``file_symbols`` / ``file_class_methods``
  (Ruby ``self`` IS the current object, so ``self.foo`` binds via the
  single-class gate; bare ``foo`` binds via the flat top-level scan),
* CONSERVATIVE ``builtin`` classification on the FULL dotted call name only,
* ``project`` resolution gated to Ruby, and
* the MOAT: a callee whose name also exists in another language's file must
  NEVER bind to that file — it stays ``unknown`` (or the Ruby same-file def).
"""

from __future__ import annotations

from tree_sitter_analyzer.synapse_resolver._registry import (
    get_language_resolver,
    registered_languages,
)
from tree_sitter_analyzer.synapse_resolver.languages.ruby import (
    build_ruby_context,
    resolve_ruby_callee,
)


def _ctx(
    *,
    file_symbols=None,
    file_class_methods=None,
    global_name_table=None,
    file_languages=None,
):
    """Build a Ruby resolver context from explicit maps (thunk-style fcm)."""
    return build_ruby_context(
        imports_by_file={},
        file_languages=file_languages or {},
        file_symbols=file_symbols or {},
        global_name_table=global_name_table or {},
        file_class_methods=lambda: file_class_methods or {},
    )


# ---------------------------------------------------------------------------
# registration / discovery
# ---------------------------------------------------------------------------
def test_ruby_is_registered() -> None:
    assert "ruby" in registered_languages()
    assert get_language_resolver("ruby") is not None


# ---------------------------------------------------------------------------
# gating — zero cost for non-Ruby projects
# ---------------------------------------------------------------------------
def test_build_returns_none_when_no_ruby_file_indexed() -> None:
    ctx = build_ruby_context(
        imports_by_file={},
        file_languages={"a.py": "python", "B.java": "java"},
        file_symbols={},
        global_name_table={},
        file_class_methods=lambda: (_ for _ in ()).throw(
            AssertionError("thunk must NOT be forced for a non-Ruby index")
        ),
    )
    assert ctx is None


# ---------------------------------------------------------------------------
# local — same-file resolution
# ---------------------------------------------------------------------------
def test_bare_call_to_same_file_function_is_local() -> None:
    ctx = _ctx(
        file_languages={"app.rb": "ruby"},
        file_symbols={"app.rb": [("helper", "function", 7)]},
    )
    assert resolve_ruby_callee("helper", "helper", "app.rb", ctx) == (
        7,
        "local",
        "app.rb",
    )


def test_bare_call_does_not_bind_to_same_file_method() -> None:
    """A bare ``render`` (no receiver) in a file whose only same-name symbol is a
    class METHOD must NOT bind: a method needs an owning receiver, and in a
    multi-class file the flat ``file_symbols`` scan cannot prove the method
    belongs to the caller's class. A bare same-file call binds only a top-level
    ``function``."""
    ctx = _ctx(
        file_languages={"app.rb": "ruby"},
        file_symbols={
            "app.rb": [("run", "method", 1), ("render", "method", 2)],
        },
        file_class_methods={"app.rb": {"A": {"run": 1}, "B": {"render": 2}}},
    )
    assert resolve_ruby_callee("render", "render", "app.rb", ctx) == (
        None,
        "unknown",
        "",
    )


def test_unknown_bare_name_stays_unknown() -> None:
    """A bare call with no same-file def and no project owner stays ``unknown``
    (conservative) — never leaks into the Python cascade as a builtin."""
    ctx = _ctx(file_languages={"app.rb": "ruby"})
    assert resolve_ruby_callee("puts", "puts", "app.rb", ctx) == (
        None,
        "unknown",
        "",
    )


# ---------------------------------------------------------------------------
# local — self.<method> (Ruby self IS the current object)
# ---------------------------------------------------------------------------
def test_self_method_call_is_local_via_class_methods() -> None:
    """In Ruby ``self`` is the current object, so ``self.render`` in a single-class
    file resolves ``local`` (unlike JS, where ``self`` is the global scope)."""
    ctx = _ctx(
        file_languages={"app.rb": "ruby"},
        file_class_methods={"app.rb": {"Widget": {"render": 11}}},
    )
    assert resolve_ruby_callee("render", "self.render", "app.rb", ctx) == (
        11,
        "local",
        "app.rb",
    )


def test_self_method_does_not_bind_across_sibling_classes() -> None:
    """``class A; def run; self.render; end; end; class B; def render; end; end``.
    The caller ``A#run`` does NOT define ``render``; only the SIBLING class ``B``
    does. Without the caller's enclosing class we cannot prove ``self.render`` is
    a call on ``A``, so binding it to ``B#render`` is a concrete wrong edge. With
    two+ classes in the file, ``self.<method>`` must stay ``unknown``."""
    ctx = _ctx(
        file_languages={"app.rb": "ruby"},
        file_class_methods={
            "app.rb": {"A": {"run": 1}, "B": {"render": 2}},
        },
    )
    assert resolve_ruby_callee("render", "self.render", "app.rb", ctx) == (
        None,
        "unknown",
        "",
    )


def test_self_method_does_not_bind_sibling_via_file_symbols() -> None:
    """Real resolver contexts populate ``file_symbols`` with EVERY method in the
    file, including sibling-class methods. A ``self.``-qualified call is a METHOD
    call; it must NOT short-circuit through the flat same-file symbol lookup.
    With 2+ classes it stays ``unknown``."""
    ctx = _ctx(
        file_languages={"app.rb": "ruby"},
        file_symbols={
            "app.rb": [("run", "method", 1), ("render", "method", 2)],
        },
        file_class_methods={
            "app.rb": {"A": {"run": 1}, "B": {"render": 2}},
        },
    )
    assert resolve_ruby_callee("render", "self.render", "app.rb", ctx) == (
        None,
        "unknown",
        "",
    )


def test_self_method_single_class_binds_even_with_flat_symbols() -> None:
    """The single-class case must still bind via ``file_class_methods`` even when
    the flat ``file_symbols`` row for the method is present — proving the bind
    comes from the unambiguous class path, not the flat scan."""
    ctx = _ctx(
        file_languages={"app.rb": "ruby"},
        file_symbols={"app.rb": [("render", "method", 11)]},
        file_class_methods={"app.rb": {"Widget": {"render": 11}}},
    )
    assert resolve_ruby_callee("render", "self.render", "app.rb", ctx) == (
        11,
        "local",
        "app.rb",
    )


# ---------------------------------------------------------------------------
# builtin — namespaced core calls, full-name match only
# ---------------------------------------------------------------------------
def test_namespaced_builtin_classifies_as_builtin() -> None:
    ctx = _ctx(file_languages={"app.rb": "ruby"})
    assert resolve_ruby_callee("sqrt", "Math.sqrt", "app.rb", ctx) == (
        None,
        "builtin",
        "",
    )
    assert resolve_ruby_callee("sin", "Math.sin", "app.rb", ctx) == (
        None,
        "builtin",
        "",
    )


def test_bare_builtin_method_name_is_not_builtin() -> None:
    """A bare ``sqrt`` (no namespace) must NOT classify as builtin — every domain
    object can define such names; only the dotted form is safe."""
    ctx = _ctx(file_languages={"app.rb": "ruby"})
    assert resolve_ruby_callee("sqrt", "sqrt", "app.rb", ctx) == (
        None,
        "unknown",
        "",
    )
    # ``vec.log(...)`` — a domain method, not Math.log — stays unknown.
    assert resolve_ruby_callee("log", "vec.log", "app.rb", ctx) == (
        None,
        "unknown",
        "",
    )


def test_puts_is_not_builtin() -> None:
    """``puts`` is a ubiquitous bare ``Kernel`` name that every object/DSL can
    define; deliberately not in the builtin tier, so it stays ``unknown``."""
    ctx = _ctx(file_languages={"app.rb": "ruby"})
    assert resolve_ruby_callee("puts", "Kernel.puts", "app.rb", ctx) == (
        None,
        "unknown",
        "",
    )


def test_project_shadow_of_builtin_receiver_suppresses_builtin() -> None:
    """If the project owns a Ruby constant literally named ``Math``, ``Math.sqrt``
    is no longer a safe builtin — it could be the project's Math."""
    ctx = _ctx(
        file_languages={"geo.rb": "ruby"},
        global_name_table={"Math": [("geo.rb", 3)]},
    )
    _sid, res, _ = resolve_ruby_callee("sqrt", "Math.sqrt", "geo.rb", ctx)
    assert res != "builtin"


# ---------------------------------------------------------------------------
# project — single Ruby global
# ---------------------------------------------------------------------------
def test_single_ruby_global_resolves_to_project() -> None:
    ctx = _ctx(
        file_languages={"a.rb": "ruby", "b.rb": "ruby"},
        global_name_table={"compute": [("b.rb", 99)]},
        file_symbols={"b.rb": [("compute", "function", 99)]},
    )
    assert resolve_ruby_callee("compute", "compute", "a.rb", ctx) == (
        99,
        "project",
        "b.rb",
    )


def test_bare_call_does_not_bind_to_a_method_global() -> None:
    """A BARE ``render`` (no receiver) cannot call a class METHOD — methods need
    an owning receiver. The lone Ruby owner of ``render`` here is a *method* on a
    class in another file, so the bare call must NOT bind to it; it stays
    ``unknown`` rather than wiring a wrong cross-file edge."""
    ctx = _ctx(
        file_languages={"a.rb": "ruby", "widget.rb": "ruby"},
        global_name_table={"render": [("widget.rb", 50)]},
        file_symbols={"widget.rb": [("render", "method", 50)]},
    )
    assert resolve_ruby_callee("render", "render", "a.rb", ctx) == (
        None,
        "unknown",
        "",
    )


def test_bare_call_does_not_bind_to_a_class_global() -> None:
    """A bare ``Widget`` whose only owner is a *class* is a constant reference, not
    a plain call; conservatively it is not a bare-callable project target, so it
    stays ``unknown`` rather than binding to the class symbol."""
    ctx = _ctx(
        file_languages={"a.rb": "ruby", "widget.rb": "ruby"},
        global_name_table={"Widget": [("widget.rb", 60)]},
        file_symbols={"widget.rb": [("Widget", "class", 60)]},
    )
    assert resolve_ruby_callee("Widget", "Widget", "a.rb", ctx) == (
        None,
        "unknown",
        "",
    )


def test_bare_call_binds_to_a_function_global() -> None:
    """The complement: a bare call whose lone Ruby owner is a top-level
    *function* IS a valid bare-callable project target and binds."""
    ctx = _ctx(
        file_languages={"a.rb": "ruby", "util.rb": "ruby"},
        global_name_table={"compute": [("util.rb", 70)]},
        file_symbols={"util.rb": [("compute", "function", 70)]},
    )
    assert resolve_ruby_callee("compute", "compute", "a.rb", ctx) == (
        70,
        "project",
        "util.rb",
    )


def test_ambiguous_global_stays_unknown() -> None:
    """Two Ruby definitions of the same bare name → unknown (no guess)."""
    ctx = _ctx(
        file_languages={"a.rb": "ruby", "b.rb": "ruby", "c.rb": "ruby"},
        global_name_table={"compute": [("b.rb", 1), ("c.rb", 2)]},
        file_symbols={
            "b.rb": [("compute", "function", 1)],
            "c.rb": [("compute", "function", 2)],
        },
    )
    assert resolve_ruby_callee("compute", "compute", "a.rb", ctx) == (
        None,
        "unknown",
        "",
    )


# ---------------------------------------------------------------------------
# THE MOAT — mandatory no-cross-language-mis-wire test
# ---------------------------------------------------------------------------
def test_no_cross_language_mis_wire_global() -> None:
    """A bare callee whose ONLY project definition lives in a Python file must
    NOT bind to that Python file — it stays ``unknown``. (Same name, foreign
    language: the exact CodeGraph failure this project exists to beat.)"""
    ctx = _ctx(
        file_languages={"a.rb": "ruby", "util.py": "python"},
        # ``parse`` is defined ONLY in Python — a Ruby caller must not bind it.
        global_name_table={"parse": [("util.py", 42)]},
        file_symbols={"util.py": [("parse", "function", 42)]},
    )
    assert resolve_ruby_callee("parse", "parse", "a.rb", ctx) == (
        None,
        "unknown",
        "",
    )


def test_no_cross_language_mis_wire_prefers_ruby_same_name() -> None:
    """When the name exists in BOTH a Ruby file and a foreign file, only the Ruby
    definition is eligible — the resolver binds the Ruby one, never the foreign
    file, and never reports the foreign file as the target."""
    ctx = _ctx(
        file_languages={
            "a.rb": "ruby",
            "b.rb": "ruby",
            "Service.java": "java",
        },
        global_name_table={"handle": [("b.rb", 8), ("Service.java", 100)]},
        file_symbols={
            "b.rb": [("handle", "function", 8)],
            "Service.java": [("handle", "method", 100)],
        },
    )
    sid, res, target = resolve_ruby_callee("handle", "handle", "a.rb", ctx)
    # Exactly one Ruby owner (b.rb) → bound; the Java file is filtered out.
    assert (sid, res, target) == (8, "project", "b.rb")
    assert target != "Service.java"


def test_no_cross_language_builtin_suppression_ignores_foreign_owner() -> None:
    """A foreign-language symbol named ``Math`` must NOT suppress the Ruby builtin
    ``Math.sqrt`` — only a Ruby ``Math`` shadows it."""
    ctx = _ctx(
        file_languages={"app.rb": "ruby", "Math.java": "java"},
        global_name_table={"Math": [("Math.java", 1)]},
    )
    assert resolve_ruby_callee("sqrt", "Math.sqrt", "app.rb", ctx) == (
        None,
        "builtin",
        "",
    )
