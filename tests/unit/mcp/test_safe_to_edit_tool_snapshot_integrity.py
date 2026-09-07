"""#1376：test_safe_to_edit_tool_snapshot_integrity 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import json
import os
import sqlite3
from pathlib import Path

import pytest

import tests.unit.mcp._safe_to_edit_tool_helpers as _fixtures
from tests.unit.mcp._safe_to_edit_tool_helpers import _BrokenConnection, _symbol_conn
from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import (
    SafeToEditTool,
)
from tree_sitter_analyzer.mcp.tools.utils import safe_to_edit_helpers as helpers

tool = _fixtures.tool
_close_index_snapshot_registry = _fixtures._close_index_snapshot_registry


def test_live_violations_query_degrades_on_corrupt_db_file(
    tmp_path: Path,
) -> None:
    """非 SQLite 的 index.db 降级为空违规列表。"""
    from tree_sitter_analyzer.mcp.tools.utils.constraint_violation_query import (
        violations_for_files,
    )

    (tmp_path / ".ast-cache").mkdir()
    (tmp_path / ".ast-cache" / "index.db").write_text(
        "not-a-sqlite-database", encoding="utf-8"
    )
    assert violations_for_files(str(tmp_path), ["app.py"]) == []


def test_snapshot_dependency_view_degrades_on_closed_conn() -> None:
    """不可读连接降级为空视图，不抛出异常。"""

    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        build_snapshot_file_dependency_view,
    )

    conn = sqlite3.connect(":memory:")
    conn.close()
    view = build_snapshot_file_dependency_view(conn, "app.py")
    assert view.dependents_of("app.py") == []
    assert view.dependencies_of("app.py") == []


def test_snapshot_constraint_query_reads_from_given_conn() -> None:
    """conn 变体返回查询行；缺表时降级为 []。"""

    from tree_sitter_analyzer.mcp.tools.utils.constraint_violation_query import (
        violations_for_files_from_conn,
    )

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE ast_constraint_violations ("
        "rule_id TEXT NOT NULL, caller_file TEXT NOT NULL, "
        "caller_name TEXT NOT NULL, caller_line INTEGER NOT NULL, "
        "callee_name TEXT NOT NULL, callee_file TEXT NOT NULL DEFAULT '', "
        "severity TEXT NOT NULL, detected_at INTEGER NOT NULL)"
    )
    conn.execute(
        "INSERT INTO ast_constraint_violations VALUES "
        "('R1', 'app.py', 'app', 1, 'secret', '', 'error', 1)"
    )
    rows = violations_for_files_from_conn(conn, ["app.py"])
    assert rows == [
        {
            "rule_id": "R1",
            "caller_file": "app.py",
            "caller_name": "app",
            "caller_line": 1,
            "callee_name": "secret",
            "callee_file": "",
            "severity": "error",
            "detected_at": 1,
            "factor": "constraint_violation",
        }
    ]
    assert violations_for_files_from_conn(conn, []) == []
    bare = sqlite3.connect(":memory:")
    assert violations_for_files_from_conn(bare, ["app.py"]) == []


# RFC-0022 P0.4: 快照依赖视图遇到
# schema 漂移（旧连接缺少 edges/ast_index 表）时降级为空视图，确保
# schema 漂移后，路由仍应如实分类，而不是崩溃。
def test_snapshot_dependency_view_degrades_on_schema_drift() -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        build_snapshot_file_dependency_view,
        snapshot_inventory,
    )

    conn = sqlite3.connect(":memory:")
    view = build_snapshot_file_dependency_view(conn, "app.py")
    assert view.dependents_of("app.py") == []
    assert view.dependencies_of("app.py") == []
    # 不可读清单降级为空集合，保持失败关闭。
    assert snapshot_inventory(conn) == frozenset()

    # edges 存在而 ast_index 缺失时，精确解析会查询缺失的
    # 表，并降级为未索引。
    conn.execute("CREATE TABLE edges (file_path TEXT, callee_name TEXT, kind TEXT)")
    conn.execute("INSERT INTO edges VALUES ('routes.py', 'app', 'imports')")
    partial = build_snapshot_file_dependency_view(conn, "app.py")
    assert partial.dependents_of("app.py") == []

    # Codex P2 (#1299): 当前版本的 edges 表虽存在但损坏时，
    # 若缺少读取器所选取的 callee_name 列，路由必须失败，
    # 不能静默降级为空视图，否则会低估
    # 风险。
    import pytest

    damaged = sqlite3.connect(":memory:")
    damaged.row_factory = sqlite3.Row
    damaged.execute(
        "CREATE TABLE edges (source_node_id TEXT, target_node_id TEXT, "
        "kind TEXT, file_path TEXT)"
    )
    with pytest.raises(ValueError, match="CORRUPT_INDEX"):
        build_snapshot_file_dependency_view(damaged, "app.py")


@pytest.mark.parametrize("stored_path", [None, "", 42, b"app.py"])
def test_snapshot_inventory_rejects_malformed_paths(stored_path: object) -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        snapshot_inventory,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE ast_index (file_path)")
    conn.execute("INSERT INTO ast_index VALUES (?)", (stored_path,))

    with pytest.raises(ValueError, match="CORRUPT_INDEX"):
        snapshot_inventory(conn)


def test_certified_facts_load_inventory_when_not_precomputed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    import tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers as helpers

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT, symbols_json TEXT, imports_json TEXT)"
    )
    conn.execute("INSERT INTO ast_index VALUES ('app.py', '{}', '[]')")
    inventory = frozenset({"app.py"})
    loads: list[object] = []

    def load_inventory(snapshot_conn):
        loads.append(snapshot_conn)
        return inventory

    monkeypatch.setattr(helpers, "snapshot_inventory", load_inventory)
    monkeypatch.setattr(
        helpers,
        "_certified_exercising_tests",
        lambda snapshot_conn, rel_path, dependents, **_kwargs: [],
    )
    context = helpers.SafeToEditContext(
        file_path="app.py",
        edit_type="refactor",
        resolved_path=str(tmp_path / "app.py"),
        project_root=str(tmp_path),
        graph=helpers.FileDependencyView(
            rel_path="app.py", dependencies=set(), dependents=set()
        ),
        scorer=SimpleNamespace(
            score_file=lambda *args, **kwargs: SimpleNamespace(
                grade="A", total=100, dimensions={}
            )
        ),
        snapshot_conn=conn,
    )

    helpers._collect_safe_to_edit_facts(context)

    assert loads == [conn]


def test_certified_facts_normalize_windows_snapshot_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    import tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers as helpers

    captured: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(helpers.os, "sep", "\\")
    monkeypatch.setattr(helpers, "to_relative", lambda *_args: "pkg\\app.py")
    monkeypatch.setattr(
        helpers,
        "_certified_exercising_tests",
        lambda _conn, rel_path, dependents, **_kwargs: (
            captured.append((rel_path, dependents)) or []
        ),
    )
    context = helpers.SafeToEditContext(
        file_path="pkg/app.py",
        edit_type="refactor",
        resolved_path=str(tmp_path / "pkg" / "app.py"),
        project_root=str(tmp_path),
        graph=helpers.FileDependencyView(
            rel_path="pkg/app.py",
            dependencies={"pkg/dep.py"},
            dependents={"tests/test_app.py"},
        ),
        scorer=SimpleNamespace(
            score_file=lambda *args, **kwargs: SimpleNamespace(
                grade="A", total=100, dimensions={}
            )
        ),
        snapshot_conn=sqlite3.connect(":memory:"),
        certified_inventory=frozenset({"pkg/app.py", "tests/test_app.py"}),
    )

    facts = helpers._collect_safe_to_edit_facts(context)

    assert facts.dependencies == ["pkg/dep.py"]
    assert captured == [("pkg/app.py", ["tests/test_app.py"])]


def test_safe_to_edit_preserves_posix_literal_backslash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    import tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers as helpers

    literal_path = "pkg/a\\b.py"
    monkeypatch.setattr(helpers.os, "sep", "/")
    monkeypatch.setattr(helpers, "to_relative", lambda *_args: literal_path)
    monkeypatch.setattr(helpers, "find_test_files", lambda *_args: [])
    context = helpers.SafeToEditContext(
        file_path=literal_path,
        edit_type="refactor",
        resolved_path=str(tmp_path / literal_path),
        project_root=str(tmp_path),
        graph=helpers.FileDependencyView(
            rel_path=literal_path,
            dependencies={"pkg/dep.py"},
            dependents={"tests/test_app.py"},
        ),
        scorer=SimpleNamespace(
            score_file=lambda *args, **kwargs: SimpleNamespace(
                grade="A", total=100, dimensions={}
            )
        ),
    )

    facts = helpers._collect_safe_to_edit_facts(context)

    assert facts.dependencies == ["pkg/dep.py"]
    assert facts.dependents == ["tests/test_app.py"]


@pytest.mark.skipif(
    os.name == "nt",
    reason="tracked: PR #1308 POSIX-only literal-backslash filename contract",
)
def test_snapshot_route_preserves_posix_literal_backslash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    import tree_sitter_analyzer.mcp.tools.safe_to_edit_tool as tool_module

    literal_path = "pkg/a\\b.py"
    target = tmp_path / literal_path
    target.parent.mkdir()
    target.write_text("value = 1\n", encoding="utf-8")
    captured: list[str] = []
    monkeypatch.setattr(tool_module.os, "sep", "/")
    monkeypatch.setattr(
        tool_module, "snapshot_inventory", lambda _conn: frozenset({literal_path})
    )
    monkeypatch.setattr(tool_module, "_syntax_error_response", lambda *_args: None)
    monkeypatch.setattr(
        tool_module,
        "build_snapshot_file_dependency_view",
        lambda _conn, rel_path, **_kwargs: captured.append(rel_path) or object(),
    )
    monkeypatch.setattr(
        tool_module,
        "snapshot_stale_edges",
        lambda _conn, rel_path, **_kwargs: captured.append(rel_path) or [],
    )
    monkeypatch.setattr(
        tool_module,
        "_build_safe_to_edit_result",
        lambda _context: {
            "success": True,
            "verdict": "SAFE",
            "agent_summary": {"summary_line": "safe"},
        },
    )
    tool = SafeToEditTool(str(tmp_path))
    monkeypatch.setattr(tool, "_get_scorer", lambda: object())

    result = tool._read_existing_payload(
        {"file_path": literal_path},
        str(target),
        object(),
        SimpleNamespace(canonical_root=str(tmp_path)),
    )

    assert result["success"] is True
    assert captured == [literal_path, literal_path]


def test_snapshot_route_normalizes_windows_separator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    import tree_sitter_analyzer.mcp.tools.safe_to_edit_tool as tool_module

    target = tmp_path / "pkg" / "app.py"
    target.parent.mkdir()
    target.write_text("value = 1\n", encoding="utf-8")
    captured: list[str] = []
    monkeypatch.setattr(tool_module.os, "sep", "\\")
    monkeypatch.setattr(tool_module, "_to_relative", lambda *_args: "pkg\\app.py")
    monkeypatch.setattr(
        tool_module, "snapshot_inventory", lambda _conn: frozenset({"pkg/app.py"})
    )
    monkeypatch.setattr(tool_module, "_syntax_error_response", lambda *_args: None)
    monkeypatch.setattr(
        tool_module,
        "build_snapshot_file_dependency_view",
        lambda _conn, rel_path, **_kwargs: captured.append(rel_path) or object(),
    )
    monkeypatch.setattr(
        tool_module,
        "snapshot_stale_edges",
        lambda _conn, rel_path, **_kwargs: captured.append(rel_path) or [],
    )
    monkeypatch.setattr(
        tool_module,
        "_build_safe_to_edit_result",
        lambda _context: {
            "success": True,
            "verdict": "SAFE",
            "agent_summary": {"summary_line": "safe"},
        },
    )
    tool = SafeToEditTool(str(tmp_path))
    monkeypatch.setattr(tool, "_get_scorer", lambda: object())

    result = tool._read_existing_payload(
        {"file_path": "pkg/app.py"},
        str(target),
        object(),
        SimpleNamespace(canonical_root=str(tmp_path)),
    )

    assert result["success"] is True
    assert captured == ["pkg/app.py", "pkg/app.py"]


def test_certified_import_facts_default_to_empty_inventory() -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        _certified_import_facts_available,
    )

    assert _certified_import_facts_available("app.py") is True


def test_symbol_projection_completeness_rejects_query_failure() -> None:
    assert (
        helpers._symbol_walk_projections_complete(
            _BrokenConnection(), frozenset({"app.py"}), {"python"}
        )
        is False
    )


def test_symbol_projection_completeness_ignores_irrelevant_rows() -> None:
    conn = _symbol_conn(
        json.dumps(
            {
                "truncated_depth": False,
                "import_projection_complete": True,
                "syntax_error": False,
            }
        )
    )
    conn.execute("INSERT INTO ast_index VALUES ('notes.md', 'not-json', 0)")

    assert helpers._symbol_walk_projections_complete(
        conn, frozenset({"app.py"}), {"python"}
    )


def test_symbol_projection_completeness_rejects_incomplete_walk() -> None:
    conn = _symbol_conn(json.dumps({"import_projection_complete": False}))

    assert (
        helpers._symbol_walk_projections_complete(
            conn, frozenset({"app.py"}), {"python"}
        )
        is False
    )


def test_symbol_projection_completeness_rejects_syntax_error() -> None:
    conn = _symbol_conn(json.dumps({"syntax_error": True}))

    assert (
        helpers._symbol_walk_projections_complete(
            conn, frozenset({"app.py"}), {"python"}
        )
        is False
    )


@pytest.mark.parametrize(
    "missing_field",
    ["truncated_depth", "import_projection_complete", "syntax_error"],
)
def test_symbol_projection_completeness_requires_every_proof_field(
    missing_field: str,
) -> None:
    payload = {
        "truncated_depth": False,
        "import_projection_complete": True,
        "syntax_error": False,
    }
    payload.pop(missing_field)

    assert not helpers._symbol_walk_projections_complete(
        _symbol_conn(json.dumps(payload)), frozenset({"app.py"}), {"python"}
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


def test_symbol_projection_rejects_stale_extractor_version() -> None:
    conn = _symbol_conn(json.dumps({"truncated_depth": False}))
    conn.execute("UPDATE ast_index SET extractor_version = 24")

    assert (
        helpers._symbol_walk_projections_complete(
            conn, frozenset({"app.py"}), {"python"}
        )
        is False
    )
