"""#1376：test_safe_to_edit_tool_java_projection 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import json
import sqlite3

import pytest

import tests.unit.mcp._safe_to_edit_tool_helpers as _fixtures
from tree_sitter_analyzer.mcp.tools.utils import safe_to_edit_helpers as helpers

tool = _fixtures.tool
_close_index_snapshot_registry = _fixtures._close_index_snapshot_registry


def test_snapshot_dependency_view_matches_javascript_directory_index_import() -> None:
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
                json.dumps([{"text": "import './lib';", "line": 1}]),
            ),
            ("src/lib/index.ts", "[]"),
        ],
    )

    view = build_snapshot_file_dependency_view(conn, "src/lib/index.ts")

    assert view.dependents_of("src/lib/index.ts") == ["src/main.ts"]


def test_snapshot_dependency_view_rejects_bare_javascript_package() -> None:
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
            ("src/main.ts", json.dumps([{"text": "import 'react'"}])),
            ("react.ts", "[]"),
        ],
    )

    view = build_snapshot_file_dependency_view(conn, "src/main.ts")

    assert view.dependencies_of("src/main.ts") == []


def test_snapshot_java_static_import_resolves_owner_class() -> None:
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
                "src/main/java/com/acme/Main.java",
                json.dumps([{"text": "import static com.acme.Util.helper;"}]),
            ),
            ("src/main/java/com/acme/Util.java", "[]"),
        ],
    )

    view = build_snapshot_file_dependency_view(conn, "src/main/java/com/acme/Main.java")

    assert view.dependencies_of("src/main/java/com/acme/Main.java") == [
        "src/main/java/com/acme/Util.java"
    ]


def test_snapshot_java_wildcard_import_expands_indexed_package() -> None:
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
                "src/main/java/com/acme/Main.java",
                json.dumps([{"text": "import com.acme.*;"}]),
            ),
            ("src/main/java/com/acme/Helper.java", "[]"),
            ("src/main/java/com/acme/Util.java", "[]"),
            ("src/main/java/com/acme/sub/Nested.java", "[]"),
        ],
    )

    view = build_snapshot_file_dependency_view(conn, "src/main/java/com/acme/Main.java")
    reverse_view = build_snapshot_file_dependency_view(
        conn, "src/main/java/com/acme/Util.java"
    )

    assert view.dependencies_of("src/main/java/com/acme/Main.java") == [
        "src/main/java/com/acme/Helper.java",
        "src/main/java/com/acme/Util.java",
    ]
    assert reverse_view.dependents_of("src/main/java/com/acme/Util.java") == [
        "src/main/java/com/acme/Main.java"
    ]


def test_snapshot_java_wildcard_import_marks_package_edge_stale() -> None:
    # PR #1308 review: 未解析的通配符行以包名作为 callee_name。

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
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
            (
                "src/main/java/com/acme/Main.java",
                json.dumps([{"text": "import com.acme.*;"}]),
            ),
            ("src/main/java/com/acme/Util.java", "[]"),
        ],
    )
    conn.execute(
        "INSERT INTO edges VALUES "
        "(1, 'imports', 'src/main/java/com/acme/Main.java', 'com.acme', '')"
    )

    assert snapshot_stale_edges(conn, "src/main/java/com/acme/Util.java") == [
        "imports:src/main/java/com/acme/Main.java->src/main/java/com/acme/Util.java#1"
    ]


def test_snapshot_import_resolution_bounds_javascript_paths() -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _projection_search_tokens,
        _resolve_import_spec_from_inventory,
    )

    inventory = frozenset(
        {"shared.ts", "src/main.ts", "src/util.mts", "pkg/__init__.py"}
    )

    assert (
        _resolve_import_spec_from_inventory("../shared", "src/main.ts", inventory)
        == "shared.ts"
    )
    assert (
        _resolve_import_spec_from_inventory("../shared", "main.ts", inventory) is None
    )
    assert _resolve_import_spec_from_inventory("./", "main.ts", inventory) is None
    assert (
        _resolve_import_spec_from_inventory("./util.mts", "src/main.js", inventory)
        == "src/util.mts"
    )
    assert "./__init__" not in _projection_search_tokens("pkg/__init__.py")


@pytest.mark.parametrize("importer_suffix", ["Use.kt", "Use.scala"])
def test_snapshot_syntax_envelope_marks_mixed_jvm_java_unavailable(
    importer_suffix: str,
) -> None:
    # PR #1308 review: 非 Java 的 JVM 引用缺少认证投影。

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
                "src/main/java/com/acme/Util.java",
                json.dumps([{"text": "package com.acme;"}]),
            ),
            (
                f"src/test/jvm/com/acme/{importer_suffix}",
                json.dumps([{"text": "import com.acme.Util"}]),
            ),
        ],
    )

    envelope = build_snapshot_syntax_causal_envelope(
        conn,
        "src/main/java/com/acme/Util.java",
        "src/main/java/com/acme/Util.java",
    )

    assert envelope == {
        "dependents": None,
        "dependencies": None,
        "exercising_tests": None,
        "constraint_verdict": "unknown",
        "verification_command": None,
        "stale_edges": None,
    }


def test_snapshot_syntax_envelope_marks_same_package_java_unavailable() -> None:
    # PR #1308 review: 即使没有 import 行，也可能存在同包引用。

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
    package_projection = json.dumps([{"text": "package com.acme;"}])
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?, '{}')",
        [
            ("src/main/java/com/acme/Util.java", package_projection),
            ("src/test/java/com/acme/UtilTest.java", package_projection),
        ],
    )

    envelope = build_snapshot_syntax_causal_envelope(
        conn,
        "src/main/java/com/acme/Util.java",
        "src/main/java/com/acme/Util.java",
    )

    assert envelope == {
        "dependents": None,
        "dependencies": None,
        "exercising_tests": None,
        "constraint_verdict": "unknown",
        "verification_command": None,
        "stale_edges": None,
    }


def test_snapshot_syntax_envelope_certifies_single_java_file() -> None:
    # PR #1308 review: 同包处理失败关闭，同时让可证明的项目仍可使用。

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
        "CREATE TABLE ast_index (file_path TEXT, imports_json TEXT, "
        "symbols_json TEXT, extractor_version INTEGER)"
    )
    conn.execute(
        "INSERT INTO ast_index VALUES (?, ?, "
        '\'{"truncated_depth": false, "import_projection_complete": true, '
        '"syntax_error": false}\', 38)',
        (
            "src/main/java/com/acme/Util.java",
            json.dumps([{"text": "package com.acme;"}]),
        ),
    )

    envelope = build_snapshot_syntax_causal_envelope(
        conn,
        "src/main/java/com/acme/Util.java",
        "src/main/java/com/acme/Util.java",
    )

    assert envelope == {
        "dependents": [],
        "dependencies": [],
        "exercising_tests": [],
        "constraint_verdict": "unknown",
        "verification_command": None,
        "stale_edges": [],
    }


def test_snapshot_syntax_envelope_rejects_missing_java_projection() -> None:
    # PR #1308 review: Java 清单中的每个成员都必须有导入投影。

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        build_snapshot_syntax_causal_envelope,
    )

    target = "src/main/java/com/acme/Util.java"
    absent = "src/test/java/org/example/Use.java"
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT, imports_json TEXT, symbols_json TEXT)"
    )
    conn.execute(
        "INSERT INTO ast_index VALUES (?, ?, '{}')",
        (target, json.dumps([{"text": "package com.acme;"}])),
    )

    envelope = build_snapshot_syntax_causal_envelope(
        conn,
        target,
        target,
        inventory=frozenset({target, absent}),
    )

    assert envelope["dependents"] is None


def test_snapshot_syntax_envelope_rejects_conflicting_java_packages() -> None:
    # PR #1308 review: 损坏的多包投影不能认证 Java。

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        build_snapshot_syntax_causal_envelope,
    )

    target = "src/main/java/com/acme/Util.java"
    other = "src/main/java/org/example/Use.java"
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT, imports_json TEXT, "
        "symbols_json TEXT, extractor_version INTEGER)"
    )
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?, "
        '\'{"truncated_depth": false, "import_projection_complete": true, '
        '"syntax_error": false}\', 38)',
        [
            (
                target,
                json.dumps(
                    [
                        {"text": "package com.acme;"},
                        {"text": "package forged.name;"},
                    ]
                ),
            ),
            (other, json.dumps([{"text": "package org.example;"}])),
        ],
    )

    envelope = build_snapshot_syntax_causal_envelope(conn, target, target)

    assert envelope["dependencies"] is None


def test_snapshot_syntax_envelope_rejects_unprojected_java_target() -> None:
    # PR #1308 review: 被检查的 Java 目标自身也必须具有投影。

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        build_snapshot_syntax_causal_envelope,
    )

    target = "src/main/java/com/acme/Missing.java"
    first = "src/main/java/com/acme/Util.java"
    second = "src/main/java/org/example/Use.java"
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT, imports_json TEXT, symbols_json TEXT)"
    )
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?, '{}')",
        [
            (first, json.dumps([{"text": "package com.acme;"}])),
            (second, json.dumps([{"text": "package org.example;"}])),
        ],
    )

    envelope = build_snapshot_syntax_causal_envelope(
        conn,
        target,
        target,
        inventory=frozenset({first, second}),
    )

    assert envelope["exercising_tests"] is None


def test_certified_java_facts_reject_unprojected_jvm_languages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(helpers, "_symbol_walk_projections_complete", lambda *_: True)

    assert (
        helpers._certified_import_facts_available(
            "src/Util.java",
            conn=object(),
            inventory=frozenset({"src/Util.java", "src/Use.kt"}),
        )
        is False
    )


def test_java_multi_file_projection_fails_closed_for_qualified_references() -> None:
    inventory = frozenset({"src/com/acme/Util.java", "src/org/example/Use.java"})

    assert (
        helpers._java_same_package_projection_complete(
            object(), "src/com/acme/Util.java", inventory
        )
        is False
    )
