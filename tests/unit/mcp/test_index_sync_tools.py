#!/usr/bin/env python3
"""Tests for codegraph_full_index, codegraph_autoindex, and codegraph_incremental_sync MCP tools."""

import os
from pathlib import Path

import pytest


@pytest.fixture
def project_root(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text(
        "def hello():\n    print('hello')\n\ndef goodbye():\n    hello()\n"
    )
    return str(tmp_path)


class TestCodeGraphFullIndexTool:
    def test_tool_definition(self):
        from tree_sitter_analyzer.mcp.tools.full_index_tool import (
            CodeGraphFullIndexTool,
        )

        tool = CodeGraphFullIndexTool()
        defn = tool.get_tool_definition()
        assert defn["name"] == "codegraph_full_index"
        schema = defn["inputSchema"]
        assert "mode" in schema["properties"]
        assert "max_files" in schema["properties"]
        assert "resolve_synapse" in schema["properties"]
        assert "include_activation" in schema["properties"]

    def test_schema_defaults(self):
        from tree_sitter_analyzer.mcp.tools.full_index_tool import (
            CodeGraphFullIndexTool,
        )

        tool = CodeGraphFullIndexTool()
        schema = tool.get_tool_schema()
        assert schema["properties"]["mode"]["default"] == "incremental"
        assert schema["properties"]["max_files"]["default"] == 20000
        assert schema["properties"]["include_activation"]["default"] is False

    def test_validate_arguments_valid(self):
        from tree_sitter_analyzer.mcp.tools.full_index_tool import (
            CodeGraphFullIndexTool,
        )

        tool = CodeGraphFullIndexTool()
        assert tool.validate_arguments({"mode": "full"}) is True
        assert tool.validate_arguments({"mode": "incremental"}) is True

    def test_validate_arguments_invalid(self):
        from tree_sitter_analyzer.mcp.tools.full_index_tool import (
            CodeGraphFullIndexTool,
        )

        tool = CodeGraphFullIndexTool()
        with pytest.raises(ValueError, match="Invalid mode"):
            tool.validate_arguments({"mode": "bad"})

    @pytest.mark.asyncio
    async def test_execute_no_project_root(self):
        from tree_sitter_analyzer.mcp.tools.full_index_tool import (
            CodeGraphFullIndexTool,
        )

        tool = CodeGraphFullIndexTool()
        result = await tool.execute({"mode": "incremental"})
        assert result["success"] is False
        assert result["verdict"] == "ERROR"

    @pytest.mark.asyncio
    async def test_execute_incremental(self, project_root):
        from tree_sitter_analyzer.mcp.tools.full_index_tool import (
            CodeGraphFullIndexTool,
        )

        tool = CodeGraphFullIndexTool(project_root=project_root)
        result = await tool.execute(
            {"mode": "incremental", "max_files": 10, "output_format": "json"}
        )
        assert result["success"] is True
        # PR #1254: portable source certification makes ordinary indexing
        # authoritative on Windows as well as POSIX.
        assert result["verdict"] == "INFO"
        assert "phases" in result

    @pytest.mark.asyncio
    async def test_execute_full(self, project_root):
        from tree_sitter_analyzer.mcp.tools.full_index_tool import (
            CodeGraphFullIndexTool,
        )

        tool = CodeGraphFullIndexTool(project_root=project_root)
        result = await tool.execute(
            {"mode": "full", "max_files": 10, "output_format": "json"}
        )
        # PR #1254: the normal full-index producer now stamps a portable
        # manifest on hosts without /dev/fd.
        assert result["success"] is True
        assert "phases" in result
        assert "elapsed_seconds" in result


class TestCodeGraphAutoIndexTool:
    def test_tool_definition(self):
        from tree_sitter_analyzer.mcp.tools.auto_index_tool import (
            CodeGraphAutoIndexTool,
        )

        tool = CodeGraphAutoIndexTool()
        defn = tool.get_tool_definition()
        assert defn["name"] == "codegraph_autoindex"
        schema = defn["inputSchema"]
        assert "mode" in schema["properties"]

    def test_schema_defaults(self):
        from tree_sitter_analyzer.mcp.tools.auto_index_tool import (
            CodeGraphAutoIndexTool,
        )

        tool = CodeGraphAutoIndexTool()
        schema = tool.get_tool_schema()
        assert schema["properties"]["mode"]["default"] == "status"

    def test_validate_arguments_valid(self):
        from tree_sitter_analyzer.mcp.tools.auto_index_tool import (
            CodeGraphAutoIndexTool,
        )

        tool = CodeGraphAutoIndexTool()
        assert tool.validate_arguments({"mode": "status"}) is True
        assert tool.validate_arguments({"mode": "warm"}) is True
        assert tool.validate_arguments({"mode": "reset"}) is True

    def test_validate_arguments_invalid(self):
        from tree_sitter_analyzer.mcp.tools.auto_index_tool import (
            CodeGraphAutoIndexTool,
        )

        tool = CodeGraphAutoIndexTool()
        with pytest.raises(ValueError, match="Invalid mode"):
            tool.validate_arguments({"mode": "bad"})

    @pytest.mark.asyncio
    async def test_execute_status_no_root(self):
        from tree_sitter_analyzer.mcp.tools.auto_index_tool import (
            CodeGraphAutoIndexTool,
        )

        tool = CodeGraphAutoIndexTool()
        result = await tool.execute({"mode": "status"})
        assert result["success"] is True
        assert result["indexed"] is False

    @pytest.mark.asyncio
    async def test_execute_status(self, project_root):
        from tree_sitter_analyzer.mcp.tools.auto_index_tool import (
            CodeGraphAutoIndexTool,
        )

        tool = CodeGraphAutoIndexTool(project_root=project_root)
        result = await tool.execute({"mode": "status", "output_format": "json"})
        assert result["success"] is True
        assert "indexed" in result

    @pytest.mark.asyncio
    async def test_execute_warm(self, project_root):
        from tree_sitter_analyzer.mcp.tools.auto_index_tool import (
            CodeGraphAutoIndexTool,
        )

        tool = CodeGraphAutoIndexTool(project_root=project_root)
        result = await tool.execute(
            {"mode": "warm", "max_files": 10, "output_format": "json"}
        )
        assert result["success"] is True
        assert "total_files" in result

    @pytest.mark.asyncio
    async def test_execute_reset(self, project_root):
        from tree_sitter_analyzer.mcp.tools.auto_index_tool import (
            CodeGraphAutoIndexTool,
        )

        tool = CodeGraphAutoIndexTool(project_root=project_root)
        result = await tool.execute({"mode": "reset", "output_format": "json"})
        assert result["success"] is True
        assert result["action"] == "reset"


class TestCodeGraphIncrementalSyncTool:
    def test_tool_definition(self):
        from tree_sitter_analyzer.mcp.tools.incremental_sync_tool import (
            CodeGraphIncrementalSyncTool,
        )

        tool = CodeGraphIncrementalSyncTool()
        defn = tool.get_tool_definition()
        assert defn["name"] == "codegraph_incremental_sync"
        schema = defn["inputSchema"]
        assert "mode" in schema["properties"]
        assert schema["properties"]["mode"]["default"] == "sync"

    def test_validate_arguments_valid(self):
        from tree_sitter_analyzer.mcp.tools.incremental_sync_tool import (
            CodeGraphIncrementalSyncTool,
        )

        tool = CodeGraphIncrementalSyncTool()
        assert tool.validate_arguments({"mode": "sync"}) is True
        assert tool.validate_arguments({"mode": "changes"}) is True
        assert tool.validate_arguments({"mode": "status"}) is True

    def test_validate_arguments_invalid(self):
        from tree_sitter_analyzer.mcp.tools.incremental_sync_tool import (
            CodeGraphIncrementalSyncTool,
        )

        tool = CodeGraphIncrementalSyncTool()
        with pytest.raises(ValueError, match="Invalid mode"):
            tool.validate_arguments({"mode": "bad"})

    @pytest.mark.asyncio
    async def test_execute_no_project_root(self):
        from tree_sitter_analyzer.mcp.tools.incremental_sync_tool import (
            CodeGraphIncrementalSyncTool,
        )

        tool = CodeGraphIncrementalSyncTool()
        result = await tool.execute({"mode": "sync"})
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_execute_sync(self, project_root):
        from tree_sitter_analyzer.mcp.tools.incremental_sync_tool import (
            CodeGraphIncrementalSyncTool,
        )

        tool = CodeGraphIncrementalSyncTool(project_root=project_root)
        result = await tool.execute(
            {"mode": "sync", "max_files": 10, "output_format": "json"}
        )
        # 2026-09-07：公开 sync 已传入真实候选证据，不再走无认证的旧遍历。
        assert (result["success"], result["verdict"], result["completeness"]) == (
            True,
            "INFO",
            "complete",
        )
        assert result["mode"] == "sync"

    @pytest.mark.asyncio
    async def test_execute_changes(self, project_root):
        from tree_sitter_analyzer.mcp.tools.incremental_sync_tool import (
            CodeGraphIncrementalSyncTool,
        )

        tool = CodeGraphIncrementalSyncTool(project_root=project_root)
        result = await tool.execute({"mode": "changes", "output_format": "json"})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_status(self, project_root):
        from tree_sitter_analyzer.mcp.tools.incremental_sync_tool import (
            CodeGraphIncrementalSyncTool,
        )

        tool = CodeGraphIncrementalSyncTool(project_root=project_root)
        result = await tool.execute({"mode": "status", "output_format": "json"})
        assert result["success"] is True


@pytest.mark.asyncio
async def test_sync_uses_cache_authority_for_symlink_root(tmp_path):
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool
    from tree_sitter_analyzer.mcp.tools.incremental_sync_tool import (
        CodeGraphIncrementalSyncTool,
    )

    # #1385：真实目录别名不得与 cache 的规范根目录产生候选认证冲突。
    root = tmp_path / "actual"
    root.mkdir()
    source = root / "leaf.py"
    source.write_text("def leaf():\n    return 1\n", encoding="utf-8")
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(root, target_is_directory=True)
    except OSError as exc:
        if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
            pytest.skip("#1385：Windows 当前账号没有创建目录符号链接的权限")
        raise
    initial = await CodeGraphFullIndexTool(str(root)).execute({"max_files": 1})
    assert initial["success"] is True
    source.write_text("def leaf_v2():\n    return 2\n", encoding="utf-8")
    tool = CodeGraphIncrementalSyncTool(str(alias))
    result = await tool.execute({"mode": "sync", "max_files": 1})
    assert result["success"] is True, result
    assert (result["completeness"], result["updated_files"]) == ("complete", 1)
    assert tool.project_root == str(alias)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["changes", "status"])
