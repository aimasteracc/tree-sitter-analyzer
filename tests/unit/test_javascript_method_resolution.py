"""RFC-0010 first wave: JavaScript per-language callee resolver.

Unit-level tests that drive ``resolve_javascript_callee`` against a hand-built
context (no full index needed). They assert the four guarantees of a SAFE,
self-contained resolver:

* same-file ``local`` resolution from ``file_symbols`` / ``file_class_methods``,
* CONSERVATIVE ``builtin`` classification on the FULL dotted call name only,
* ``project`` resolution gated to the JS family, and
* the MOAT: a callee whose name also exists in another language's file must
  NEVER bind to that file — it stays ``unknown`` (or the JS same-file def).
"""

from __future__ import annotations

from tree_sitter_analyzer.synapse_resolver._registry import (
    get_language_resolver,
    registered_languages,
)
from tree_sitter_analyzer.synapse_resolver.languages.javascript import (
    build_javascript_context,
    resolve_javascript_callee,
)


def _ctx(
    *,
    file_symbols=None,
    file_class_methods=None,
    global_name_table=None,
    file_languages=None,
    shadowed_globals=None,
):
    """Build a JS resolver context from explicit maps (thunk-style fcm)."""
    return build_javascript_context(
        imports_by_file={},
        file_languages=file_languages or {},
        file_symbols=file_symbols or {},
        global_name_table=global_name_table or {},
        file_class_methods=lambda: file_class_methods or {},
        js_shadowed_globals=shadowed_globals,
    )


# ---------------------------------------------------------------------------
# registration / discovery
# ---------------------------------------------------------------------------
def test_javascript_is_registered() -> None:
    assert "javascript" in registered_languages()
    assert get_language_resolver("javascript") is not None


def test_jsx_is_registered() -> None:
    """Codex P2 #346: ``.jsx`` files are tagged ``"jsx"`` by the detector, and
    ``resolve_callee`` looks up the registry by that exact language string. If
    only ``"javascript"`` is registered, JSX callers bypass this SAFE resolver
    and fall through to the Python cascade (e.g. a bare ``len()`` in a ``.jsx``
    file would be mis-classified as a Python builtin). The ``jsx`` dialect must
    route to the same resolver so it stays conservative."""
    assert "jsx" in registered_languages()
    assert get_language_resolver("jsx") is not None


# ---------------------------------------------------------------------------
# gating — zero cost for non-JS projects
# ---------------------------------------------------------------------------
def test_build_returns_none_when_no_js_file_indexed() -> None:
    ctx = build_javascript_context(
        imports_by_file={},
        file_languages={"a.py": "python", "B.java": "java"},
        file_symbols={},
        global_name_table={},
        file_class_methods=lambda: (_ for _ in ()).throw(
            AssertionError("thunk must NOT be forced for a non-JS index")
        ),
    )
    assert ctx is None


def test_build_returns_context_when_js_file_indexed() -> None:
    ctx = _ctx(file_languages={"app.js": "javascript"})
    assert ctx is not None


def test_build_returns_context_when_only_jsx_file_indexed() -> None:
    """Codex P2 #346: a project containing only ``.jsx`` files (tagged ``"jsx"``)
    must still build the JS context — otherwise JSX callers get no resolver."""
    ctx = _ctx(file_languages={"App.jsx": "jsx"})
    assert ctx is not None


def test_jsx_caller_bare_call_stays_unknown_not_python_builtin() -> None:
    """Codex P2 #346: the canonical bug — a bare ``len()`` in a JSX file. With
    the JS resolver active for ``jsx``, an unowned bare name stays ``unknown``
    (conservative) instead of leaking to the Python cascade as a builtin."""
    ctx = _ctx(file_languages={"App.jsx": "jsx"})
    assert resolve_javascript_callee("len", "len", "App.jsx", ctx) == (
        None,
        "unknown",
        "",
    )


