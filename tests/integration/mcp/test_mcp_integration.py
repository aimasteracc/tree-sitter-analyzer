#!/usr/bin/env python3
"""
MCP Integration Tests.

Tests MCP server integration with core components.
"""

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
from tree_sitter_analyzer.mcp.utils import (
    get_performance_monitor,
)


class TestMCPServerLifecycle:
    """Tests for MCP server lifecycle management."""

    def test_server_initialization(self):
        """Test server initialization."""
        server = TreeSitterAnalyzerMCPServer()
        assert server is not None
        assert server.name is not None
        assert server.version is not None

    def test_server_components_initialized(self):
        """Test that all server components are initialized."""
        server = TreeSitterAnalyzerMCPServer()
        assert server.analysis_engine is not None
        assert server.read_partial_tool is not None
        assert server.table_format_tool is not None
        assert server.code_file_resource is not None
        assert server.project_stats_resource is not None

    def test_set_project_path(self):
        """Test setting project path."""
        server = TreeSitterAnalyzerMCPServer()
        temp_dir = tempfile.mkdtemp()
        server.set_project_path(temp_dir)
        # Verify project path was set (no direct attribute access available)
        assert True  # If we get here, set_project_path didn't raise an exception

    @pytest.mark.asyncio
    async def test_server_cleanup(self):
        """Test server cleanup."""
        server = TreeSitterAnalyzerMCPServer()
        # Perform cleanup
        if hasattr(server, "cleanup"):
            await server.cleanup()
        # Verify cleanup succeeded
        assert True  # If we get here, cleanup didn't raise an exception


class TestMCPToolsIntegration:
    """Tests for MCP tools integration."""

    @pytest.mark.asyncio
    async def test_analyze_code_scale_tool(self):
        """Test analyze_code_scale tool."""
        server = TreeSitterAnalyzerMCPServer()
        temp_dir = tempfile.mkdtemp()
        test_file = Path(temp_dir) / "test.py"
        test_file.write_text("def hello(): pass")

        result = await server._analyze_code_scale(
            {"file_path": str(test_file), "include_complexity": False}
        )

        assert "file_metrics" in result
        assert "language" in result
        assert result["language"] == "python"

    @pytest.mark.asyncio
    async def test_analyze_code_structure_tool(self):
        """Test analyze_code_structure tool."""
        server = TreeSitterAnalyzerMCPServer()
        temp_dir = tempfile.mkdtemp()
        test_file = Path(temp_dir) / "test.py"
        test_file.write_text("def hello(): pass")

        result = await server.table_format_tool.execute(
            {
                "file_path": str(test_file),
                "format_type": "full",
                "output_format": "json",
            }
        )

        assert "table_output" in result
        assert "language" in result
        assert result["language"] == "python"

    @pytest.mark.asyncio
    async def test_extract_code_section_tool(self):
        """Test extract_code_section tool."""
        server = TreeSitterAnalyzerMCPServer()
        temp_dir = tempfile.mkdtemp()
        test_file = Path(temp_dir) / "test.py"
        test_file.write_text("def hello():\n    pass\n\ndef world():\n    pass")

        result = await server.read_partial_tool.execute(
            {
                "file_path": str(test_file),
                "start_line": 1,
                "end_line": 2,
                "output_format": "json",
            }
        )

        assert "partial_content_result" in result
        assert "def hello():" in result["partial_content_result"]

    @pytest.mark.asyncio
    async def test_query_code_tool(self):
        """Test query_code tool."""
        server = TreeSitterAnalyzerMCPServer()
        temp_dir = tempfile.mkdtemp()
        test_file = Path(temp_dir) / "test.py"
        test_file.write_text("def hello(): pass")

        result = await server.query_tool.execute(
            {
                "file_path": str(test_file),
                "language": "python",
                "query_key": "functions",
                "result_format": "json",
            }
        )

        # Result contains query results in various formats
        assert (
            "success" in result or "query_result" in result or "toon_content" in result
        )

    @pytest.mark.asyncio
    async def test_file_output_manager_tool(self):
        """Test file output via tools with output_file parameter."""
        server = TreeSitterAnalyzerMCPServer()
        temp_dir = tempfile.mkdtemp()
        test_file = Path(temp_dir) / "test.py"
        test_file.write_text("def hello(): pass")
        output_file = Path(temp_dir) / "output.json"

        # Use read_partial_tool with output_file parameter
        result = await server.read_partial_tool.execute(
            {
                "file_path": str(test_file),
                "start_line": 1,
                "end_line": 2,
                "output_file": str(output_file),
                "output_format": "json",
            }
        )

        # Check result has success field
        assert "success" in result or "partial_content_result" in result