@pytest.mark.parametrize("change", ["new", "modified", "deleted"])
async def test_sync_preview_shares_exclusions(project_root, mode, change):
    from tree_sitter_analyzer.mcp.tools.incremental_sync_tool import (
        CodeGraphIncrementalSyncTool,
    )

    # #1385：被 sync 排除的语料不能让 changes/status 永远显示未同步。
    root = Path(project_root)
    corpus = root / "tests/golden/corpus_probe"
    corpus.mkdir(parents=True)
    (corpus / "excluded.py").write_text("def excluded():\n    pass\n", encoding="utf-8")
    tool = CodeGraphIncrementalSyncTool(project_root)
    synced = await tool.execute({"mode": "sync", "max_files": 1})
    assert (synced["success"], synced["completeness"]) == (True, "complete")
    clean = await tool.execute({"mode": mode})
    assert clean["success"] is True
    if mode == "changes":
        assert (clean["new"], clean["modified"], clean["deleted"]) == ([], [], [])
    else:
        assert (clean["pending_changes"], clean["up_to_date"]) == (0, True)
    source = root / ("new.py" if change == "new" else "src/main.py")
    if change == "deleted":
        source.unlink()
    else:
        source.write_text("def changed():\n    return 2\n", encoding="utf-8")
    dirty = await tool.execute({"mode": mode})
    assert dirty["success"] is True
    if mode == "changes":
        expected = {"new": [], "modified": [], "deleted": []}
        expected[change] = [source.relative_to(root).as_posix()]
        assert {key: dirty[key] for key in expected} == expected
    else:
        assert (dirty["pending_changes"], dirty["up_to_date"]) == (1, False)


