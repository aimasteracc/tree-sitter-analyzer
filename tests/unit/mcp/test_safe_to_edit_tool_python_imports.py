"""#1376：test_safe_to_edit_tool_python_imports 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import ast
import json
import sqlite3

import tests.unit.mcp._safe_to_edit_tool_helpers as _fixtures
from tests.unit.mcp._safe_to_edit_tool_helpers import _projection_conn
from tree_sitter_analyzer.mcp.tools.utils import safe_to_edit_helpers as helpers

tool = _fixtures.tool
_close_index_snapshot_registry = _fixtures._close_index_snapshot_registry


def test_snapshot_dependency_view_reads_aliased_python_dynamic_import() -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        build_snapshot_file_dependency_view,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE edges (file_path TEXT, callee_name TEXT, kind TEXT)")
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?)",
        [
            (
                "app.py",
                json.dumps(
                    [
                        {"text": "from importlib import import_module as load"},
                        {"text": "load('pkg.util')"},
                    ]
                ),
            ),
            ("pkg/util.py", "[]"),
        ],
    )

    view = build_snapshot_file_dependency_view(conn, "app.py")

    assert view.dependencies_of("app.py") == ["pkg/util.py"]


def test_snapshot_dependency_view_resolves_parent_relative_python_import() -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        build_snapshot_file_dependency_view,
        snapshot_stale_edges,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE edges ("
        "id INTEGER PRIMARY KEY, kind TEXT, file_path TEXT, "
        "callee_name TEXT, callee_resolved_file TEXT)"
    )
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?)",
        [
            ("pkg/app.py", "[]"),
            ("pkg/__init__.py", "[]"),
            (
                "pkg/sub/routes.py",
                json.dumps([{"text": "from .. import app", "line": 1}]),
            ),
        ],
    )
    conn.execute(
        "INSERT INTO edges VALUES (1, 'imports', 'pkg/sub/routes.py', '..', '')"
    )

    view = build_snapshot_file_dependency_view(conn, "pkg/app.py")

    assert view.dependents_of("pkg/app.py") == ["pkg/sub/routes.py"]
    assert snapshot_stale_edges(conn, "pkg/app.py") == [
        "imports:pkg/sub/routes.py->pkg/app.py#1"
    ]


def test_snapshot_python_import_stops_initializers_at_source_root() -> None:
    # PR #1308 review: import pkg.app 不能执行 src/__init__.py。

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        build_snapshot_file_dependency_view,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE edges (file_path TEXT, callee_name TEXT, kind TEXT)")
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?)",
        [
            ("src/__init__.py", "[]"),
            ("src/pkg/__init__.py", "[]"),
            ("src/pkg/app.py", "[]"),
            ("consumer.py", json.dumps([{"text": "import pkg.app"}])),
        ],
    )

    view = build_snapshot_file_dependency_view(conn, "consumer.py")

    assert view.dependencies_of("consumer.py") == [
        "src/pkg/__init__.py",
        "src/pkg/app.py",
    ]


def test_snapshot_python_import_normalizes_line_continuation() -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        build_snapshot_file_dependency_view,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE edges (file_path TEXT, callee_name TEXT, kind TEXT)")
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?)",
        [
            ("pkg/a.py", "[]"),
            ("pkg/b.py", "[]"),
            (
                "routes.py",
                json.dumps([{"text": "import pkg.a, \\\n pkg.b"}]),
            ),
        ],
    )

    view = build_snapshot_file_dependency_view(conn, "routes.py")
    reverse_view = build_snapshot_file_dependency_view(conn, "pkg/b.py")

    assert view.dependencies_of("routes.py") == ["pkg/a.py", "pkg/b.py"]
    assert reverse_view.dependents_of("pkg/b.py") == ["routes.py"]


def test_snapshot_import_targets_keep_python_wildcard_on_package() -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _import_targets_from_text,
    )

    inventory = frozenset({"pkg/__init__.py"})

    assert _import_targets_from_text("from pkg import *", "routes.py", inventory) == {
        "pkg/__init__.py"
    }


def test_snapshot_import_targets_ignore_invalid_python_direct_spec() -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _import_targets_from_text,
    )

    assert (
        _import_targets_from_text("import pkg-name", "routes.py", frozenset()) == set()
    )


def test_snapshot_import_targets_accept_python_unicode_identifier() -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _import_targets_from_text,
    )

    inventory = frozenset({"éclair.py"})

    assert _import_targets_from_text("import éclair", "routes.py", inventory) == {
        "éclair.py"
    }


def test_python_projected_call_simple_arguments_rejects_unparseable_and_statement() -> (
    None
):
    assert helpers._python_projected_call_has_simple_arguments("if (") is False
    assert helpers._python_projected_call_has_simple_arguments("value = 1") is False


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
            "builtins.__import__",
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


def test_python_static_projection_parser_covers_invalid_and_wildcard_forms() -> None:
    assert helpers._python_static_import_specs("if (") is None
    assert helpers._python_static_import_specs("import os\nimport sys") is None
    assert helpers._python_static_import_specs("value") == ()
    assert helpers._python_static_import_specs("from pkg import *") == ("pkg",)
    assert helpers._python_static_import_specs("from pkg import value") == (
        "pkg",
        "pkg.value",
    )


def test_python_from_import_ambiguity_parser_ignores_invalid_projection() -> None:
    assert (
        helpers._python_from_import_is_ambiguous("if (", "app.py", frozenset()) is False
    )


def test_python_builtins_loader_projection_is_complete() -> None:
    conn = _projection_conn(
        [
            (
                "app.py",
                [
                    {"text": "import builtins"},
                    {"text": "builtins.__import__('pkg.util')"},
                ],
            ),
            ("pkg/util.py", []),
        ]
    )
    inventory = frozenset({"app.py", "pkg/util.py"})

    assert helpers._python_import_projection_complete(conn, inventory) is True
