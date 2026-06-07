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
    shadow_locals: dict[str, set[str]] | None = None,
):
    return build_typescript_resolver_context(
        imports_by_file={},
        file_languages=file_languages or {"a.ts": "typescript"},
        file_symbols=file_symbols or {},
        global_name_table=global_name_table or {},
        file_class_methods=lambda: file_class_methods or {},
        shadow_locals=shadow_locals,
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
# Codex P2 #1 — this/super must resolve within the caller's class, never bind
# to an unrelated class's same-named method elsewhere in the file.
# ---------------------------------------------------------------------------
def test_this_method_ambiguous_across_classes_stays_unknown() -> None:
    """``class A { foo(){} } class B { bar(){ this.foo(); } foo(){} }``.

    Without the caller's enclosing class, ``this.foo()`` is ambiguous between
    ``A.foo`` and ``B.foo``. The resolver must NOT bind ``B.bar -> A.foo`` (the
    file-wide first-match bug); it stays ``unknown`` (conservative: precision
    over recall)."""
    ctx = _ctx(
        # file_symbols carries A.foo FIRST — the broken file-wide lookup would
        # return it for B's ``this.foo()``.
        file_symbols={"a.ts": [("foo", "method", 5), ("foo", "method", 8)]},
        file_class_methods={"a.ts": {"A": {"foo": 5}, "B": {"foo": 8, "bar": 7}}},
    )
    sym_id, resolution, resolved_file = resolve_typescript_callee(
        "foo", "this.foo", "a.ts", ctx
    )
    assert (sym_id, resolution, resolved_file) == (None, "unknown", "")


def test_this_method_unambiguous_resolves_local() -> None:
    """When exactly one class in the file defines the method, ``this.foo()``
    resolves ``local`` (single owner — no ambiguity)."""
    ctx = _ctx(
        file_symbols={"a.ts": []},
        file_class_methods={"a.ts": {"Service": {"run": 11}}},
    )
    sym_id, resolution, resolved_file = resolve_typescript_callee(
        "run", "this.run", "a.ts", ctx
    )
    assert (sym_id, resolution, resolved_file) == (11, "local", "a.ts")


def test_this_method_never_falls_through_to_top_level_function() -> None:
    """``this.helper()`` must NOT bind to a top-level ``function helper`` — a
    method call through ``this`` is class-scoped, not module-scoped."""
    ctx = _ctx(
        file_symbols={"a.ts": [("helper", "function", 3)]},
        file_class_methods={"a.ts": {}},
    )
    sym_id, resolution, resolved_file = resolve_typescript_callee(
        "helper", "this.helper", "a.ts", ctx
    )
    assert (sym_id, resolution, resolved_file) == (None, "unknown", "")


# ---------------------------------------------------------------------------
# Codex P2 #2/#3 — variable/import shadowing of a builtin global name must
# suppress the builtin classification (gate also honors non-function locals).
# ---------------------------------------------------------------------------
def test_variable_shadow_suppresses_builtin() -> None:
    """``const Promise = require('bluebird'); Promise.all(...)`` — ``Promise`` is
    shadowed by a local variable, so the call must NOT classify ``builtin``."""
    ctx = _ctx(shadow_locals={"a.ts": {"Promise"}})
    _sym, resolution, _file = resolve_typescript_callee(
        "all", "Promise.all", "a.ts", ctx
    )
    assert resolution != "builtin"


def test_import_shadow_suppresses_builtin() -> None:
    """``import { Map } from './map'; Map.of(...)`` — ``Map`` is shadowed by an
    import binding, so the call must NOT classify ``builtin``."""
    ctx = _ctx(shadow_locals={"a.ts": {"Map"}})
    _sym, resolution, _file = resolve_typescript_callee("of", "Map.of", "a.ts", ctx)
    assert resolution != "builtin"


def test_shadow_local_is_file_scoped() -> None:
    """A shadow in ``other.ts`` must NOT suppress the builtin in ``a.ts``."""
    ctx = _ctx(shadow_locals={"other.ts": {"Math"}})
    _sym, resolution, _file = resolve_typescript_callee(
        "random", "Math.random", "a.ts", ctx
    )
    assert resolution == "builtin"


def test_integration_import_shadow_suppresses_builtin(tmp_path: Path) -> None:
    """FULL INDEX PATH (Codex P2 #3): ``import { Map } from './map'`` shadows the
    ``Map`` global. ``Map.of()`` must NOT be classified ``builtin`` even though
    ``ast_imports`` is empty for TS — the resolver builds the shadow set from the
    TS symbol rows itself."""
    db = _index(
        tmp_path,
        {
            "svc.ts": (
                "import { Map } from './map';\n"
                "class Service {\n"
                "  run(): void { Map.of(1); }\n"
                "}\n"
            ),
            "map.ts": "export class Map { static of(x: number): void {} }\n",
        },
    )
    res = _resolution_for(db, "of")
    assert res, "expected a Map.of() edge"
    assert "builtin" not in res, (
        f"import-shadowed Map.of must NOT classify builtin; got {res}"
    )


def test_integration_import_shadow_no_project_symbol_suppresses_builtin(
    tmp_path: Path,
) -> None:
    """FULL INDEX PATH (Codex P2 #4): ``import { Map } from 'immutable'`` with NO
    project class named ``Map``. The TS plugin stores the import's raw statement
    under the ``text`` field (not ``name``/``source``), so the shadow set must be
    built from ``text``. Without that, ``Map.of()`` is wrongly ``builtin`` because
    the ``global_name_table`` path can't save it either (no project ``Map``)."""
    db = _index(
        tmp_path,
        {
            "svc.ts": (
                "import { Map } from 'immutable';\n"
                "class Service {\n"
                "  run(): void { Map.of(1); }\n"
                "}\n"
            ),
        },
    )
    res = _resolution_for(db, "of")
    assert res, "expected a Map.of() edge"
    assert "builtin" not in res, (
        f"import-shadowed Map.of (no project symbol) must NOT classify builtin; "
        f"got {res}"
    )


def test_integration_default_import_shadow_suppresses_builtin(tmp_path: Path) -> None:
    """FULL INDEX PATH (Codex P2 #4): a default import ``import Promise from
    'bluebird'`` (statement stored under ``text``) shadows the ``Promise`` global;
    ``Promise.all()`` must NOT classify ``builtin``."""
    db = _index(
        tmp_path,
        {
            "svc.ts": (
                "import Promise from 'bluebird';\n"
                "class Service {\n"
                "  run(): void { Promise.all([]); }\n"
                "}\n"
            ),
        },
    )
    res = _resolution_for(db, "all")
    assert res, "expected a Promise.all() edge"
    assert "builtin" not in res, (
        f"default-import-shadowed Promise.all must NOT classify builtin; got {res}"
    )


def test_integration_variable_shadow_suppresses_builtin(tmp_path: Path) -> None:
    """FULL INDEX PATH: ``const Promise = require('bluebird')`` shadows the
    ``Promise`` global; ``Promise.all()`` must NOT classify ``builtin``."""
    db = _index(
        tmp_path,
        {
            "svc.ts": (
                "const Promise = require('bluebird');\n"
                "class Service {\n"
                "  run(): void { Promise.all([]); }\n"
                "}\n"
            ),
        },
    )
    res = _resolution_for(db, "all")
    assert res, "expected a Promise.all() edge"
    assert "builtin" not in res, (
        f"variable-shadowed Promise.all must NOT classify builtin; got {res}"
    )


def test_integration_unshadowed_global_still_builtin(tmp_path: Path) -> None:
    """Guard: an UN-shadowed ``Math.max()`` must still classify ``builtin`` — the
    shadow gate must not over-suppress."""
    db = _index(
        tmp_path,
        {"svc.ts": ("class Service {\n  run(): void { Math.max(1, 2); }\n}\n")},
    )
    res = _resolution_for(db, "max")
    assert res, "expected a Math.max() edge"
    assert "builtin" in res, f"unshadowed Math.max must classify builtin; got {res}"


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
