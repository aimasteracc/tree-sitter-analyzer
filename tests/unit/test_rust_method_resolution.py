"""RFC-0010 Rust resolver — SAFE, self-contained per-language callee resolution.

Rust call-edge extraction is not yet wired into ``function_extraction.py`` (only
python / js / ts / java / go / c / cpp appear in ``_CALL_NODE_TYPES``), so a real
``index_project`` run produces zero Rust ``calls`` edges and the resolver is never
invoked end-to-end. These tests therefore drive the resolver's CONTRACT SURFACE
directly: build the context from synthetic ``file_symbols`` / ``global_name_table``
/ ``file_languages`` maps (exactly the shapes ``_build_resolver_context_uncached``
passes) and call ``resolve_rust_callee`` — the same function the registry dispatch
in ``synapse_resolver/__init__.py`` calls.

The resolver is deliberately CONSERVATIVE (RFC-0008 lesson): it resolves
same-file / same-language local calls, classifies a tiny set of distinctively-std
associated-function paths (``Vec::new`` / ``Box::new`` / ``std::``-pathed calls),
and returns ``unknown`` for everything else. An empty tier is correct — a
mis-classification is the failure this machinery exists to prevent.
"""

from __future__ import annotations

from tree_sitter_analyzer.synapse_resolver.languages.rust import (
    build_rust_resolver_context,
    resolve_rust_callee,
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
):
    """Build a Rust resolver context the way the registry would."""
    if global_name_table is None:
        global_name_table = {}
        for fp, syms in file_symbols.items():
            for name, _kind, sid in syms:
                global_name_table.setdefault(name, []).append((fp, sid))
    return build_rust_resolver_context(
        imports_by_file={},
        file_languages=file_languages,
        file_symbols=file_symbols,
        global_name_table=global_name_table,
        file_class_methods=_thunk(),
    )


# ---------------------------------------------------------------------------
# opt-out: no Rust file indexed -> None (zero cost)
# ---------------------------------------------------------------------------
def test_build_context_returns_none_when_no_rust_file() -> None:
    ctx = build_rust_resolver_context(
        imports_by_file={},
        file_languages={"app.py": "python", "Service.java": "java"},
        file_symbols={},
        global_name_table={},
        file_class_methods=_thunk(),
    )
    assert ctx is None, "no Rust file -> opt out so non-Rust projects pay nothing"


# ---------------------------------------------------------------------------
# (a) local same-file / same-language resolution
# ---------------------------------------------------------------------------
def test_local_free_function_resolves_local() -> None:
    """A bare call to a free function defined in the same file -> local."""
    ctx = _ctx(
        file_symbols={"lib.rs": [("helper_fn", "function", 7)]},
        file_languages={"lib.rs": "rust"},
    )
    sym_id, resolution, resolved_file = resolve_rust_callee(
        "helper_fn", "helper_fn", "lib.rs", ctx
    )
    assert resolution == "local"
    assert sym_id == 7
    assert resolved_file == "lib.rs"


def test_self_method_resolves_local() -> None:
    """``self.helper()`` -> the same-file ``helper`` method (local)."""
    ctx = _ctx(
        file_symbols={"lib.rs": [("helper", "method", 11)]},
        file_languages={"lib.rs": "rust"},
    )
    sym_id, resolution, resolved_file = resolve_rust_callee(
        "helper", "self.helper", "lib.rs", ctx
    )
    assert resolution == "local"
    assert sym_id == 11
    assert resolved_file == "lib.rs"


def test_self_method_resolves_local_when_method_name_unique() -> None:
    """``self.helper()`` resolves local only when exactly ONE method named
    ``helper`` is defined in the file — a single impl, so no owner ambiguity."""
    ctx = _ctx(
        file_symbols={
            "lib.rs": [
                ("call", "method", 10),
                ("helper", "method", 11),
            ]
        },
        file_languages={"lib.rs": "rust"},
    )
    sym_id, resolution, resolved_file = resolve_rust_callee(
        "helper", "self.helper", "lib.rs", ctx
    )
    assert resolution == "local"
    assert sym_id == 11
    assert resolved_file == "lib.rs"


