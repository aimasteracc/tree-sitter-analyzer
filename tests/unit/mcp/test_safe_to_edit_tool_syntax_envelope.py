"""#1376：test_safe_to_edit_tool_syntax_envelope 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import json
import sqlite3

import tests.unit.mcp._safe_to_edit_tool_helpers as _fixtures
from tree_sitter_analyzer.ast_cache import _AST_CACHE_EXTRACTOR_VERSION

tool = _fixtures.tool
_close_index_snapshot_registry = _fixtures._close_index_snapshot_registry


def test_snapshot_syntax_envelope_keeps_complete_exercising_tests() -> None:
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
        "INSERT INTO ast_index VALUES "
        "('app.py', '[]', "
        '\'{"truncated_depth": false, "import_projection_complete": true, '
        '"syntax_error": false}\', ?)',
        (_AST_CACHE_EXTRACTOR_VERSION,),
    )
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, '[]', "
        '\'{"truncated_depth": false, "import_projection_complete": true, '
        '"syntax_error": false}\', ?)',
        [
            (f"tests/test_app_{index}.py", _AST_CACHE_EXTRACTOR_VERSION)
            for index in range(12)
        ],
    )
    conn.executemany(
        "INSERT INTO edges VALUES (?, 'calls', ?, 'answer', 'app.py')",
        [(index + 1, f"tests/test_app_{index}.py") for index in range(12)],
    )

    envelope = build_snapshot_syntax_causal_envelope(conn, "app.py", "app.py")

    assert len(envelope["exercising_tests"]) == 12
    assert envelope["verification_command"] == (
        "uv run pytest " + " ".join(envelope["exercising_tests"]) + " -q"
    )


def test_snapshot_syntax_envelope_excludes_unrelated_nearby_test() -> None:
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
    conn.executemany(
        "INSERT INTO ast_index VALUES (?, '[]', "
        '\'{"truncated_depth": false, "import_projection_complete": true, '
        '"syntax_error": false}\', ?)',
        [
            ("app.py", _AST_CACHE_EXTRACTOR_VERSION),
            ("tests/test_app.py", _AST_CACHE_EXTRACTOR_VERSION),
        ],
    )

    envelope = build_snapshot_syntax_causal_envelope(conn, "app.py", "app.py")

    assert envelope["exercising_tests"] == []


def test_snapshot_syntax_envelope_marks_unsupported_import_facts_unavailable() -> None:
    from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
        build_snapshot_syntax_causal_envelope,
    )

    envelope = build_snapshot_syntax_causal_envelope(
        sqlite3.connect(":memory:"), "src/main.go", "src/main.go"
    )

    assert envelope == {
        "dependents": None,
        "dependencies": None,
        "exercising_tests": None,
        "constraint_verdict": "unknown",
        "verification_command": None,
        "stale_edges": None,
    }


def test_snapshot_syntax_envelope_marks_typescript_alias_unavailable() -> None:
    # PR #1308 review: 裸模块标识可能通过快照之外的 tsconfig 解析。
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
            ("src/main.ts", json.dumps([{"text": "import { run } from '@app/util'"}])),
            ("src/util.ts", "[]"),
        ],
    )

    envelope = build_snapshot_syntax_causal_envelope(conn, "src/util.ts", "src/util.ts")

    assert envelope == {
        "dependents": None,
        "dependencies": None,
        "exercising_tests": None,
        "constraint_verdict": "unknown",
        "verification_command": None,
        "stale_edges": None,
    }


def test_snapshot_syntax_envelope_marks_dynamic_python_import_unavailable() -> None:
    # PR #1308 review: 非字面量模块名不能认证传入边。
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
            ("app.py", json.dumps([{"text": "__import__(module_name)"}])),
            ("pkg/util.py", "[]"),
        ],
    )

    envelope = build_snapshot_syntax_causal_envelope(conn, "pkg/util.py", "pkg/util.py")

    assert envelope == {
        "dependents": None,
        "dependencies": None,
        "exercising_tests": None,
        "constraint_verdict": "unknown",
        "verification_command": None,
        "stale_edges": None,
    }


def test_snapshot_syntax_envelope_marks_truncated_projection_unavailable() -> None:
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
        "INSERT INTO ast_index VALUES (?, ?, ?)",
        [
            ("app.py", "[]", json.dumps({"truncated_depth": True})),
            ("pkg/util.py", "[]", json.dumps({"truncated_depth": False})),
        ],
    )

    envelope = build_snapshot_syntax_causal_envelope(conn, "pkg/util.py", "pkg/util.py")

    assert envelope == {
        "dependents": None,
        "dependencies": None,
        "exercising_tests": None,
        "constraint_verdict": "unknown",
        "verification_command": None,
        "stale_edges": None,
    }


def test_snapshot_syntax_envelope_marks_incomplete_import_projection_unavailable() -> (
    None
):
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
    conn.execute(
        "INSERT INTO ast_index VALUES (?, '[]', ?)",
        ("app.py", json.dumps({"import_projection_complete": False})),
    )

    envelope = build_snapshot_syntax_causal_envelope(conn, "app.py", "app.py")

    assert envelope == {
        "dependents": None,
        "dependencies": None,
        "exercising_tests": None,
        "constraint_verdict": "unknown",
        "verification_command": None,
        "stale_edges": None,
    }


def test_live_syntax_error_response_preserves_json_envelope(tmp_path):
    """损坏源码通过实际工具入口返回明确错误封套。"""
    import asyncio

    from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import SafeToEditTool

    (tmp_path / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    result = asyncio.run(
        SafeToEditTool(str(tmp_path)).execute(
            {"file_path": "broken.py", "output_format": "json"}
        )
    )
    assert result["verdict"] == "ERROR"
    assert result["signal"] == "syntax_error"
    assert result["output_format"] == "json"