def test_jsx_local_resolution_works() -> None:
    """A same-file bare call inside a ``.jsx`` file resolves ``local``."""
    ctx = _ctx(
        file_languages={"App.jsx": "jsx"},
        file_symbols={"App.jsx": [("renderRow", "function", 12)]},
    )
    assert resolve_javascript_callee("renderRow", "renderRow", "App.jsx", ctx) == (
        12,
        "local",
        "App.jsx",
    )


# ---------------------------------------------------------------------------
# local — same-file resolution
# ---------------------------------------------------------------------------
def test_bare_call_to_same_file_function_is_local() -> None:
    ctx = _ctx(
        file_languages={"app.js": "javascript"},
        file_symbols={"app.js": [("helper", "function", 7)]},
    )
    assert resolve_javascript_callee("helper", "helper", "app.js", ctx) == (
        7,
        "local",
        "app.js",
    )


def test_self_receiver_does_not_bind_to_same_file_helper() -> None:
    """Codex P2 #346: in browser/worker JS, ``self`` is the global scope
    (``Window.self`` / ``WorkerGlobalScope.self``), NOT the current object.
    ``self.foo()`` must NOT bind to a same-file helper named ``foo`` — that is a
    concrete wrong edge. The conservative result is ``unknown``."""
    ctx = _ctx(
        file_languages={"worker.js": "javascript"},
        file_symbols={"worker.js": [("postMessage", "function", 4)]},
    )
    assert resolve_javascript_callee(
        "postMessage", "self.postMessage", "worker.js", ctx
    ) == (None, "unknown", "")


def test_self_receiver_does_not_bind_to_same_file_method() -> None:
    """``self.render()`` must not bind a same-file class method ``render`` —
    ``self`` is global scope in JS, not ``this``."""
    ctx = _ctx(
        file_languages={"app.js": "javascript"},
        file_class_methods={"app.js": {"Widget": {"render": 11}}},
    )
    assert resolve_javascript_callee("render", "self.render", "app.js", ctx) == (
        None,
        "unknown",
        "",
    )


def test_this_method_call_is_local_via_class_methods() -> None:
    ctx = _ctx(
        file_languages={"app.js": "javascript"},
        file_class_methods={"app.js": {"Widget": {"render": 11}}},
    )
    assert resolve_javascript_callee("render", "this.render", "app.js", ctx) == (
        11,
        "local",
        "app.js",
    )


def test_this_method_does_not_bind_across_sibling_classes() -> None:
    """Codex P2 #346: ``class A { run() { this.render(); } } class B { render(){} }``.
    The caller ``A.run`` does NOT define ``render``; only the SIBLING class ``B``
    does. Without the caller's enclosing class we cannot prove ``this.render`` is
    a call on ``A``, so binding it to ``B.render`` is a concrete wrong edge. With
    two+ classes in the file, ``this.<method>`` must stay ``unknown``."""
    ctx = _ctx(
        file_languages={"app.js": "javascript"},
        file_class_methods={
            "app.js": {"A": {"run": 1}, "B": {"render": 2}},
        },
    )
    assert resolve_javascript_callee("render", "this.render", "app.js", ctx) == (
        None,
        "unknown",
        "",
    )


def test_this_method_single_class_still_binds() -> None:
    """Sanity: with exactly ONE class in the file, ``this.<method>`` is
    unambiguous — ``this`` can only be that class — so the local bind holds."""
    ctx = _ctx(
        file_languages={"app.js": "javascript"},
        file_class_methods={"app.js": {"Widget": {"render": 11}}},
    )
    assert resolve_javascript_callee("render", "this.render", "app.js", ctx) == (
        11,
        "local",
        "app.js",
    )


# ---------------------------------------------------------------------------
# builtin — namespaced globals, full-name match only
# ---------------------------------------------------------------------------
def test_namespaced_builtin_classifies_as_builtin() -> None:
    ctx = _ctx(file_languages={"app.js": "javascript"})
    assert resolve_javascript_callee("parse", "JSON.parse", "app.js", ctx) == (
        None,
        "builtin",
        "",
    )
    assert resolve_javascript_callee("keys", "Object.keys", "app.js", ctx) == (
        None,
        "builtin",
        "",
    )


