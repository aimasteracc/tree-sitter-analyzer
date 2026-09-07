"""#1376：test_safe_to_edit_tool_stale_edges 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import json
import sqlite3

import pytest

import tests.unit.mcp._safe_to_edit_tool_helpers as _fixtures
from tests.unit.mcp._safe_to_edit_tool_helpers import (
    _BrokenConnection,
    _reverse_dependency_conn,
)
from tree_sitter_analyzer.mcp.tools.utils import safe_to_edit_helpers as helpers

tool = _fixtures.tool
_close_index_snapshot_registry = _fixtures._close_index_snapshot_registry


def test_snapshot_edge_names_exclude_init_basename() -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _edge_import_names_for_target,
    )

    inventory = frozenset({"pkg/__init__.py"})

    assert "__init__" not in _edge_import_names_for_target("pkg/__init__.py", inventory)


def test_snapshot_causal_view_rejects_malformed_resolved_edge() -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        build_snapshot_file_dependency_view,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE edges ("
        "id INTEGER PRIMARY KEY, kind TEXT, file_path TEXT, "
        "callee_name TEXT, callee_resolved_file TEXT)"
    )
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.execute("INSERT INTO ast_index VALUES ('app.py', '[]')")
    conn.execute(
        "INSERT INTO edges VALUES (1, 'calls', 'app.py', 'normalize', ?)",
        (sqlite3.Binary(b"util.py"),),
    )

    with pytest.raises(ValueError, match="CORRUPT_INDEX"):
        build_snapshot_file_dependency_view(conn, "app.py")


def test_snapshot_stale_edges_rejects_malformed_relevant_row() -> None:
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
    conn.execute("INSERT INTO ast_index VALUES ('app.py', '[]')")
    conn.execute(
        "INSERT INTO edges VALUES (1, 'calls', ?, 'handler', 'app.py')",
        (sqlite3.Binary(b"routes.py"),),
    )

    with pytest.raises(ValueError, match="CORRUPT_INDEX"):
        snapshot_stale_edges(conn, "app.py")


def test_snapshot_needle_importers_fails_closed_without_projection() -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _snapshot_needle_importers,
    )

    conn = sqlite3.connect(":memory:")
    with pytest.raises(ValueError, match="CORRUPT_INDEX"):
        _snapshot_needle_importers(conn, "app.py", {"routes.py"})


@pytest.mark.parametrize(
    ("stored_path", "imports_json", "candidates"),
    [
        (b"routes.py", "[]", {b"routes.py"}),
        ("routes.py", "not-json", {"routes.py"}),
        ("routes.py", "42", {"routes.py"}),
        ("routes.py", "[42]", {"routes.py"}),
        (None, None, {"routes.py"}),
    ],
    ids=["blob-path", "invalid-json", "scalar-json", "invalid-item", "missing-row"],
)
def test_snapshot_needle_importers_rejects_malformed_projection(
    stored_path: str | bytes | None,
    imports_json: str | None,
    candidates: set[str],
) -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _snapshot_needle_importers,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    if stored_path is not None:
        conn.execute("INSERT INTO ast_index VALUES (?, ?)", (stored_path, imports_json))

    with pytest.raises(ValueError, match="CORRUPT_INDEX"):
        _snapshot_needle_importers(
            conn,
            "app.py",
            candidates,
            inventory=frozenset({"app.py", "routes.py"}),
        )


def test_snapshot_needle_importers_ignores_unrelated_import_text() -> None:
    import json

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _snapshot_needle_importers,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.execute(
        "INSERT INTO ast_index VALUES ('routes.py', ?)",
        (json.dumps([{"text": "import other"}]),),
    )

    assert _snapshot_needle_importers(conn, "app.py", {"routes.py"}) == set()


def test_snapshot_needle_importers_ignores_calls_after_invalid_loader_projection() -> (
    None
):
    import json

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _snapshot_needle_importers,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE ast_index (file_path TEXT, imports_json TEXT)")
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, ?)",
        [
            (
                "routes.py",
                json.dumps([{"text": "if ("}, {"text": "load('app')"}]),
            ),
            ("app.py", "[]"),
        ],
    )

    assert _snapshot_needle_importers(conn, "app.py", {"routes.py"}) == set()


def test_snapshot_stale_edges_uses_bounded_snapshot_queries() -> None:
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
    conn.execute("INSERT INTO ast_index VALUES ('app.py', '[]')")
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, '[]')",
        [(f"caller_{index}.py",) for index in range(1, 101)],
    )
    conn.executemany(
        "INSERT INTO edges VALUES (?, 'imports', ?, ?, '')",
        [(index, f"caller_{index}.py", f"missing_{index}") for index in range(1, 101)],
    )
    queries: list[str] = []
    conn.set_trace_callback(queries.append)

    assert snapshot_stale_edges(conn, "app.py") == []
    assert len(queries) == 2
    assert "SELECT file_path, imports_json FROM ast_index" not in queries


def test_snapshot_stale_edges_fails_closed_without_required_schema() -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        snapshot_stale_edges,
    )

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE edges (kind TEXT, file_path TEXT)")

    with pytest.raises(ValueError, match="CORRUPT_INDEX"):
        snapshot_stale_edges(conn, "app.py")


def test_reverse_dependency_snapshot_uses_resolved_and_import_edges() -> None:
    conn = _reverse_dependency_conn(
        [("app.py", "[]"), ("pkg/util.py", "[]"), ("outside.py", "[]")]
    )
    conn.execute(
        "CREATE TABLE edges (kind TEXT, file_path, callee_name, callee_resolved_file)"
    )
    conn.executemany(
        "INSERT INTO edges VALUES (?, ?, ?, ?)",
        [
            ("calls", "app.py", "run", "pkg/util.py"),
            ("imports", "app.py", "pkg.util", ""),
            ("imports", "app.py", "missing.module", ""),
            ("imports", "app.py", 7, ""),
            ("calls", "outside.py", "run", "pkg/util.py"),
        ],
    )

    assert helpers._snapshot_reverse_dependencies(
        conn, frozenset({"app.py", "pkg/util.py"})
    ) == {"pkg/util.py": {"app.py"}}


def test_reverse_dependency_snapshot_rejects_corrupt_resolved_edge() -> None:
    conn = _reverse_dependency_conn([("app.py", "[]"), ("pkg/util.py", "[]")])
    conn.execute(
        "CREATE TABLE edges (kind TEXT, file_path, callee_name, callee_resolved_file)"
    )
    conn.execute("INSERT INTO edges VALUES ('calls', 7, 'run', 'pkg/util.py')")

    with pytest.raises(ValueError, match="CORRUPT_INDEX"):
        helpers._snapshot_reverse_dependencies(
            conn, frozenset({"app.py", "pkg/util.py"})
        )


@pytest.mark.parametrize(
    ("caller", "raw_imports"),
    [
        (None, "[]"),
        ("app.py", "not-json"),
        ("app.py", "{}"),
        ("app.py", "[1]"),
    ],
)
def test_reverse_dependency_snapshot_rejects_corrupt_ast_rows(
    caller: object, raw_imports: object
) -> None:
    conn = _reverse_dependency_conn([(caller, raw_imports)])

    with pytest.raises(ValueError, match="CORRUPT_INDEX"):
        helpers._snapshot_reverse_dependencies(conn, frozenset({"app.py"}))


def test_reverse_dependency_snapshot_skips_outside_and_invalid_projection_rows() -> (
    None
):
    conn = _reverse_dependency_conn(
        [("outside.py", "not-json"), ("app.py", json.dumps(["if ("]))]
    )

    assert helpers._snapshot_reverse_dependencies(conn, frozenset({"app.py"})) == {}


def test_reverse_dependency_snapshot_degrades_when_tables_are_unreadable() -> None:
    assert (
        helpers._snapshot_reverse_dependencies(_BrokenConnection(), frozenset()) == {}
    )
