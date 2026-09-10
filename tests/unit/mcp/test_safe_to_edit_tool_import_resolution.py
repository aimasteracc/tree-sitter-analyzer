"""#1376：test_safe_to_edit_tool_import_resolution 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import json
import sqlite3

import pytest

import tests.unit.mcp._safe_to_edit_tool_helpers as _fixtures
from tests.unit.mcp._safe_to_edit_tool_helpers import (
    _projection_conn,
    _snapshot_view_with_resolved_edge,
)
from tree_sitter_analyzer.mcp.tools.utils import safe_to_edit_helpers as helpers

tool = _fixtures.tool
_close_index_snapshot_registry = _fixtures._close_index_snapshot_registry


# RFC-0022 P0.4: 快照依赖视图解析精确的 IMPORTS 边，
# 同时通过 imports_json 的 needle 查询召回成员导入，与
# 传统实时轴保持一致，即 from pkg import app 或 from . import app。
def test_snapshot_dependency_view_recalls_member_imports() -> None:
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        build_snapshot_file_dependency_view,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE edges (file_path TEXT, callee_name TEXT, kind TEXT)")
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.execute("INSERT INTO edges VALUES ('routes.py', 'app', 'imports')")
    # C44: callee_name 为 BLOB 的行不能中止整个 edges 遍历。
    conn.execute(
        "INSERT INTO edges VALUES ('blobbed.py', ?, 'imports')", (b"blob-module",)
    )
    # 目标自身的 import 行也可能是 BLOB，此时第一遍跳过。
    conn.execute("INSERT INTO edges VALUES ('app.py', ?, 'imports')", (b"blob-own",))
    # C53: 第二遍遇到 BLOB 类型 importer 路径应跳过，而非致命失败。
    conn.execute("INSERT INTO edges VALUES (?, 'app', 'imports')", (b"blob-path",))
    conn.execute("INSERT INTO edges VALUES ('app.py', 'app', 'imports')")
    # app.py 导入未被索引的模块时，resolved 为 None。
    conn.execute("INSERT INTO edges VALUES ('app.py', 'missing.mod', 'imports')")
    # 相对导入 .sibling 用于覆盖相对路径分支。
    conn.execute("INSERT INTO edges VALUES ('pkg/app.py', '.sibling', 'imports')")
    # 不存在对应清单目标时，应忽略父级相对路径。
    conn.execute("INSERT INTO edges VALUES ('pkg/app.py', '..up', 'imports')")
    conn.execute(
        "INSERT INTO ast_index VALUES ('routes.py', ?)",
        (json.dumps([{"text": "from app import UserService", "line": 1}]),),
    )
    conn.execute(
        "INSERT INTO ast_index VALUES ('unrelated.py', ?)",
        (json.dumps([{"text": "import os", "line": 1}]),),
    )
    conn.execute(
        "INSERT INTO ast_index VALUES ('app.py', ?)",
        (json.dumps([{"text": "import os", "line": 1}]),),
    )
    # C64: import happy 不能因子串匹配而命中 app 的 needle。
    conn.execute(
        "INSERT INTO ast_index VALUES ('tests/test_happy.py', ?)",
        (json.dumps([{"text": "import happy", "line": 1}]),),
    )
    conn.execute(
        "INSERT INTO ast_index VALUES ('later.py', ?)",
        (json.dumps([{"text": "from app import Member", "line": 1}]),),
    )
    view = build_snapshot_file_dependency_view(conn, "app.py")
    # routes.py 命中 needle 查询；unrelated.py 覆盖不匹配分支，
    # 不会增加依赖方；随后命中的条目仍须计入。
    assert view.dependents_of("app.py") == ["later.py", "routes.py"]


@pytest.mark.parametrize(
    ("stored_path", "imports_json"),
    [
        ("candidate.py", "not-json-app"),
        ("candidate.py", '"app"'),
        ("candidate.py", '[{"text": "import app"}, 42]'),
        (b"candidate.py", '[{"text": "import app"}]'),
    ],
    ids=["invalid-json", "scalar-json", "invalid-item", "blob-path"],
)
def test_snapshot_dependency_view_rejects_malformed_candidate_projection(
    stored_path: object,
    imports_json: str,
) -> None:
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        build_snapshot_file_dependency_view,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE edges (file_path TEXT, callee_name TEXT, kind TEXT)")
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.execute("INSERT INTO ast_index VALUES ('app.py', '[]')")
    conn.execute("INSERT INTO ast_index VALUES (?, ?)", (stored_path, imports_json))

    with pytest.raises(ValueError, match="CORRUPT_INDEX"):
        build_snapshot_file_dependency_view(
            conn,
            "app.py",
            inventory=frozenset({"app.py", "candidate.py"}),
        )


def test_snapshot_dependency_view_rejects_malformed_target_projection() -> None:
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        build_snapshot_file_dependency_view,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE edges (file_path TEXT, callee_name TEXT, kind TEXT)")
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.execute("INSERT INTO ast_index VALUES ('app.py', 'not-json')")

    with pytest.raises(ValueError, match="CORRUPT_INDEX"):
        build_snapshot_file_dependency_view(conn, "app.py")


def test_snapshot_dependency_view_binds_member_import_to_its_package() -> None:
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
            ("pkg/app.py", "[]"),
            ("other/app.py", "[]"),
            ("other/__init__.py", "[]"),
            (
                "routes.py",
                json.dumps([{"text": "from other import app", "line": 1}]),
            ),
        ],
    )

    pkg_view = build_snapshot_file_dependency_view(conn, "pkg/app.py")
    other_view = build_snapshot_file_dependency_view(conn, "other/app.py")

    assert pkg_view.dependents_of("pkg/app.py") == []
    assert other_view.dependents_of("other/app.py") == ["routes.py"]


def test_snapshot_dependency_view_filters_dependent_outside_inventory() -> None:
    view = _snapshot_view_with_resolved_edge("vendor/use.py", "app.py")

    assert view.dependents_of("app.py") == []


def test_snapshot_dependency_view_filters_dependency_outside_inventory() -> None:
    view = _snapshot_view_with_resolved_edge("app.py", "removed.py")

    assert view.dependencies_of("app.py") == []


def test_snapshot_import_module_name_reads_dynamic_import_with_options() -> None:
    # PR #1308 review: 符号引用匹配使用相同的第一个参数。
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _import_module_name,
    )

    assert (
        _import_module_name("import('./data.json', { with: { type: 'json' } })")
        == "./data.json"
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("import(`./util`)", "./util"),
        ("import(`./${name}`)", None),
        ("module?.require('./util.js')", "./util.js"),
        ("require?.('./util.js')", "./util.js"),
        ("module?.require?.('./util.js')", "./util.js"),
        ("importlib.import_module('pkg.util')", "pkg.util"),
        ("__import__('pkg.util')", "pkg.util"),
        ('/// <reference path="./types.d.ts" />', "./types.d.ts"),
    ],
)
def test_snapshot_import_module_name_reads_static_dynamic_forms(
    text: str, expected: str | None
) -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _import_module_name,
    )

    assert _import_module_name(text) == expected

    assert (
        _import_module_name("import('./util', { with: { type: 'javascript' } })")
        == "./util"
    )


@pytest.mark.parametrize(
    ("spec", "importer", "inventory", "expected"),
    [
        ("./util", "src/main.ts", {"src/util.py", "src/util.ts"}, "src/util.ts"),
        ("./types", "src/main.ts", {"src/types.d.ts"}, "src/types.d.ts"),
        ("./lib", "src/main.js", {"src/lib/index.js"}, "src/lib/index.js"),
        (
            "com.example.Util",
            "src/Main.java",
            {"com/example/Util.java"},
            "com/example/Util.java",
        ),
        ("pkg/lib", "cmd/main.go", {"pkg/lib.go"}, "pkg/lib.go"),
        ("./util.ts", "src/main.ts", {"src/util.ts"}, "src/util.ts"),
        ("./util.py", "src/main.ts", {"src/util.py"}, None),
        ("./", "main.js", {"index.js"}, "index.js"),
        ("react", "src/main.ts", {"react.ts"}, None),
        ("pkg", "main.py", {"pkg.py", "pkg/__init__.py"}, "pkg/__init__.py"),
        ("./util.h", "src/main.c", {"src/util.h"}, "src/util.h"),
        ("./util.hpp", "src/main.cpp", {"src/util.hpp"}, "src/util.hpp"),
        ("pkg.app", "consumer.py", {"src/pkg/app.py"}, "src/pkg/app.py"),
        (
            "com.acme.App",
            "src/main/java/com/acme/Main.java",
            {"src/main/java/com/acme/App.java"},
            "src/main/java/com/acme/App.java",
        ),
        (
            "com.acme.Outer.Inner",
            "src/main/java/com/acme/Main.java",
            {"src/main/java/com/acme/Outer.java"},
            "src/main/java/com/acme/Outer.java",
        ),
        (
            "com.acme.Outer.Inner",
            "Main.java",
            {"com/acme/Outer.java"},
            "com/acme/Outer.java",
        ),
        (
            "com.acme.Outer.Inner",
            "src/main/java/com/acme/Main.java",
            {
                "src/main/java/com/acme/Outer.java",
                "vendor/com/acme/Outer.java",
            },
            None,
        ),
        (
            "pkg.app",
            "consumer.py",
            {"src/pkg/app.py", "vendor/pkg/app.py"},
            None,
        ),
        (
            "pkg.app",
            "consumer.py",
            {"src/pkg/app.py", "vendor/pkg/app/__init__.py"},
            None,
        ),
    ],
)
def test_snapshot_import_resolution_uses_importer_language(
    spec: str,
    importer: str,
    inventory: set[str],
    expected: str | None,
) -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _resolve_import_spec_from_inventory,
    )

    assert (
        _resolve_import_spec_from_inventory(spec, importer, frozenset(inventory))
        == expected
    )


def test_python_import_root_rejects_unrelated_resolution() -> None:
    # PR #1308 review: 只有被已解析模块证明的根目录才能界定 init 文件。
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _python_import_root,
    )

    assert _python_import_root("pkg.app", "vendor/other.py") is None


def test_snapshot_dependency_view_finds_root_index_dependent() -> None:
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

    view = build_snapshot_file_dependency_view(conn, "index.js")

    assert view.dependents_of("index.js") == ["main.js"]


def test_snapshot_import_resolution_rejects_empty_spec() -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _resolve_import_spec_from_inventory,
    )

    assert _resolve_import_spec_from_inventory("", "pkg/routes.py", frozenset()) is None


@pytest.mark.parametrize(
    ("file_path", "imports_json", "create_table", "expected"),
    [
        ("app.py", "[]", False, None),
        (b"app.py", "[]", True, {}),
        ("app.py", "not-json", True, None),
        ("app.py", "{}", True, None),
        ("app.py", "[42]", True, None),
    ],
    ids=["missing-table", "invalid-path", "invalid-json", "scalar", "invalid-item"],
)
def test_snapshot_import_texts_fail_closed_on_invalid_projection(
    file_path: str | bytes,
    imports_json: str,
    create_table: bool,
    expected: dict[str, list[str]] | None,
) -> None:
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _snapshot_import_texts,
    )

    conn = sqlite3.connect(":memory:")
    if create_table:
        conn.execute("CREATE TABLE ast_index (file_path, imports_json TEXT)")
        conn.execute("INSERT INTO ast_index VALUES (?, ?)", (file_path, imports_json))

    assert _snapshot_import_texts(conn, frozenset({"app.py"})) == expected


def test_snapshot_import_targets_ignore_non_import_text() -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _import_targets_from_text,
    )

    assert (
        _import_targets_from_text(
            "configure('pkg.util')", "app.py", frozenset({"pkg/util.py"})
        )
        == set()
    )


@pytest.mark.parametrize(
    ("text", "importer"),
    [
        ("import(`./util`)", "src/main.ts"),
        ("importlib.import_module('pkg.util')", "app.py"),
        ("__import__('pkg.util')", "app.py"),
    ],
)
def test_snapshot_import_targets_resolve_literal_dynamic_imports(
    text: str, importer: str
) -> None:
    # PR #1308 review: 字面量动态加载属于快照依赖。
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _import_targets_from_text,
    )

    inventory = frozenset({"src/util.ts", "pkg/util.py"})
    expected = {"src/util.ts"} if importer.endswith(".ts") else {"pkg/util.py"}
    assert _import_targets_from_text(text, importer, inventory) == expected

    assert (
        _import_targets_from_text("raise RuntimeError", "routes.py", frozenset())
        == set()
    )


def test_snapshot_import_targets_preserve_members_after_inline_comments() -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _import_targets_from_text,
    )

    inventory = frozenset({"pkg/b.py"})

    assert _import_targets_from_text(
        "from pkg import (a, # first member\n b)", "routes.py", inventory
    ) == {"pkg/b.py"}


@pytest.mark.parametrize("loader", ["import", "require"])
def test_projected_alias_parser_excludes_canonical_loaders(loader: str) -> None:
    assert helpers._jsts_projected_alias_spec(f"{loader}('./util')") is None


def test_projected_alias_parser_handles_template_literals() -> None:
    assert helpers._jsts_projected_alias_spec("load(`./util`)") == "./util"
    assert helpers._jsts_projected_alias_spec("import(`./util`)") is None
    assert helpers._jsts_projected_alias_spec("load(`./${name}`)") is None


def test_python_relative_inventory_match_can_be_empty() -> None:
    assert (
        helpers._python_inventory_matches(
            ".missing", "pkg/app.py", frozenset({"pkg/app.py"})
        )
        == set()
    )


def test_dependency_view_ignores_calls_when_loader_projection_is_invalid() -> None:
    conn = _projection_conn(
        [
            ("app.py", [{"text": "if ("}, {"text": "load('pkg.util')"}]),
            ("pkg/util.py", []),
        ]
    )
    conn.row_factory = sqlite3.Row

    view = helpers.build_snapshot_file_dependency_view(
        conn,
        "app.py",
        inventory=frozenset({"app.py", "pkg/util.py"}),
    )

    assert view.dependencies_of("app.py") == []
    assert view.dependents_of("app.py") == []


def test_python_inventory_matches_root_and_source_root_candidates() -> None:
    inventory = frozenset({"pkg/util.py", "src/pkg/util.py"})

    assert helpers._python_inventory_matches("pkg.util", "app.py", inventory) == {
        "pkg/util.py",
        "src/pkg/util.py",
    }


def test_python_resolver_rejects_root_and_source_root_ambiguity() -> None:
    inventory = frozenset({"app.py", "pkg/util.py", "src/pkg/util.py"})

    assert (
        helpers._resolve_import_spec_from_inventory("pkg.util", "app.py", inventory)
        is None
    )


def test_python_resolver_rejects_duplicate_normalized_candidate() -> None:
    inventory = frozenset({"pkg.py", "./pkg.py"})

    assert (
        helpers._resolve_import_spec_from_inventory("pkg", "app.py", inventory) is None
    )
