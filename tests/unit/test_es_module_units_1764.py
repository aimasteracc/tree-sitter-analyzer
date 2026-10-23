"""#1764：ES 模块绑定的拒绝分支、读不到的事实，以及按导入保留的未解析调用点。"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from tests.unit.test_es_module_exports_1764 import _binder
from tree_sitter_analyzer.graph.es_import_sites import imported_unresolved_rows
from tree_sitter_analyzer.synapse_resolver._es_module_binding import UNKNOWN
from tree_sitter_analyzer.synapse_resolver.languages.typescript import (
    TypeScriptResolverContext,
    _imported,
    build_typescript_resolver_context,
)

_LIB = (
    "export function f() {}\n"
    "export class Box {\n  static make() {}\n}\n"
    "const utils = {\n  helper,\n};\n"
    "function helper() {}\n"
    "export default utils;\n"
)


def _lib_binder(tmp_path: Path, use: str) -> Any:
    files = {"lib.ts": _LIB, "use.ts": use}
    symbols = {
        "lib.ts": [
            ("f", "function", 1),
            ("Box", "class", 2),
            ("make", "method", 3),
            ("helper", "function", 8),
        ]
    }
    binder = _binder(tmp_path, files, symbols)
    binder._class_methods = {"lib.ts": {"Box": {"make": 3}}}
    return binder


def test_member_calls_bind_classes_and_default_objects(tmp_path: Path) -> None:
    binder = _lib_binder(
        tmp_path, "import u, { Box, f } from './lib';\nimport * as ns from './lib';\n"
    )
    assert binder.bind("Box", "make", "use.ts") == (3, "lib.ts", None)
    assert binder.bind("Box", "missing", "use.ts") is None
    # `export default utils` names `const utils = { helper }`: the object member.
    assert binder.bind("u", "helper", "use.ts") == (8, "lib.ts", None)
    # `ns.f.x()`: `f` is a function, not a namespace, so the walk stops.
    assert binder.bind("ns.f", "x", "use.ts") is None
    assert binder.bind("ns", "nope", "use.ts") is None
    assert binder.bind("missing", "f", "use.ts") is None


def test_reassigned_or_shadowed_receivers_are_not_bound(tmp_path: Path) -> None:
    binder = _lib_binder(
        tmp_path,
        "import * as ns from './lib';\nimport { f } from './lib';\nns.f = () => 1;\n",
    )
    assert binder.bind("ns", "f", "use.ts") is None
    binder._variables = {"use.ts": {"f": [(9, 4)], "ns": [(10, 5)]}}
    assert binder.bind("", "f", "use.ts") is None
    assert binder.bind("ns", "make", "use.ts") is None


def test_unreadable_caller_source_counts_as_assigned(tmp_path: Path) -> None:
    binder = _lib_binder(tmp_path, "import * as ns from './lib';\n")
    (tmp_path / "use.ts").unlink()
    binder._objects._text.clear()
    assert binder.bind("ns", "f", "use.ts") is None


def test_local_import_from_outside_the_project_is_unknown(tmp_path: Path) -> None:
    files = {
        "a.ts": "import { x } from 'pkg';\nexport { x };\n",
        "b.ts": "export { y };\n",
    }
    binder = _binder(tmp_path, files, {})
    assert binder.find("a.ts", "x", 0) == UNKNOWN
    assert binder.find("b.ts", "y", 0) == UNKNOWN


def test_depth_limit_is_unknown(tmp_path: Path) -> None:
    binder = _binder(tmp_path, {"a.ts": "export function x() {}\n"}, {})
    assert binder.find("a.ts", "x", 10_000) == UNKNOWN


def test_resolver_moat_and_missing_binder(tmp_path: Path) -> None:
    ctx = TypeScriptResolverContext(file_languages={"use.ts": "typescript"})
    assert _imported(ctx, "", "f", "use.ts") == (None, "unknown", "")

    class _Binder:
        def bind(self, receiver: str, simple: str, caller: str) -> Any:
            return {"py": (1, "mod.py", None), "ts": (2, "lib.ts", {"local": simple})}[
                receiver or "ts"
            ]

    ctx = TypeScriptResolverContext(
        file_languages={
            "use.ts": "typescript",
            "mod.py": "python",
            "lib.ts": "typescript",
        },
        binder=_Binder(),  # type: ignore[arg-type]
    )
    assert _imported(ctx, "py", "f", "use.ts") == (None, "unknown", "")
    assert _imported(ctx, "", "g", "use.ts") == (2, "project", "lib.ts", {"local": "g"})


def test_context_without_project_root_has_no_binder() -> None:
    ctx = build_typescript_resolver_context(
        imports_by_file={},
        file_languages={"a.ts": "typescript"},
        file_symbols={},
        global_name_table={},
        file_class_methods=dict,
        shadow_locals={},
    )
    assert ctx is not None and ctx.binder is None


# ------------------------------------------------------------ es_import_sites
def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE ast_index (file_path TEXT, language TEXT)")
    conn.execute(
        "CREATE TABLE ast_imports (file_path TEXT, local_name TEXT, module_path TEXT,"
        " is_star INTEGER, alias_of TEXT, language TEXT)"
    )
    conn.execute(
        "CREATE TABLE edges (id INTEGER PRIMARY KEY, kind TEXT, file_path TEXT,"
        " callee_name TEXT, callee_full TEXT, language TEXT, callee_resolution TEXT,"
        " callee_resolved_file TEXT, target_node_id TEXT, metadata TEXT,"
        " source_node_id TEXT, line INTEGER)"
    )
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?)",
        [("jws.ts", "typescript"), ("jwt.ts", "typescript"), ("m.py", "python")],
    )
    conn.executemany(
        "INSERT INTO ast_imports VALUES (?, ?, ?, 0, '', 'typescript')",
        [("jwt.ts", "verifying", "./jws"), ("jwt.ts", "makeSig", "./jws")],
    )
    conn.executemany(
        "INSERT INTO edges (kind, file_path, callee_name, callee_full, language,"
        " callee_resolution, callee_resolved_file, target_node_id) VALUES"
        " (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                "calls",
                "jwt.ts",
                "verifying",
                "verifying",
                "typescript",
                "unknown",
                "",
                "",
            ),
            ("calls", "jwt.ts", "makeSig", "makeSig", "typescript", "unknown", "", ""),
            (
                "calls",
                "loc.ts",
                "verifying",
                "verifying",
                "typescript",
                "unknown",
                "",
                "",
            ),
            ("calls", "m.py", "verifying", "verifying", "python", "unknown", "", ""),
            (
                "calls",
                "jws.ts",
                "verifying",
                "verifying",
                "typescript",
                "unknown",
                "",
                "",
            ),
            (
                "calls",
                "jwt.ts",
                "verifying",
                "verifying",
                "typescript",
                "project",
                "",
                "",
            ),
            (
                "imports",
                "jwt.ts",
                "",
                "",
                "typescript",
                "unknown",
                "jws.ts",
                "module:./jws",
            ),
        ],
    )
    return conn


def _rows(conn: sqlite3.Connection, name: str, file: str, seen: set[int]) -> list[int]:
    return sorted(
        row["id"]
        for row in imported_unresolved_rows(
            conn,
            name,
            file,
            seen,
            is_resolved=lambda r: r["callee_resolution"] == "project",
            source_file=lambda r: r["file_path"],
        )
    )


def test_imported_unresolved_rows_keep_only_import_bound_es_calls() -> None:
    conn = _db()
    # 1: imported `verifying()`; 2: renamed import `makeSig()` of the declaring file.
    # 3 (no import), 4 (Python), 5 (declaring file), 6 (resolved) are not added.
    assert _rows(conn, "verifying", "jws.ts", set()) == [1, 2]
    assert _rows(conn, "verifying", "jws.ts", {1, 2}) == []
    assert _rows(conn, "verifying", "m.py", set()) == []
    assert _rows(conn, "a.b", "jws.ts", set()) == []
    assert _rows(conn, "verifying", "", set()) == []


def test_imported_unresolved_rows_tolerate_a_broken_index() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    assert _rows(conn, "verifying", "jws.ts", set()) == []


@pytest.mark.parametrize(
    ("exports", "local", "alias_of", "reaches"),
    [
        (None, "en", "", True),
        ({"named": []}, "en", "", True),
        # `export default function () {}`: `en()` calls the anonymous default.
        ({"locals": {"default": ""}, "default_kind": "declaration"}, "en", "", False),
        # `export default signer` names the queried function (#1768).
        (
            {"locals": {"default": "getTypeName"}, "default_kind": "ident"},
            "en",
            "",
            True,
        ),
        # `export default other` where `other` is another declared function.
        ({"locals": {"default": "other"}, "default_kind": "ident"}, "en", "", False),
        # `const alias = getTypeName; export default alias`: a variable may be the target.
        ({"locals": {"default": "alias"}, "default_kind": "ident"}, "en", "", True),
        ({"locals": {"default": ""}, "default_kind": "expression"}, "en", "", True),
        # `import { other as o }`: the export `other` is another declaration.
        ({"locals": {"other": "other"}}, "o", "other", False),
        ({"locals": {}, "reexports": [["o", "./x", "o"]]}, "o", "", True),
        ({"locals": {}, "stars": ["./x"]}, "o", "", True),
        ({"locals": {}, "complete": False}, "o", "", True),
        ({"locals": {}}, "o", "", False),
    ],
)
def test_a_renamed_binding_is_evidence_unless_the_export_rules_it_out(
    exports: dict[str, Any] | None, local: str, alias_of: str, reaches: bool
) -> None:
    from tree_sitter_analyzer.graph.es_import_sites import _may_reach

    defined = {"getTypeName", "other"}
    assert _may_reach(exports, defined, "getTypeName", local, alias_of) is reaches


# axios `http.js`: `export default <expression>` beside named exports. A named import
# `{ other }` cannot be the default; only an unreadable import statement keeps both.
_AXIOS_LIKE = {
    "locals": {"default": "", "other": "other"},
    "default_kind": "expression",
}


@pytest.mark.parametrize(
    ("form", "reaches"), [("named", False), ("default", True), ("", True)]
)
def test_the_import_statement_form_decides_default_or_named(
    form: str, reaches: bool
) -> None:
    from tree_sitter_analyzer.graph.es_import_sites import _may_reach

    defined = {"getTypeName", "other"}
    assert _may_reach(_AXIOS_LIKE, defined, "getTypeName", "other", "", form) is reaches


def test_binding_form_reads_the_import_statement() -> None:
    import json

    from tree_sitter_analyzer.graph.es_import_sites import _binding_form

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index (file_path TEXT, symbols_json TEXT)")
    statements = [
        "import httpAdapter, { other as o, __isSame } from './http.js'",
        "import type T from './t'",
    ]
    payload = {"symbols": [{"kind": "import", "text": s} for s in statements]}
    conn.execute("INSERT INTO ast_index VALUES ('t.js', ?)", (json.dumps(payload),))
    cache: dict[str, list[str]] = {}
    assert _binding_form(conn, "t.js", "httpAdapter", cache) == "default"
    assert _binding_form(conn, "t.js", "__isSame", cache) == "named"
    assert _binding_form(conn, "t.js", "T", cache) == "default"
    assert _binding_form(conn, "t.js", "missing", cache) == ""
    assert _binding_form(conn, "absent.js", "x", {}) == ""
    broken = sqlite3.connect(":memory:")
    assert _binding_form(broken, "t.js", "x", {}) == ""


def test_an_exported_function_const_is_not_an_alias() -> None:
    from tree_sitter_analyzer.graph.es_import_sites import _may_reach
    from tree_sitter_analyzer.synapse_resolver._javascript_object_exports import (
        export_shape,
    )

    shape = export_shape(
        "export const __isSame = (u: string): boolean => !!u;\n"
        "export const alias = target;\n"
        "export let later = () => 1;\n"
        "export const gen = async function () {};\n"
    )
    assert shape is not None
    assert shape["function_consts"] == ["__isSame", "gen"]
    reach = lambda local: _may_reach(shape, set(), "target", local, "", "named")  # noqa: E731
    assert reach("__isSame") is False
    assert reach("gen") is False
    assert reach("alias") is True  # `const alias = target` may be the target
    assert reach("later") is True  # `let` can be reassigned


def test_a_one_hop_const_alias_to_another_declaration_is_not_evidence() -> None:
    from tree_sitter_analyzer.graph.es_import_sites import _may_reach
    from tree_sitter_analyzer.synapse_resolver._javascript_object_exports import (
        export_shape,
    )

    shape = export_shape(
        "function isSame() {}\n"
        "export const __isSame = isSame;\n"
        "export const __target = target;\n"
        "export const __unknown = imported;\n"
    )
    assert shape is not None
    assert shape["const_aliases"] == {
        "__isSame": "isSame",
        "__target": "target",
        "__unknown": "imported",
    }
    defined = {"isSame", "target"}
    reach = lambda local: _may_reach(shape, defined, "target", local, "", "named")  # noqa: E731
    assert reach("__isSame") is False
    assert reach("__target") is True
    assert reach("__unknown") is True  # an identifier that is not a declaration here
