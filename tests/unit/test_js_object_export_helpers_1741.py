"""#1741：默认导出对象解析器的纯函数与拒绝分支（不建索引）。"""

from __future__ import annotations

import sqlite3

import pytest

from tree_sitter_analyzer.synapse_resolver import _javascript_object_exports as J
from tree_sitter_analyzer.synapse_resolver._imports import ImportEntry


def _entry(
    file_path: str, module: str, local: str, *, star: bool = False, alias: str = ""
) -> ImportEntry:
    return ImportEntry(
        file_path=file_path,
        language="javascript",
        module_path=module,
        local_name=local,
        is_relative=module.startswith("."),
        is_star=star,
        alias_of=alias,
        line=1,
    )


def _resolver(
    tmp_path,
    files: dict[str, str],
    imports: dict[str, list[ImportEntry]],
    symbols=None,
    variables=None,
):
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return J.ObjectExportResolver(
        project_root=str(tmp_path),
        imports_by_file=imports,
        indexed_files=frozenset(files),
        file_symbols=symbols or {},
        variables=variables or {},
    )


# --------------------------------------------------------------------------- parsing


def test_parse_members_shapes() -> None:
    members = J._parse_members(
        " a, b: c, 'q': d, ...spread, m() { return 1; }, async n() {}, lit: 3, fn: () => 1 "
    )
    assert members == {
        "a": ["a"],
        "b": ["c"],
        "q": ["d"],
        "...": ["spread"],
        "m": [""],
        "n": [""],
        "lit": [""],
        "fn": [""],
    }


@pytest.mark.parametrize("body", ["[k]: v", "...a.b", "a b", "a, (", "'x"])
def test_parse_members_rejects_untrustworthy_bodies(body: str) -> None:
    assert J._parse_members(body) is None


def test_default_object_text_direct_and_identifier() -> None:
    assert J._default_object_text("export default {\n  a,\n};\n") == "\n  a,\n"
    text = "const api = { a, b };\nexport default api;\n"
    assert J._default_object_text(text) == " a, b "


@pytest.mark.parametrize(
    "text",
    [
        "export default class X {}\n",
        "export default api;\n",  # no declaration
        "const api = {a};\nconst api = {b};\nexport default api;\n",  # ambiguous
        "const api = make();\nexport default api;\n",  # not an object
        "export default {\n  a,\n};\nexport default {\n  b,\n};\n",  # two defaults
        "export default { a, \n",  # unbalanced
    ],
)
def test_default_object_text_refuses_other_shapes(text: str) -> None:
    assert J._default_object_text(text) is None


def test_balanced_skips_strings_and_rejects_extra_close() -> None:
    assert J._balanced("{ a: '}', b }") == " a: '}', b "
    assert J._balanced('{ a: "x\\"}" }') == ' a: "x\\"}" '
    assert J._balanced("{ a ") is None


def test_named_exports_map_and_export_star() -> None:
    text = (
        "export function f() {}\n"
        "export async function g() {}\n"
        "export const h = 1;\n"
        "export class K {}\n"
        "export { _n as navigator, origin, };\n"
    )
    assert J._named_exports(text) == {
        "f": "f",
        "g": "g",
        "h": "h",
        "K": "K",
        "navigator": "_n",
        "origin": "origin",
    }
    assert J._named_exports("export * from './x.js';\n") is None


def test_export_shape_records_default_and_named() -> None:
    shape = J.export_shape(
        "// c\nexport function f() {}\nexport default { f, ...more };\n"
    )
    assert shape == {"named": ["f"], "default": {"...": ["more"], "f": ["f"]}}
    assert J.export_shape("export default class X {}\n") == {
        "named": [],
        "default": None,
    }
    assert J.export_shape("const x = 1;\n") is None


def test_js_variables_tolerates_missing_connection_and_tables() -> None:
    assert J._js_variables(None, {}) == {}
    conn = sqlite3.connect(":memory:")
    assert J._js_variables(conn, {"a.js": "javascript"}) == {}
    conn.execute(
        "CREATE TABLE ast_symbol_rows (id INTEGER, name TEXT, kind TEXT, file_path TEXT, line INTEGER)"
    )
    conn.executemany(
        "INSERT INTO ast_symbol_rows VALUES (?, ?, 'variable', ?, ?)",
        [(1, "f", "a.js", 3), (2, "g", "b.py", 1)],
    )
    assert J._js_variables(conn, {"a.js": "javascript", "b.py": "python"}) == {
        "a.js": {"f": [(1, 3)]}
    }


# --------------------------------------------------------------------------- resolver


_UTILS = (
    "function f() {}\nconst g = (x) => x;\nconst h = 3;\nexport default { f, g, h };\n"
)


def test_resolver_binds_function_and_arrow_variable(tmp_path) -> None:
    r = _resolver(
        tmp_path,
        {"u.js": _UTILS, "c.js": "import utils from './u.js';\nutils.f();\n"},
        {"c.js": [_entry("c.js", "./u.js", "utils")]},
        symbols={"u.js": [("f", "function", 10)]},
        variables={"u.js": {"g": [(11, 2)], "h": [(12, 3)]}},
    )
    assert r.resolve("utils", "f", "c.js") == (10, "u.js")
    assert r.resolve("utils", "g", "c.js") == (11, "u.js")
    # ``const h = 3`` is not a function.
    assert r.resolve("utils", "h", "c.js") is None
    assert r.resolve("utils", "missing", "c.js") is None


