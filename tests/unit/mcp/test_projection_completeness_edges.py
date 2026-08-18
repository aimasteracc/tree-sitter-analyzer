"""Fail-closed boundary tests for certified import projections."""

from __future__ import annotations

import ast
import json
import sqlite3
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.tools.utils import safe_to_edit_helpers as helpers


def _projection_conn(rows: list[tuple[str, object]]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?)",
        [(path, json.dumps(imports)) for path, imports in rows],
    )
    return conn


def _symbol_conn(raw_symbols: object) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index (file_path TEXT, symbols_json TEXT)")
    conn.execute("INSERT INTO ast_index VALUES ('app.py', ?)", (raw_symbols,))
    return conn


def test_certified_java_facts_require_complete_reflection_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(helpers, "_symbol_walk_projections_complete", lambda *_: True)
    monkeypatch.setattr(
        helpers, "_java_same_package_projection_complete", lambda *_: True
    )
    monkeypatch.setattr(
        helpers, "_java_reflection_projection_complete", lambda *_: False
    )

    assert (
        helpers._certified_import_facts_available(
            "src/Util.java", conn=object(), inventory=frozenset()
        )
        is False
    )


def test_python_projected_call_rejects_non_calls_and_unqualified_owners() -> None:
    assert helpers._python_projected_call("value") is None
    assert helpers._python_projected_call("(factory()).load()") is None


def test_python_loader_projection_rejects_invalid_or_multiple_statements() -> None:
    assert helpers._python_dynamic_loader_names_from_projection(["if ("]) is None
    assert (
        helpers._python_dynamic_loader_names_from_projection(["import os\nimport sys"])
        is None
    )


def test_python_loader_projection_tracks_annotated_alias_chains() -> None:
    names = helpers._python_dynamic_loader_names_from_projection(
        [
            "import importlib as il",
            "from importlib import import_module, invalidate_caches",
            "loader: object = il.import_module",
            "later = loader",
            "ignored = missing",
            "holder.loader = loader",
        ]
    )

    assert names == frozenset(
        {
            "__import__",
            "importlib.import_module",
            "il.import_module",
            "import_module",
            "loader",
            "later",
        }
    )


def test_python_ast_name_rejects_attribute_with_dynamic_owner() -> None:
    expression = ast.parse("(factory()).load").body[0]
    assert isinstance(expression, ast.Expr)

    assert helpers._python_ast_name(expression.value) is None


def test_query_only_jsts_specifier_is_not_resolved() -> None:
    assert (
        helpers._resolve_import_spec_from_inventory(
            "?worker", "src/main.ts", frozenset({"src/main.ts"})
        )
        is None
    )


class _BrokenConnection:
    def execute(self, _query: str) -> Any:
        raise sqlite3.DatabaseError("broken snapshot")


def test_symbol_projection_completeness_rejects_query_failure() -> None:
    assert (
        helpers._symbol_walk_projections_complete(
            _BrokenConnection(), frozenset({"app.py"}), {"python"}
        )
        is False
    )


@pytest.mark.parametrize("payload", ["not-json", "[]"])
def test_symbol_projection_completeness_rejects_malformed_payload(
    payload: str,
) -> None:
    conn = _symbol_conn(payload)

    assert (
        helpers._symbol_walk_projections_complete(
            conn, frozenset({"app.py"}), {"python"}
        )
        is False
    )


def test_commonjs_projection_rejects_missing_extensionless_target() -> None:
    conn = _projection_conn([("src/main.js", [{"text": "require('./missing')"}])])

    assert (
        helpers._jsts_import_projection_complete(conn, frozenset({"src/main.js"}))
        is False
    )


def test_commonjs_projection_accepts_extensionless_file_target() -> None:
    conn = _projection_conn(
        [
            ("src/main.js", [{"text": "require('./util')"}]),
            ("src/util.js", []),
        ]
    )
    inventory = frozenset({"src/main.js", "src/util.js"})

    assert helpers._jsts_import_projection_complete(conn, inventory) is True


def test_commonjs_loader_alias_projection_fails_closed() -> None:
    conn = _projection_conn(
        [
            ("src/main.js", [{"text": "load('./util')"}]),
            ("src/util.js", []),
        ]
    )

    assert (
        helpers._jsts_import_projection_complete(
            conn, frozenset({"src/main.js", "src/util.js"})
        )
        is False
    )


def test_python_static_projection_parser_covers_invalid_and_wildcard_forms() -> None:
    assert helpers._python_static_import_specs("if (") is None
    assert helpers._python_static_import_specs("import os\nimport sys") is None
    assert helpers._python_static_import_specs("value") == ()
    assert helpers._python_static_import_specs("from pkg import *") == ("pkg",)
    assert helpers._python_static_import_specs("from pkg import value") == (
        "pkg",
        "pkg.value",
    )


