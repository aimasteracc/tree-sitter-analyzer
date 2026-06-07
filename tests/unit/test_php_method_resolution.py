"""RFC-0010 second wave: the PHP per-language callee resolver.

PHP calls come in several syntactic shapes the resolver must classify
correctly without ever guessing:

* bare / same-file       — ``helper()`` resolves to a same-file ``function``.
* namespaced free call   — ``\\App\\helper()`` / ``App\\helper()`` resolve on the
  last segment as a same-file free function (the ``\\`` split is a namespace,
  not a class/instance receiver).
* global built-in        — ``strlen()`` / ``array_map()`` / ``json_encode()``
  classify as ``builtin`` ONLY when the project does not itself define a free
  function of that name (shadowing preserved).
* self method call       — ``$this->m()`` / ``self::m()`` / ``static::m()`` /
  ``parent::m()`` bind ``local`` ONLY when exactly ONE class in the caller file
  defines ``m`` (the enclosing class is not carried by the edge → ambiguous
  across classes stays ``unknown``).
* receiver call          — ``Foo::bar()`` (static) / ``$obj->bar()`` (instance)
  / ``App\\Util::run()`` carry a class type the edge does not record; the
  resolver must NEVER guess a same-name method elsewhere → ``unknown``.

The mandatory moat assertion: a callee whose bare name also exists as a symbol
in ANOTHER language's file must NEVER bind to that file — PHP only ever resolves
``local`` against its own (same-language) caller file, and the built-in shadow
gate is language-aware so a same-named Python symbol never suppresses (nor is
bound by) the PHP classification.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.synapse_resolver import ResolvedCallee, resolve_callee
from tree_sitter_analyzer.synapse_resolver import languages as _languages
from tree_sitter_analyzer.synapse_resolver._context import ResolverContext
from tree_sitter_analyzer.synapse_resolver._registry import (
    get_language_resolver,
    registered_languages,
)
from tree_sitter_analyzer.synapse_resolver.languages.php import (
    PhpResolverContext,
    build_php_context,
    resolve_php_callee,
)


# ---------------------------------------------------------------------------
# Registration / discovery
# ---------------------------------------------------------------------------
def test_php_is_registered_via_discovery() -> None:
    """Dropping ``languages/php.py`` auto-registers the PHP resolver — no edit
    to any shared file."""
    assert "php" in registered_languages()
    assert get_language_resolver("php") is not None
    assert "php" in {
        m.name
        for m in __import__("pkgutil").iter_modules(_languages.__path__)
        if not m.name.startswith("_")
    }


# ---------------------------------------------------------------------------
# build_php_context gating (zero cost when no PHP file is indexed)
# ---------------------------------------------------------------------------
def test_build_context_returns_none_without_php_files() -> None:
    ctx = build_php_context(
        imports_by_file={},
        file_languages={"a.py": "python"},
        file_symbols={},
        global_name_table={},
        file_class_methods=lambda: {},
    )
    assert ctx is None


def test_build_context_built_when_php_file_present() -> None:
    ctx = build_php_context(
        imports_by_file={},
        file_languages={"app.php": "php"},
        file_symbols={"app.php": [("helper", "function", 7)]},
        global_name_table={"helper": [("app.php", 7)]},
        file_class_methods=lambda: {},
    )
    assert isinstance(ctx, PhpResolverContext)
    assert "app.php" in ctx.file_symbols


def test_build_context_does_not_force_thunk_for_non_php() -> None:
    """The lazy class-method thunk must NOT be forced when no PHP file exists."""
    forced = {"hit": False}

    def _thunk() -> dict:
        forced["hit"] = True
        return {}

    ctx = build_php_context(
        imports_by_file={},
        file_languages={"a.py": "python"},
        file_symbols={},
        global_name_table={},
        file_class_methods=_thunk,
    )
    assert ctx is None
    assert forced["hit"] is False


# ---------------------------------------------------------------------------
# Direct resolver unit tests
# ---------------------------------------------------------------------------
def _ctx(
    symbols: dict[str, list[tuple[str, str, int]]],
    *,
    class_methods: dict[str, dict[str, dict[str, int]]] | None = None,
    global_table: dict[str, list[tuple[str, int]]] | None = None,
    languages: dict[str, str] | None = None,
) -> PhpResolverContext:
    """Build a PHP context for unit tests.

    ``global_table`` defaults to one derived from ``symbols`` so the built-in
    shadow gate sees the project's own free functions; ``languages`` defaults to
    tagging every file ``php``.
    """
    if global_table is None:
        global_table = {}
        for fp, syms in symbols.items():
            for name, _kind, sym_id in syms:
                global_table.setdefault(name, []).append((fp, sym_id))
    if languages is None:
        languages = dict.fromkeys(symbols, "php")
    built = build_php_context(
        imports_by_file={},
        file_languages=languages,
        file_symbols=symbols,
        global_name_table=global_table,
        file_class_methods=lambda: class_methods or {},
    )
    assert built is not None
    return built


def test_same_file_free_function_resolves_local() -> None:
    ctx = _ctx({"app.php": [("helper", "function", 7), ("main", "function", 11)]})
    sym_id, resolution, resolved = resolve_php_callee(
        "helper", "helper", "app.php", ctx
    )
    assert (sym_id, resolution, resolved) == (7, "local", "app.php")


def test_namespaced_free_call_resolves_local_on_last_segment() -> None:
    """``\\App\\helper`` (namespace ``\\`` split) resolves to a same-file free
    function ``helper`` — a namespace prefix is not a class/instance receiver."""
    ctx = _ctx({"app.php": [("helper", "function", 7)]})
    sym_id, resolution, resolved = resolve_php_callee(
        "helper", "\\App\\helper", "app.php", ctx
    )
    assert (sym_id, resolution, resolved) == (7, "local", "app.php")


def test_relative_namespaced_free_call_resolves_local() -> None:
    ctx = _ctx({"app.php": [("helper", "function", 7)]})
    sym_id, resolution, resolved = resolve_php_callee(
        "helper", "App\\helper", "app.php", ctx
    )
    assert (sym_id, resolution, resolved) == (7, "local", "app.php")


def test_builtin_bare_function_classifies_builtin() -> None:
    ctx = _ctx({"app.php": [("main", "function", 11)]})
    sym_id, resolution, resolved = resolve_php_callee(
        "strlen", "strlen", "app.php", ctx
    )
    assert (sym_id, resolution, resolved) == (None, "builtin", "")


def test_builtin_array_map_classifies_builtin() -> None:
    ctx = _ctx({"app.php": [("main", "function", 11)]})
    _sym, resolution, _file = resolve_php_callee(
        "array_map", "array_map", "app.php", ctx
    )
    assert resolution == "builtin"


def test_builtin_json_encode_classifies_builtin() -> None:
    ctx = _ctx({"app.php": [("main", "function", 11)]})
    _sym, resolution, _file = resolve_php_callee(
        "json_encode", "json_encode", "app.php", ctx
    )
    assert resolution == "builtin"


def test_project_free_function_shadows_builtin() -> None:
    """A project free function named like a built-in (``count``) shadows it —
    the same-file ``local`` resolution wins, never ``builtin`` (precision)."""
    ctx = _ctx({"app.php": [("count", "function", 3), ("main", "function", 11)]})
    sym_id, resolution, resolved = resolve_php_callee("count", "count", "app.php", ctx)
    assert (sym_id, resolution, resolved) == (3, "local", "app.php")


def test_project_owns_builtin_name_in_other_php_file_suppresses_builtin() -> None:
    """A project free function named ``count`` in ANOTHER php file shadows the
    built-in for a caller that does not define it locally — stays ``unknown``
    rather than ``builtin`` (the project owns the name)."""
    ctx = _ctx(
        {
            "caller.php": [("main", "function", 11)],
            "lib.php": [("count", "function", 3)],
        }
    )
    sym_id, resolution, resolved = resolve_php_callee(
        "count", "count", "caller.php", ctx
    )
    assert (sym_id, resolution, resolved) == (None, "unknown", "")


def test_this_method_call_unique_class_resolves_local() -> None:
    """``$this->process`` binds to the single class defining ``process``."""
    ctx = _ctx(
        {"app.php": [("process", "method", 9)]},
        class_methods={"app.php": {"Service": {"process": 9, "run": 5}}},
    )
    sym_id, resolution, resolved = resolve_php_callee(
        "process", "$this->process", "app.php", ctx
    )
    assert (sym_id, resolution, resolved) == (9, "local", "app.php")


def test_self_static_call_unique_class_resolves_local() -> None:
    ctx = _ctx(
        {"app.php": [("make", "method", 4)]},
        class_methods={"app.php": {"Factory": {"make": 4}}},
    )
    sym_id, resolution, resolved = resolve_php_callee(
        "make", "self::make", "app.php", ctx
    )
    assert (sym_id, resolution, resolved) == (4, "local", "app.php")


def test_this_method_call_ambiguous_across_classes_stays_unknown() -> None:
    """Two classes in one file both define ``save`` — the caller's enclosing
    class is not carried by the edge, so ``$this->save`` is ambiguous and must
    stay ``unknown`` (never the file-wide first match)."""
    ctx = _ctx(
        {"app.php": [("save", "method", 5)]},
        class_methods={
            "app.php": {"A": {"save": 5}, "B": {"save": 9}},
        },
    )
    sym_id, resolution, resolved = resolve_php_callee(
        "save", "$this->save", "app.php", ctx
    )
    assert (sym_id, resolution, resolved) == (None, "unknown", "")


def test_parent_call_resolves_unique_class_method() -> None:
    ctx = _ctx(
        {"app.php": [("boot", "method", 7)]},
        class_methods={"app.php": {"Base": {"boot": 7}}},
    )
    _sym, resolution, _file = resolve_php_callee("boot", "parent::boot", "app.php", ctx)
    assert resolution == "local"


def test_static_receiver_call_stays_unknown() -> None:
    """``Foo::bar`` — ``Foo`` is a class whose definition the edge does not
    resolve to a type here; the resolver must NOT guess a same-name ``bar``."""
    ctx = _ctx(
        {"app.php": [("bar", "method", 5)]},
        class_methods={"app.php": {"Other": {"bar": 5}}},
    )
    sym_id, resolution, resolved = resolve_php_callee("bar", "Foo::bar", "app.php", ctx)
    assert (sym_id, resolution, resolved) == (None, "unknown", "")


def test_namespaced_static_receiver_call_stays_unknown() -> None:
    """``App\\Util::run`` is a static RECEIVER call (last separator ``::``), NOT
    a namespaced free function — it must stay ``unknown`` even though the
    receiver text contains a ``\\`` namespace."""
    ctx = _ctx(
        {"app.php": [("run", "function", 5)]},
    )
    sym_id, resolution, resolved = resolve_php_callee(
        "run", "App\\Util::run", "app.php", ctx
    )
    assert (sym_id, resolution, resolved) == (None, "unknown", "")


def test_instance_receiver_call_stays_unknown() -> None:
    """``$obj->bar`` — receiver is a variable whose class type the edge does not
    carry. Never guess a same-name method elsewhere."""
    ctx = _ctx(
        {"app.php": [("bar", "method", 5)]},
        class_methods={"app.php": {"Other": {"bar": 5}}},
    )
    sym_id, resolution, resolved = resolve_php_callee(
        "bar", "$obj->bar", "app.php", ctx
    )
    assert (sym_id, resolution, resolved) == (None, "unknown", "")


def test_bare_name_not_in_file_and_not_builtin_stays_unknown() -> None:
    ctx = _ctx({"app.php": [("main", "function", 11)]})
    sym_id, resolution, resolved = resolve_php_callee(
        "missing", "missing", "app.php", ctx
    )
    assert (sym_id, resolution, resolved) == (None, "unknown", "")


def test_bare_call_does_not_bind_sibling_method() -> None:
    """A bare ``render()`` must NOT bind to a same-file class ``method`` named
    ``render`` (a method needs a receiver) — only a top-level ``function``."""
    ctx = _ctx({"app.php": [("render", "method", 5)]})
    sym_id, resolution, resolved = resolve_php_callee(
        "render", "render", "app.php", ctx
    )
    assert (sym_id, resolution, resolved) == (None, "unknown", "")


def test_external_tier_is_empty() -> None:
    """The PHP external tier is intentionally empty (RFC-0008 precision)."""
    from tree_sitter_analyzer.synapse_resolver.languages._php_constants import (
        EXTERNAL_FUNCTIONS_PHP,
    )

    assert EXTERNAL_FUNCTIONS_PHP == frozenset()


# ---------------------------------------------------------------------------
# Integration through the registry dispatch (resolve_callee)
# ---------------------------------------------------------------------------
def test_resolve_callee_routes_php_to_php_resolver() -> None:
    php_ctx = _ctx({"app.php": [("helper", "function", 7)]})
    ctx = ResolverContext(
        project_root=".",
        cache=None,
        file_languages={"app.php": "php"},
        lang_contexts={"php": php_ctx},
    )
    res = resolve_callee("helper", "app.php", ctx, "helper")
    assert isinstance(res, ResolvedCallee)
    assert (res.callee_symbol_id, res.resolution, res.resolved_file) == (
        7,
        "local",
        "app.php",
    )


def test_resolve_callee_php_builtin_through_registry() -> None:
    php_ctx = _ctx({"app.php": [("main", "function", 11)]})
    ctx = ResolverContext(
        project_root=".",
        cache=None,
        file_languages={"app.php": "php"},
        lang_contexts={"php": php_ctx},
    )
    res = resolve_callee("strlen", "app.php", ctx, "strlen")
    assert res.resolution == "builtin"


# ---------------------------------------------------------------------------
# THE MOAT — no cross-language mis-wire (MANDATORY)
# ---------------------------------------------------------------------------
def test_no_cross_language_mis_wire_direct() -> None:
    """A PHP caller's bare ``helper`` must NEVER resolve to a Python file that
    happens to define ``helper``. The PHP resolver only consults its own caller
    file (same-language by construction)."""
    ctx = build_php_context(
        imports_by_file={},
        file_languages={"app.php": "php", "util.py": "python"},
        # Python file defines `helper`; the PHP caller file does NOT.
        file_symbols={"util.py": [("helper", "function", 3)]},
        global_name_table={"helper": [("util.py", 3)]},
        file_class_methods=lambda: {},
    )
    assert ctx is not None
    sym_id, resolution, resolved = resolve_php_callee(
        "helper", "helper", "app.php", ctx
    )
    # MUST NOT bind to util.py — stays unknown.
    assert (sym_id, resolution, resolved) == (None, "unknown", "")
    assert resolved != "util.py"


def test_no_cross_language_builtin_name_not_suppressed_by_python() -> None:
    """A Python symbol named ``count`` must NOT suppress PHP's ``count`` built-in
    classification (the shadow gate is language-aware). PHP has no interop family
    with Python, so a Python ``count`` is not a PHP owner."""
    ctx = build_php_context(
        imports_by_file={},
        file_languages={"app.php": "php", "util.py": "python"},
        file_symbols={"util.py": [("count", "function", 3)]},
        global_name_table={"count": [("util.py", 3)]},
        file_class_methods=lambda: {},
    )
    assert ctx is not None
    sym_id, resolution, resolved = resolve_php_callee("count", "count", "app.php", ctx)
    # The Python `count` is NOT a PHP owner → builtin classification stands,
    # and the resolver NEVER binds to util.py.
    assert (sym_id, resolution, resolved) == (None, "builtin", "")
    assert resolved != "util.py"


def test_no_cross_language_mis_wire_end_to_end(tmp_path: Path) -> None:
    """Index a polyglot repo where ``helper`` exists as a Python def AND as a
    PHP free function in separate files. Build the real resolver context from
    the index and assert the PHP caller's bare ``helper`` resolves to the PHP
    file's own symbol id (same-language) — NEVER the Python file. This proves
    the moat holds through the production context builder, not just a hand-built
    context."""
    (tmp_path / "py").mkdir()
    (tmp_path / "py" / "helpers.py").write_text("def helper(s):\n    return len(s)\n")
    (tmp_path / "app.php").write_text(
        "<?php\n"
        "namespace App;\n\n"
        "function helper($s) {\n"
        "    return strlen($s);\n"
        "}\n\n"
        "function main() {\n"
        "    return helper('hi');\n"
        "}\n"
    )
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project()
        from tree_sitter_analyzer.synapse_resolver._context import (
            build_resolver_context,
        )

        rctx = build_resolver_context(cache)
    finally:
        cache.close()

    # The PHP file's own `helper` symbol id (looked up from the index).
    db = str(tmp_path / ".ast-cache" / "index.db")
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        php_helper = conn.execute(
            "SELECT id FROM ast_symbol_rows "
            "WHERE name = 'helper' AND file_path = 'app.php'"
        ).fetchone()
        py_helper = conn.execute(
            "SELECT id FROM ast_symbol_rows "
            "WHERE name = 'helper' AND file_path = 'py/helpers.py'"
        ).fetchone()
    finally:
        conn.close()
    assert php_helper is not None and py_helper is not None

    res = resolve_callee("helper", "app.php", rctx, "helper")
    # Same-language bind only: the PHP caller resolves to app.php's helper,
    # NEVER the Python file's helper.
    assert res.resolved_file != "py/helpers.py"
    assert res.callee_symbol_id != py_helper["id"]
    assert (res.callee_symbol_id, res.resolution, res.resolved_file) == (
        php_helper["id"],
        "local",
        "app.php",
    )
