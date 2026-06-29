"""RFC-0010 Kotlin resolver — SAFE, self-contained per-language callee resolution.

Kotlin call-edge extraction is not yet wired into ``function_extraction.py``
(only python / js / ts / java / go / c / cpp appear in ``_CALL_NODE_TYPES``), so
a real ``index_project`` run produces zero Kotlin ``calls`` edges and the
resolver is never invoked end-to-end. These tests therefore drive the resolver's
CONTRACT SURFACE directly: build the context from synthetic ``file_symbols`` /
``global_name_table`` / ``file_languages`` maps (the shapes
``_build_resolver_context_uncached`` passes) and call ``resolve_kotlin_callee`` —
the same function the registry dispatch in ``synapse_resolver/__init__.py`` calls.

The resolver is deliberately CONSERVATIVE (RFC-0008 lesson): it resolves
same-file / same-language local calls (bare top-level functions, and
``this.``/``super.`` member calls only when the method name is unique in the
file), classifies a tiny set of auto-imported stdlib TOP-LEVEL functions
(``listOf`` / ``println`` / ``require``) gated on project non-ownership, and
returns ``unknown`` for everything else. An empty/strict tier is correct — a
mis-classification is the failure this machinery exists to prevent.

THE MOAT (the #1 requirement): a Kotlin callee is NEVER bound to a symbol in a
different language's file — including a Java file, because Kotlin and Java are
not one ``languages_compatible`` family.
"""

from __future__ import annotations

from tree_sitter_analyzer.synapse_resolver.languages.kotlin import (
    build_kotlin_resolver_context,
    resolve_kotlin_callee,
)


def _thunk(value: dict[str, dict[str, dict[str, int]]] | None = None):
    """A zero-arg lazy file_class_methods thunk (the registry passes a callable)."""

    def _inner() -> dict[str, dict[str, dict[str, int]]]:
        return value or {}

    return _inner


def _ctx(
    *,
    file_symbols: dict[str, list[tuple[str, str, int]]],
    file_languages: dict[str, str],
    global_name_table: dict[str, list[tuple[str, int]]] | None = None,
    file_class_methods: dict[str, dict[str, dict[str, int]]] | None = None,
):
    """Build a Kotlin resolver context the way the registry would."""
    if global_name_table is None:
        global_name_table = {}
        for fp, syms in file_symbols.items():
            for name, _kind, sid in syms:
                global_name_table.setdefault(name, []).append((fp, sid))
    return build_kotlin_resolver_context(
        imports_by_file={},
        file_languages=file_languages,
        file_symbols=file_symbols,
        global_name_table=global_name_table,
        file_class_methods=_thunk(file_class_methods),
    )


# ---------------------------------------------------------------------------
# opt-out: no Kotlin file indexed -> None (zero cost)
# ---------------------------------------------------------------------------
def test_build_context_returns_none_when_no_kotlin_file() -> None:
    ctx = build_kotlin_resolver_context(
        imports_by_file={},
        file_languages={"app.py": "python", "Service.java": "java"},
        file_symbols={},
        global_name_table={},
        file_class_methods=_thunk(),
    )
    assert ctx is None, "no Kotlin file -> opt out so non-Kotlin projects pay nothing"


# ---------------------------------------------------------------------------
# (a) local same-file / same-language resolution
# ---------------------------------------------------------------------------
def test_local_top_level_function_resolves_local() -> None:
    """A bare call to a top-level function defined in the same file -> local."""
    ctx = _ctx(
        file_symbols={"Main.kt": [("helperFn", "function", 7)]},
        file_languages={"Main.kt": "kotlin"},
    )
    sym_id, resolution, resolved_file = resolve_kotlin_callee(
        "helperFn", "helperFn", "Main.kt", ctx
    )
    assert resolution == "local"
    assert sym_id == 7
    assert resolved_file == "Main.kt"


def test_this_method_resolves_local_when_unique() -> None:
    """``this.helper()`` -> the same-file ``helper`` method (local) when unique."""
    ctx = _ctx(
        file_symbols={"Main.kt": [("helper", "method", 11)]},
        file_languages={"Main.kt": "kotlin"},
    )
    sym_id, resolution, resolved_file = resolve_kotlin_callee(
        "helper", "this.helper", "Main.kt", ctx
    )
    assert resolution == "local"
    assert sym_id == 11
    assert resolved_file == "Main.kt"


def test_super_method_resolves_local_when_unique() -> None:
    """``super.helper()`` is also a member call -> unique same-file method."""
    ctx = _ctx(
        file_symbols={"Main.kt": [("helper", "method", 12)]},
        file_languages={"Main.kt": "kotlin"},
    )
    sym_id, resolution, _ = resolve_kotlin_callee(
        "helper", "super.helper", "Main.kt", ctx
    )
    assert resolution == "local"
    assert sym_id == 12


