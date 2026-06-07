"""RFC-0010 first-wave RED-first: the TypeScript per-language resolver.

The TypeScript resolver REPLACES the Python cascade for ``.ts``/``.tsx`` callers
(``file_languages == "typescript"``). It must:

* resolve SAME-FILE/SAME-LANGUAGE local calls (no receiver or ``this``/``super``)
  from its context's ``file_symbols`` — never regressing the local edges the
  Python fallback used to produce;
* classify a call whose receiver head is a DISTINCTIVE JS/TS global object
  (``console``/``JSON``/``Math``/``Object``/``Promise``/…) as ``builtin`` — but
  ONLY when the project defines no compatible-language (TS/JS) symbol of that
  global name (shadowing preserved);
* keep CONSERVATIVE bare-method-name tiers (the RFC-0008 lesson: an over-broad
  table mis-classifies domain methods) — generic names like ``substring`` /
  ``push`` / ``map`` stay ``unknown``;
* return ``unknown`` for everything else.

THE MOAT (mandatory): a callee whose name also exists as a symbol in ANOTHER
language's file must NEVER bind to that other-language file — it resolves to the
same-language definition or stays ``unknown``. ``languages_compatible`` treats
JS/TS as one family but Python as incompatible.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.synapse_resolver.languages.typescript import (
    build_typescript_resolver_context,
    resolve_typescript_callee,
)


# ---------------------------------------------------------------------------
# integration helpers (index real files, read classified edges back)
# ---------------------------------------------------------------------------
def _index(tmp_path: Path, files: dict[str, str]) -> str:
    for name, body in files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project()
    finally:
        cache.close()
    return str(tmp_path / ".ast-cache" / "index.db")


def _resolution_for(db_path: str, callee_name: str) -> list[str]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT callee_resolution FROM edges "
            "WHERE kind = 'calls' AND callee_name = ?",
            (callee_name,),
        ).fetchall()
        return [r["callee_resolution"] for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# unit: direct resolver calls against a hand-built context
# ---------------------------------------------------------------------------
def _ctx(
    *,
    file_symbols: dict[str, list[tuple[str, str, int]]] | None = None,
    file_languages: dict[str, str] | None = None,
    global_name_table: dict[str, list[tuple[str, int]]] | None = None,
    file_class_methods: dict[str, dict[str, dict[str, int]]] | None = None,
    imports_by_file: dict[str, list] | None = None,
):
    return build_typescript_resolver_context(
        imports_by_file=imports_by_file or {},
        file_languages=file_languages or {"a.ts": "typescript"},
        file_symbols=file_symbols or {},
        global_name_table=global_name_table or {},
        file_class_methods=lambda: file_class_methods or {},
    )


def test_build_context_none_when_no_typescript_file() -> None:
    """Zero cost for non-TS projects: gated on ``file_languages``."""
    ctx = build_typescript_resolver_context(
        imports_by_file={},
        file_languages={"a.py": "python"},
        file_symbols={},
        global_name_table={},
        file_class_methods=lambda: {},
    )
    assert ctx is None


def test_build_context_present_for_tsx() -> None:
    """A ``.tsx`` file (tagged ``typescript``) builds a context."""
    ctx = build_typescript_resolver_context(
        imports_by_file={},
        file_languages={"a.tsx": "typescript"},
        file_symbols={},
        global_name_table={},
        file_class_methods=lambda: {},
    )
    assert ctx is not None


def test_local_no_receiver_resolves_same_file() -> None:
    ctx = _ctx(file_symbols={"a.ts": [("helper", "function", 7)]})
    sym_id, resolution, resolved_file = resolve_typescript_callee(
        "helper", "helper", "a.ts", ctx
    )
    assert (sym_id, resolution, resolved_file) == (7, "local", "a.ts")


def test_local_this_receiver_resolves_class_method() -> None:
    ctx = _ctx(
        file_symbols={"a.ts": []},
        file_class_methods={"a.ts": {"Service": {"run": 11}}},
    )
    sym_id, resolution, resolved_file = resolve_typescript_callee(
        "run", "this.run", "a.ts", ctx
    )
    assert (sym_id, resolution, resolved_file) == (11, "local", "a.ts")


def test_global_object_receiver_classifies_builtin() -> None:
    ctx = _ctx()
    _sym, resolution, _file = resolve_typescript_callee(
        "log", "console.log", "a.ts", ctx
    )
    assert resolution == "builtin"


def test_json_receiver_classifies_builtin() -> None:
    ctx = _ctx()
    _sym, resolution, _file = resolve_typescript_callee(
        "stringify", "JSON.stringify", "a.ts", ctx
    )
    assert resolution == "builtin"


def test_bare_generic_method_stays_unknown() -> None:
    """``s.substring(2)`` — ``substring`` is a domain-collidable bare method name
    with a non-distinctive receiver; conservative tier keeps it ``unknown``."""
    ctx = _ctx()
    _sym, resolution, _file = resolve_typescript_callee(
        "substring", "s.substring", "a.ts", ctx
    )
    assert resolution == "unknown"


def test_project_shadows_builtin_global_name() -> None:
    """If the project defines a TS symbol named ``Math`` (a distinctive global),
    ``Math.random()`` must NOT be claimed ``builtin`` (shadowing preserved)."""
    ctx = _ctx(
        file_languages={"a.ts": "typescript", "math.ts": "typescript"},
        global_name_table={"Math": [("math.ts", 99)]},
    )
    _sym, resolution, _file = resolve_typescript_callee(
        "random", "Math.random", "a.ts", ctx
    )
    assert resolution != "builtin"


def test_no_cross_language_bind_for_global_object_owner() -> None:
    """THE MOAT: a Python file owning a symbol named ``console`` must NOT
    suppress the TS ``builtin`` classification (Python is incompatible), and must
    NEVER be bound as the resolved file."""
    ctx = _ctx(
        file_languages={"a.ts": "typescript", "py_console.py": "python"},
        global_name_table={"console": [("py_console.py", 3)]},
    )
    _sym, resolution, resolved_file = resolve_typescript_callee(
        "log", "console.log", "a.ts", ctx
    )
    assert resolution == "builtin"
    assert resolved_file != "py_console.py"


# ---------------------------------------------------------------------------
# Codex P2 (PR #347): this/super must resolve within the CALLER's class, never
# bleed across class boundaries in the same file.
# ---------------------------------------------------------------------------
def test_this_receiver_does_not_bind_other_class_method() -> None:
    """``class A { foo(){} } class B { bar(){ this.foo(); } foo(){} }``.

    Two classes in one file each define ``foo``. A ``this.foo()`` in ``B`` is
    ambiguous from the resolver's seat (no enclosing-class signal is passed), so
    binding it to *either* class's ``foo`` would risk the wrong edge
    (``B.bar -> A.foo``). Conservative: stay ``unknown`` rather than mis-wire.
    """
    ctx = _ctx(
        file_symbols={"a.ts": []},
        file_class_methods={"a.ts": {"A": {"foo": 1}, "B": {"foo": 2, "bar": 3}}},
    )
    sym_id, resolution, resolved_file = resolve_typescript_callee(
        "foo", "this.foo", "a.ts", ctx
    )
    assert resolution == "unknown", (
        f"ambiguous this.foo across two classes must stay unknown; got {resolution}"
    )
    assert sym_id is None
    assert resolved_file == ""


def test_this_receiver_does_not_fall_back_to_free_function() -> None:
    """``this.foo()`` must NOT bind a top-level free function ``foo`` — a
    method call on the instance is not the same symbol as a module function.
    The file-wide symbol scan (which would grab the free function) must not run
    for a ``this``/``super`` receiver."""
    ctx = _ctx(file_symbols={"a.ts": [("foo", "function", 5)]})
    sym_id, resolution, _file = resolve_typescript_callee(
        "foo", "this.foo", "a.ts", ctx
    )
    assert resolution == "unknown", (
        f"this.foo must not bind a free function foo; got {resolution}"
    )
    assert sym_id is None


def test_this_receiver_single_class_still_resolves() -> None:
    """When exactly ONE class in the file defines the method, ``this.foo()`` is
    unambiguous and still resolves ``local`` (no regression of the happy path)."""
    ctx = _ctx(
        file_symbols={"a.ts": []},
        file_class_methods={"a.ts": {"Service": {"run": 11}}},
    )
    sym_id, resolution, resolved_file = resolve_typescript_callee(
        "run", "this.run", "a.ts", ctx
    )
    assert (sym_id, resolution, resolved_file) == (11, "local", "a.ts")


# ---------------------------------------------------------------------------
# Codex P2 (PR #347): honor variable/import shadowing for TS globals.
# ---------------------------------------------------------------------------
def test_import_shadows_builtin_global_name() -> None:
    """``import { Map } from './map'; Map.of(...)`` — the imported local name
    ``Map`` shadows the JS built-in global, so the call must NOT classify
    ``builtin``. The shadowing gate consults import local-names, not only the
    function/method/class ``global_name_table``."""
    from tree_sitter_analyzer.synapse_resolver._imports import ImportEntry

    ctx = _ctx(
        imports_by_file={
            "a.ts": [
                ImportEntry(
                    file_path="a.ts",
                    language="typescript",
                    module_path="./map",
                    local_name="Map",
                )
            ]
        },
    )
    _sym, resolution, _file = resolve_typescript_callee("of", "Map.of", "a.ts", ctx)
    assert resolution != "builtin", (
        f"imported Map shadows the global; must not be builtin; got {resolution}"
    )


def test_aliased_import_shadows_builtin_global_name() -> None:
    """``import Promise from 'bluebird'`` bound under local name ``Promise``
    shadows the global ``Promise``; ``Promise.all(...)`` stays non-builtin."""
    from tree_sitter_analyzer.synapse_resolver._imports import ImportEntry

    ctx = _ctx(
        imports_by_file={
            "a.ts": [
                ImportEntry(
                    file_path="a.ts",
                    language="typescript",
                    module_path="bluebird",
                    local_name="Promise",
                )
            ]
        },
    )
    _sym, resolution, _file = resolve_typescript_callee(
        "all", "Promise.all", "a.ts", ctx
    )
    assert resolution != "builtin"


def test_import_in_other_file_does_not_shadow() -> None:
    """An import of ``Map`` in a DIFFERENT file must not suppress the ``builtin``
    classification in ``a.ts`` (shadowing is per-file/file-local)."""
    from tree_sitter_analyzer.synapse_resolver._imports import ImportEntry

    ctx = _ctx(
        file_languages={"a.ts": "typescript", "b.ts": "typescript"},
        imports_by_file={
            "b.ts": [
                ImportEntry(
                    file_path="b.ts",
                    language="typescript",
                    module_path="./map",
                    local_name="Map",
                )
            ]
        },
    )
    _sym, resolution, _file = resolve_typescript_callee("of", "Map.of", "a.ts", ctx)
    assert resolution == "builtin", (
        f"an import in b.ts must not shadow a.ts's Map; got {resolution}"
    )


# ---------------------------------------------------------------------------
# integration: through the full index + resolve_callee pipeline
# ---------------------------------------------------------------------------
def test_integration_local_call_resolves(tmp_path: Path) -> None:
    db = _index(
        tmp_path,
        {
            "svc.ts": (
                "function helper(x: number): number { return x + 1; }\n"
                "class Service {\n"
                "  run(): number { return helper(1); }\n"
                "}\n"
            )
        },
    )
    res = _resolution_for(db, "helper")
    assert res, "expected a helper() edge"
    assert "local" in res, f"local TS call must resolve local; got {res}"


def test_integration_console_log_classifies_builtin(tmp_path: Path) -> None:
    db = _index(
        tmp_path,
        {"svc.ts": ("class Service {\n  run(): void { console.log('hi'); }\n}\n")},
    )
    res = _resolution_for(db, "log")
    assert res, "expected a log() edge"
    assert "builtin" in res, f"console.log must classify builtin; got {res}"
    assert "unknown" not in res


def test_integration_bare_method_stays_unknown(tmp_path: Path) -> None:
    db = _index(
        tmp_path,
        {
            "svc.ts": (
                "class Service {\n  run(s: string): void { s.substring(2); }\n}\n"
            )
        },
    )
    res = _resolution_for(db, "substring")
    assert res, "expected a substring() edge"
    assert "builtin" not in res
    assert "stdlib" not in res
    assert "unknown" in res, (
        f"bare s.substring (domain-collidable) must stay unknown; got {res}"
    )


def test_integration_no_cross_language_mis_wire(tmp_path: Path) -> None:
    """MANDATORY no-cross-language-mis-wire test.

    A TS ``helper()`` call and a Python ``def helper`` coexist. The TS caller's
    ``helper`` must resolve to the TypeScript ``svc.ts`` definition (``local``),
    NEVER to the Python ``other.py`` file — the exact CodeGraph failure this
    project exists to beat.
    """
    db = _index(
        tmp_path,
        {
            "svc.ts": (
                "function helper(x: number): number { return x + 1; }\n"
                "class Service {\n"
                "  run(): number { return helper(1); }\n"
                "}\n"
            ),
            "other.py": "def helper():\n    return 1\n",
        },
    )
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT callee_resolution, callee_resolved_file FROM edges "
            "WHERE kind = 'calls' AND callee_name = 'helper' "
            "AND file_path = 'svc.ts'",
        ).fetchall()
    finally:
        conn.close()
    assert rows, "expected a TS helper() edge from svc.ts"
    for r in rows:
        assert r["callee_resolved_file"] != "other.py", (
            "TS helper() must NEVER bind to the Python other.py definition "
            "(cross-language mis-wire — the CodeGraph failure)"
        )
        assert r["callee_resolution"] in ("local", "project", "unknown")
