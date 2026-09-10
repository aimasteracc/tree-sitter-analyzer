"""#1376：test_safe_to_edit_tool_include_projection 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import json
import sqlite3

import pytest

import tests.unit.mcp._safe_to_edit_tool_helpers as _fixtures
from tests.unit.mcp._safe_to_edit_tool_helpers import _projection_conn
from tree_sitter_analyzer.ast_cache import _AST_CACHE_EXTRACTOR_VERSION
from tree_sitter_analyzer.mcp.tools.utils import safe_to_edit_helpers as helpers

tool = _fixtures.tool
_close_index_snapshot_registry = _fixtures._close_index_snapshot_registry


def test_snapshot_syntax_envelope_marks_ambiguous_include_root_unavailable() -> None:
    # PR #1308 review: 两个清单后缀匹配不能认证 include 根目录。
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        build_snapshot_syntax_causal_envelope,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE edges ("
        "id INTEGER PRIMARY KEY, kind TEXT, file_path TEXT, "
        "callee_name TEXT, callee_resolved_file TEXT)"
    )
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT, imports_json TEXT, symbols_json TEXT)"
    )
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?, '{}')",
        [
            (
                "src/main.c",
                json.dumps([{"text": '#include "project/util.h"'}]),
            ),
            ("include-one/project/util.h", "[]"),
            ("include-two/project/util.h", "[]"),
        ],
    )

    envelope = build_snapshot_syntax_causal_envelope(
        conn,
        "include-one/project/util.h",
        "include-one/project/util.h",
    )

    assert envelope == {
        "dependents": None,
        "dependencies": None,
        "exercising_tests": None,
        "constraint_verdict": "unknown",
        "verification_command": None,
        "stale_edges": None,
    }


@pytest.mark.parametrize("include_text", ["#include HDR", "#include <util.h>"])
def test_snapshot_syntax_envelope_marks_nonquoted_include_unavailable(
    include_text: str,
) -> None:
    # PR #1308: 依赖宏或构建配置的 include 没有快照绑定的解析结果。
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        build_snapshot_syntax_causal_envelope,
    )

    target = "include/util.h"
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE edges ("
        "id INTEGER PRIMARY KEY, kind TEXT, file_path TEXT, "
        "callee_name TEXT, callee_resolved_file TEXT)"
    )
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT, imports_json TEXT, symbols_json TEXT)"
    )
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?, '{}')",
        [
            ("src/main.c", json.dumps([{"text": include_text}])),
            (target, "[]"),
        ],
    )

    envelope = build_snapshot_syntax_causal_envelope(conn, target, target)

    assert envelope == {
        "dependents": None,
        "dependencies": None,
        "exercising_tests": None,
        "constraint_verdict": "unknown",
        "verification_command": None,
        "stale_edges": None,
    }


def test_snapshot_syntax_envelope_rejects_uncaptured_include_root() -> None:
    # 唯一的后缀匹配不能捕获编译器 -I 搜索顺序。
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        build_snapshot_syntax_causal_envelope,
    )

    target = "include/project/util.h"
    importer = "src/main.c"
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE edges ("
        "id INTEGER PRIMARY KEY, kind TEXT, file_path TEXT, "
        "callee_name TEXT, callee_resolved_file TEXT)"
    )
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT, imports_json TEXT, "
        "symbols_json TEXT, extractor_version INTEGER)"
    )
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?, "
        '\'{"truncated_depth": false, "import_projection_complete": true, '
        '"syntax_error": false}\', ?)',
        [
            (
                importer,
                json.dumps(
                    [
                        {"text": "#define DEBUG 1"},
                        {"text": '#include "project/util.h"'},
                    ]
                ),
                _AST_CACHE_EXTRACTOR_VERSION,
            ),
            (target, "[]", _AST_CACHE_EXTRACTOR_VERSION),
        ],
    )

    envelope = build_snapshot_syntax_causal_envelope(conn, target, target)

    assert envelope == {
        "dependents": None,
        "dependencies": None,
        "exercising_tests": None,
        "constraint_verdict": "unknown",
        "verification_command": None,
        "stale_edges": None,
    }


def test_snapshot_syntax_envelope_rejects_missing_c_projection_table() -> None:
    # PR #1308 review: 缺少 include 投影时，C 因果关系不可用。
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        build_snapshot_syntax_causal_envelope,
    )

    target = "include/project/util.h"
    envelope = build_snapshot_syntax_causal_envelope(
        sqlite3.connect(":memory:"),
        target,
        target,
        inventory=frozenset({target}),
    )

    assert envelope["stale_edges"] is None


def test_snapshot_syntax_envelope_rejects_unprojected_c_inventory_file() -> None:
    # PR #1308 review: 每个潜在 C 导入方都必须有 imports 投影。
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        build_snapshot_syntax_causal_envelope,
    )

    target = "include/project/util.h"
    absent = "src/main.c"
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT, imports_json TEXT, symbols_json TEXT)"
    )
    conn.execute("INSERT INTO ast_index VALUES (?, '[]', '{}')", (target,))

    envelope = build_snapshot_syntax_causal_envelope(
        conn,
        target,
        target,
        inventory=frozenset({target, absent}),
    )

    assert envelope["verification_command"] is None


def test_c_same_directory_include_certifies_with_non_import_projection() -> None:
    inventory = frozenset({"src/main.c", "src/util.h"})
    conn = _projection_conn(
        [
            ("src/main.c", [{"text": "int value;"}, {"text": '#include "util.h"'}]),
            ("src/util.h", []),
        ]
    )

    assert helpers._quoted_include_projection_complete(conn, "src/util.h", inventory)


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


def test_include_next_projection_fails_closed() -> None:
    conn = _projection_conn(
        [
            ("src/main.cpp", [{"text": '#include_next "util.h"'}]),
            ("include/util.h", []),
        ]
    )
    inventory = frozenset({"src/main.cpp", "include/util.h"})

    assert not helpers._quoted_include_projection_complete(
        conn, "include/util.h", inventory
    )


def test_include_projection_rejects_missing_snapshot_table() -> None:
    assert (
        helpers._quoted_include_projection_complete(
            sqlite3.connect(":memory:"), "include/util.h", frozenset()
        )
        is False
    )


def test_include_projection_rejects_unprojected_inventory_file() -> None:
    conn = _projection_conn([("include/util.h", [])])

    assert (
        helpers._quoted_include_projection_complete(
            conn,
            "include/util.h",
            frozenset({"include/util.h", "src/main.c"}),
        )
        is False
    )