def test_self_method_ambiguous_across_impls_stays_unknown() -> None:
    """Codex P2: ``self.helper()`` must NOT bind when the SAME file defines
    ``helper`` in two different impl blocks (``impl A`` and ``impl B``).

    The resolver receives no caller-owner type, so it cannot tell which
    ``helper`` the ``self`` refers to. Binding to whichever row appears first
    would corrupt the call edge — the exact mis-bind Codex flagged. The
    conservative answer is ``unknown`` (precision over recall)."""
    ctx = _ctx(
        file_symbols={
            "lib.rs": [
                ("helper", "method", 11),  # impl A { fn helper }
                ("call", "method", 12),  # impl B { fn call -> self.helper() }
                ("helper", "method", 13),  # impl B { fn helper }
            ]
        },
        file_languages={"lib.rs": "rust"},
    )
    sym_id, resolution, resolved_file = resolve_rust_callee(
        "helper", "self.helper", "lib.rs", ctx
    )
    assert resolution == "unknown", (
        "an ambiguous self.method across multiple impls must NOT bind to the "
        f"first row; got {resolution} -> sym_id={sym_id}"
    )
    assert sym_id is None
    assert resolved_file == ""


def test_selfcap_method_ambiguous_across_impls_stays_unknown() -> None:
    """The ``Self::helper()`` associated-call form has the same ambiguity hazard
    as ``self.helper()`` and must also stay ``unknown`` when duplicated."""
    ctx = _ctx(
        file_symbols={
            "lib.rs": [
                ("helper", "method", 21),
                ("helper", "method", 22),
            ]
        },
        file_languages={"lib.rs": "rust"},
    )
    sym_id, resolution, _ = resolve_rust_callee("helper", "Self::helper", "lib.rs", ctx)
    assert resolution == "unknown"
    assert sym_id is None


def test_bare_free_fn_unaffected_by_method_duplicate() -> None:
    """A bare free-function call still resolves local even if an unrelated
    duplicate METHOD name exists — the ambiguity guard targets receiver-qualified
    (self/Self) calls, and a Rust module cannot define two free fns of one name."""
    ctx = _ctx(
        file_symbols={
            "lib.rs": [
                ("run", "function", 30),  # the unique free fn we call
                ("helper", "method", 31),  # duplicate method name, irrelevant
                ("helper", "method", 32),
            ]
        },
        file_languages={"lib.rs": "rust"},
    )
    sym_id, resolution, _ = resolve_rust_callee("run", "run", "lib.rs", ctx)
    assert resolution == "local"
    assert sym_id == 30


def test_self_method_does_not_bind_to_free_function() -> None:
    """Codex P2 (#2): a receiver-qualified call ``self.helper()`` must NOT bind to a
    top-level FREE FUNCTION named ``helper``.

    In Rust's symbol rows, both impl methods and top-level free functions are
    extracted from ``function_item`` nodes; a free fn lands as ``kind='function'``
    while an impl/trait method lands as ``kind='method'`` (because
    ``_find_parent_class`` finds the enclosing ``impl_item``). A ``self.`` /
    ``Self::`` receiver can only mean an impl/trait method, never a free function,
    so counting ``function`` rows as candidate methods would corrupt the call edge
    for valid code where the receiver method simply is not the free fn. The
    conservative answer is ``unknown``."""
    ctx = _ctx(
        file_symbols={"lib.rs": [("helper", "function", 7)]},  # a FREE fn only
        file_languages={"lib.rs": "rust"},
    )
    sym_id, resolution, resolved_file = resolve_rust_callee(
        "helper", "self.helper", "lib.rs", ctx
    )
    assert resolution == "unknown", (
        "self.helper() must not bind to a top-level free fn named helper; "
        f"got {resolution} -> sym_id={sym_id}"
    )
    assert sym_id is None
    assert resolved_file == ""


def test_selfcap_assoc_does_not_bind_to_free_function() -> None:
    """The ``Self::helper()`` form has the same hazard: a same-file FREE function
    named ``helper`` (``kind='function'``) is not a candidate for a receiver-
    qualified associated call and must stay ``unknown``."""
    ctx = _ctx(
        file_symbols={"lib.rs": [("helper", "function", 9)]},
        file_languages={"lib.rs": "rust"},
    )
    sym_id, resolution, _ = resolve_rust_callee("helper", "Self::helper", "lib.rs", ctx)
    assert resolution == "unknown"
    assert sym_id is None