def test_this_method_ambiguous_across_classes_stays_unknown() -> None:
    """Codex P2: ``this.helper()`` must NOT bind when the SAME file defines
    ``helper`` in two different classes. No caller-owner class is threaded
    through the resolver, so binding the first row would corrupt the edge."""
    ctx = _ctx(
        file_symbols={
            "Main.kt": [
                ("helper", "method", 11),  # class A { fun helper }
                ("call", "method", 12),  # class B { fun call -> this.helper() }
                ("helper", "method", 13),  # class B { fun helper }
            ]
        },
        file_languages={"Main.kt": "kotlin"},
        file_class_methods={
            "Main.kt": {
                "A": {"helper": 11},
                "B": {"call": 12, "helper": 13},
            }
        },
    )
    sym_id, resolution, resolved_file = resolve_kotlin_callee(
        "helper", "this.helper", "Main.kt", ctx
    )
    assert resolution == "unknown", (
        "an ambiguous this.method across multiple classes must NOT bind to the "
        f"first row; got {resolution} -> sym_id={sym_id}"
    )
    assert sym_id is None
    assert resolved_file == ""


def test_this_method_does_not_bind_to_top_level_function() -> None:
    """A receiver-qualified ``this.helper()`` must NOT bind to a top-level FREE
    FUNCTION named ``helper`` (``kind='function'``). A ``this``/``super``
    receiver can only mean a member method."""
    ctx = _ctx(
        file_symbols={"Main.kt": [("helper", "function", 7)]},  # a top-level fn only
        file_languages={"Main.kt": "kotlin"},
    )
    sym_id, resolution, resolved_file = resolve_kotlin_callee(
        "helper", "this.helper", "Main.kt", ctx
    )
    assert resolution == "unknown"
    assert sym_id is None
    assert resolved_file == ""


def test_unknown_local_name_stays_unknown() -> None:
    """A bare name with no same-file definition and no stdlib signature -> unknown."""
    ctx = _ctx(
        file_symbols={"Main.kt": [("helper", "function", 1)]},
        file_languages={"Main.kt": "kotlin"},
    )
    _sym_id, resolution, _ = resolve_kotlin_callee("mystery", "mystery", "Main.kt", ctx)
    assert resolution == "unknown"


def test_bare_call_does_not_guess_other_file_same_language() -> None:
    """A bare call whose name is defined only in ANOTHER Kotlin file -> unknown
    (no single-global binding — only the caller's own file is consulted)."""
    ctx = _ctx(
        file_symbols={
            "Other.kt": [("helper", "function", 50)],
            "Main.kt": [("caller", "function", 51)],
        },
        file_languages={"Other.kt": "kotlin", "Main.kt": "kotlin"},
    )
    sym_id, resolution, resolved_file = resolve_kotlin_callee(
        "helper", "helper", "Main.kt", ctx
    )
    assert resolution == "unknown"
    assert sym_id is None
    assert resolved_file == ""


# ---------------------------------------------------------------------------
# (b) conservative stdlib tier — auto-imported bare top-level functions
# ---------------------------------------------------------------------------
def test_bare_listof_classifies_stdlib() -> None:
    """``listOf()`` is an auto-imported stdlib builder -> stdlib."""
    ctx = _ctx(
        file_symbols={"Main.kt": [("caller", "function", 1)]},
        file_languages={"Main.kt": "kotlin"},
    )
    _sym_id, resolution, _ = resolve_kotlin_callee("listOf", "listOf", "Main.kt", ctx)
    assert resolution == "stdlib", f"listOf must be stdlib; got {resolution}"


def test_bare_println_classifies_stdlib() -> None:
    ctx = _ctx(
        file_symbols={"Main.kt": [("caller", "function", 1)]},
        file_languages={"Main.kt": "kotlin"},
    )
    _sym_id, resolution, _ = resolve_kotlin_callee("println", "println", "Main.kt", ctx)
    assert resolution == "stdlib"


def test_bare_require_classifies_stdlib() -> None:
    ctx = _ctx(
        file_symbols={"Main.kt": [("caller", "function", 1)]},
        file_languages={"Main.kt": "kotlin"},
    )
    _sym_id, resolution, _ = resolve_kotlin_callee("require", "require", "Main.kt", ctx)
    assert resolution == "stdlib"


def test_local_def_shadows_stdlib_bare_function() -> None:
    """A project top-level ``fun println(...)`` in the caller file shadows the
    stdlib claim: a bare ``println()`` resolves LOCAL, never stdlib."""
    ctx = _ctx(
        file_symbols={"Main.kt": [("println", "function", 3)]},
        file_languages={"Main.kt": "kotlin"},
    )
    sym_id, resolution, _ = resolve_kotlin_callee("println", "println", "Main.kt", ctx)
    assert resolution == "local"
    assert sym_id == 3


