"""#1376：test_safe_to_edit_tool_java_imports 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import json
import sqlite3

import pytest

import tests.unit.mcp._safe_to_edit_tool_helpers as _fixtures
from tests.unit.mcp._safe_to_edit_tool_helpers import _projection_conn
from tree_sitter_analyzer.mcp.tools.utils import safe_to_edit_helpers as helpers

tool = _fixtures.tool
_close_index_snapshot_registry = _fixtures._close_index_snapshot_registry


def test_snapshot_dependency_view_reads_javascript_projection_both_ways() -> None:
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
                json.dumps([{"text": "import './setup';", "line": 1}]),
            ),
            ("src/setup.ts", "[]"),
        ],
    )

    main_view = build_snapshot_file_dependency_view(conn, "src/main.ts")
    setup_view = build_snapshot_file_dependency_view(conn, "src/setup.ts")

    assert main_view.dependencies_of("src/main.ts") == ["src/setup.ts"]
    assert setup_view.dependents_of("src/setup.ts") == ["src/main.ts"]


def test_snapshot_dependency_view_reads_java_class_for_name() -> None:
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
                "src/main/java/com/acme/Main.java",
                json.dumps([{"text": 'Class.forName("com.acme.Util")'}]),
            ),
            ("src/main/java/com/acme/Util.java", "[]"),
        ],
    )

    view = build_snapshot_file_dependency_view(conn, "src/main/java/com/acme/Main.java")

    assert view.dependencies_of("src/main/java/com/acme/Main.java") == [
        "src/main/java/com/acme/Util.java"
    ]


def test_snapshot_dependency_view_reads_static_java_class_for_name() -> None:
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
                "src/main/java/com/acme/Main.java",
                json.dumps(
                    [
                        {"text": "import static java.lang.Class.forName;"},
                        {"text": 'forName("com.acme.Util")'},
                    ]
                ),
            ),
            ("src/main/java/com/acme/Util.java", "[]"),
        ],
    )

    view = build_snapshot_file_dependency_view(conn, "src/main/java/com/acme/Main.java")

    assert view.dependencies_of("src/main/java/com/acme/Main.java") == [
        "src/main/java/com/acme/Util.java"
    ]


def test_snapshot_java_import_resolves_maven_source_root() -> None:
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
                "src/main/java/com/acme/Main.java",
                json.dumps([{"text": "import com.acme.Util;"}]),
            ),
            ("src/main/java/com/acme/Util.java", "[]"),
        ],
    )

    view = build_snapshot_file_dependency_view(conn, "src/main/java/com/acme/Main.java")
    assert view.dependencies_of("src/main/java/com/acme/Main.java") == [
        "src/main/java/com/acme/Util.java"
    ]


def test_snapshot_import_targets_ignore_invalid_java_direct_spec() -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _import_targets_from_text,
    )

    assert (
        _import_targets_from_text("import pkg-name;", "Routes.java", frozenset())
        == set()
    )


@pytest.mark.parametrize(
    ("projection", "expected"),
    [
        ('Class.forName("com.acme.Util")', True),
        ("Class.forName(className)", False),
    ],
)
def test_java_reflection_projection_requires_literal_target(
    projection: str, expected: bool
) -> None:
    import sqlite3

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _java_reflection_projection_complete,
    )

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?)",
        [
            ("src/Main.java", json.dumps([{"text": projection}])),
            ("src/com/acme/Util.java", "[]"),
        ],
    )

    assert (
        _java_reflection_projection_complete(
            conn, frozenset({"src/Main.java", "src/com/acme/Util.java"})
        )
        is expected
    )


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


def test_java_inventory_match_prefers_exact_candidate() -> None:
    assert helpers._java_inventory_matches(
        "com.acme.Util$Inner", frozenset({"com/acme/Util.java"})
    ) == {"com/acme/Util.java"}


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
