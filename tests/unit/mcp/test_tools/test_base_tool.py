#!/usr/bin/env python3
"""
Unit tests for base_tool module

Tests the BaseMCPTool base class and MCPTool protocol.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.base_tool import BaseMCPTool, MCPTool
from tree_sitter_analyzer.security import SecurityValidator


class ConcreteMCPTool(BaseMCPTool):
    """Concrete implementation of BaseMCPTool for testing"""

    def __init__(self, project_root: str | None = None) -> None:
        super().__init__(project_root)
        self.tool_name = "concrete_tool"

    def get_tool_definition(self) -> dict:
        """Get tool definition"""
        return {
            "name": self.tool_name,
            "description": "Test tool",
        }

    async def execute(self, arguments: dict) -> dict:
        """Execute tool"""
        return {"result": "success", "arguments": arguments}

    def validate_arguments(self, arguments: dict) -> bool:
        """Validate arguments"""
        return "file_path" in arguments


class TestBaseMCPToolInit:
    """Test BaseMCPTool initialization"""

    def test_init_without_project_root(self):
        """Test initialization without project root"""
        tool = ConcreteMCPTool()
        assert tool.project_root is None
        assert tool.security_validator is not None
        assert tool.path_resolver is not None

    def test_init_with_project_root(self):
        """Test initialization with project root"""
        tool = ConcreteMCPTool(project_root="/test/path")
        assert tool.project_root == "/test/path"
        assert tool.security_validator is not None
        assert tool.path_resolver is not None

    def test_init_creates_security_validator(self):
        """Test that security validator is created correctly"""
        tool = ConcreteMCPTool(project_root="/test")
        assert isinstance(tool.security_validator, SecurityValidator)

    def test_init_creates_path_resolver(self):
        """Test that path resolver is created correctly"""
        tool = ConcreteMCPTool(project_root="/test")
        assert tool.path_resolver is not None


class TestSetProjectPath:
    """Test set_project_path method"""

    def test_set_project_path_updates_root(self):
        """Test that set_project_path updates project root"""
        tool = ConcreteMCPTool(project_root="/old/path")
        tool.set_project_path("/new/path")
        assert tool.project_root == "/new/path"

    def test_set_project_path_updates_security_validator(self):
        """Test that security validator is updated"""
        tool = ConcreteMCPTool(project_root="/old/path")
        old_validator = tool.security_validator
        tool.set_project_path("/new/path")
        assert tool.security_validator is not old_validator

    def test_set_project_path_updates_path_resolver(self):
        """Test that path resolver is updated"""
        tool = ConcreteMCPTool(project_root="/old/path")
        old_resolver = tool.path_resolver
        tool.set_project_path("/new/path")
        assert tool.path_resolver is not old_resolver

    @patch("tree_sitter_analyzer.mcp.tools.base_tool.get_shared_cache")
    def test_set_project_path_clears_cache(self, mock_get_cache):
        """Test that shared cache is cleared when project path changes"""
        mock_cache = MagicMock()
        mock_get_cache.return_value = mock_cache

        tool = ConcreteMCPTool(project_root="/old/path")
        tool.set_project_path("/new/path")

        mock_cache.clear.assert_called_once()


class TestResolveAndValidateFilePath:
    """Test resolve_and_validate_file_path method"""

    def test_resolve_valid_file_path(self, tmp_path):
        """Test resolving a valid file path"""
        tool = ConcreteMCPTool(project_root=str(tmp_path))
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        result = tool.resolve_and_validate_file_path(str(test_file))
        assert str(test_file.resolve()) in result

    def test_resolve_relative_file_path(self, tmp_path):
        """Test resolving a relative file path"""
        tool = ConcreteMCPTool(project_root=str(tmp_path))
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        result = tool.resolve_and_validate_file_path("test.txt")
        assert str(test_file.resolve()) in result

    def test_resolve_absolute_file_path(self, tmp_path):
        """Test resolving an absolute file path"""
        tool = ConcreteMCPTool(project_root=str(tmp_path))
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        result = tool.resolve_and_validate_file_path(str(test_file.resolve()))
        assert str(test_file.resolve()) in result

    def test_resolve_nonexistent_file(self, tmp_path):
        """Test that nonexistent file path can be resolved (security only, no existence check)"""
        tool = ConcreteMCPTool(project_root=str(tmp_path))

        # resolve_and_validate_file_path only does security validation, not existence check
        # It should resolve the path successfully even if file doesn't exist
        result = tool.resolve_and_validate_file_path("nonexistent.txt")
        assert "nonexistent.txt" in result or "nonexistent.txt" in Path(result).name

    def test_validate_file_outside_project(self, tmp_path):
        """Test that file outside project raises ValueError"""
        tool = ConcreteMCPTool(project_root=str(tmp_path))

        with tempfile.TemporaryDirectory() as outside_dir:
            outside_file = Path(outside_dir) / "outside.txt"
            outside_file.write_text("content")

            with pytest.raises(ValueError, match="Invalid file path"):
                tool.resolve_and_validate_file_path(str(outside_file))

    def test_validate_file_without_project_root(self, tmp_path):
        """Test validation without project root"""
        tool = ConcreteMCPTool(project_root=None)
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        # Should work with absolute path even without project root
        result = tool.resolve_and_validate_file_path(str(test_file.resolve()))
        assert str(test_file.resolve()) in result

    @patch("tree_sitter_analyzer.mcp.tools.base_tool.get_shared_cache")
    def test_resolve_uses_cache(self, mock_get_cache):
        """Test that shared cache is used for caching"""
        mock_cache = MagicMock()
        mock_cache.get_security_validation.return_value = (True, "")
        mock_cache.get_resolved_path.return_value = None
        mock_get_cache.return_value = mock_cache

        tool = ConcreteMCPTool(project_root="/test")
        tool.resolve_and_validate_file_path("test.txt")

        mock_cache.get_security_validation.assert_called()
        mock_cache.get_resolved_path.assert_called()

    @patch("tree_sitter_analyzer.mcp.tools.base_tool.get_shared_cache")
    def test_resolve_caches_validation(self, mock_get_cache):
        """Test that validation result is cached"""
        mock_cache = MagicMock()
        mock_cache.get_security_validation.return_value = None
        mock_cache.get_resolved_path.return_value = "/resolved/path"
        mock_cache.set_security_validation.return_value = None
        mock_get_cache.return_value = mock_cache

        tool = ConcreteMCPTool(project_root="/test")
        tool.resolve_and_validate_file_path("test.txt")

        # Check that validation was cached for both original and resolved path
        assert mock_cache.set_security_validation.call_count >= 1

    @patch("tree_sitter_analyzer.mcp.tools.base_tool.get_shared_cache")
    def test_resolve_caches_resolved_path(self, mock_get_cache):
        """Test that resolved path is cached"""
        mock_cache = MagicMock()
        mock_cache.get_security_validation.return_value = (True, "")
        mock_cache.get_resolved_path.return_value = None
        mock_cache.set_resolved_path.return_value = None
        mock_get_cache.return_value = mock_cache

        tool = ConcreteMCPTool(project_root="/test")
        tool.resolve_and_validate_file_path("test.txt")

        mock_cache.set_resolved_path.assert_called_once()


class TestResolveAndValidateDirectoryPath:
    """Test resolve_and_validate_directory_path method"""

    def test_resolve_valid_directory(self, tmp_path):
        """Test resolving a valid directory"""
        tool = ConcreteMCPTool(project_root=str(tmp_path))
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()

        result = tool.resolve_and_validate_directory_path(str(test_dir))
        assert str(test_dir.resolve()) in result

    def test_resolve_relative_directory(self, tmp_path):
        """Test resolving a relative directory"""
        tool = ConcreteMCPTool(project_root=str(tmp_path))
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()

        result = tool.resolve_and_validate_directory_path("test_dir")
        assert str(test_dir.resolve()) in result

    def test_resolve_absolute_directory(self, tmp_path):
        """Test resolving an absolute directory"""
        tool = ConcreteMCPTool(project_root=str(tmp_path))
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()

        result = tool.resolve_and_validate_directory_path(str(test_dir.resolve()))
        assert str(test_dir.resolve()) in result

    def test_validate_nonexistent_directory(self, tmp_path):
        """Test that nonexistent directory raises ValueError"""
        tool = ConcreteMCPTool(project_root=str(tmp_path))

        with pytest.raises(ValueError, match="Invalid directory path"):
            tool.resolve_and_validate_directory_path("nonexistent_dir")

    def test_validate_directory_outside_project(self, tmp_path):
        """Test that directory outside project raises ValueError"""
        tool = ConcreteMCPTool(project_root=str(tmp_path))

        with tempfile.TemporaryDirectory() as outside_dir:
            with pytest.raises(ValueError, match="Invalid directory path"):
                tool.resolve_and_validate_directory_path(outside_dir)

    def test_validate_file_instead_of_directory(self, tmp_path):
        """Test that file path raises ValueError"""
        tool = ConcreteMCPTool(project_root=str(tmp_path))
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        with pytest.raises(ValueError, match="Invalid directory path"):
            tool.resolve_and_validate_directory_path(str(test_file))


class TestAbstractMethods:
    """Test abstract methods"""

    def test_get_tool_definition_is_abstract(self):
        """Test that get_tool_definition is abstract"""
        with pytest.raises(TypeError):
            BaseMCPTool()  # type: ignore

    def test_execute_is_abstract(self):
        """Test that execute is abstract"""
        with pytest.raises(TypeError):
            BaseMCPTool()  # type: ignore

    def test_validate_arguments_is_abstract(self):
        """Test that validate_arguments is abstract"""
        with pytest.raises(TypeError):
            BaseMCPTool()  # type: ignore


class TestMCPToolProtocol:
    """Test MCPTool protocol class"""

    def test_mcp_tool_get_tool_definition(self):
        """Test MCPTool protocol get_tool_definition"""
        tool = ConcreteMCPTool()
        definition = tool.get_tool_definition()
        assert definition["name"] == "concrete_tool"

    @pytest.mark.asyncio
    async def test_mcp_tool_execute(self):
        """Test MCPTool protocol execute"""
        tool = ConcreteMCPTool()
        result = await tool.execute({"test": "value"})
        assert result["result"] == "success"

    def test_mcp_tool_validate_arguments(self):
        """Test MCPTool protocol validate_arguments"""
        tool = ConcreteMCPTool()
        assert tool.validate_arguments({"file_path": "test"}) is True
        assert tool.validate_arguments({}) is False

    def test_mcp_tool_execute_raises_not_implemented(self):
        """Test that default execute raises NotImplementedError"""

        # Create a minimal concrete implementation
        class MinimalTool(MCPTool):
            def get_tool_definition(self):
                return {}

            def validate_arguments(self, arguments):
                return True

        tool = MinimalTool()

        # The execute method in MCPTool is not abstract, it raises NotImplementedError
        # This test verifies the default behavior
        with pytest.raises(
            NotImplementedError, match="Subclasses must implement execute method"
        ):
            # Note: execute is async, so we need to check the coroutine behavior
            # The NotImplementedError is raised when the coroutine is awaited
            import asyncio

            coro = tool.execute({})
            asyncio.run(coro)

    def test_mcp_tool_validate_arguments_raises_not_implemented(self):
        """Test that default validate_arguments raises NotImplementedError"""

        # Create a minimal concrete implementation
        class MinimalTool(MCPTool):
            def get_tool_definition(self):
                return {}

            async def execute(self, arguments):
                return {}

        tool = MinimalTool()

        with pytest.raises(
            NotImplementedError, match="must implement validate_arguments method"
        ):
            tool.validate_arguments({})


class TestBaseToolIntegration:
    """Integration tests for BaseMCPTool"""

    def test_full_workflow_with_file_validation(self, tmp_path):
        """Test complete workflow with file validation"""
        tool = ConcreteMCPTool(project_root=str(tmp_path))
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        # Resolve and validate file
        resolved_path = tool.resolve_and_validate_file_path("test.txt")

        # Use in execute
        args = {"file_path": resolved_path}
        assert tool.validate_arguments(args) is True

    def test_project_path_change_invalidates_cache(self, tmp_path):
        """Test that changing project path invalidates cache"""
        tool = ConcreteMCPTool(project_root=str(tmp_path))
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        # First resolve
        tool.resolve_and_validate_file_path("test.txt")

        # Change project path
        with tempfile.TemporaryDirectory() as new_dir:
            tool.set_project_path(new_dir)

            # Cache should be cleared
            # This is tested via mock in TestSetProjectPath
            assert tool.project_root == new_dir