def test_self_method_binds_method_even_when_free_fn_shares_name() -> None:
    """When BOTH a free fn ``helper`` and exactly one impl METHOD ``helper`` exist in
    the file, ``self.helper()`` binds to the METHOD row (the free fn is ignored).

    The method name is unique among ``method`` rows (one impl), so this is an
    unambiguous, safe bind — and it must pick the method, never the free fn."""
    ctx = _ctx(
        file_symbols={
            "lib.rs": [
                ("helper", "function", 40),  # free fn — must be ignored
                ("helper", "method", 41),  # the one impl method — the right target
            ]
        },
        file_languages={"lib.rs": "rust"},
    )
    sym_id, resolution, resolved_file = resolve_rust_callee(
        "helper", "self.helper", "lib.rs", ctx
    )
    assert resolution == "local"
    assert sym_id == 41, "must bind the method row, not the free fn row"
    assert resolved_file == "lib.rs"


def test_unknown_local_name_stays_unknown() -> None:
    """A bare name with no same-file definition and no std signature -> unknown."""
    ctx = _ctx(
        file_symbols={"lib.rs": [("helper", "function", 1)]},
        file_languages={"lib.rs": "rust"},
    )
    _sym_id, resolution, _ = resolve_rust_callee("mystery", "mystery", "lib.rs", ctx)
    assert resolution == "unknown"


# ---------------------------------------------------------------------------
# (b) conservative std tiers
# ---------------------------------------------------------------------------
def test_std_path_call_classifies_stdlib() -> None:
    """A ``std::``-pathed associated call (``std::mem::swap``) -> stdlib."""
    ctx = _ctx(
        file_symbols={"lib.rs": [("caller", "function", 1)]},
        file_languages={"lib.rs": "rust"},
    )
    _sym_id, resolution, _ = resolve_rust_callee(
        "swap", "std::mem::swap", "lib.rs", ctx
    )
    assert resolution == "stdlib", f"std::mem::swap must be stdlib; got {resolution}"


def test_core_path_call_classifies_stdlib() -> None:
    """``core::`` and ``alloc::`` paths are equally part of the std distribution."""
    ctx = _ctx(
        file_symbols={"lib.rs": [("caller", "function", 1)]},
        file_languages={"lib.rs": "rust"},
    )
    _sym_id, resolution, _ = resolve_rust_callee(
        "from", "core::convert::From::from", "lib.rs", ctx
    )
    assert resolution == "stdlib"


def test_vec_new_associated_fn_classifies_stdlib() -> None:
    """``Vec::new`` is a distinctively-std associated function -> stdlib."""
    ctx = _ctx(
        file_symbols={"lib.rs": [("caller", "function", 1)]},
        file_languages={"lib.rs": "rust"},
    )
    _sym_id, resolution, _ = resolve_rust_callee("new", "Vec::new", "lib.rs", ctx)
    assert resolution == "stdlib", f"Vec::new must be stdlib; got {resolution}"


def test_box_new_associated_fn_classifies_stdlib() -> None:
    ctx = _ctx(
        file_symbols={"lib.rs": [("caller", "function", 1)]},
        file_languages={"lib.rs": "rust"},
    )
    _sym_id, resolution, _ = resolve_rust_callee("new", "Box::new", "lib.rs", ctx)
    assert resolution == "stdlib"


def test_bare_new_stays_unknown() -> None:
    """A bare ``new`` with no std path (could be any project type) -> unknown.

    ``new`` is the single most common associated-fn name in all Rust code; a bare
    receiver-less ``new`` carries no std evidence, so the conservative tier must
    NOT claim it (RFC-0008 precision lesson: an empty/strict tier beats a false
    positive)."""
    ctx = _ctx(
        file_symbols={"lib.rs": [("caller", "function", 1)]},
        file_languages={"lib.rs": "rust"},
    )
    _sym_id, resolution, _ = resolve_rust_callee("new", "new", "lib.rs", ctx)
    assert resolution == "unknown", f"bare new must stay unknown; got {resolution}"


def test_unknown_user_type_associated_fn_stays_unknown() -> None:
    """``MyType::build`` (a project type's associated fn) -> unknown, never stdlib."""
    ctx = _ctx(
        file_symbols={"lib.rs": [("caller", "function", 1)]},
        file_languages={"lib.rs": "rust"},
    )
    _sym_id, resolution, _ = resolve_rust_callee(
        "build", "MyType::build", "lib.rs", ctx
    )
    assert resolution == "unknown"