class TestIndexToolsRegistered:
    """Wave C2: the three index lifecycle tools are no longer top-level
    registry entries — they are actions on the ``index`` facade
    (full/auto/sync). These tests verify the facade exposes those actions
    and routes them to the original inner tools.
    """

    def test_full_index_registered(self):
        from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry

        _, by_name = create_tool_registry(None)
        assert "index" in by_name
        assert "full" in by_name["index"].action_map
        assert (
            type(by_name["index"].action_map["full"]).__name__
            == "CodeGraphFullIndexTool"
        )

    def test_autoindex_registered(self):
        from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry

        _, by_name = create_tool_registry(None)
        assert "auto" in by_name["index"].action_map
        assert (
            type(by_name["index"].action_map["auto"]).__name__
            == "CodeGraphAutoIndexTool"
        )

    def test_incremental_sync_registered(self):
        from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry

        _, by_name = create_tool_registry(None)
        assert "sync" in by_name["index"].action_map
        assert (
            type(by_name["index"].action_map["sync"]).__name__
            == "CodeGraphIncrementalSyncTool"
        )

    def test_registered_tool_count(self):
        from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry

        _, by_name = create_tool_registry(None)
        index_actions = set(by_name["index"].action_map)
        assert {"full", "auto", "sync"} <= index_actions
