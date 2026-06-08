"""Unit + integration tests for the C resolver (RFC-0010 second wave).

Covers the conservative cascade in
``synapse_resolver/languages/c.py``: local same-file resolution, single-global
project resolution, the conservative libc free-function tier (shadowed by
project ownership), and — MANDATORY — the no-cross-language-mis-wire moat
(a callee whose name also exists in a non-C file must NOT bind to that file).

C is simpler than C++: there are no namespaces (no ``std::`` qualifier), no
member methods to disambiguate by class. A C call is either an unqualified free
function, a struct field access (``->`` / ``.`` on a value — never a resolvable
free function), or a libc free function. The moat is also DIRECTIONAL: a C
caller must NEVER bind to a C++ definition (``languages_compatible('c', 'cpp')``
is False), while a C caller MAY resolve another C file / C-tagged ``.h`` header.
"""

from __future__ import annotations

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.synapse_resolver import ResolverContext, resolve_callee
from tree_sitter_analyzer.synapse_resolver._context import build_resolver_context
from tree_sitter_analyzer.synapse_resolver._registry import get_language_resolver
from tree_sitter_analyzer.synapse_resolver.languages._c_constants import (
    LIBC_FUNCTIONS_C,
    is_libc_function,
)
from tree_sitter_analyzer.synapse_resolver.languages.c import (
    CResolverContext,
    build_c_context,
    resolve_c_callee,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_ctx() -> CResolverContext:
    """service.c + helper.c, with a same-named Python symbol elsewhere.

    ``helper.c`` defines a project-unique ``compute_total``. ``service.c``
    defines a local ``run`` and ``parse``. A Python file also defines ``parse``
    (the cross-language collision used by the moat test). ``malloc`` is a libc
    function NOT owned by the project.
    """
    service = "src/service.c"
    helper = "src/helper.c"
    py = "scripts/util.py"
    file_symbols = {
        service: [
            ("run", "function", 2),
            ("parse", "function", 3),
        ],
        helper: [
            ("compute_total", "function", 11),
        ],
        py: [("parse", "function", 99)],
    }
    global_name_table = {
        "run": [(service, 2)],
        # ``parse`` is defined in BOTH a C file and a Python file — ambiguous
        # across languages. The C caller must only ever see the C one.
        "parse": [(service, 3), (py, 99)],
        # ``compute_total`` is the single project-wide (C) definition.
        "compute_total": [(helper, 11)],
        # ``only_python`` lives ONLY in the Python file.
        "only_python": [(py, 99)],
    }
    file_languages = {service: "c", helper: "c", py: "python"}
    return build_c_context(
        imports_by_file={},
        file_languages=file_languages,
        file_symbols=file_symbols,
        global_name_table=global_name_table,
        file_class_methods=lambda: {},
    )


# ---------------------------------------------------------------------------
# build_c_context gating
# ---------------------------------------------------------------------------


class TestBuildCContext:
    def test_returns_none_when_no_c_file(self) -> None:
        ctx = build_c_context(
            imports_by_file={},
            file_languages={"a.py": "python", "b.go": "go"},
            file_symbols={},
            global_name_table={},
            file_class_methods=lambda: {},
        )
        assert ctx is None

    def test_builds_when_c_present(self) -> None:
        ctx = build_c_context(
            imports_by_file={},
            file_languages={"a.c": "c"},
            file_symbols={},
            global_name_table={},
            file_class_methods=lambda: {},
        )
        assert isinstance(ctx, CResolverContext)

    def test_cpp_only_project_does_not_build_c_context(self) -> None:
        # A pure-C++ project must NOT spin up a C context: the C resolver only
        # drives callers whose own file is tagged ``c``.
        ctx = build_c_context(
            imports_by_file={},
            file_languages={"a.cpp": "cpp"},
            file_symbols={},
            global_name_table={},
            file_class_methods=lambda: {},
        )
        assert ctx is None


# ---------------------------------------------------------------------------
# libc free-function tier
# ---------------------------------------------------------------------------


class TestLibcTier:
    def test_malloc_is_stdlib(self) -> None:
        ctx = _build_ctx()
        sym, res, f = resolve_c_callee("malloc", "malloc", "src/service.c", ctx)
        assert (sym, res, f) == (None, "stdlib", "")

    def test_printf_is_stdlib(self) -> None:
        ctx = _build_ctx()
        _sym, res, _f = resolve_c_callee("printf", "printf", "src/service.c", ctx)
        assert res == "stdlib"

    def test_memcpy_is_stdlib(self) -> None:
        ctx = _build_ctx()
        _sym, res, _f = resolve_c_callee("memcpy", "memcpy", "src/service.c", ctx)
        assert res == "stdlib"

    def test_project_shadows_libc_name(self) -> None:
        """If the project defines a function whose name collides with a libc
        name, the project owns it — libc classification is suppressed.

        ``compute_total`` is not libc, but to prove shadowing we add a project
        function named ``malloc`` and confirm it no longer classifies stdlib.
        """
        service = "src/service.c"
        ctx = build_c_context(
            imports_by_file={},
            file_languages={service: "c"},
            file_symbols={service: [("malloc", "function", 7)]},
            global_name_table={"malloc": [(service, 7)]},
            file_class_methods=lambda: {},
        )
        # Same-file local wins first; the libc tier never even runs here.
        sym, res, f = resolve_c_callee("malloc", "malloc", service, ctx)
        assert res == "local"
        assert sym == 7

    def test_project_shadows_libc_from_other_file(self) -> None:
        """A project ``malloc`` in ANOTHER C file shadows the libc tier too.

        Called from a third C file with no local ``malloc``: the single-global
        project tier binds the project definition, NOT libc.
        """
        a = "src/a.c"
        b = "src/b.c"
        ctx = build_c_context(
            imports_by_file={},
            file_languages={a: "c", b: "c"},
            file_symbols={a: [("malloc", "function", 7)], b: []},
            global_name_table={"malloc": [(a, 7)]},
            file_class_methods=lambda: {},
        )
        sym, res, f = resolve_c_callee("malloc", "malloc", b, ctx)
        assert res == "project"
        assert f == a
        assert sym == 7

    def test_is_libc_function_helper(self) -> None:
        assert is_libc_function("malloc")
        assert is_libc_function("printf")
        assert is_libc_function("memcpy")
        assert not is_libc_function("")
        assert not is_libc_function("my_custom_fn")
        # Conservatively pruned names that collide with user code must NOT be
        # in the libc set (precision over recall).
        assert not is_libc_function("free")
        assert not is_libc_function("open")
        assert not is_libc_function("read")
        assert not is_libc_function("write")
        assert not is_libc_function("close")
        assert not is_libc_function("find")
        assert not is_libc_function("sort")

    def test_libc_set_is_nonempty_and_lowercase(self) -> None:
        # The set is deliberately small but must carry the high-confidence core.
        assert LIBC_FUNCTIONS_C
        assert "malloc" in LIBC_FUNCTIONS_C
        assert "strlen" in LIBC_FUNCTIONS_C


# ---------------------------------------------------------------------------
# local + project resolution
# ---------------------------------------------------------------------------


class TestLocalAndProject:
    def test_local_free_function(self) -> None:
        ctx = _build_ctx()
        sym, res, f = resolve_c_callee("run", "run", "src/service.c", ctx)
        assert res == "local"
        assert f == "src/service.c"
        assert sym == 2

    def test_single_global_project(self) -> None:
        ctx = _build_ctx()
        # ``compute_total`` is defined once, in another C file -> project.
        sym, res, f = resolve_c_callee(
            "compute_total", "compute_total", "src/service.c", ctx
        )
        assert res == "project"
        assert f == "src/helper.c"
        assert sym == 11

    def test_struct_field_receiver_is_unknown(self) -> None:
        ctx = _build_ctx()
        # ``obj->do_thing()`` — receiver is a struct value / function pointer
        # field, not a resolvable free function. Conservative: unknown.
        _sym, res, _f = resolve_c_callee(
            "do_thing", "obj->do_thing", "src/service.c", ctx
        )
        assert res == "unknown"

    def test_dot_receiver_is_unknown(self) -> None:
        ctx = _build_ctx()
        _sym, res, _f = resolve_c_callee(
            "do_thing", "obj.do_thing", "src/service.c", ctx
        )
        assert res == "unknown"

    def test_truly_unknown_name(self) -> None:
        ctx = _build_ctx()
        _sym, res, _f = resolve_c_callee(
            "nonexistent", "nonexistent", "src/service.c", ctx
        )
        assert res == "unknown"


# ---------------------------------------------------------------------------
# THE MOAT — no cross-language mis-wire (MANDATORY)
# ---------------------------------------------------------------------------


class TestNoCrossLanguageMisWire:
    def test_ambiguous_name_resolves_to_c_def_not_python(self) -> None:
        """``parse`` exists in BOTH a .c and a .py file.

        A C caller must resolve to the SAME-FILE C definition (local), never
        the Python file. Either way the resolved file must be C.
        """
        ctx = _build_ctx()
        sym, res, f = resolve_c_callee("parse", "parse", "src/service.c", ctx)
        assert f != "scripts/util.py"
        assert f == "src/service.c"
        assert res == "local"
        assert sym == 3

    def test_python_only_symbol_is_never_bound(self) -> None:
        """``only_python`` exists ONLY in a Python file.

        The C caller must NOT bind to it — the language-compat gate drops the
        sole candidate, so the result is ``unknown`` with NO resolved file.
        This is the exact CodeGraph failure this project exists to beat.
        """
        ctx = _build_ctx()
        sym, res, f = resolve_c_callee(
            "only_python", "only_python", "src/service.c", ctx
        )
        assert res == "unknown"
        assert f == ""
        assert sym is None

    def test_ambiguous_global_foreign_plus_self_stays_c(self) -> None:
        """A name with one C and one Python global, called from a 3rd C file.

        ``parse`` has (service.c, py). Called from helper.c (no local
        ``parse``): the Python candidate is gated out, leaving exactly one
        same-language candidate (service.c) -> project, never the .py file.
        """
        ctx = _build_ctx()
        sym, res, f = resolve_c_callee("parse", "parse", "src/helper.c", ctx)
        assert f != "scripts/util.py"
        assert res == "project"
        assert f == "src/service.c"
        assert sym == 3

    def test_c_caller_never_binds_cpp_definition(self) -> None:
        """DIRECTIONAL MOAT: a C caller must NEVER bind a C++ definition.

        ``languages_compatible('c', 'cpp')`` is False (pure-C → C++ is a
        foreign binding). ``cpp_only`` lives only in a .cpp file, so a C caller
        must leave it ``unknown`` — even though it is the sole global candidate.
        """
        c_file = "src/main.c"
        cpp_file = "src/widget.cpp"
        ctx = build_c_context(
            imports_by_file={},
            file_languages={c_file: "c", cpp_file: "cpp"},
            file_symbols={
                c_file: [("main", "function", 1)],
                cpp_file: [("cpp_only", "function", 50)],
            },
            global_name_table={"cpp_only": [(cpp_file, 50)]},
            file_class_methods=lambda: {},
        )
        sym, res, f = resolve_c_callee("cpp_only", "cpp_only", c_file, ctx)
        assert res == "unknown"
        assert f == ""
        assert sym is None
        assert not f.endswith(".cpp")


# ---------------------------------------------------------------------------
# C-header same-tag compat (C resolves its own .h headers, indexed as ``c``)
# ---------------------------------------------------------------------------


class TestCHeaderCompat:
    def test_c_resolves_c_header_symbol(self) -> None:
        """A C caller MAY resolve a symbol declared in a C-tagged header.

        ``.h`` files are indexed as ``c``, so this is a same-tag binding — not
        a cross-language one. (The directional gate only blocks c -> cpp.)
        """
        c_file = "src/main.c"
        c_header = "include/api.h"
        ctx = build_c_context(
            imports_by_file={},
            file_languages={c_file: "c", c_header: "c"},
            file_symbols={
                c_file: [("main", "function", 1)],
                c_header: [("c_api_init", "function", 5)],
            },
            global_name_table={"c_api_init": [(c_header, 5)]},
            file_class_methods=lambda: {},
        )
        assert ctx is not None
        sym, res, f = resolve_c_callee("c_api_init", "c_api_init", c_file, ctx)
        assert res == "project"
        assert f == c_header
        assert sym == 5


# ---------------------------------------------------------------------------
# Registry + dispatch integration through the public resolve_callee
# ---------------------------------------------------------------------------


class TestRegistrationAndDispatch:
    def test_c_is_registered(self) -> None:
        resolver = get_language_resolver("c")
        assert resolver is not None
        assert resolver.language == "c"

    def test_resolve_callee_dispatches_to_c(self) -> None:
        c_ctx = _build_ctx()
        ctx = ResolverContext(
            project_root=".",
            cache=None,
            file_languages={
                "src/service.c": "c",
                "src/helper.c": "c",
                "scripts/util.py": "python",
            },
            lang_contexts={"c": c_ctx},
        )
        # libc tier through the public entry point.
        resolved = resolve_callee("malloc", "src/service.c", ctx, callee_full="malloc")
        assert resolved.resolution == "stdlib"

        # Single-global project resolution through the public entry point.
        resolved = resolve_callee(
            "compute_total",
            "src/service.c",
            ctx,
            callee_full="compute_total",
        )
        assert resolved.resolution == "project"
        assert resolved.resolved_file == "src/helper.c"

    def test_resolve_callee_moat_through_public_api(self) -> None:
        c_ctx = _build_ctx()
        ctx = ResolverContext(
            project_root=".",
            cache=None,
            file_languages={
                "src/service.c": "c",
                "scripts/util.py": "python",
            },
            lang_contexts={"c": c_ctx},
        )
        resolved = resolve_callee(
            "only_python", "src/service.c", ctx, callee_full="only_python"
        )
        assert resolved.resolution == "unknown"
        assert resolved.resolved_file == ""


# ---------------------------------------------------------------------------
# Real-index integration — drive the FULL pipeline: write real .c/.py files,
# index them with ASTCache, build the resolver context the way production does,
# and exercise resolve_c_callee against the context the index actually produced.
#
# As with the C++ resolver, the production symbol maps come from the generic
# ``_ast_extraction._walk_for_symbols`` walker; tree-sitter C function
# definitions expose their identifier under ``function_declarator`` rather than
# a direct ``name`` field, so ordinary C free functions may be absent from
# ``ast_symbol_rows``. The maps-INDEPENDENT libc tier and THE MOAT hold
# regardless and are asserted here; the local-tier production gap is captured by
# a strict xfail that flips to PASS once the shared walker recovers C symbols.
# ---------------------------------------------------------------------------


def _index_and_build(tmp_path, files: dict[str, str]):
    """Write ``files`` into ``tmp_path``, index them, return (root, c_ctx)."""
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
    return project, resolver_ctx.lang_context("c")


_REAL_C = (
    "#include <stdlib.h>\n"
    "#include <string.h>\n"
    "int helper(void) { return 1; }\n"
    "int run(void) {\n"
    "    void *p = malloc(8);\n"
    "    return helper();\n"
    "}\n"
)
# A Python file defining the SAME bare name ``helper`` — the cross-language
# collision the moat must never bind a C caller to.
_REAL_PY = "def helper():\n    return 2\n"

# A freestanding / embedded C project that defines its OWN ``malloc`` (a custom
# allocator — common in firmware, kernels, and allocator libraries). A call to
# ``malloc`` here MUST NOT be classified ``stdlib``: the project owns it. This is
# the Codex P2 (PR #353) regression target.
_REAL_C_CUSTOM_MALLOC = (
    "void *malloc(unsigned long n) { return (void *)0; }\n"
    "void use(void) {\n"
    "    void *p = malloc(16);\n"
    "    (void)p;\n"
    "}\n"
)
# A Python file ALSO defining ``malloc`` — a foreign-language same-name symbol
# that the C resolver's ownership gate must NOT count (the moat): a Python
# ``malloc`` must neither shadow the libc tier nor get bound.
_REAL_PY_MALLOC = "def malloc(n):\n    return None\n"


class TestRealIndexIntegration:
    def test_c_context_is_built_from_real_index(self, tmp_path) -> None:
        """A parsed ``.c`` file yields a non-None C resolver context."""
        _root, c_ctx = _index_and_build(tmp_path, {"service.c": _REAL_C})
        assert c_ctx is not None
        assert isinstance(c_ctx, CResolverContext)
        # The language map MUST tag the indexed file as c — this is what gates
        # every project binding (the moat).
        assert c_ctx.file_languages.get("service.c") == "c"

    def test_libc_tier_resolves_on_real_index(self, tmp_path) -> None:
        """``malloc`` -> ``stdlib`` end-to-end (maps-independent tier).

        This tier reads only the bare name and the project-ownership gate, so it
        works regardless of whether the symbol walker recovered any C
        definitions — proving the resolver does real, correct work on a
        production index. (No project ``malloc`` here, so it is not shadowed.)
        """
        _root, c_ctx = _index_and_build(tmp_path, {"service.c": _REAL_C})
        sym, res, f = resolve_c_callee("malloc", "malloc", "service.c", c_ctx)
        assert (sym, res, f) == (None, "stdlib", "")

    def test_moat_holds_on_real_index(self, tmp_path) -> None:
        """THE MOAT on a REAL index: a C caller's ``helper`` call must never
        bind to the same-named Python ``helper`` definition."""
        _root, c_ctx = _index_and_build(
            tmp_path, {"service.c": _REAL_C, "util.py": _REAL_PY}
        )
        _sym, _res, f = resolve_c_callee("helper", "helper", "service.c", c_ctx)
        assert f != "util.py"
        assert not f.endswith(".py")

    def test_project_defined_malloc_is_not_stdlib_on_real_index(self, tmp_path) -> None:
        """Codex P2 (PR #353): a C project that DEFINES its own ``malloc`` must
        NOT have a ``malloc()`` call classified ``stdlib``.

        The libc tier may only fire when the project owns no compatible-language
        function of that name. Here the project owns ``malloc`` (a C
        ``function_definition``), so the call must resolve to the project
        definition (``local``/``project``) — never ``stdlib``.
        """
        _root, c_ctx = _index_and_build(
            tmp_path, {"alloc.c": _REAL_C_CUSTOM_MALLOC}
        )
        sym, res, f = resolve_c_callee("malloc", "malloc", "alloc.c", c_ctx)
        assert res != "stdlib", (
            "project-defined malloc must shadow the libc tier, got stdlib"
        )
        # It is the project's own C definition (same file => local).
        assert res in {"local", "project"}
        assert sym is not None
        assert f == "alloc.c"

    def test_foreign_malloc_does_not_shadow_libc_on_real_index(self, tmp_path) -> None:
        """THE MOAT under the custom-libc fix: a Python ``malloc`` must NOT count
        as a C owner. With only a foreign (Python) ``malloc`` present, the C
        ``malloc()`` call still classifies ``stdlib`` and is NEVER bound to the
        Python definition."""
        _root, c_ctx = _index_and_build(
            tmp_path,
            {"service.c": _REAL_C, "util.py": _REAL_PY_MALLOC},
        )
        sym, res, f = resolve_c_callee("malloc", "malloc", "service.c", c_ctx)
        assert (sym, res, f) == (None, "stdlib", "")

    def test_local_free_function_resolves_on_real_index(self, tmp_path) -> None:
        """An unqualified call to a same-file C free function (``helper``) must
        resolve ``local`` on a real index.

        This was previously a ``strict`` xfail: the shared generic symbol walker
        (``_ast_extraction._walk_for_symbols``) gated on
        ``child_by_field_name('name')``, which tree-sitter C
        ``function_definition`` nodes do not expose (the identifier lives under
        ``function_declarator``), so C free functions never reached
        ``ast_symbol_rows``. The walker now recovers C function names via
        ``_c_function_def_name``, so the local / single-global tiers fire and
        this is a hard PASS.
        """
        _root, c_ctx = _index_and_build(tmp_path, {"service.c": _REAL_C})
        _sym, res, f = resolve_c_callee("helper", "helper", "service.c", c_ctx)
        assert res == "local"
        assert f == "service.c"