def test_project_def_shadows_std_associated_fn() -> None:
    """If the project defines ``new`` and the call is ``Vec::new`` BUT a same-file
    ``Vec`` impl exists locally... we still classify by std path only when the
    project does NOT own the name. A project-owned bare name resolves local first.

    Here a project-defined free fn named ``swap`` must shadow the std tier: a bare
    same-file ``swap()`` resolves local, never stdlib."""
    ctx = _ctx(
        file_symbols={"lib.rs": [("swap", "function", 3)]},
        file_languages={"lib.rs": "rust"},
    )
    sym_id, resolution, _ = resolve_rust_callee("swap", "swap", "lib.rs", ctx)
    assert resolution == "local"
    assert sym_id == 3


# ---------------------------------------------------------------------------
# (THE MOAT) no cross-language mis-wire — MANDATORY
# ---------------------------------------------------------------------------
def test_no_cross_language_mis_wire_to_other_language_symbol() -> None:
    """CRITICAL: a Rust callee whose bare name also exists as a symbol in a
    DIFFERENT language's file must NEVER bind to that other-language file.

    ``helper`` is defined in BOTH a Python file and a Rust file. A Rust caller in
    ``other.rs`` (which does NOT define ``helper``) must resolve to ``unknown`` —
    it must not be wired to the Python ``helper`` symbol. This is the exact
    CodeGraph cross-language false-bind that this resolver exists to beat."""
    file_symbols = {
        "app.py": [("helper", "function", 100)],
        "lib.rs": [("helper", "function", 200)],
        "other.rs": [("caller", "function", 300)],
    }
    ctx = _ctx(
        file_symbols=file_symbols,
        file_languages={"app.py": "python", "lib.rs": "rust", "other.rs": "rust"},
    )
    sym_id, resolution, resolved_file = resolve_rust_callee(
        "helper", "helper", "other.rs", ctx
    )
    # Must NOT bind to the Python file under any circumstance.
    assert resolved_file != "app.py", (
        "Rust caller must never bind to a Python symbol (the moat); "
        f"got resolved_file={resolved_file!r}"
    )
    assert sym_id != 100
    # ``helper`` is defined in two Rust files (lib.rs + ambiguous) — but the caller
    # is in other.rs which defines no helper, so a conservative same-file-only
    # resolver returns unknown rather than guessing a different Rust file.
    assert resolution == "unknown"


def test_cross_language_bare_name_collision_python_only_owner() -> None:
    """A bare Rust call whose name exists ONLY in a Python file -> unknown, never
    bound to the Python file (single global candidate in the wrong language)."""
    file_symbols = {
        "app.py": [("compute", "function", 100)],
        "lib.rs": [("caller", "function", 200)],
    }
    ctx = _ctx(
        file_symbols=file_symbols,
        file_languages={"app.py": "python", "lib.rs": "rust"},
    )
    sym_id, resolution, resolved_file = resolve_rust_callee(
        "compute", "compute", "lib.rs", ctx
    )
    assert resolved_file != "app.py"
    assert sym_id != 100
    assert resolution == "unknown"


def test_std_name_collision_with_python_symbol_still_stdlib() -> None:
    """A Rust ``std::mem::swap`` must classify stdlib even though a Python file
    defines a ``swap`` symbol — the Python symbol is invisible to the Rust caller
    (``languages_compatible`` is False), so it does not suppress the std tier."""
    file_symbols = {
        "swapper.py": [("swap", "function", 100)],
        "lib.rs": [("caller", "function", 200)],
    }
    ctx = _ctx(
        file_symbols=file_symbols,
        file_languages={"swapper.py": "python", "lib.rs": "rust"},
    )
    _sym_id, resolution, resolved_file = resolve_rust_callee(
        "swap", "std::mem::swap", "lib.rs", ctx
    )
    assert resolution == "stdlib"
    assert resolved_file != "swapper.py"


# ---------------------------------------------------------------------------
# registration wiring
# ---------------------------------------------------------------------------
def test_rust_is_registered() -> None:
    """Importing the languages package registers 'rust' in the registry."""
    import tree_sitter_analyzer.synapse_resolver.languages as _languages  # noqa: F401
    from tree_sitter_analyzer.synapse_resolver._registry import registered_languages

    assert "rust" in registered_languages()