def test_bare_builtin_method_name_is_not_builtin() -> None:
    """A bare ``parse`` / ``keys`` (no namespace) must NOT classify as builtin —
    every domain object defines such names; only the dotted form is safe."""
    ctx = _ctx(file_languages={"app.js": "javascript"})
    assert resolve_javascript_callee("parse", "parse", "app.js", ctx) == (
        None,
        "unknown",
        "",
    )
    # ``users.map(...)`` — a domain array method, not Array.from — stays unknown.
    assert resolve_javascript_callee("map", "users.map", "app.js", ctx) == (
        None,
        "unknown",
        "",
    )


def test_console_log_is_not_builtin() -> None:
    """``console`` is a commonly shadowed domain logger name; deliberately not
    in the builtin table, so ``console.log`` stays unknown (conservative)."""
    ctx = _ctx(file_languages={"app.js": "javascript"})
    assert resolve_javascript_callee("log", "console.log", "app.js", ctx) == (
        None,
        "unknown",
        "",
    )


def test_project_shadow_of_builtin_receiver_suppresses_builtin() -> None:
    """If the project owns a JS object literally named ``Math``, ``Math.max``
    is no longer a safe builtin — it could be the project's Math."""
    ctx = _ctx(
        file_languages={"geo.js": "javascript"},
        global_name_table={"Math": [("geo.js", 3)]},
    )
    sid, res, _ = resolve_javascript_callee("max", "Math.max", "geo.js", ctx)
    assert res != "builtin"


def test_variable_shadow_of_builtin_receiver_suppresses_builtin() -> None:
    """Codex P2 #346: ``const Math = { max() {} }; Math.max()``. The shadow is a
    ``kind='variable'`` row, which the shared ``global_name_table`` (built from
    function/method/class only) never sees. The resolver must consult the
    JS-family variable shadows too — otherwise ``Math.max`` is wrongly marked
    terminal ``builtin`` even though the project owns the receiver."""
    ctx = _ctx(
        file_languages={"geo.js": "javascript"},
        shadowed_globals={"Math"},
    )
    sid, res, _ = resolve_javascript_callee("max", "Math.max", "geo.js", ctx)
    assert res != "builtin"


def test_variable_shadow_only_blocks_the_shadowed_receiver() -> None:
    """A variable shadow of ``Math`` must NOT suppress an unrelated builtin
    (``JSON.parse``) — the gate is per-receiver-name, not global."""
    ctx = _ctx(
        file_languages={"app.js": "javascript"},
        shadowed_globals={"Math"},
    )
    assert resolve_javascript_callee("parse", "JSON.parse", "app.js", ctx) == (
        None,
        "builtin",
        "",
    )


# ---------------------------------------------------------------------------
# project — single JS-family global
# ---------------------------------------------------------------------------
def test_single_js_global_resolves_to_project() -> None:
    ctx = _ctx(
        file_languages={"a.js": "javascript", "b.js": "javascript"},
        global_name_table={"compute": [("b.js", 99)]},
        file_symbols={"b.js": [("compute", "function", 99)]},
    )
    assert resolve_javascript_callee("compute", "compute", "a.js", ctx) == (
        99,
        "project",
        "b.js",
    )


def test_bare_call_does_not_bind_to_a_method_global() -> None:
    """Codex P2 #346: ``global_name_table`` holds every function/method/class,
    but a BARE ``render()`` (no receiver/import) cannot call a class METHOD —
    methods need an owning receiver. The lone JS-family owner of ``render`` here
    is a *method* on a class in another file, so the bare call must NOT bind to
    it; it stays ``unknown`` rather than wiring a wrong cross-file edge."""
    ctx = _ctx(
        file_languages={"a.js": "javascript", "widget.js": "javascript"},
        global_name_table={"render": [("widget.js", 50)]},
        file_symbols={"widget.js": [("render", "method", 50)]},
    )
    assert resolve_javascript_callee("render", "render", "a.js", ctx) == (
        None,
        "unknown",
        "",
    )


