"""Unit + integration tests for the C# resolver (RFC-0010 second wave).

Covers the conservative cascade in
``synapse_resolver/languages/csharp.py``: ``System.``-qualified stdlib
classification, the near-exclusive BCL static-type qualifier tier (shadow-gated
by ``_project_owns``), local same-file resolution, single-global project
resolution, the empty bare-method-name tiers, and — MANDATORY — the
no-cross-language-mis-wire moat (a callee whose name also exists in a non-C#
file must NEVER bind to that file).
"""

from __future__ import annotations

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.synapse_resolver import ResolverContext, resolve_callee
from tree_sitter_analyzer.synapse_resolver._context import build_resolver_context
from tree_sitter_analyzer.synapse_resolver._registry import get_language_resolver
from tree_sitter_analyzer.synapse_resolver.languages._csharp_constants import (
    BCL_STATIC_TYPES_CSHARP,
    EXTERNAL_METHODS_CSHARP,
    STDLIB_METHODS_CSHARP,
    is_system_qualifier,
)
from tree_sitter_analyzer.synapse_resolver.languages.csharp import (
    CSharpResolverContext,
    build_csharp_context,
    resolve_csharp_callee,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_ctx() -> CSharpResolverContext:
    """Greeter.cs + Helper.cs + a same-named Python symbol elsewhere.

    ``Greeter.cs`` defines a local ``World`` method, a ``Run`` method and a
    ``Greeter`` class. ``Helper.cs`` defines a project-unique ``ComputeTotal``.
    A Python file also defines ``Run`` (the cross-language collision the moat
    test exercises).
    """
    greeter = "src/Greeter.cs"
    helper = "src/Helper.cs"
    py = "scripts/util.py"
    file_symbols = {
        greeter: [
            ("Greeter", "class", 1),
            ("Hello", "method", 2),
            ("Run", "method", 3),
            ("World", "method", 4),
        ],
        helper: [
            ("Helper", "class", 10),
            ("ComputeTotal", "method", 11),
        ],
        py: [("Run", "function", 99)],
    }
    global_name_table = {
        "Hello": [(greeter, 2)],
        # ``Run`` is defined in BOTH a C# file and a Python file — ambiguous
        # across languages. The C# caller must only ever see the C# one.
        "Run": [(greeter, 3), (py, 99)],
        "World": [(greeter, 4)],
        # ``ComputeTotal`` is the single project-wide (C#) definition.
        "ComputeTotal": [(helper, 11)],
        # ``OnlyPython`` lives ONLY in the Python file.
        "OnlyPython": [(py, 99)],
        "Greeter": [(greeter, 1)],
    }
    file_languages = {greeter: "csharp", helper: "csharp", py: "python"}
    ctx = build_csharp_context(
        imports_by_file={},
        file_languages=file_languages,
        file_symbols=file_symbols,
        global_name_table=global_name_table,
        file_class_methods=lambda: {},
    )
    assert ctx is not None
    return ctx


# ---------------------------------------------------------------------------
# build_csharp_context gating
# ---------------------------------------------------------------------------


class TestBuildCSharpContext:
    def test_returns_none_when_no_csharp_file(self) -> None:
        ctx = build_csharp_context(
            imports_by_file={},
            file_languages={"a.py": "python", "b.go": "go"},
            file_symbols={},
            global_name_table={},
            file_class_methods=lambda: {},
        )
        assert ctx is None

    def test_builds_when_csharp_present(self) -> None:
        ctx = build_csharp_context(
            imports_by_file={},
            file_languages={"a.cs": "csharp"},
            file_symbols={},
            global_name_table={},
            file_class_methods=lambda: {},
        )
        assert isinstance(ctx, CSharpResolverContext)

    def test_does_not_call_class_methods_thunk(self) -> None:
        calls: list[int] = []

        def thunk() -> dict[str, object]:
            calls.append(1)
            return {}

        build_csharp_context(
            imports_by_file={},
            file_languages={"a.cs": "csharp"},
            file_symbols={},
            global_name_table={},
            file_class_methods=thunk,
        )
        assert calls == []  # conservative cascade never needs the class map


# ---------------------------------------------------------------------------
# System.* fully-qualified stdlib tier
# ---------------------------------------------------------------------------


class TestSystemQualifier:
    def test_fully_qualified_system_console_is_stdlib(self) -> None:
        ctx = _build_ctx()
        sym, res, f = resolve_csharp_callee(
            "WriteLine", "System.Console.WriteLine", "src/Greeter.cs", ctx
        )
        assert (sym, res, f) == (None, "stdlib", "")

    def test_nested_system_namespace_is_stdlib(self) -> None:
        ctx = _build_ctx()
        _sym, res, _f = resolve_csharp_callee(
            "Select",
            "System.Linq.Enumerable.Select",
            "src/Greeter.cs",
            ctx,
        )
        assert res == "stdlib"

    def test_is_system_qualifier_helper(self) -> None:
        assert is_system_qualifier("System")
        assert is_system_qualifier("System.Console")
        assert is_system_qualifier("System.Linq.Enumerable")
        assert not is_system_qualifier("")
        assert not is_system_qualifier("Console")
        # A user namespace that merely starts with the letters "System" must NOT
        # match — the check is on the ``System.`` token boundary.
        assert not is_system_qualifier("Systemx")
        assert not is_system_qualifier("MySystem")
        assert not is_system_qualifier("SystemExt")


# ---------------------------------------------------------------------------
# BCL static-type qualifier tier (shadow-gated)
# ---------------------------------------------------------------------------


class TestBclStaticTypeTier:
    def test_bare_console_writeline_is_stdlib(self) -> None:
        ctx = _build_ctx()
        sym, res, f = resolve_csharp_callee(
            "WriteLine", "Console.WriteLine", "src/Greeter.cs", ctx
        )
        assert (sym, res, f) == (None, "stdlib", "")

    def test_bare_string_format_is_stdlib(self) -> None:
        ctx = _build_ctx()
        _sym, res, _f = resolve_csharp_callee(
            "Format", "String.Format", "src/Greeter.cs", ctx
        )
        assert res == "stdlib"

    def test_bare_math_max_is_stdlib(self) -> None:
        ctx = _build_ctx()
        _sym, res, _f = resolve_csharp_callee("Max", "Math.Max", "src/Greeter.cs", ctx)
        assert res == "stdlib"

    def test_project_owned_static_type_shadows_bcl(self) -> None:
        """If the project itself defines a class named ``Console`` (a same-
        language symbol), the bare ``Console.WriteLine`` claim must be
        SUPPRESSED — shadowing preserved, the call stays ``unknown``.
        """
        greeter = "src/Greeter.cs"
        mine = "src/Console.cs"
        ctx = build_csharp_context(
            imports_by_file={},
            file_languages={greeter: "csharp", mine: "csharp"},
            file_symbols={
                greeter: [("Hello", "method", 1)],
                mine: [("Console", "class", 7)],
            },
            global_name_table={"Console": [(mine, 7)]},
            file_class_methods=lambda: {},
        )
        assert ctx is not None
        _sym, res, _f = resolve_csharp_callee(
            "WriteLine", "Console.WriteLine", greeter, ctx
        )
        assert res == "unknown"

    def test_foreign_language_console_does_not_shadow_bcl(self) -> None:
        """A same-named symbol in a NON-C# file must NOT shadow the BCL claim —
        ``languages_compatible('csharp', 'python')`` is False, so a Python
        ``Console`` is not a C# owner and ``Console.WriteLine`` stays stdlib.
        """
        greeter = "src/Greeter.cs"
        py = "scripts/console.py"
        ctx = build_csharp_context(
            imports_by_file={},
            file_languages={greeter: "csharp", py: "python"},
            file_symbols={
                greeter: [("Hello", "method", 1)],
                py: [("Console", "class", 7)],
            },
            global_name_table={"Console": [(py, 7)]},
            file_class_methods=lambda: {},
        )
        assert ctx is not None
        _sym, res, _f = resolve_csharp_callee(
            "WriteLine", "Console.WriteLine", greeter, ctx
        )
        assert res == "stdlib"

    def test_non_bcl_static_type_is_unknown(self) -> None:
        ctx = _build_ctx()
        _sym, res, _f = resolve_csharp_callee(
            "Frobnicate", "MyHelper.Frobnicate", "src/Greeter.cs", ctx
        )
        assert res == "unknown"


# ---------------------------------------------------------------------------
# local + project resolution
# ---------------------------------------------------------------------------


class TestLocalAndProject:
    def test_local_bare_method(self) -> None:
        ctx = _build_ctx()
        sym, res, f = resolve_csharp_callee("Run", "Run", "src/Greeter.cs", ctx)
        assert res == "local"
        assert f == "src/Greeter.cs"
        assert sym == 3

    def test_this_qualified_member_is_local(self) -> None:
        ctx = _build_ctx()
        sym, res, f = resolve_csharp_callee(
            "World", "this.World", "src/Greeter.cs", ctx
        )
        assert res == "local"
        assert f == "src/Greeter.cs"
        assert sym == 4

    def test_single_global_project(self) -> None:
        ctx = _build_ctx()
        # ``ComputeTotal`` is defined once, in another C# file -> project.
        sym, res, f = resolve_csharp_callee(
            "ComputeTotal", "ComputeTotal", "src/Greeter.cs", ctx
        )
        assert res == "project"
        assert f == "src/Helper.cs"
        assert sym == 11

    def test_instance_receiver_is_unknown(self) -> None:
        ctx = _build_ctx()
        # ``obj.DoThing()`` — receiver is a variable, not a resolvable type.
        _sym, res, _f = resolve_csharp_callee(
            "DoThing", "obj.DoThing", "src/Greeter.cs", ctx
        )
        assert res == "unknown"

    def test_truly_unknown_name(self) -> None:
        ctx = _build_ctx()
        _sym, res, _f = resolve_csharp_callee(
            "Nonexistent", "Nonexistent", "src/Greeter.cs", ctx
        )
        assert res == "unknown"

    def test_empty_method_tiers(self) -> None:
        # The bare-method-name tiers are intentionally empty (RFC-0008).
        assert STDLIB_METHODS_CSHARP == frozenset()
        assert EXTERNAL_METHODS_CSHARP == frozenset()
        # The BCL static-type set is non-empty but conservative.
        assert "Console" in BCL_STATIC_TYPES_CSHARP
        assert "Math" in BCL_STATIC_TYPES_CSHARP


# ---------------------------------------------------------------------------
# Explicit self/base-receiver semantics (wave-1 Codex P2 lesson)
# ---------------------------------------------------------------------------


class TestSelfReceiver:
    """An explicit ``this.`` / ``base.`` receiver asserts the target is a
    member. The resolver must NOT downgrade that into binding a cross-file
    global (``project``) — only a same-file member may bind.
    """

    def test_this_call_does_not_bind_cross_file_global(self) -> None:
        # ``this.ComputeTotal`` — ``ComputeTotal`` is a single project-wide
        # global in ANOTHER file. A member call must not bind it: ``unknown``.
        ctx = _build_ctx()
        sym, res, f = resolve_csharp_callee(
            "ComputeTotal", "this.ComputeTotal", "src/Greeter.cs", ctx
        )
        assert res == "unknown"
        assert f == ""
        assert sym is None

    def test_base_call_binds_same_file_member(self) -> None:
        ctx = _build_ctx()
        sym, res, f = resolve_csharp_callee(
            "World", "base.World", "src/Greeter.cs", ctx
        )
        assert res == "local"
        assert sym == 4

    def test_ambiguous_self_member_stays_unknown(self) -> None:
        """When >1 class in the file defines the member name, a ``this.`` call
        cannot be proven to target the caller's class -> ``unknown``."""
        multi = "src/Multi.cs"
        file_symbols = {
            multi: [
                ("A", "class", 1),
                ("Dispatch", "method", 2),  # A.Dispatch
                ("Dispatch", "method", 3),  # B.Dispatch — same simple name
                ("Solo", "method", 4),  # A.Solo — single owner class
                ("B", "class", 5),
            ],
        }
        file_class_methods = {
            multi: {
                "A": {"Dispatch": 2, "Solo": 4},
                "B": {"Dispatch": 3},
            }
        }
        ctx = build_csharp_context(
            imports_by_file={},
            file_languages={multi: "csharp"},
            file_symbols=file_symbols,
            global_name_table={
                "Dispatch": [(multi, 2), (multi, 3)],
                "Solo": [(multi, 4)],
            },
            file_class_methods=lambda: file_class_methods,
        )
        assert ctx is not None
        sym, res, f = resolve_csharp_callee("Dispatch", "this.Dispatch", multi, ctx)
        assert (sym, res, f) == (None, "unknown", "")
        # The single-owner member still binds.
        sym, res, f = resolve_csharp_callee("Solo", "this.Solo", multi, ctx)
        assert res == "local"
        assert sym == 4


# ---------------------------------------------------------------------------
# THE MOAT — no cross-language mis-wire (MANDATORY)
# ---------------------------------------------------------------------------


class TestNoCrossLanguageMisWire:
    def test_ambiguous_name_resolves_to_csharp_def_not_python(self) -> None:
        """``Run`` exists in BOTH a .cs and a .py file.

        A C# caller must resolve to the SAME-FILE C# definition (local),
        never the Python file.
        """
        ctx = _build_ctx()
        sym, res, f = resolve_csharp_callee("Run", "Run", "src/Greeter.cs", ctx)
        assert f != "scripts/util.py"
        assert f == "src/Greeter.cs"
        assert res == "local"
        assert sym == 3

    def test_python_only_symbol_is_never_bound(self) -> None:
        """``OnlyPython`` exists ONLY in a Python file.

        The C# caller must NOT bind to it — the language-compat gate drops the
        sole candidate, so the result is ``unknown`` with NO resolved file.
        This is the exact CodeGraph failure this project exists to beat.
        """
        ctx = _build_ctx()
        sym, res, f = resolve_csharp_callee(
            "OnlyPython", "OnlyPython", "src/Greeter.cs", ctx
        )
        assert res == "unknown"
        assert f == ""
        assert sym is None

    def test_ambiguous_global_foreign_plus_self_stays_csharp(self) -> None:
        """``Run`` has (Greeter.cs, util.py); called from a 3rd C# file.

        From Helper.cs (no local ``Run``): the Python candidate is gated out,
        leaving exactly one same-language candidate (Greeter.cs) -> project,
        never the .py file.
        """
        ctx = _build_ctx()
        sym, res, f = resolve_csharp_callee("Run", "Run", "src/Helper.cs", ctx)
        assert f != "scripts/util.py"
        assert res == "project"
        assert f == "src/Greeter.cs"
        assert sym == 3


# ---------------------------------------------------------------------------
# Registry + dispatch integration through the public resolve_callee
# ---------------------------------------------------------------------------


class TestRegistrationAndDispatch:
    def test_csharp_is_registered(self) -> None:
        resolver = get_language_resolver("csharp")
        assert resolver is not None
        assert resolver.language == "csharp"

    def test_resolve_callee_dispatches_to_csharp(self) -> None:
        cs_ctx = _build_ctx()
        ctx = ResolverContext(
            project_root=".",
            cache=None,
            file_languages={
                "src/Greeter.cs": "csharp",
                "src/Helper.cs": "csharp",
                "scripts/util.py": "python",
            },
            lang_contexts={"csharp": cs_ctx},
        )
        # System.* qualifier through the public entry point.
        resolved = resolve_callee(
            "WriteLine",
            "src/Greeter.cs",
            ctx,
            callee_full="System.Console.WriteLine",
        )
        assert resolved.resolution == "stdlib"

        # Single-global project resolution through the public entry point.
        resolved = resolve_callee(
            "ComputeTotal",
            "src/Greeter.cs",
            ctx,
            callee_full="ComputeTotal",
        )
        assert resolved.resolution == "project"
        assert resolved.resolved_file == "src/Helper.cs"

    def test_resolve_callee_moat_through_public_api(self) -> None:
        cs_ctx = _build_ctx()
        ctx = ResolverContext(
            project_root=".",
            cache=None,
            file_languages={
                "src/Greeter.cs": "csharp",
                "scripts/util.py": "python",
            },
            lang_contexts={"csharp": cs_ctx},
        )
        resolved = resolve_callee(
            "OnlyPython", "src/Greeter.cs", ctx, callee_full="OnlyPython"
        )
        assert resolved.resolution == "unknown"
        assert resolved.resolved_file == ""


# ---------------------------------------------------------------------------
# Real-index integration — drive the FULL pipeline: write real .cs/.py files,
# index them with ASTCache, build the resolver context the way production does,
# and exercise resolve_csharp_callee against the context the index actually
# produced (NOT a fabricated map). The C# symbol walker DOES populate
# class/method rows (unlike C++), so the local tier fires end-to-end here.
# ---------------------------------------------------------------------------


def _index_and_build(tmp_path, files: dict[str, str]):
    """Write ``files`` into ``tmp_path``, index them, return (cache, cs_ctx).

    The cache is returned OPEN — the C# local tier consults the lazy
    class-methods thunk (which reads the DB), so resolution must happen before
    the connection is closed. Callers close the cache when done.
    """
    project = tmp_path / "proj"
    project.mkdir()
    for rel, body in files.items():
        (project / rel).write_text(body)
    cache = ASTCache(str(project))
    cache.index_project(max_files=100)
    resolver_ctx = build_resolver_context(cache)
    return cache, resolver_ctx.lang_context("csharp")


_REAL_CS = (
    "using System;\n"
    "namespace App {\n"
    "  public class Greeter {\n"
    "    public void Hello() {\n"
    '      Console.WriteLine("hi");\n'
    "      Helper();\n"
    "      this.World();\n"
    "    }\n"
    "    private void Helper() { }\n"
    "    public void World() { }\n"
    "  }\n"
    "}\n"
)
# A Python file defining the SAME bare name ``Helper`` — the cross-language
# collision the moat must never bind a C# caller to.
_REAL_PY = "def Helper():\n    return 2\n"


class TestRealIndexIntegration:
    def test_csharp_context_is_built_from_real_index(self, tmp_path) -> None:
        cache, cs_ctx = _index_and_build(tmp_path, {"Greeter.cs": _REAL_CS})
        try:
            assert cs_ctx is not None
            assert isinstance(cs_ctx, CSharpResolverContext)
            assert cs_ctx.file_languages.get("Greeter.cs") == "csharp"
        finally:
            cache.close()

    def test_system_qualifier_resolves_on_real_index(self, tmp_path) -> None:
        cache, cs_ctx = _index_and_build(tmp_path, {"Greeter.cs": _REAL_CS})
        try:
            sym, res, f = resolve_csharp_callee(
                "WriteLine", "Console.WriteLine", "Greeter.cs", cs_ctx
            )
            assert (sym, res, f) == (None, "stdlib", "")
        finally:
            cache.close()

    def test_local_method_resolves_on_real_index(self, tmp_path) -> None:
        """The C# walker DOES record methods, so an unqualified same-file call
        resolves ``local`` end-to-end (no xfail needed, unlike C++)."""
        cache, cs_ctx = _index_and_build(tmp_path, {"Greeter.cs": _REAL_CS})
        try:
            sym, res, f = resolve_csharp_callee(
                "Helper", "Helper", "Greeter.cs", cs_ctx
            )
            assert res == "local"
            assert f == "Greeter.cs"
        finally:
            cache.close()

    def test_moat_holds_on_real_index(self, tmp_path) -> None:
        """A C# caller's ``Helper`` call must never bind to the same-named
        Python ``Helper`` definition on a real index."""
        cache, cs_ctx = _index_and_build(
            tmp_path, {"Greeter.cs": _REAL_CS, "util.py": _REAL_PY}
        )
        try:
            _sym, _res, f = resolve_csharp_callee(
                "Helper", "Helper", "Greeter.cs", cs_ctx
            )
            assert f != "util.py"
            assert not f.endswith(".py")
        finally:
            cache.close()
