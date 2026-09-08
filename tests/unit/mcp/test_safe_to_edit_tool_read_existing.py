"""#1376：test_safe_to_edit_tool_read_existing 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import sqlite3
import sys
from pathlib import Path

import pytest

import tests.unit.mcp._safe_to_edit_tool_helpers as _fixtures
from tests.unit.mcp._safe_to_edit_tool_helpers import _run
from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade
from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import (
    SafeToEditTool,
)

tool = _fixtures.tool
_close_index_snapshot_registry = _fixtures._close_index_snapshot_registry


@pytest.mark.asyncio
async def test_edit_safe_explicit_read_existing_honors_compact_only(
    tmp_path,
) -> None:
    file_path = tmp_path / "inside.py"
    file_path.write_text("value = 1\n", encoding="utf-8")
    result = await build_edit_facade(str(tmp_path)).execute(
        {
            "action": "safe",
            "file_path": "inside.py",
            "access_mode": "read_existing",
            "snapshot_id": "idxsnap_test",
            "source_generation": "idxsrc-v3:test",
            "output_format": "json",
            "compact_only": True,
        }
    )

    if sys.platform.startswith("linux"):
        # RFC-0022 P0.4: 认证后端实际运行并分类处理
        # 缺失快照。分类后的失败仍保留控制字段，
        # 以及 wire-owner 回显。
        assert {
            key: result[key]
            for key in (
                "success",
                "verdict",
                "access_mode",
                "access_state",
                "access_reason",
                "output_format",
                "action_version",
            )
        } == {
            "success": False,
            "verdict": "ERROR",
            "access_mode": "read_existing",
            "access_state": "unknown",
            "access_reason": "INDEX_SNAPSHOT_UNKNOWN",
            "output_format": "json",
            "action_version": "edit.safe/v1",
        }
        return

    # RFC-0022 P0.4/P0.5: 控制字段必须位于顶层。
    # RFC-0027 L6.1: provenance 仅位于顶层。
    provenance = result.pop("provenance")
    assert provenance["served_from"] == "computed"
    assert set(provenance) == {
        "served_from",
        "tool",
        "action",
        "normalized_args",
        "generation",
        "producer_version",
        "extra_inputs",
    }

    assert {
        key: result[key]
        for key in (
            "success",
            "verdict",
            "access_mode",
            "access_state",
            "access_reason",
            "output_format",
            "action_version",
        )
    } == {
        "success": True,
        "verdict": "WARN",
        "access_mode": "read_existing",
        "access_state": "unknown",
        "access_reason": "READ_EXISTING_AUTHORITY_UNCERTIFIED",
        "output_format": "json",
        # RFC-0022 P0.5: envelope 中包含 wire owner 回显。
        "action_version": "edit.safe/v1",
    }


@pytest.mark.asyncio
async def test_read_existing_rejects_traversal_before_unavailable(tmp_path):
    tool = SafeToEditTool(str(tmp_path))

    with pytest.raises(
        ValueError,
        match=r"^Invalid file path: Security validation failed:",
    ):
        await tool.execute(
            {
                "file_path": "../outside.py",
                "access_mode": "read_existing",
                "snapshot_id": "idxsnap_test",
                "source_generation": "idxsrc-v3:test",
                "output_format": "json",
            }
        )


def test_execute_read_existing_fails_closed_without_project_root() -> None:
    # Codex P1 (#1257): project_root 未绑定时，resolve_and_validate_
    # file_path 会向 SecurityValidator 传入 base_path=None，从而跳过
    # 项目边界层；read_existing 路由必须失败关闭，
    # 返回稳定的 MISSING_PROJECT_ROOT 错误。Review P2 (#1299)：
    # 失败应返回包含 evidence 和 action_version 的分类 envelope，而非
    # 直接抛出异常。
    tool = SafeToEditTool()  # 未绑定项目根目录。
    result = _run(
        tool.execute(
            {
                "file_path": "src/app.py",
                "access_mode": "read_existing",
                "snapshot_id": "snap-1",
                "source_generation": "1",
            }
        )
    )
    assert result["success"] is False
    assert result["error_code"] == "MISSING_PROJECT_ROOT"
    assert result["access_reason"] == "MISSING_PROJECT_ROOT"
    assert result["access_state"] == "missing"
    assert result["action_version"] == "edit.safe/v1"
    assert result["source_snapshots"] == []


def test_read_existing_payload_missing_indexed_file_returns_not_found(
    tmp_path: Path,
) -> None:
    """已索引目标在读取时缺失，仍返回 FILE_NOT_FOUND。Codex P1 第四轮（C19）：文件确实位于 ast_index 中，因此通过清单检查，随后由文件系统存在性探测回答。"""
    from types import SimpleNamespace

    from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import SafeToEditTool

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE ast_index (file_path TEXT)")
    conn.execute("INSERT INTO ast_index VALUES ('app.py')")
    tool = SafeToEditTool(str(tmp_path))
    with pytest.raises(ValueError, match="FILE_NOT_FOUND"):
        tool._read_existing_payload(
            {"file_path": "app.py", "edit_type": "refactor"},
            str(tmp_path / "app.py"),
            conn,
            snapshot=SimpleNamespace(canonical_root=str(tmp_path.resolve())),
        )


def test_read_existing_payload_language_detection_degrades(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """快照路由中的语言检测失败时，结果不包含语言键。Codex-review P3 (#1299)：语言检测是尽力而为的操作，异常只能产生无语言结果，不能导致崩溃。"""
    from types import SimpleNamespace

    import tree_sitter_analyzer.mcp.tools.safe_to_edit_tool as tool_module

    target = tmp_path / "app.py"
    target.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(
        tool_module,
        "_syntax_error_response",
        lambda resolved, file_path, edit_type: None,
    )

    def boom(*args, **kwargs):
        raise RuntimeError("detector down")

    monkeypatch.setattr(
        "tree_sitter_analyzer.language_detector.detect_language_from_file", boom
    )
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # FILE_NOT_INDEXED 检查需要 ast_index 中存在目标。
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT, symbols_json TEXT, imports_json TEXT)"
    )
    conn.execute("INSERT INTO ast_index VALUES ('app.py', '{}', '[]')")
    conn.execute(
        "CREATE TABLE edges ("
        "id INTEGER PRIMARY KEY, kind TEXT, file_path TEXT, "
        "callee_name TEXT, callee_resolved_file TEXT)"
    )
    tool = tool_module.SafeToEditTool(str(tmp_path))
    result = tool._read_existing_payload(
        {"file_path": "app.py", "edit_type": "refactor"},
        str(target),
        conn,
        snapshot=SimpleNamespace(canonical_root=str(tmp_path)),
    )
    assert result["success"] is True
    assert "language" not in result


