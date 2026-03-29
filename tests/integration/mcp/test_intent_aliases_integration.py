#!/usr/bin/env python3
"""
Integration tests for Intent Aliases with MCP Server.

Tests that aliases work end-to-end through the MCP server:
- Tool calls with alias names
- Parameter passing
- Result format consistency
- Error handling with aliases
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
from tree_sitter_analyzer.mcp.utils.error_handler import AnalysisError


@pytest.fixture(scope="session")
def server():
    """
    Session-scoped MCP server fixture.

    Creates ONE server instance for the entire test session.
    This prevents race conditions when tests run in parallel.
    """
    return TreeSitterAnalyzerMCPServer()


class TestIntentAliasIntegration:
    """测试 Intent Alias 在 MCP Server 中的集成"""

    @pytest.fixture
    def temp_python_file(self):
        """
        Create a temporary Python file in an isolated directory.

        Each test gets its own unique directory to prevent parallel
        tests from finding each other's files.
        """
        # Create unique directory for this test
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            test_file = tmpdir_path / "test_example.py"

            content = '''
def example_function():
    """Example function for testing"""
    return "Hello, World!"

class ExampleClass:
    def method(self):
        pass
'''
            test_file.write_text(content, encoding='utf-8')
            yield test_file
            # Cleanup automatic via TemporaryDirectory context manager

    @pytest.mark.asyncio
    async def test_locate_usage_alias_calls_search_content(
        self, server, temp_python_file
    ):
        """locate_usage alias 应该调用 search_content 工具并返回正确格式"""
        # Use alias name
        result = await server.call_tool(
            "locate_usage",
            arguments={
                "roots": [str(temp_python_file.parent)],
                "query": "example_function",
                "output_format": "json",
            }
        )

        # Should succeed and return results in tool's native format
        assert result["success"] is True
        assert "count" in result
        assert "results" in result
        assert result["count"] > 0
        # Verify the search actually found our function
        found = any("example_function" in str(r) for r in result["results"])
        assert found, f"Should find 'example_function' in results: {result['results']}"

    @pytest.mark.asyncio
    async def test_map_structure_alias_calls_list_files(
        self, server, temp_python_file
    ):
        """map_structure alias 应该调用 list_files 工具并返回正确格式"""
        result = await server.call_tool(
            "map_structure",
            arguments={
                "roots": [str(temp_python_file.parent)],
                "pattern": "*.py",
                "glob": True,
                "output_format": "json",
            }
        )

        # Should succeed and return results in tool's native format
        assert result["success"] is True
        assert "count" in result
        assert "results" in result
        # Should find our temp Python file
        found = any(temp_python_file.name in str(r) for r in result["results"])
        assert found, f"Should find {temp_python_file.name} in results"

    @pytest.mark.asyncio
    async def test_extract_structure_alias_calls_analyze_code_structure(
        self, server, temp_python_file
    ):
        """extract_structure alias 应该调用 analyze_code_structure 工具"""
        result = await server.call_tool(
            "extract_structure",
            arguments={
                "file_path": str(temp_python_file),
                "language": "python",
                "output_format": "json",
            }
        )

        # Should succeed and return structure info in tool's native format
        assert result["success"] is True
        assert "format_type" in result
        # Should contain our function and class
        result_str = str(result)
        assert "example_function" in result_str
        assert "ExampleClass" in result_str

    @pytest.mark.asyncio
    async def test_original_tool_name_still_works(
        self, server, temp_python_file
    ):
        """原始工具名应该仍然有效（向后兼容）"""
        # Call with original name
        result_original = await server.call_tool(
            "search_content",
            arguments={
                "roots": [str(temp_python_file.parent)],
                "query": "example_function",
                "output_format": "json",
            }
        )

        # Call with alias
        result_alias = await server.call_tool(
            "locate_usage",
            arguments={
                "roots": [str(temp_python_file.parent)],
                "query": "example_function",
                "output_format": "json",
            }
        )

        # Results should be identical (both return same tool's response)
        assert result_original["success"] == result_alias["success"]
        assert result_original["count"] == result_alias["count"]
        # Results content should match
        assert result_original["results"] == result_alias["results"]


class TestIntentAliasErrorHandling:
    """测试 Intent Alias 的错误处理"""

    @pytest.mark.asyncio
    async def test_unknown_alias_raises_error(self, server):
        """未知的 alias 应该返回错误"""
        with pytest.raises(ValueError, match="Unknown tool"):
            await server.call_tool(
                "invalid_alias_name",
                arguments={}
            )

    @pytest.mark.asyncio
    async def test_alias_with_invalid_params_raises_error(
        self, server
    ):
        """Alias + 无效参数应该返回错误"""
        with pytest.raises(AnalysisError):
            await server.call_tool(
                "locate_usage",
                arguments={
                    "invalid_param": "value"
                }
            )


class TestMultipleAliasesForSameTool:
    """测试同一工具的多个 alias"""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory with files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create some test files
            (tmpdir_path / "file1.py").write_text("# Python file 1")
            (tmpdir_path / "file2.py").write_text("# Python file 2")
            (tmpdir_path / "README.md").write_text("# Readme")

            yield tmpdir_path

    @pytest.mark.asyncio
    async def test_map_structure_and_discover_files_same_result(
        self, server, temp_dir
    ):
        """map_structure 和 discover_files 应该返回相同结果"""
        # Call with first alias
        result1 = await server.call_tool(
            "map_structure",
            arguments={
                "roots": [str(temp_dir)],
                "pattern": "*.py",
                "glob": True,
                "output_format": "json"
            }
        )

        # Call with second alias
        result2 = await server.call_tool(
            "discover_files",
            arguments={
                "roots": [str(temp_dir)],
                "pattern": "*.py",
                "glob": True,
                "output_format": "json"
            }
        )

        # Results should be identical (both map to same tool)
        assert result1["success"] == result2["success"]
        assert result1["count"] == result2["count"]
        assert result1["results"] == result2["results"]

    @pytest.mark.asyncio
    async def test_locate_usage_and_find_usage_same_result(
        self, server, temp_dir
    ):
        """locate_usage 和 find_usage 应该返回相同结果"""
        # Create a test file with searchable content
        test_file = temp_dir / "test.py"
        test_file.write_text("def search_target():\n    pass")

        # Call with first alias
        result1 = await server.call_tool(
            "locate_usage",
            arguments={
                "roots": [str(temp_dir)],
                "query": "search_target",
                "output_format": "json"
            }
        )

        # Call with second alias
        result2 = await server.call_tool(
            "find_usage",
            arguments={
                "roots": [str(temp_dir)],
                "query": "search_target",
                "output_format": "json"
            }
        )

        # Results should be identical (both map to same tool)
        assert result1["success"] == result2["success"]
        assert result1["count"] == result2["count"]
        assert result1["results"] == result2["results"]


class TestAliasWithAllToolParameters:
    """测试 Alias 支持原始工具的所有参数"""

    @pytest.fixture
    def temp_dir_with_files(self):
        """Create temp directory with multiple files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create test files
            (tmpdir_path / "app.py").write_text(
                "def target(): pass\nclass TargetClass: pass"
            )
            (tmpdir_path / "utils.py").write_text(
                "def helper(): pass"
            )
            (tmpdir_path / "test.py").write_text(
                "import target\ntarget()"
            )

            yield tmpdir_path

    @pytest.mark.asyncio
    async def test_locate_usage_supports_all_search_content_params(
        self, server, temp_dir_with_files
    ):
        """locate_usage 应该支持 search_content 的所有参数"""
        result = await server.call_tool(
            "locate_usage",
            arguments={
                "roots": [str(temp_dir_with_files)],
                "query": "target",
                "include_globs": ["*.py"],
                "case": "sensitive",
                "output_format": "json",
            }
        )

        # Should succeed and respect all parameters
        assert result["success"] is True
        assert "count" in result
        assert "results" in result
        # Should find matches (target appears in multiple files)
        assert result["count"] > 0

    @pytest.mark.asyncio
    async def test_map_structure_supports_all_list_files_params(
        self, server, temp_dir_with_files
    ):
        """map_structure 应该支持 list_files 的所有参数"""
        result = await server.call_tool(
            "map_structure",
            arguments={
                "roots": [str(temp_dir_with_files)],
                "pattern": "*.py",
                "glob": True,
                "max_depth": 1,
                "exclude": ["test*.py"],
                "output_format": "json",
            }
        )

        # Should succeed and respect all parameters
        assert result["success"] is True
        assert "results" in result
        # Should exclude test.py
        result_str = str(result["results"])
        assert "test.py" not in result_str
        # Should include app.py and utils.py
        assert "app.py" in result_str or "utils.py" in result_str