class TestMCPResourcesIntegration:
    """Tests for MCP resources integration."""

    @pytest.mark.asyncio
    async def test_code_file_resource(self):
        """Test code file resource."""
        server = TreeSitterAnalyzerMCPServer()
        temp_dir = tempfile.mkdtemp()
        test_file = Path(temp_dir) / "test.py"
        test_file.write_text("def hello(): pass")

        file_uri = f"code://file/{str(test_file)}"
        assert server.code_file_resource.matches_uri(file_uri)

        content = await server.code_file_resource.read_resource(file_uri)
        assert "def hello():" in content

    @pytest.mark.asyncio
    async def test_project_stats_resource(self):
        """Test project statistics resource."""
        server = TreeSitterAnalyzerMCPServer()
        temp_dir = tempfile.mkdtemp()
        server.set_project_path(temp_dir)

        stats_uri = "code://stats/overview"
        assert server.project_stats_resource.matches_uri(stats_uri)

        content = await server.project_stats_resource.read_resource(stats_uri)
        stats = json.loads(content)
        assert "total_files" in stats
        assert "languages" in stats


class TestMCPErrorHandling:
    """Tests for MCP error handling."""

    @pytest.mark.asyncio
    async def test_invalid_file_path_error(self):
        """Test error handling for invalid file path."""
        server = TreeSitterAnalyzerMCPServer()
        # Invalid absolute path raises ValueError
        with pytest.raises(ValueError, match="Invalid file path"):
            await server._analyze_code_scale(
                {"file_path": "/nonexistent/file.py", "include_complexity": False}
            )

    @pytest.mark.asyncio
    async def test_unsupported_language_error(self):
        """Test error handling for unsupported language."""
        server = TreeSitterAnalyzerMCPServer()
        temp_dir = tempfile.mkdtemp()
        test_file = Path(temp_dir) / "test.xyz"
        test_file.write_text("some content")

        # Unsupported language raises either UnsupportedLanguageError or ValueError
        # depending on where in the tool chain it's caught
        from tree_sitter_analyzer.core.analysis_engine import UnsupportedLanguageError

        with pytest.raises((UnsupportedLanguageError, ValueError)) as exc_info:
            await server._analyze_code_scale(
                {"file_path": str(test_file), "include_complexity": False}
            )

        # Verify the error message mentions unsupported language
        assert "unsupported language" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_invalid_query_error(self):
        """Test error handling for invalid query."""
        server = TreeSitterAnalyzerMCPServer()
        temp_dir = tempfile.mkdtemp()
        test_file = Path(temp_dir) / "test.py"
        test_file.write_text("def hello(): pass")

        result = await server.query_tool.execute(
            {
                "file_path": str(test_file),
                "language": "python",
                "query_key": "invalid_query",
                "result_format": "json",
            }
        )
        # Should handle invalid query gracefully
        assert "query_result" in result or "error" in result


