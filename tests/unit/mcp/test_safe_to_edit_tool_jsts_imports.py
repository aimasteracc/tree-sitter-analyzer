"""#1376：test_safe_to_edit_tool_jsts_imports 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import json
import sqlite3

import pytest

import tests.unit.mcp._safe_to_edit_tool_helpers as _fixtures
from tests.unit.mcp._safe_to_edit_tool_helpers import _projection_conn
from tree_sitter_analyzer.mcp.tools.utils import safe_to_edit_helpers as helpers

tool = _fixtures.tool
_close_index_snapshot_registry = _fixtures._close_index_snapshot_registry


def test_snapshot_dependency_view_reads_commonjs_projection() -> None:
    import sqlite3

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
            ("src/main.ts", json.dumps([{"text": "require('./legacy')", "line": 1}])),
            ("src/legacy.ts", "[]"),
        ],
    )

    view = build_snapshot_file_dependency_view(conn, "src/main.ts")

    assert view.dependencies_of("src/main.ts") == ["src/legacy.ts"]


def test_snapshot_dependency_view_reads_dynamic_import_projection() -> None:
    import sqlite3

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
            ("src/main.ts", json.dumps([{"text": "import('./lazy')", "line": 1}])),
            ("src/lazy.ts", "[]"),
        ],
    )

    view = build_snapshot_file_dependency_view(conn, "src/main.ts")

    assert view.dependencies_of("src/main.ts") == ["src/lazy.ts"]


def test_snapshot_dependency_view_reads_dynamic_import_with_options() -> None:
    # PR #1308 review: 后面存在 options 参数时，第一个字面量仍是模块标识。
    import sqlite3

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
                "src/main.ts",
                json.dumps(
                    [
                        {
                            "text": (
                                "import('./util', { with: { type: 'javascript' } })"
                            ),
                            "line": 1,
                        }
                    ]
                ),
            ),
            ("src/util.ts", "[]"),
        ],
    )

    view = build_snapshot_file_dependency_view(conn, "src/main.ts")

    assert view.dependencies_of("src/main.ts") == ["src/util.ts"]


@pytest.mark.parametrize(
    "projection", ["export { run } from './util';", "export * from './util';"]
)
def test_snapshot_dependency_view_reads_jsts_reexport(projection: str) -> None:
    import sqlite3

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
            ("src/index.ts", json.dumps([{"text": projection}])),
            ("src/util.ts", "[]"),
        ],
    )

    view = build_snapshot_file_dependency_view(conn, "src/index.ts")

    assert view.dependencies_of("src/index.ts") == ["src/util.ts"]


@pytest.mark.parametrize(
    "projection",
    ["import './util.js?worker';", "export * from './util.js#worker';"],
)
def test_snapshot_dependency_view_normalizes_jsts_url_suffix(
    projection: str,
) -> None:
    import sqlite3

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
            ("src/index.ts", json.dumps([{"text": projection}])),
            ("src/util.js", "[]"),
        ],
    )

    view = build_snapshot_file_dependency_view(conn, "src/index.ts")

    assert view.dependencies_of("src/index.ts") == ["src/util.js"]


def test_snapshot_dependency_view_reads_module_require() -> None:
    import sqlite3

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
            ("src/main.js", json.dumps([{"text": "module.require('./util')"}])),
            ("src/util.js", "[]"),
        ],
    )

    view = build_snapshot_file_dependency_view(conn, "src/main.js")

    assert view.dependencies_of("src/main.js") == ["src/util.js"]


def test_snapshot_dependency_view_substitutes_typescript_source_for_js_spec() -> None:
    import sqlite3

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
            ("src/index.ts", json.dumps([{"text": "import './util.js'"}])),
            ("src/util.ts", "[]"),
        ],
    )

    view = build_snapshot_file_dependency_view(conn, "src/index.ts")

    assert view.dependencies_of("src/index.ts") == ["src/util.ts"]


def test_snapshot_dependency_view_reads_typescript_path_reference() -> None:
    import sqlite3

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
                "src/index.ts",
                json.dumps([{"text": '/// <reference path="./types.d.ts" />'}]),
            ),
            ("src/types.d.ts", "[]"),
        ],
    )

    view = build_snapshot_file_dependency_view(conn, "src/index.ts")

    assert view.dependencies_of("src/index.ts") == ["src/types.d.ts"]


def test_snapshot_dependency_view_resolves_root_commonjs_directory() -> None:
    import sqlite3

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
            ("main.js", json.dumps([{"text": "require('./')"}])),
            ("index.js", "[]"),
        ],
    )

    view = build_snapshot_file_dependency_view(conn, "main.js")

    assert view.dependencies_of("main.js") == ["index.js"]


def test_snapshot_typescript_declaration_import_is_bidirectional() -> None:
    import sqlite3

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
                "src/main.ts",
                json.dumps([{"text": "import type { Foo } from './types'"}]),
            ),
            ("src/types.d.ts", "[]"),
        ],
    )

    view = build_snapshot_file_dependency_view(conn, "src/main.ts")
    reverse_view = build_snapshot_file_dependency_view(conn, "src/types.d.ts")

    assert view.dependencies_of("src/main.ts") == ["src/types.d.ts"]
    assert reverse_view.dependents_of("src/types.d.ts") == ["src/main.ts"]


@pytest.mark.parametrize(
    ("import_extension", "declaration_extension"),
    [("mjs", "d.mts"), ("cjs", "d.cts")],
)
def test_snapshot_nodenext_declaration_import_is_bidirectional(
    import_extension: str, declaration_extension: str
) -> None:
    target = f"src/util.{declaration_extension}"
    conn = _projection_conn(
        [
            ("src/main.ts", [{"text": f"import './util.{import_extension}'"}]),
            (target, []),
        ]
    )
    conn.row_factory = sqlite3.Row
    inventory = frozenset({"src/main.ts", target})

    view = helpers.build_snapshot_file_dependency_view(
        conn, target, inventory=inventory
    )

    assert view.dependents_of(target) == ["src/main.ts"]
