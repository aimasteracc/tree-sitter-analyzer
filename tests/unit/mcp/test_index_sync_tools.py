#!/usr/bin/env python3
"""Tests for codegraph_full_index, codegraph_autoindex, and codegraph_incremental_sync MCP tools."""

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

    def test_schema_defaults(self):
        from tree_sitter_analyzer.mcp.tools.full_index_tool import (
            CodeGraphFullIndexTool,
        )

        tool = CodeGraphFullIndexTool()
        schema = tool.get_tool_schema()
        assert schema["properties"]["mode"]["default"] == "incremental"
        assert schema["properties"]["max_files"]["default"] == 5000

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
        assert result["success"] is True
        assert "mode" in result

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


class TestIndexToolsRegistered:
    def test_full_index_registered(self):
        from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry

        _, by_name = create_tool_registry(None)
        assert "codegraph_full_index" in by_name

    def test_autoindex_registered(self):
        from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry

        _, by_name = create_tool_registry(None)
        assert "codegraph_autoindex" in by_name

    def test_incremental_sync_registered(self):
        from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry

        _, by_name = create_tool_registry(None)
        assert "codegraph_incremental_sync" in by_name

    def test_registered_tool_count(self):
        from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry

        tools, _ = create_tool_registry(None)
        registered_names = [name for name, _ in tools]
        assert "codegraph_full_index" in registered_names
        assert "codegraph_autoindex" in registered_names
        assert "codegraph_incremental_sync" in registered_names
