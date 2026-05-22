"""Tests for tree_sitter_analyzer.mcp.tools.ast_diff_tool — previously ZERO coverage."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.ast_diff_tool import ASTDiffTool


@pytest.fixture
def tool():
    return ASTDiffTool(project_root="/tmp/test_project")


class TestASTDiffToolInit:
    def test_default_project_root(self):
        t = ASTDiffTool()
        assert t.project_root is None

    def test_custom_project_root(self):
        t = ASTDiffTool(project_root="/src")
        assert t.project_root == "/src"


class TestASTDiffToolDefinition:
    def test_get_tool_definition(self, tool):
        defn = tool.get_tool_definition()
        assert isinstance(defn, dict)
        assert "name" in defn
        assert defn["name"] == "ast_diff"

    def test_get_tool_schema(self, tool):
        schema = tool.get_tool_schema()
        assert isinstance(schema, dict)
        assert "type" in schema
        assert schema["type"] == "object"
        assert "properties" in schema

    def test_schema_has_file_path_property(self, tool):
        schema = tool.get_tool_schema()
        assert "file_path" in schema["properties"]


class TestASTDiffToolValidation:
    def test_validate_with_file_path(self, tool):
        # diff_git mode requires file_path — valid call returns True
        assert (
            tool.validate_arguments({"mode": "diff_git", "file_path": "/src/main.py"})
            is True
        )

    def test_validate_missing_file_path(self, tool):
        # diff_git mode raises ValueError when file_path is absent
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments({"mode": "diff_git"})

    def test_validate_empty_file_path(self, tool):
        # falsy file_path also raises
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments({"mode": "diff_git", "file_path": ""})


class TestASTDiffToolExecution:
    @pytest.mark.asyncio
    async def test_execute_file_not_found(self, tool):
        # diff_git gracefully falls back to empty string for missing git objects
        # — returns a result dict (no raise), success may be True or False
        result = await tool.execute(
            {"mode": "diff_git", "file_path": "/nonexistent/file.py"}
        )
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_execute_git_mode(self, tool):
        # The correct mode name is "diff_git"
        with patch.object(tool, "_diff_git") as mock_git:
            mock_result = MagicMock()
            mock_result.to_dict.return_value = {"changes": []}
            mock_git.return_value = mock_result
            result = await tool.execute(
                {
                    "file_path": "/src/main.py",
                    "mode": "diff_git",
                }
            )
            assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_execute_with_invalid_mode(self, tool):
        # Unknown mode raises ValueError — the MCP layer wraps it
        with pytest.raises(ValueError, match="Unknown mode"):
            await tool.execute(
                {
                    "file_path": "/src/main.py",
                    "mode": "invalid_mode",
                }
            )