def test_bare_call_does_not_bind_to_a_class_global() -> None:
    """A bare ``Widget()`` whose only owner is a *class* is a construction, not a
    plain function call; conservatively it is not a bare-callable project target,
    so it stays ``unknown`` rather than binding to the class symbol."""
    ctx = _ctx(
        file_languages={"a.js": "javascript", "widget.js": "javascript"},
        global_name_table={"Widget": [("widget.js", 60)]},
        file_symbols={"widget.js": [("Widget", "class", 60)]},
    )
    assert resolve_javascript_callee("Widget", "Widget", "a.js", ctx) == (
        None,
        "unknown",
        "",
    )


def test_bare_call_binds_to_a_function_global() -> None:
    """The complement of the above: a bare call whose lone JS-family owner is a
    top-level *function* IS a valid bare-callable project target and binds."""
    ctx = _ctx(
        file_languages={"a.js": "javascript", "util.js": "javascript"},
        global_name_table={"compute": [("util.js", 70)]},
        file_symbols={"util.js": [("compute", "function", 70)]},
    )
    assert resolve_javascript_callee("compute", "compute", "a.js", ctx) == (
        70,
        "project",
        "util.js",
    )


def test_ts_family_global_is_resolvable_from_js_caller() -> None:
    """JS/TS are one interop family — a single ``.ts`` global is a valid bind."""
    ctx = _ctx(
        file_languages={"a.js": "javascript", "b.ts": "typescript"},
        global_name_table={"compute": [("b.ts", 5)]},
        file_symbols={"b.ts": [("compute", "function", 5)]},
    )
    sid, res, target = resolve_javascript_callee("compute", "compute", "a.js", ctx)
    assert (sid, res, target) == (5, "project", "b.ts")


def test_ambiguous_global_stays_unknown() -> None:
    """Two JS definitions of the same bare name → unknown (no guess)."""
    ctx = _ctx(
        file_languages={
            "a.js": "javascript",
            "b.js": "javascript",
            "c.js": "javascript",
        },
        global_name_table={"compute": [("b.js", 1), ("c.js", 2)]},
    )
    assert resolve_javascript_callee("compute", "compute", "a.js", ctx) == (
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
        file_languages={"a.js": "javascript", "util.py": "python"},
        # ``parse`` is defined ONLY in Python — a JS caller must not bind it.
        global_name_table={"parse": [("util.py", 42)]},
    )
    assert resolve_javascript_callee("parse", "parse", "a.js", ctx) == (
        None,
        "unknown",
        "",
    )


def test_no_cross_language_mis_wire_prefers_js_same_name() -> None:
    """When the name exists in BOTH a JS file and a foreign file, only the JS
    definition is eligible — the resolver binds the JS one, never the foreign
    file, and never reports the foreign file as the target."""
    ctx = _ctx(
        file_languages={
            "a.js": "javascript",
            "b.js": "javascript",
            "Service.java": "java",
        },
        global_name_table={"handle": [("b.js", 8), ("Service.java", 100)]},
        file_symbols={
            "b.js": [("handle", "function", 8)],
            "Service.java": [("handle", "method", 100)],
        },
    )
    sid, res, target = resolve_javascript_callee("handle", "handle", "a.js", ctx)
    # Exactly one JS-family owner (b.js) → bound; the Java file is filtered out.
    assert (sid, res, target) == (8, "project", "b.js")
    assert target != "Service.java"


def test_no_cross_language_builtin_suppression_ignores_foreign_owner() -> None:
    """A foreign-language symbol named ``Math`` must NOT suppress the JS builtin
    ``Math.max`` — only a JS-family ``Math`` shadows it."""
    ctx = _ctx(
        file_languages={"app.js": "javascript", "Math.java": "java"},
        global_name_table={"Math": [("Math.java", 1)]},
    )
    assert resolve_javascript_callee("max", "Math.max", "app.js", ctx) == (
        None,
        "builtin",
        "",
    )