def test_read_existing_payload_scans_snapshot_inventory_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    import tree_sitter_analyzer.mcp.tools.safe_to_edit_tool as tool_module

    target = tmp_path / "app.py"
    target.write_text("answer = 42\n", encoding="utf-8")
    monkeypatch.setattr(
        tool_module,
        "_syntax_error_response",
        lambda resolved, file_path, edit_type: None,
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
    conn.execute("INSERT INTO ast_index VALUES ('app.py', '[]', '{}')")
    queries: list[str] = []
    conn.set_trace_callback(queries.append)

    tool = tool_module.SafeToEditTool(str(tmp_path))
    result = tool._read_existing_payload(
        {"file_path": "app.py", "edit_type": "refactor"},
        str(target),
        conn,
        snapshot=SimpleNamespace(canonical_root=str(tmp_path.resolve())),
    )

    assert result["success"] is True
    assert queries.count("SELECT file_path FROM ast_index") == 1


def test_read_existing_payload_without_snapshot_keeps_syntax_envelope_unknown(
    tmp_path: Path,
) -> None:
    target = tmp_path / "app.py"
    target.write_text("def broken(:\n", encoding="utf-8")
    result = SafeToEditTool(str(tmp_path))._read_existing_payload(
        {"file_path": "app.py"}, str(target), sqlite3.connect(":memory:")
    )

    assert result["signal"] == "syntax_error"
    assert result["causal_envelope"] == {
        "dependents": None,
        "dependencies": None,
        "exercising_tests": None,
        "constraint_verdict": "unknown",
        "verification_command": None,
        "stale_edges": None,
    }