def test_project_owns_stdlib_name_in_other_kotlin_file_suppresses_stdlib() -> None:
    """If the project defines ``listOf`` as a function in ANOTHER Kotlin file, the
    stdlib claim is suppressed (project owns the name) but the caller's own file
    has no def -> unknown, never a cross-file bind."""
    ctx = _ctx(
        file_symbols={
            "Util.kt": [("listOf", "function", 30)],
            "Main.kt": [("caller", "function", 31)],
        },
        file_languages={"Util.kt": "kotlin", "Main.kt": "kotlin"},
    )
    sym_id, resolution, resolved_file = resolve_kotlin_callee(
        "listOf", "listOf", "Main.kt", ctx
    )
    assert resolution == "unknown"
    assert sym_id is None
    assert resolved_file != "Util.kt"


def test_receiver_method_call_stays_unknown() -> None:
    """A receiver method call (``items.map`` — receiver type not inferable) -> unknown.
    Bare-method-name tiers are intentionally empty (RFC-0008 precision lesson)."""
    ctx = _ctx(
        file_symbols={"Main.kt": [("caller", "function", 1)]},
        file_languages={"Main.kt": "kotlin"},
    )
    _sym_id, resolution, _ = resolve_kotlin_callee("map", "items.map", "Main.kt", ctx)
    assert resolution == "unknown"


def test_qualified_stdlib_name_on_receiver_stays_unknown() -> None:
    """A stdlib NAME used as a member call (``something.listOf``) is NOT the bare
    auto-imported function — the bare-function tier requires a receiver-less call,
    so a receiver-qualified ``listOf`` stays unknown (no false stdlib claim)."""
    ctx = _ctx(
        file_symbols={"Main.kt": [("caller", "function", 1)]},
        file_languages={"Main.kt": "kotlin"},
    )
    _sym_id, resolution, _ = resolve_kotlin_callee(
        "listOf", "factory.listOf", "Main.kt", ctx
    )
    assert resolution == "unknown"


# ---------------------------------------------------------------------------
# (THE MOAT) no cross-language mis-wire — MANDATORY
# ---------------------------------------------------------------------------
def test_no_cross_language_mis_wire_to_java_symbol() -> None:
    """CRITICAL: a Kotlin callee whose bare name also exists as a symbol in a
    JAVA file must NEVER bind to that Java file. Kotlin and Java are not one
    ``languages_compatible`` family, so even on the JVM the moat is absolute.

    ``helper`` is defined in BOTH a Java file and a Kotlin file. A Kotlin caller
    in ``Other.kt`` (which does NOT define ``helper``) must resolve to ``unknown``
    — never wired to the Java ``helper`` symbol."""
    file_symbols = {
        "Service.java": [("helper", "method", 100)],
        "Lib.kt": [("helper", "function", 200)],
        "Other.kt": [("caller", "function", 300)],
    }
    ctx = _ctx(
        file_symbols=file_symbols,
        file_languages={
            "Service.java": "java",
            "Lib.kt": "kotlin",
            "Other.kt": "kotlin",
        },
    )
    sym_id, resolution, resolved_file = resolve_kotlin_callee(
        "helper", "helper", "Other.kt", ctx
    )
    assert resolved_file != "Service.java", (
        "Kotlin caller must never bind to a Java symbol (the moat); "
        f"got resolved_file={resolved_file!r}"
    )
    assert sym_id != 100
    assert resolution == "unknown"


def test_no_cross_language_mis_wire_to_python_symbol() -> None:
    """A bare Kotlin call whose name exists ONLY in a Python file -> unknown,
    never bound to the Python file."""
    file_symbols = {
        "app.py": [("compute", "function", 100)],
        "Main.kt": [("caller", "function", 200)],
    }
    ctx = _ctx(
        file_symbols=file_symbols,
        file_languages={"app.py": "python", "Main.kt": "kotlin"},
    )
    sym_id, resolution, resolved_file = resolve_kotlin_callee(
        "compute", "compute", "Main.kt", ctx
    )
    assert resolved_file != "app.py"
    assert sym_id != 100
    assert resolution == "unknown"


def test_stdlib_name_collision_with_java_symbol_still_stdlib() -> None:
    """A Kotlin bare ``listOf()`` must classify stdlib even though a Java file
    defines a ``listOf`` symbol — the Java symbol is invisible to the Kotlin
    caller (``languages_compatible('kotlin', 'java')`` is False), so it does not
    suppress the stdlib tier."""
    file_symbols = {
        "Factory.java": [("listOf", "method", 100)],
        "Main.kt": [("caller", "function", 200)],
    }
    ctx = _ctx(
        file_symbols=file_symbols,
        file_languages={"Factory.java": "java", "Main.kt": "kotlin"},
    )
    _sym_id, resolution, resolved_file = resolve_kotlin_callee(
        "listOf", "listOf", "Main.kt", ctx
    )
    assert resolution == "stdlib"
    assert resolved_file != "Factory.java"


# ---------------------------------------------------------------------------
# registration wiring
# ---------------------------------------------------------------------------
def test_kotlin_is_registered() -> None:
    """Importing the languages package registers 'kotlin' in the registry."""
    import tree_sitter_analyzer.synapse_resolver.languages as _languages  # noqa: F401
    from tree_sitter_analyzer.synapse_resolver._registry import registered_languages

    assert "kotlin" in registered_languages()
