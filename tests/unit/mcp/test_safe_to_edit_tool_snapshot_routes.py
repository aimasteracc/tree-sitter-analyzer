"""#1376：test_safe_to_edit_tool_snapshot_routes 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import os
import sqlite3
import sys
from pathlib import Path

import pytest

import tests.unit.mcp._safe_to_edit_tool_helpers as _fixtures
from tests.unit.mcp._safe_to_edit_tool_helpers import (
    _indexed_project,
    _publish_index_snapshot,
)
from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import (
    SafeToEditTool,
)

tool = _fixtures.tool
_close_index_snapshot_registry = _fixtures._close_index_snapshot_registry


@pytest.mark.slow_ok  # 真实 git、index_project 和源码捕获会产生子进程工作。
@pytest.mark.skipif(
    sys.platform.startswith("win") or not os.path.exists("/dev/fd"),
    reason="tracked: RFC-0022 P0.4 source recapture needs POSIX /dev/fd",
)
@pytest.mark.asyncio
async def test_edit_safe_read_existing_consumes_published_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """认证后端从快照提供风险 envelope。"""
    import tree_sitter_analyzer.read_existing_access as read_access

    monkeypatch.setattr(read_access, "read_existing_platform_supported", lambda: True)
    project = _indexed_project(tmp_path)
    published = _publish_index_snapshot(project)

    tool = SafeToEditTool(str(project))
    result = await tool.execute(
        {
            "file_path": "app.py",
            "access_mode": "read_existing",
            "snapshot_id": published.snapshot_id,
            "source_generation": published.source_generation,
            "output_format": "json",
        }
    )

    assert result["success"] is True
    assert result["access_mode"] == "read_existing"
    assert result["access_state"] == "available"
    assert result["access_reason"] is None
    assert result["source_snapshots"] == [
        {
            "kind": "index",
            "snapshot_id": published.snapshot_id,
            "source_generation": published.source_generation,
        }
    ]
    # 回显必须来自已获取的快照，并与
    # source_snapshots 记录逐字节匹配（RFC-0022 路由表通用规则 5）。
    assert result["snapshot_id"] == published.snapshot_id
    assert result["source_generation"] == published.source_generation
    assert result["action_version"] == "edit.safe/v1"
    assert result["risk_level"] in {"safe", "caution", "dangerous"}
    assert result["health_grade"]
    causal = result["causal_envelope"]
    assert causal["dependents"] is None
    assert causal["dependencies"] is None
    assert causal["exercising_tests"] is None
    assert causal["constraint_verdict"] == "unknown"
    assert causal["verification_command"] is None
    assert causal["stale_edges"] is None


@pytest.mark.slow_ok  # 真实 git、index_project 和源码捕获会产生子进程工作。
@pytest.mark.skipif(
    sys.platform.startswith("win") or not os.path.exists("/dev/fd"),
    reason="tracked: RFC-0022 P0.4 source recapture needs POSIX /dev/fd",
)
@pytest.mark.asyncio
async def test_edit_safe_read_existing_ignores_unbound_constraint_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """未绑定的约束行不能升级判定；认证读取保持零写入。Codex P1 (#1299 第四轮，C21)：重新索引会标记 manifest，但不会重算 ast_constraint_violations，因此这些行不能证明自己匹配已发布代次，认证路由不能据此升级为 UNSAFE。路由也绝不能创建 .ast-cache/fixture_index.json。"""

    import tree_sitter_analyzer.read_existing_access as read_access
    from tree_sitter_analyzer.index_snapshot import (
        REGISTRY,
        IndexSnapshot,
        _capture_sources_with_deadline,
    )
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor

    monkeypatch.setattr(read_access, "read_existing_platform_supported", lambda: True)
    project = _indexed_project(tmp_path)
    scope = make_source_scope_descriptor()
    current = _capture_sources_with_deadline(str(project), scope, deadline=10**18)
    assert current.state == "exact", current.reason
    conn = sqlite3.connect(str(project / ".ast-cache" / "index.db"))
    conn.row_factory = sqlite3.Row
    conn.execute(
        "INSERT INTO ast_constraint_violations VALUES "
        "('R1', 'app.py', 'app', 1, 'secret', '', 'error', 1)"
    )
    conn.commit()
    snapshot = IndexSnapshot(
        None,
        current.fingerprint,
        "index-fp",
        current.generation,
        "complete",
        None,
        str(project.resolve()),
        2,
        None,
        None,
        scope,
    )
    published = REGISTRY.publish(snapshot, conn, 0)

    tool = SafeToEditTool(str(project))
    result = await tool.execute(
        {
            "file_path": "app.py",
            "access_mode": "read_existing",
            "snapshot_id": published.snapshot_id,
            "source_generation": published.source_generation,
            "output_format": "json",
        }
    )

    assert result["success"] is True
    assert result["access_state"] == "available"
    # 预置的 error 严重级别行不能升级判定，因为无法证明它
    # 属于已发布代次（C21）。CAUTION 判定来自
    # 快照依赖视图，因为 routes.py 导入 app.py，绝不是
    # 约束行不能作为该判定的来源。
    assert result["verdict"] == "CAUTION"
    assert result["downstream_count"] == 1
    assert not any(
        factor.get("factor") == "constraint_violation"
        for factor in result["risk_factors"]
    )
    # 零写入：认证读取从不持久化 fixture 索引。
    assert not (project / ".ast-cache" / "fixture_index.json").exists()


@pytest.mark.slow_ok  # 真实 git、index_project 和源码捕获会产生子进程工作。
@pytest.mark.skipif(
    sys.platform.startswith("win") or not os.path.exists("/dev/fd"),
    reason="tracked: RFC-0022 P0.4 source recapture needs POSIX /dev/fd",
)
@pytest.mark.asyncio
async def test_edit_safe_read_existing_unindexed_target_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """快照清单外的目标不能通过未认证读取提供。Codex P1 (#1299)：隐藏或排除文件不在源码重新捕获范围内，因此认证路由以 FILE_NOT_INDEXED 拒绝它们，而不是读取并评分其实时字节。"""
    import tree_sitter_analyzer.read_existing_access as read_access

    monkeypatch.setattr(read_access, "read_existing_platform_supported", lambda: True)
    project = _indexed_project(tmp_path)
    # 故意构造语法错误（Codex P1 第三轮）；清单检查必须
    # 先于语法探测运行；清单外的损坏文件
    # 不能提前返回表示语法错误的成功 envelope。
    (project / ".hidden.py").write_text("def broken(:\n", encoding="utf-8")
    published = _publish_index_snapshot(project)

    tool = SafeToEditTool(str(project))
    result = await tool.execute(
        {
            "file_path": ".hidden.py",
            "access_mode": "read_existing",
            "snapshot_id": published.snapshot_id,
            "source_generation": published.source_generation,
            "output_format": "json",
        }
    )

    assert result["success"] is False
    assert result["error_code"] == "FILE_NOT_INDEXED"
    assert result["access_reason"] == "FILE_NOT_INDEXED"
    assert result["action_version"] == "edit.safe/v1"
    assert result["source_snapshots"] == [
        {
            "kind": "index",
            "snapshot_id": published.snapshot_id,
            "source_generation": published.source_generation,
        }
    ]


@pytest.mark.slow_ok  # 真实 git、index_project 和源码捕获会产生子进程工作。
@pytest.mark.skipif(
    sys.platform.startswith("win") or not os.path.exists("/dev/fd"),
    reason="tracked: RFC-0022 P0.4 source recapture needs POSIX /dev/fd",
)
@pytest.mark.asyncio
async def test_edit_safe_read_existing_generation_mismatch_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """错误的 source_generation token 产生分类结果，不能读取成功。"""
    import tree_sitter_analyzer.read_existing_access as read_access

    monkeypatch.setattr(read_access, "read_existing_platform_supported", lambda: True)
    project = _indexed_project(tmp_path)
    published = _publish_index_snapshot(project)

    tool = SafeToEditTool(str(project))
    result = await tool.execute(
        {
            "file_path": "app.py",
            "access_mode": "read_existing",
            "snapshot_id": published.snapshot_id,
            "source_generation": "WRONG-GENERATION",
            "output_format": "json",
        }
    )

    assert result["success"] is False
    assert result["access_state"] == "unknown"
    assert result["access_reason"] == "SOURCE_GENERATION_MISMATCH"
    assert result["error_code"] == "SOURCE_GENERATION_MISMATCH"
    assert result["source_snapshots"] == []
    assert result["action_version"] == "edit.safe/v1"


@pytest.mark.slow_ok  # 真实 git、index_project 和源码捕获会产生子进程工作。
@pytest.mark.skipif(
    sys.platform.startswith("win") or not os.path.exists("/dev/fd"),
    reason="tracked: RFC-0022 P0.4 source recapture needs POSIX /dev/fd",
)
@pytest.mark.asyncio
async def test_edit_safe_read_existing_syntax_error_short_circuits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """损坏文件会像传统轴一样提前结束快照路由。"""
    import tree_sitter_analyzer.read_existing_access as read_access

    monkeypatch.setattr(read_access, "read_existing_platform_supported", lambda: True)
    project = _indexed_project(tmp_path)
    (project / "app.py").write_text("def broken(:\n", encoding="utf-8")
    published = _publish_index_snapshot(project)

    tool = SafeToEditTool(str(project))
    result = await tool.execute(
        {
            "file_path": "app.py",
            "access_mode": "read_existing",
            "snapshot_id": published.snapshot_id,
            "source_generation": published.source_generation,
            "output_format": "json",
        }
    )
    assert result["success"] is True
    assert result["verdict"] == "ERROR"
    assert result["access_state"] == "available"
    causal = result["causal_envelope"]
    assert causal["dependents"] is None
    assert causal["dependencies"] is None
    assert causal["exercising_tests"] is None
    assert causal["constraint_verdict"] == "unknown"
    assert causal["verification_command"] is None
    assert causal["stale_edges"] is None
    assert result["source_snapshots"] == [
        {
            "kind": "index",
            "snapshot_id": published.snapshot_id,
            "source_generation": published.source_generation,
        }
    ]


@pytest.mark.slow_ok  # 真实 git、index_project 和源码捕获会产生子进程工作。
@pytest.mark.skipif(
    sys.platform.startswith("win") or not os.path.exists("/dev/fd"),
    reason="tracked: RFC-0022 P0.4 source recapture needs POSIX /dev/fd",
)
@pytest.mark.asyncio
async def test_edit_safe_read_existing_missing_file_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """快照路由对缺失目标失败关闭。Codex P1 第四轮（C19）：清单检查先于任何实时文件系统探测；未被快照索引的文件无论是否存在，都从快照返回 FILE_NOT_INDEXED，不能使用未认证的磁盘状态。已索引但被删除的文件则在读取前重新捕获时产生 SOURCE_GENERATION_MISMATCH。"""
    import tree_sitter_analyzer.read_existing_access as read_access

    monkeypatch.setattr(read_access, "read_existing_platform_supported", lambda: True)
    project = _indexed_project(tmp_path)
    published = _publish_index_snapshot(project)

    tool = SafeToEditTool(str(project))
    result = await tool.execute(
        {
            "file_path": "does_not_exist.py",
            "access_mode": "read_existing",
            "snapshot_id": published.snapshot_id,
            "source_generation": published.source_generation,
            "output_format": "json",
        }
    )
    assert result["success"] is False
    assert result["error_code"] == "FILE_NOT_INDEXED"
    assert result["access_reason"] == "FILE_NOT_INDEXED"
    assert result["access_state"] == "unknown"
    assert result["action_version"] == "edit.safe/v1"