@pytest.mark.parametrize(
    ("receiver", "simple"),
    [("utils.x", "f"), ("a-b", "f"), ("utils", "1x"), ("utils.default", "f")],
)
def test_resolver_rejects_malformed_or_non_default_receivers(
    tmp_path, receiver: str, simple: str
) -> None:
    r = _resolver(
        tmp_path,
        {"u.js": _UTILS, "c.js": "import utils from './u.js';\n"},
        {"c.js": [_entry("c.js", "./u.js", "utils")]},
        symbols={"u.js": [("f", "function", 10)]},
    )
    assert r.resolve(receiver, simple, "c.js") is None


def test_resolver_refuses_without_root_ambiguous_or_aliased_bindings(tmp_path) -> None:
    files = {"u.js": _UTILS, "c.js": "import utils from './u.js';\n"}
    symbols = {"u.js": [("f", "function", 10)]}
    no_root = J.ObjectExportResolver(
        project_root=None,
        imports_by_file={},
        indexed_files=frozenset(files),
        file_symbols=symbols,
    )
    assert no_root.resolve("utils", "f", "c.js") is None
    twice = _resolver(
        tmp_path,
        files,
        {
            "c.js": [
                _entry("c.js", "./u.js", "utils"),
                _entry("c.js", "./v.js", "utils"),
            ]
        },
        symbols=symbols,
    )
    assert twice.resolve("utils", "f", "c.js") is None
    aliased = _resolver(
        tmp_path,
        files,
        {"c.js": [_entry("c.js", "./u.js", "utils", alias="x")]},
        symbols=symbols,
    )
    assert aliased.resolve("utils", "f", "c.js") is None
    unindexed = _resolver(
        tmp_path, files, {"c.js": [_entry("c.js", "./zz.js", "utils")]}, symbols=symbols
    )
    assert unindexed.resolve("utils", "f", "c.js") is None


def test_resolver_unreadable_caller_source_is_treated_as_assigned(tmp_path) -> None:
    r = _resolver(
        tmp_path,
        {"u.js": _UTILS},
        {"c.js": [_entry("c.js", "./u.js", "utils")]},
        symbols={"u.js": [("f", "function", 10)]},
    )
    # c.js does not exist on disk but is "indexed": no proof it does not reassign utils.f.
    r._indexed = frozenset({"u.js", "c.js"})
    assert r.resolve("utils", "f", "c.js") is None


def test_resolver_follows_named_import_inside_the_export_object(tmp_path) -> None:
    r = _resolver(
        tmp_path,
        {
            "impl.js": "export function real() {}\n",
            "u.js": "import { real as f } from './impl.js';\nexport default { f };\n",
            "c.js": "import utils from './u.js';\n",
        },
        {
            "u.js": [_entry("u.js", "./impl.js", "f", alias="real")],
            "c.js": [_entry("c.js", "./u.js", "utils")],
        },
        symbols={"impl.js": [("real", "function", 7)]},
    )
    assert r.resolve("utils", "f", "c.js") == (7, "impl.js")


def test_resolver_duplicate_member_or_two_spread_sources_is_ambiguous(tmp_path) -> None:
    r = _resolver(
        tmp_path,
        {
            "a.js": "function f() {}\nexport default { f };\n",
            "b.js": "function f() {}\nexport default { f };\n",
            "dup.js": "function f() {}\nexport default { f, f };\n",
            "both.js": "import a from './a.js';\nimport b from './b.js';\nexport default { ...a, ...b };\n",
            "c.js": "import d from './dup.js';\nimport both from './both.js';\n",
        },
        {
            "both.js": [
                _entry("both.js", "./a.js", "a"),
                _entry("both.js", "./b.js", "b"),
            ],
            "c.js": [
                _entry("c.js", "./dup.js", "d"),
                _entry("c.js", "./both.js", "both"),
            ],
        },
        symbols={
            "a.js": [("f", "function", 1)],
            "b.js": [("f", "function", 2)],
            "dup.js": [("f", "function", 3)],
        },
    )
    assert r.resolve("d", "f", "c.js") is None
    assert r.resolve("both", "f", "c.js") is None


def test_function_variable_id_checks_the_declaration(tmp_path) -> None:
    r = _resolver(
        tmp_path,
        {
            "v.js": "const a = function () {};\nlet b = async (x) => x;\nvar c = x => x;\nconst d = {};\n"
        },
        {},
        variables={
            "v.js": {
                "a": [(1, 1)],
                "b": [(2, 2)],
                "c": [(3, 3)],
                "d": [(4, 4)],
                "e": [(5, 99)],
                "f": [(6, 1), (7, 2)],
            }
        },
    )
    assert [r._function_variable_id("v.js", n) for n in "abcdef"] == [
        1,
        2,
        3,
        None,
        None,
        None,
    ]
    assert r._function_variable_id("missing.js", "a") is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("(()", False),  # unbalanced: keep the guard
        ("(() => 'a)')", True),  # a quoted paren in the body does not end the literal
        (
            "(a = ')') => 1",
            False,
        ),  # unusual params fall back to the guard (conservative)
        ("", False),
    ],
)
def test_function_literal_detection_edge_cases(text: str, expected: bool) -> None:
    from tree_sitter_analyzer.mcp.tools.callers_dispatch import is_function_literal

    assert is_function_literal(text) is expected