def test_python_relative_inventory_match_can_be_empty() -> None:
    assert (
        helpers._python_inventory_matches(
            ".missing", "pkg/app.py", frozenset({"pkg/app.py"})
        )
        == set()
    )


def test_python_projection_rejects_invalid_loader_statement() -> None:
    conn = _projection_conn([("app.py", [{"text": "if ("}])])

    assert (
        helpers._python_import_projection_complete(conn, frozenset({"app.py"})) is False
    )


def test_python_projection_rejects_invalid_static_statement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = _projection_conn([("app.py", [{"text": "if ("}])])
    monkeypatch.setattr(
        helpers,
        "_python_dynamic_loader_names_from_projection",
        lambda _: frozenset({"__import__"}),
    )

    assert (
        helpers._python_import_projection_complete(conn, frozenset({"app.py"})) is False
    )


def test_python_projection_rejects_ambiguous_dynamic_import() -> None:
    conn = _projection_conn(
        [
            ("app.py", [{"text": "__import__('pkg.util')"}]),
            ("src/pkg/util.py", []),
            ("vendor/pkg/util.py", []),
        ]
    )
    inventory = frozenset({"app.py", "src/pkg/util.py", "vendor/pkg/util.py"})

    assert helpers._python_import_projection_complete(conn, inventory) is False


def test_java_inventory_match_prefers_exact_candidate() -> None:
    assert helpers._java_inventory_matches(
        "com.acme.Util$Inner", frozenset({"com/acme/Util.java"})
    ) == {"com/acme/Util.java"}


def test_java_multi_file_projection_fails_closed_for_qualified_references() -> None:
    inventory = frozenset({"src/com/acme/Util.java", "src/org/example/Use.java"})

    assert (
        helpers._java_same_package_projection_complete(
            object(), "src/com/acme/Util.java", inventory
        )
        is False
    )


def test_cpp_header_unit_resolves_to_inventory() -> None:
    inventory = frozenset({"src/main.cpp", "include/util.h"})

    assert helpers._import_targets_from_text(
        'import "util.h";', "src/main.cpp", inventory
    ) == {"include/util.h"}


def test_cpp_ambiguous_header_unit_does_not_guess_target() -> None:
    inventory = frozenset({"src/main.cpp", "include-one/util.h", "include-two/util.h"})

    assert (
        helpers._import_targets_from_text('import "util.h";', "src/main.cpp", inventory)
        == set()
    )


def test_cpp_header_unit_projection_is_complete() -> None:
    conn = _projection_conn(
        [
            ("src/main.cpp", [{"text": 'import "util.h";'}]),
            ("include/util.h", []),
        ]
    )
    inventory = frozenset({"src/main.cpp", "include/util.h"})

    assert helpers._quoted_include_projection_complete(
        conn, "include/util.h", inventory
    )


def test_cpp_named_module_projection_fails_closed() -> None:
    conn = _projection_conn(
        [
            ("src/main.cpp", [{"text": "import project.core;"}]),
            ("include/util.h", []),
        ]
    )
    inventory = frozenset({"src/main.cpp", "include/util.h"})

    assert not helpers._quoted_include_projection_complete(
        conn, "include/util.h", inventory
    )


def test_java_reflection_projection_rejects_missing_snapshot_table() -> None:
    assert (
        helpers._java_reflection_projection_complete(
            sqlite3.connect(":memory:"), frozenset()
        )
        is False
    )


def test_java_reflection_projection_rejects_unbound_bare_call() -> None:
    conn = _projection_conn(
        [
            ("tool.py", [{"text": "ignored"}]),
            ("src/Main.java", [{"text": 'forName("com.acme.Util")'}]),
            ("src/com/acme/Util.java", []),
        ]
    )
    inventory = frozenset({"tool.py", "src/Main.java", "src/com/acme/Util.java"})

    assert helpers._java_reflection_projection_complete(conn, inventory) is False


def test_java_reflection_projection_rejects_ambiguous_target() -> None:
    conn = _projection_conn(
        [
            (
                "src/Main.java",
                [{"text": 'Class.forName("com.acme.Util")'}],
            ),
            ("src/com/acme/Util.java", []),
            ("vendor/com/acme/Util.java", []),
        ]
    )
    inventory = frozenset(
        {
            "src/Main.java",
            "src/com/acme/Util.java",
            "vendor/com/acme/Util.java",
        }
    )

    assert helpers._java_reflection_projection_complete(conn, inventory) is False
