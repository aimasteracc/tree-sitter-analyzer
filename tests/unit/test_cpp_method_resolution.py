"""Unit + integration tests for the C++ resolver (RFC-0010 first wave).

Covers the conservative cascade in
``synapse_resolver/languages/cpp.py``: stdlib-qualifier classification, local
same-file resolution, single-global project resolution, the empty stdlib/
external method tiers, and — MANDATORY — the no-cross-language-mis-wire moat
(a callee whose name also exists in a non-C++ file must NOT bind to that file).
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.synapse_resolver import ResolverContext, resolve_callee
from tree_sitter_analyzer.synapse_resolver._context import build_resolver_context
from tree_sitter_analyzer.synapse_resolver._registry import get_language_resolver
from tree_sitter_analyzer.synapse_resolver.languages._cpp_constants import (
    is_stdlib_qualifier,
)
from tree_sitter_analyzer.synapse_resolver.languages.cpp import (
    CppResolverContext,
    build_cpp_context,
    resolve_cpp_callee,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_ctx() -> CppResolverContext:
    """service.cpp + helper.cpp, with a same-named Python symbol elsewhere.

    ``helper.cpp`` defines a project-unique ``compute_total``. ``service.cpp``
    defines a local ``run`` and ``parse``. A Python file also defines ``parse``
    (the cross-language collision used by the moat test).
    """
    service = "src/service.cpp"
    helper = "src/helper.cpp"
    py = "scripts/util.py"
    file_symbols = {
        service: [
            ("Service", "class", 1),
            ("run", "function", 2),
            ("parse", "function", 3),
            # A real same-file METHOD (member). An explicit-``this`` call MAY
            # bind to this member; it must NEVER bind to the free functions
            # (``run`` / ``parse``) or the class above.
            ("dispatch", "method", 4),
        ],
        helper: [
            ("Helper", "class", 10),
            ("compute_total", "function", 11),
        ],
        py: [("parse", "function", 99)],
    }
    global_name_table = {
        "run": [(service, 2)],
        # ``parse`` is defined in BOTH a C++ file and a Python file — ambiguous
        # across languages. The C++ caller must only ever see the C++ one.
        "parse": [(service, 3), (py, 99)],
        # ``compute_total`` is the single project-wide (C++) definition.
        "compute_total": [(helper, 11)],
        # ``only_python`` lives ONLY in the Python file.
        "only_python": [(py, 99)],
    }
    file_languages = {service: "cpp", helper: "cpp", py: "python"}
    return build_cpp_context(
        imports_by_file={},
        file_languages=file_languages,
        file_symbols=file_symbols,
        global_name_table=global_name_table,
        file_class_methods=lambda: {},
    )


# ---------------------------------------------------------------------------
# build_cpp_context gating
# ---------------------------------------------------------------------------


class TestBuildCppContext:
    def test_returns_none_when_no_cpp_file(self) -> None:
        ctx = build_cpp_context(
            imports_by_file={},
            file_languages={"a.py": "python", "b.go": "go"},
            file_symbols={},
            global_name_table={},
            file_class_methods=lambda: {},
        )
        assert ctx is None

    def test_builds_when_cpp_present(self) -> None:
        ctx = build_cpp_context(
            imports_by_file={},
            file_languages={"a.cpp": "cpp"},
            file_symbols={},
            global_name_table={},
            file_class_methods=lambda: {},
        )
        assert isinstance(ctx, CppResolverContext)

    def test_does_not_call_class_methods_thunk(self) -> None:
        calls: list[int] = []

        def thunk() -> dict[str, object]:
            calls.append(1)
            return {}

        build_cpp_context(
            imports_by_file={},
            file_languages={"a.cpp": "cpp"},
            file_symbols={},
            global_name_table={},
            file_class_methods=thunk,
        )
        assert calls == []  # conservative cascade never needs the class map


# ---------------------------------------------------------------------------
# stdlib-qualifier tier
# ---------------------------------------------------------------------------


class TestStdlibQualifier:
    def test_std_sort_is_stdlib(self) -> None:
        ctx = _build_ctx()
        sym, res, f = resolve_cpp_callee("sort", "std::sort", "src/service.cpp", ctx)
        assert (sym, res, f) == (None, "stdlib", "")

    def test_std_make_unique_is_stdlib(self) -> None:
        ctx = _build_ctx()
        _sym, res, _f = resolve_cpp_callee(
            "make_unique", "std::make_unique", "src/service.cpp", ctx
        )
        assert res == "stdlib"

    def test_nested_std_namespace_is_stdlib(self) -> None:
        ctx = _build_ctx()
        _sym, res, _f = resolve_cpp_callee(
            "now", "std::chrono::now", "src/service.cpp", ctx
        )
        assert res == "stdlib"

    def test_is_stdlib_qualifier_helper(self) -> None:
        assert is_stdlib_qualifier("std")
        assert is_stdlib_qualifier("std::chrono")
        assert is_stdlib_qualifier("__gnu_cxx")
        assert not is_stdlib_qualifier("")
        assert not is_stdlib_qualifier("mylib")
        # A user namespace that merely starts with the letters "std" must NOT
        # match — the prefix check is on the ``std::`` token boundary.
        assert not is_stdlib_qualifier("stdx")
        assert not is_stdlib_qualifier("mystd")


# ---------------------------------------------------------------------------
# local + project resolution
# ---------------------------------------------------------------------------


class TestLocalAndProject:
    def test_local_free_function(self) -> None:
        ctx = _build_ctx()
        sym, res, f = resolve_cpp_callee("run", "run", "src/service.cpp", ctx)
        assert res == "local"
        assert f == "src/service.cpp"
        assert sym == 2

    def test_this_qualified_member_is_local(self) -> None:
        """An explicit ``this->`` call MAY bind to a same-file MEMBER.

        ``dispatch`` is a same-file ``method``; the implicit-/explicit-this
        receiver proves the target is a member, so binding to it is correct.
        """
        ctx = _build_ctx()
        sym, res, f = resolve_cpp_callee(
            "dispatch", "this->dispatch", "src/service.cpp", ctx
        )
        assert res == "local"
        assert f == "src/service.cpp"
        assert sym == 4

    def test_implicit_this_member_is_local(self) -> None:
        """An unqualified call may also resolve to a same-file member."""
        ctx = _build_ctx()
        sym, res, f = resolve_cpp_callee("dispatch", "dispatch", "src/service.cpp", ctx)
        assert res == "local"
        assert f == "src/service.cpp"
        assert sym == 4

    def test_single_global_project(self) -> None:
        ctx = _build_ctx()
        # ``compute_total`` is defined once, in another C++ file -> project.
        sym, res, f = resolve_cpp_callee(
            "compute_total", "compute_total", "src/service.cpp", ctx
        )
        assert res == "project"
        assert f == "src/helper.cpp"
        assert sym == 11

    def test_instance_receiver_is_unknown(self) -> None:
        ctx = _build_ctx()
        # ``obj->doThing()`` — receiver is a variable, not a resolvable type.
        _sym, res, _f = resolve_cpp_callee(
            "doThing", "obj->doThing", "src/service.cpp", ctx
        )
        assert res == "unknown"

    def test_non_stdlib_qualified_is_unknown(self) -> None:
        ctx = _build_ctx()
        _sym, res, _f = resolve_cpp_callee(
            "frobnicate", "mylib::frobnicate", "src/service.cpp", ctx
        )
        assert res == "unknown"

    def test_truly_unknown_name(self) -> None:
        ctx = _build_ctx()
        _sym, res, _f = resolve_cpp_callee(
            "nonexistent", "nonexistent", "src/service.cpp", ctx
        )
        assert res == "unknown"


# ---------------------------------------------------------------------------
# Explicit self-receiver semantics (Codex PR #348 P2)
# ---------------------------------------------------------------------------


class TestExplicitSelfReceiver:
    """An explicit ``this->`` / ``self`` receiver asserts the target is a
    member (or inherited member). The conservative resolver must NOT downgrade
    that into binding a bare free function (same-file ``local`` via a
    ``function`` symbol) or a cross-file global (``project``). If it cannot
    prove a member target, it stays ``unknown`` — an unknown edge is correct;
    a free-function/global mis-bind is a moat-class failure.
    """

    def test_this_call_does_not_bind_same_file_free_function(self) -> None:
        # ``this->run`` — ``run`` is a same-file FREE FUNCTION (kind=function),
        # not a member. A ``this->`` call can never reach a free function, so
        # the resolver must stay ``unknown``, not record a false ``local``.
        ctx = _build_ctx()
        sym, res, f = resolve_cpp_callee("run", "this->run", "src/service.cpp", ctx)
        assert res == "unknown"
        assert f == ""
        assert sym is None

    def test_this_call_does_not_bind_same_file_class(self) -> None:
        # ``this->Service`` — a class symbol is not a member method either.
        ctx = _build_ctx()
        sym, res, f = resolve_cpp_callee(
            "Service", "this->Service", "src/service.cpp", ctx
        )
        assert res == "unknown"
        assert sym is None

    def test_this_call_does_not_bind_cross_file_global(self) -> None:
        # ``this->compute_total`` — ``compute_total`` is a single project-wide
        # global in ANOTHER file. A member call must not bind a cross-file
        # global, so the project (single-global) tier is skipped: ``unknown``.
        ctx = _build_ctx()
        sym, res, f = resolve_cpp_callee(
            "compute_total", "this->compute_total", "src/service.cpp", ctx
        )
        assert res == "unknown"
        assert f == ""
        assert sym is None

    def test_self_receiver_variants_do_not_bind_free_function(self) -> None:
        # The other self tokens (``self``, ``(*this)``, ``*this``) follow the
        # same rule — never bind a free function for a member call.
        ctx = _build_ctx()
        for recv in ("self", "(*this)", "*this"):
            sym, res, f = resolve_cpp_callee(
                "run", f"{recv}->run", "src/service.cpp", ctx
            )
            assert res == "unknown", recv
            assert sym is None, recv

    def test_unqualified_free_function_still_binds_local(self) -> None:
        # Regression guard: an UNQUALIFIED call (no receiver) may still bind a
        # same-file free function — only the explicit-self path is tightened.
        ctx = _build_ctx()
        sym, res, f = resolve_cpp_callee("run", "run", "src/service.cpp", ctx)
        assert res == "local"
        assert sym == 2


# ---------------------------------------------------------------------------
# Multi-class owner scoping (Codex PR #348 P2, cpp.py:210)
#
# When ONE .cpp file declares more than one class and both define a method of
# the same name, a self-receiver / implicit-this member call cannot be proven
# to target the caller's own class (the resolver is not handed the caller's
# enclosing class). Binding it to "whichever class happens to be in the file"
# is a false ``local`` edge — exactly the no-miswire breach Codex flagged. The
# conservative rule: a member call binds a same-file ``method`` ONLY when that
# method name is owned by EXACTLY ONE class in the file; otherwise ``unknown``.
# ---------------------------------------------------------------------------


def _build_multiclass_ctx() -> CppResolverContext:
    """One .cpp file with TWO classes that each define ``dispatch``.

    ``A::dispatch`` (id 2) and ``B::dispatch`` (id 3) collide by simple name.
    ``A::solo`` (id 4) is owned by exactly one class. The ``file_class_methods``
    map carries the owner-class breakdown the resolver needs to detect the
    ambiguity; ``file_symbols`` (name, kind, id) alone cannot.
    """
    multi = "src/multi.cpp"
    file_symbols = {
        multi: [
            ("A", "class", 1),
            ("dispatch", "method", 2),  # A::dispatch
            ("dispatch", "method", 3),  # B::dispatch — same simple name
            ("solo", "method", 4),  # A::solo — single owner class
            ("B", "class", 5),
            ("free_fn", "function", 6),  # file-scoped free function
        ],
    }
    global_name_table = {
        "dispatch": [(multi, 2), (multi, 3)],
        "solo": [(multi, 4)],
        "free_fn": [(multi, 6)],
    }
    file_languages = {multi: "cpp"}
    file_class_methods = {
        multi: {
            "A": {"dispatch": 2, "solo": 4},
            "B": {"dispatch": 3},
        }
    }
    return build_cpp_context(
        imports_by_file={},
        file_languages=file_languages,
        file_symbols=file_symbols,
        global_name_table=global_name_table,
        file_class_methods=lambda: file_class_methods,
    )


class TestMultiClassOwnerScoping:
    def test_self_call_to_ambiguous_member_stays_unknown(self) -> None:
        # ``this->dispatch`` — ``dispatch`` is a method in BOTH A and B in this
        # file. The resolver cannot prove the caller's class, so binding either
        # one is a false ``local``. It must stay ``unknown``.
        ctx = _build_multiclass_ctx()
        sym, res, f = resolve_cpp_callee(
            "dispatch", "this->dispatch", "src/multi.cpp", ctx
        )
        assert res == "unknown"
        assert f == ""
        assert sym is None

    def test_implicit_this_call_to_ambiguous_member_stays_unknown(self) -> None:
        # The same ambiguity applies to an unqualified (implicit-this) call to a
        # member owned by >1 class: it cannot bind a single ``method``.
        ctx = _build_multiclass_ctx()
        sym, res, f = resolve_cpp_callee("dispatch", "dispatch", "src/multi.cpp", ctx)
        assert res == "unknown"
        assert sym is None

    def test_self_call_to_single_owner_member_still_binds(self) -> None:
        # ``this->solo`` — ``solo`` is owned by exactly one class (A), so the
        # member call is unambiguous and binds ``local`` to that method.
        ctx = _build_multiclass_ctx()
        sym, res, f = resolve_cpp_callee("solo", "this->solo", "src/multi.cpp", ctx)
        assert res == "local"
        assert f == "src/multi.cpp"
        assert sym == 4

    def test_unqualified_free_function_unaffected_by_method_ambiguity(self) -> None:
        # A FREE function is file-scoped (no owning class), so the multi-class
        # method ambiguity must not suppress it: an unqualified call still binds.
        ctx = _build_multiclass_ctx()
        sym, res, f = resolve_cpp_callee("free_fn", "free_fn", "src/multi.cpp", ctx)
        assert res == "local"
        assert sym == 6


# ---------------------------------------------------------------------------
# THE MOAT — no cross-language mis-wire (MANDATORY)
# ---------------------------------------------------------------------------


class TestNoCrossLanguageMisWire:
    def test_ambiguous_name_resolves_to_cpp_def_not_python(self) -> None:
        """``parse`` exists in BOTH a .cpp and a .py file.

        A C++ caller must resolve to the SAME-FILE C++ definition (local),
        never the Python file. After removing the Python candidate the C++ one
        is the single same-language global, but here it is also same-file, so
        the local tier wins. Either way the resolved file must be C++.
        """
        ctx = _build_ctx()
        sym, res, f = resolve_cpp_callee("parse", "parse", "src/service.cpp", ctx)
        assert f != "scripts/util.py"
        assert f == "src/service.cpp"
        assert res == "local"
        assert sym == 3

    def test_python_only_symbol_is_never_bound(self) -> None:
        """``only_python`` exists ONLY in a Python file.

        The C++ caller must NOT bind to it — the language-compat gate drops the
        sole candidate, so the result is ``unknown`` with NO resolved file.
        This is the exact CodeGraph failure this project exists to beat.
        """
        ctx = _build_ctx()
        sym, res, f = resolve_cpp_callee(
            "only_python", "only_python", "src/service.cpp", ctx
        )
        assert res == "unknown"
        assert f == ""
        assert sym is None

    def test_ambiguous_global_only_foreign_plus_self_stays_cpp(self) -> None:
        """A name with one C++ and one Python global, called from a 3rd C++ file.

        ``parse`` has (service.cpp, py). Called from helper.cpp (no local
        ``parse``): the Python candidate is gated out, leaving exactly one
        same-language candidate (service.cpp) -> project, never the .py file.
        """
        ctx = _build_ctx()
        sym, res, f = resolve_cpp_callee("parse", "parse", "src/helper.cpp", ctx)
        assert f != "scripts/util.py"
        assert res == "project"
        assert f == "src/service.cpp"
        assert sym == 3


# ---------------------------------------------------------------------------
# C-header directional compat (cpp -> c is legitimate, the one cross-tag case)
# ---------------------------------------------------------------------------


class TestCHeaderCompat:
    def test_cpp_resolves_c_header_symbol(self) -> None:
        """A C++ caller MAY resolve a symbol defined in a C-tagged header."""
        cpp_file = "src/main.cpp"
        c_header = "include/api.h"
        ctx = build_cpp_context(
            imports_by_file={},
            file_languages={cpp_file: "cpp", c_header: "c"},
            file_symbols={
                cpp_file: [("main", "function", 1)],
                c_header: [("c_api_init", "function", 5)],
            },
            global_name_table={"c_api_init": [(c_header, 5)]},
            file_class_methods=lambda: {},
        )
        assert ctx is not None
        sym, res, f = resolve_cpp_callee("c_api_init", "c_api_init", cpp_file, ctx)
        assert res == "project"
        assert f == c_header
        assert sym == 5


# ---------------------------------------------------------------------------
# Registry + dispatch integration through the public resolve_callee
# ---------------------------------------------------------------------------


class TestRegistrationAndDispatch:
    def test_cpp_is_registered(self) -> None:
        resolver = get_language_resolver("cpp")
        assert resolver is not None
        assert resolver.language == "cpp"

    def test_resolve_callee_dispatches_to_cpp(self) -> None:
        cpp_ctx = _build_ctx()
        ctx = ResolverContext(
            project_root=".",
            cache=None,
            file_languages={
                "src/service.cpp": "cpp",
                "src/helper.cpp": "cpp",
                "scripts/util.py": "python",
            },
            lang_contexts={"cpp": cpp_ctx},
        )
        # stdlib qualifier through the public entry point.
        resolved = resolve_callee(
            "sort", "src/service.cpp", ctx, callee_full="std::sort"
        )
        assert resolved.resolution == "stdlib"

        # Single-global project resolution through the public entry point.
        resolved = resolve_callee(
            "compute_total",
            "src/service.cpp",
            ctx,
            callee_full="compute_total",
        )
        assert resolved.resolution == "project"
        assert resolved.resolved_file == "src/helper.cpp"

    def test_resolve_callee_moat_through_public_api(self) -> None:
        cpp_ctx = _build_ctx()
        ctx = ResolverContext(
            project_root=".",
            cache=None,
            file_languages={
                "src/service.cpp": "cpp",
                "scripts/util.py": "python",
            },
            lang_contexts={"cpp": cpp_ctx},
        )
        resolved = resolve_callee(
            "only_python", "src/service.cpp", ctx, callee_full="only_python"
        )
        assert resolved.resolution == "unknown"
        assert resolved.resolved_file == ""


# ---------------------------------------------------------------------------
# Real-index integration (Codex PR #348 P2) — drive the FULL pipeline:
# write real .cpp/.py files, index them with ASTCache, build the resolver
# context the way production does, and exercise resolve_cpp_callee against the
# context the index actually produced (NOT a fabricated map).
#
# Why this matters: the unit suites above feed hand-built maps. Codex flagged
# that the production maps come from ``ast_symbol_rows`` via the generic
# ``_ast_extraction._walk_for_symbols`` walker, whose ``child_by_field_name
# ('name')`` gate misses tree-sitter C++ functions/methods (their identifier
# lives under ``function_declarator``), so the local/single-global tiers could
# silently never fire in production while the unit tests stayed green. These
# integration tests assert the behaviour on a REAL parsed index:
#   * the maps-INDEPENDENT stdlib-qualifier tier works end-to-end, and
#   * THE MOAT holds on a real index — a same-named foreign-language symbol is
#     never bound, regardless of how many C++ symbols the walker recovered.
# A separate xfail nails the current local-tier production gap as an explicit
# regression target for the extractor fix (root cause lives in the shared
# walker, out of this resolver's scope).
# ---------------------------------------------------------------------------


def _index_and_build(tmp_path, files: dict[str, str]):
    """Write ``files`` into ``tmp_path``, index them, return (root, cpp_ctx)."""
    project = tmp_path / "proj"
    project.mkdir()
    for rel, body in files.items():
        (project / rel).write_text(body)
    cache = ASTCache(str(project))
    try:
        cache.index_project(max_files=100)
        resolver_ctx = build_resolver_context(cache)
    finally:
        cache.close()
    return project, resolver_ctx.lang_context("cpp")


_REAL_CPP = (
    "#include <algorithm>\n"
    "int helper() { return 1; }\n"
    "struct Calc {\n"
    "    int run() {\n"
    "        std::sort(nullptr, nullptr);\n"
    "        return this->helper();\n"
    "    }\n"
    "};\n"
)
# A Python file defining the SAME bare name ``helper`` — the cross-language
# collision the moat must never bind a C++ caller to.
_REAL_PY = "def helper():\n    return 2\n"


class TestRealIndexIntegration:
    def test_cpp_context_is_built_from_real_index(self, tmp_path) -> None:
        """A parsed ``.cpp`` file yields a non-None C++ resolver context."""
        _root, cpp_ctx = _index_and_build(tmp_path, {"service.cpp": _REAL_CPP})
        assert cpp_ctx is not None
        assert isinstance(cpp_ctx, CppResolverContext)
        # The language map MUST tag the indexed file as cpp — this is what gates
        # every project binding (the moat). If it were absent the moat could not
        # discriminate languages.
        assert cpp_ctx.file_languages.get("service.cpp") == "cpp"

    def test_stdlib_qualifier_resolves_on_real_index(self, tmp_path) -> None:
        """``std::sort`` -> ``stdlib`` end-to-end (maps-independent tier).

        This tier reads only the call's qualifier, so it works regardless of
        whether the symbol walker recovered any C++ definitions — proving the
        resolver does real, correct work on a production index.
        """
        _root, cpp_ctx = _index_and_build(tmp_path, {"service.cpp": _REAL_CPP})
        sym, res, f = resolve_cpp_callee("sort", "std::sort", "service.cpp", cpp_ctx)
        assert (sym, res, f) == (None, "stdlib", "")

    def test_moat_holds_on_real_index(self, tmp_path) -> None:
        """THE MOAT on a REAL index: a C++ caller's ``helper`` call must never
        bind to the same-named Python ``helper`` definition.

        Whatever the walker recovered for C++, the language-compat gate must
        keep the Python file out: the result is the C++ same-language def or
        ``unknown`` — NEVER ``util.py``. This is the CodeGraph failure we beat.
        """
        _root, cpp_ctx = _index_and_build(
            tmp_path, {"service.cpp": _REAL_CPP, "util.py": _REAL_PY}
        )
        _sym, _res, f = resolve_cpp_callee("helper", "helper", "service.cpp", cpp_ctx)
        assert f != "util.py"
        assert not f.endswith(".py")

    def test_this_member_call_never_mis_binds_on_real_index(self, tmp_path) -> None:
        """``this->helper`` on a real index resolves to a C++ member or stays
        ``unknown`` — it must never bind a free function or a foreign file."""
        _root, cpp_ctx = _index_and_build(
            tmp_path, {"service.cpp": _REAL_CPP, "util.py": _REAL_PY}
        )
        sym, res, f = resolve_cpp_callee(
            "helper", "this->helper", "service.cpp", cpp_ctx
        )
        # Conservative: a same-file member ('method') is the only valid bind;
        # anything else stays unknown. Either way, never a .py file.
        assert not f.endswith(".py")
        if res == "local":
            # If bound, it must be a same-file member, never the free function.
            assert f == "service.cpp"
        else:
            assert (sym, res, f) == (None, "unknown", "")

    @pytest.mark.xfail(
        reason=(
            "Known production gap: the shared generic symbol walker "
            "(_ast_extraction._walk_for_symbols) gates on "
            "child_by_field_name('name'), which tree-sitter C++ "
            "function_definition nodes do not expose (the identifier lives "
            "under function_declarator), so ordinary C++ free functions are "
            "absent from ast_symbol_rows and the local/single-global tiers "
            "cannot fire. Root cause lives in the shared extractor, out of "
            "this resolver's scope; this xfail is the regression target so the "
            "tier flips to PASS once the walker recovers C++ symbols."
        ),
        strict=True,
    )
    def test_local_free_function_resolves_on_real_index(self, tmp_path) -> None:
        """When the extractor populates C++ symbols, an unqualified call to a
        same-file free function (``helper``) must resolve ``local``."""
        _root, cpp_ctx = _index_and_build(tmp_path, {"service.cpp": _REAL_CPP})
        _sym, res, f = resolve_cpp_callee("helper", "helper", "service.cpp", cpp_ctx)
        assert res == "local"
        assert f == "service.cpp"
