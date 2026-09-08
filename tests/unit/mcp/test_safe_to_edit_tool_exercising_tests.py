"""#1376：test_safe_to_edit_tool_exercising_tests 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import json
import sqlite3

import tests.unit.mcp._safe_to_edit_tool_helpers as _fixtures

tool = _fixtures.tool
_close_index_snapshot_registry = _fixtures._close_index_snapshot_registry


def test_certified_exercising_tests_loads_inventory_for_test_target() -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _certified_exercising_tests,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT, imports_json TEXT, symbols_json TEXT)"
    )
    conn.execute("INSERT INTO ast_index VALUES ('tests/test_app.py', '[]', '{}')")

    assert _certified_exercising_tests(conn, "tests/test_app.py", []) == [
        "tests/test_app.py"
    ]


def test_certified_symbol_tests_bind_package_reexport_to_defining_module() -> None:
    # PR #1308 review: 包导入不能关联到所有同名的兄弟模块。
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _certified_symbol_reference_tests,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT, imports_json TEXT, symbols_json TEXT)"
    )
    conn.execute(
        "CREATE TABLE edges ("
        "id INTEGER PRIMARY KEY, kind TEXT, file_path TEXT, "
        "callee_name TEXT, callee_resolved_file TEXT)"
    )
    symbol = json.dumps({"symbols": [{"name": "run"}]})
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?, ?)",
        [
            (
                "pkg/__init__.py",
                json.dumps(
                    [
                        {"text": "import os"},
                        {"text": "from .missing import run"},
                        {"text": "from .b import unrelated"},
                        {"text": "from .b import missing as run"},
                        {"text": "from .b import *"},
                        {"text": "from .b import run"},
                    ]
                ),
                "{}",
            ),
            ("pkg/a.py", "[]", symbol),
            ("pkg/b.py", "[]", symbol),
            (
                "tests/test_pkg.py",
                json.dumps([{"text": "import pkg"}, {"text": "from pkg import *"}]),
                "{}",
            ),
        ],
    )
    inventory = frozenset(
        {"pkg/__init__.py", "pkg/a.py", "pkg/b.py", "tests/test_pkg.py"}
    )

    assert (
        _certified_symbol_reference_tests(conn, inventory, "pkg/a.py", "python") == []
    )
    assert _certified_symbol_reference_tests(conn, inventory, "pkg/b.py", "python") == [
        "tests/test_pkg.py"
    ]

    conn.execute(
        "UPDATE ast_index SET symbols_json = ? WHERE file_path = 'pkg/__init__.py'",
        (symbol,),
    )
    assert (
        _certified_symbol_reference_tests(conn, inventory, "pkg/b.py", "python") == []
    )


def test_certified_symbol_tests_follow_transitive_package_reexport() -> None:
    # PR #1308 review: pkg → api → impl 的绑定最终必须仍指向 impl。
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _certified_symbol_reference_tests,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT, imports_json TEXT, symbols_json TEXT)"
    )
    conn.execute(
        "CREATE TABLE edges ("
        "id INTEGER PRIMARY KEY, kind TEXT, file_path TEXT, "
        "callee_name TEXT, callee_resolved_file TEXT)"
    )
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?, ?)",
        [
            (
                "pkg/__init__.py",
                json.dumps([{"text": "from .api import execute"}]),
                "{}",
            ),
            (
                "pkg/api.py",
                json.dumps([{"text": "from .impl import run as execute"}]),
                "{}",
            ),
            ("pkg/impl.py", "[]", json.dumps({"symbols": [{"name": "run"}]})),
            (
                "tests/test_pkg.py",
                json.dumps([{"text": "from pkg import execute as invoke"}]),
                "{}",
            ),
        ],
    )
    inventory = frozenset(
        {"pkg/__init__.py", "pkg/api.py", "pkg/impl.py", "tests/test_pkg.py"}
    )

    assert _certified_symbol_reference_tests(
        conn, inventory, "pkg/impl.py", "python"
    ) == ["tests/test_pkg.py"]


def test_certified_symbol_tests_omit_cyclic_package_reexport() -> None:
    # PR #1308 review: re-export 环不是唯一提供者的证据。
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _python_package_symbol_providers,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT, imports_json TEXT, symbols_json TEXT)"
    )
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?, '{}')",
        [
            ("pkg/__init__.py", json.dumps([{"text": "from .api import run"}])),
            ("pkg/api.py", json.dumps([{"text": "from . import run"}])),
        ],
    )
    inventory = frozenset({"pkg/__init__.py", "pkg/api.py"})

    assert _python_package_symbol_providers(
        conn, "pkg/__init__.py", ["run"], inventory
    ) == {"run": set()}


def test_certified_exercising_tests_traverse_dependent_chain() -> None:
    # PR #1308 review: test → api → util 仍必须把该测试认证为 util 的测试。

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _certified_exercising_tests,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT, imports_json TEXT, symbols_json TEXT)"
    )
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, '[]', '{}')",
        [("util.py",), ("api.py",), ("tests/test_api.py",)],
    )
    conn.execute(
        "CREATE TABLE edges ("
        "id INTEGER PRIMARY KEY, kind TEXT, file_path TEXT, "
        "callee_name TEXT, callee_resolved_file TEXT)"
    )
    conn.executemany(
        "INSERT INTO edges VALUES (?, 'calls', ?, ?, ?)",
        [
            (1, "api.py", "normalize", "util.py"),
            (2, "tests/test_api.py", "handle", "api.py"),
        ],
    )

    assert _certified_exercising_tests(
        conn, "util.py", ["api.py", "missing.py", "api.py"]
    ) == ["tests/test_api.py"]


def test_certified_exercising_tests_cover_custom_pytest_filename_pattern() -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _certified_exercising_tests,
        _pytest_exercising_projection_complete,
        _snapshot_reverse_dependencies,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT, imports_json TEXT, symbols_json TEXT)"
    )
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, '[]', '{}')",
        [("util.py",), ("checks/check_api.py",)],
    )
    conn.execute(
        "CREATE TABLE edges ("
        "kind TEXT, file_path TEXT, callee_name TEXT, callee_resolved_file TEXT)"
    )
    conn.execute(
        "INSERT INTO edges VALUES ('calls', 'checks/check_api.py', "
        "'normalize', 'util.py')"
    )

    queries: list[str] = []
    conn.set_trace_callback(queries.append)

    inventory = frozenset({"util.py", "checks/check_api.py"})
    reverse = _snapshot_reverse_dependencies(conn, inventory)

    assert (
        _certified_exercising_tests(
            conn,
            "util.py",
            ["checks/check_api.py"],
            inventory=inventory,
            reverse_dependencies=reverse,
        )
        == []
    )
    assert (
        _pytest_exercising_projection_complete(
            "util.py",
            ["checks/check_api.py"],
            inventory,
            reverse_dependencies=reverse,
        )
        is False
    )
    # 执行一次邻接查询和一次受限符号引用查询，不能
    # 对每个传递依赖方重新扫描快照。
    assert sum("FROM ast_index" in query for query in queries) == 2


def test_certified_exercising_tests_continue_through_test_chain() -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _certified_exercising_tests,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT, imports_json TEXT, symbols_json TEXT)"
    )
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, '[]', '{}')",
        [("util.py",), ("tests/test_helper.py",), ("tests/test_api.py",)],
    )
    conn.execute(
        "CREATE TABLE edges ("
        "id INTEGER PRIMARY KEY, kind TEXT, file_path TEXT, "
        "callee_name TEXT, callee_resolved_file TEXT)"
    )
    conn.executemany(
        "INSERT INTO edges VALUES (?, 'calls', ?, ?, ?)",
        [
            (1, "tests/test_helper.py", "normalize", "util.py"),
            (2, "tests/test_api.py", "fixture", "tests/test_helper.py"),
        ],
    )

    assert _certified_exercising_tests(conn, "util.py", ["tests/test_helper.py"]) == [
        "tests/test_helper.py",
        "tests/test_api.py",
    ]


def test_certified_exercising_tests_expand_conftest_scope() -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _certified_exercising_tests,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT, imports_json TEXT, symbols_json TEXT)"
    )
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, '[]', '{}')",
        [
            ("util.py",),
            ("tests/conftest.py",),
            ("tests/test_api.py",),
            ("tests/sub/test_nested.py",),
            ("other/test_outside.py",),
        ],
    )
    conn.execute(
        "CREATE TABLE edges ("
        "id INTEGER PRIMARY KEY, kind TEXT, file_path TEXT, "
        "callee_name TEXT, callee_resolved_file TEXT)"
    )
    conn.execute(
        "INSERT INTO edges VALUES (1, 'calls', 'tests/conftest.py', "
        "'fixture', 'util.py')"
    )

    assert _certified_exercising_tests(conn, "util.py", ["tests/conftest.py"]) == [
        "tests/sub/test_nested.py",
        "tests/test_api.py",
    ]


def test_certified_exercising_tests_traverse_test_named_production_file() -> None:
    # PR #1308 review: src/test_adapter.py 本身不是可运行的测试目标。

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _certified_exercising_tests,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT, imports_json TEXT, symbols_json TEXT)"
    )
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, '[]', '{}')",
        [("src/util.py",), ("src/test_adapter.py",), ("tests/test_adapter.py",)],
    )
    conn.execute(
        "CREATE TABLE edges ("
        "id INTEGER PRIMARY KEY, kind TEXT, file_path TEXT, "
        "callee_name TEXT, callee_resolved_file TEXT)"
    )
    conn.executemany(
        "INSERT INTO edges VALUES (?, 'calls', ?, ?, ?)",
        [
            (1, "src/test_adapter.py", "normalize", "src/util.py"),
            (2, "tests/test_adapter.py", "adapt", "src/test_adapter.py"),
        ],
    )

    assert _certified_exercising_tests(
        conn, "src/util.py", ["src/test_adapter.py"]
    ) == ["tests/test_adapter.py"]