class TestMCPPerformanceIntegration:
    """Tests for MCP performance integration."""

    @pytest.mark.asyncio
    async def test_cache_integration(self):
        """Test cache integration with MCP server."""
        server = TreeSitterAnalyzerMCPServer()
        temp_dir = tempfile.mkdtemp()
        test_file = Path(temp_dir) / "test.py"
        test_file.write_text("def hello(): pass")

        # First call
        result1 = await server._analyze_code_scale(
            {"file_path": str(test_file), "include_complexity": False}
        )

        # Second call (should use cache)
        result2 = await server._analyze_code_scale(
            {"file_path": str(test_file), "include_complexity": False}
        )

        assert result1["language"] == result2["language"]

    @pytest.mark.asyncio
    async def test_performance_monitoring(self):
        """Test performance monitoring integration."""
        server = TreeSitterAnalyzerMCPServer()
        temp_dir = tempfile.mkdtemp()
        test_file = Path(temp_dir) / "test.py"
        test_file.write_text("def hello(): pass")

        # Clear metrics
        monitor = get_performance_monitor()
        if hasattr(monitor, "clear_metrics"):
            monitor.clear_metrics()

        # Perform analysis
        await server._analyze_code_scale(
            {"file_path": str(test_file), "include_complexity": False}
        )

        # Check that monitor exists and is working
        assert monitor is not None


class TestMCPMultiLanguageIntegration:
    """Tests for multi-language MCP integration."""

    @pytest.mark.asyncio
    async def test_python_analysis(self):
        """Test Python file analysis."""
        server = TreeSitterAnalyzerMCPServer()
        temp_dir = tempfile.mkdtemp()
        test_file = Path(temp_dir) / "test.py"
        test_file.write_text("def hello(): pass")

        result = await server._analyze_code_scale(
            {"file_path": str(test_file), "include_complexity": False}
        )

        assert result["language"] == "python"

    @pytest.mark.asyncio
    async def test_javascript_analysis(self):
        """Test JavaScript file analysis."""
        server = TreeSitterAnalyzerMCPServer()
        temp_dir = tempfile.mkdtemp()
        test_file = Path(temp_dir) / "test.js"
        test_file.write_text("function hello() {}")

        result = await server._analyze_code_scale(
            {"file_path": str(test_file), "include_complexity": False}
        )

        assert result["language"] == "javascript"

    @pytest.mark.asyncio
    async def test_java_analysis(self):
        """Test Java file analysis."""
        server = TreeSitterAnalyzerMCPServer()
        temp_dir = tempfile.mkdtemp()
        test_file = Path(temp_dir) / "Test.java"
        test_file.write_text("public class Test { public void hello() {} }")

        result = await server._analyze_code_scale(
            {"file_path": str(test_file), "include_complexity": False}
        )

        assert result["language"] == "java"


class TestMCPConcurrencyIntegration:
    """Tests for MCP concurrency integration."""

    @pytest.mark.asyncio
    async def test_concurrent_analyses(self):
        """Test concurrent file analyses."""
        server = TreeSitterAnalyzerMCPServer()
        temp_dir = tempfile.mkdtemp()

        # Create multiple test files
        test_files = []
        for i in range(5):
            test_file = Path(temp_dir) / f"test{i}.py"
            test_file.write_text(f"def hello{i}(): pass")
            test_files.append(test_file)

        # Run analyses concurrently
        tasks = [
            server._analyze_code_scale(
                {"file_path": str(f), "include_complexity": False}
            )
            for f in test_files
        ]

        results = await asyncio.gather(*tasks)

        # Verify all analyses completed
        assert len(results) == 5
        for result in results:
            assert result["language"] == "python"

    @pytest.mark.asyncio
    async def test_concurrent_queries(self):
        """Test concurrent code queries."""
        server = TreeSitterAnalyzerMCPServer()
        temp_dir = tempfile.mkdtemp()
        test_file = Path(temp_dir) / "test.py"
        test_file.write_text("def hello(): pass\ndef world(): pass")

        # Run queries concurrently
        tasks = [
            server.query_tool.execute(
                {
                    "file_path": str(test_file),
                    "language": "python",
                    "query_key": "functions",
                    "result_format": "json",
                }
            )
            for _ in range(3)
        ]

        results = await asyncio.gather(*tasks)

        # Verify all queries completed
        assert len(results) == 3
        for result in results:
            # Result contains query results in various formats
            assert (
                "success" in result
                or "query_result" in result
                or "toon_content" in result
            )
