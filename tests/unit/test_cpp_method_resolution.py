"""Unit + integration tests for the C++ resolver (RFC-0010 first wave).

Covers the conservative cascade in
``synapse_resolver/languages/cpp.py``: stdlib-qualifier classification, local
same-file resolution, single-global project resolution, the empty stdlib/
external method tiers, and — MANDATORY — the no-cross-language-mis-wire moat
(a callee whose name also exists in a non-C++ file must NOT bind to that file).
"""

from __future__ import annotations

from tree_sitter_analyzer.synapse_resolver import ResolverContext, resolve_callee
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

    def test_this_qualified_is_local(self) -> None:
        ctx = _build_ctx()
        _sym, res, f = resolve_cpp_callee("run", "this->run", "src/service.cpp", ctx)
        assert res == "local"
        assert f == "src/service.cpp"

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
