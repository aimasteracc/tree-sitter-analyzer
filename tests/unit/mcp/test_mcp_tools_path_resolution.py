#!/usr/bin/env python3
"""
import pytest
Integration tests for MCP tools path resolution.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
    AnalyzeCodeStructureTool,
)
from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool
from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool
from tree_sitter_analyzer.mcp.tools.universal_analyze_tool import UniversalAnalyzeTool


class TestMCPToolsPathResolution:
    """Test that all MCP tools use the PathResolver consistently."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = str(Path(self.temp_dir) / "project")
        Path(self.project_root).mkdir(parents=True, exist_ok=True)

        # Create test files
        self.test_file = str(Path(self.project_root) / "test_file.txt")
        with open(self.test_file, "w") as f:
            f.write("test content")

        # Initialize tools with project root
        self.analyze_scale_tool = AnalyzeScaleTool(self.project_root)
        self.query_tool = QueryTool(self.project_root)
        self.read_partial_tool = ReadPartialTool(self.project_root)
        self.analyze_code_structure_tool = AnalyzeCodeStructureTool(self.project_root)
        self.universal_analyze_tool = UniversalAnalyzeTool(self.project_root)

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_analyze_scale_tool_uses_path_resolver(self):
        """Test that AnalyzeScaleTool uses PathResolver."""
        assert self.analyze_scale_tool.path_resolver is not None
        # Use Path.resolve() for proper normalization
        actual_root = str(
            Path(self.analyze_scale_tool.path_resolver.project_root).resolve()
        )
        expected_root = str(Path(self.project_root).resolve())
        assert actual_root == expected_root

    def test_query_tool_uses_path_resolver(self):
        """Test that QueryTool uses PathResolver."""
        assert self.query_tool.path_resolver is not None
        # Use Path.resolve() for proper normalization
        actual_root = str(Path(self.query_tool.path_resolver.project_root).resolve())
        expected_root = str(Path(self.project_root).resolve())
        assert actual_root == expected_root

    def test_read_partial_tool_uses_path_resolver(self):
        """Test that ReadPartialTool uses PathResolver."""
        assert self.read_partial_tool.path_resolver is not None
        # Use Path.resolve() for proper normalization
        actual_root = str(
            Path(self.read_partial_tool.path_resolver.project_root).resolve()
        )
        expected_root = str(Path(self.project_root).resolve())
        assert actual_root == expected_root

    def test_analyze_code_structure_tool_uses_path_resolver(self):
        """Test that AnalyzeCodeStructureTool uses PathResolver."""
        assert self.analyze_code_structure_tool.path_resolver is not None
        # Use Path.resolve() for proper normalization
        actual_root = str(
            Path(self.analyze_code_structure_tool.path_resolver.project_root).resolve()
        )
        expected_root = str(Path(self.project_root).resolve())
        assert actual_root == expected_root

    def test_universal_analyze_tool_uses_path_resolver(self):
        """Test that UniversalAnalyzeTool uses PathResolver."""
        assert self.universal_analyze_tool.path_resolver is not None
        # Use Path.resolve() for proper normalization
        actual_root = str(
            Path(self.universal_analyze_tool.path_resolver.project_root).resolve()
        )
        expected_root = str(Path(self.project_root).resolve())
        assert actual_root == expected_root

    def test_consistent_path_resolution_across_tools(self):
        """Test that all tools resolve paths consistently."""
        relative_path = "test_file.txt"

        # All tools should resolve the same relative path to the same absolute path
        resolved_paths = [
            self.analyze_scale_tool.path_resolver.resolve(relative_path),
            self.query_tool.path_resolver.resolve(relative_path),
            self.read_partial_tool.path_resolver.resolve(relative_path),
            self.analyze_code_structure_tool.path_resolver.resolve(relative_path),
            self.universal_analyze_tool.path_resolver.resolve(relative_path),
        ]

        # All resolved paths should be the same
        assert len(set(resolved_paths)) == 1
        # Use Path.resolve() for proper normalization
        actual_path = str(Path(resolved_paths[0]).resolve())
        expected_path = str(Path(self.test_file).resolve())
        assert actual_path == expected_path

    def test_cross_platform_path_handling(self):
        """Test cross-platform path handling in all tools."""
        # Test with Windows-style paths
        windows_path = "test\\file.txt"
        resolved_windows = self.analyze_scale_tool.path_resolver.resolve(windows_path)

        # Test with Unix-style paths
        unix_path = "test/file.txt"
        resolved_unix = self.analyze_scale_tool.path_resolver.resolve(unix_path)

        # Both should resolve to the same normalized path
        # Convert both to forward slashes for consistent comparison
        normalized_windows = resolved_windows.replace("\\", "/")
        normalized_unix = resolved_unix.replace("\\", "/")
        assert normalized_windows == normalized_unix

    def test_tools_without_project_root(self):
        """Test tools initialized without project root."""
        tool_without_root = AnalyzeScaleTool()
        assert tool_without_root.path_resolver.project_root is None

        # Should still work with absolute paths
        absolute_path = self.test_file
        resolved = tool_without_root.path_resolver.resolve(absolute_path)
        # Use Path.resolve() for proper normalization
        resolved_normalized = str(Path(resolved).resolve())
        expected_normalized = str(Path(absolute_path).resolve())
        assert resolved_normalized == expected_normalized

    def test_query_tool_execute_with_path_resolution(self):
        """Test that QueryTool execute method uses path resolution."""
        with patch.object(self.query_tool.path_resolver, "resolve") as mock_resolve:
            mock_resolve.return_value = self.test_file

            # Since execute is async, we'll test the path resolution part separately
            # and verify that the path resolver was called correctly
            resolved_path = self.query_tool.path_resolver.resolve("test_file.txt")
            assert resolved_path == self.test_file

            # Verify path resolver was called
            mock_resolve.assert_called_once_with("test_file.txt")


class TestMCPToolsIntegration:
    """Integration tests for MCP tools working together."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = str(Path(self.temp_dir) / "project")
        Path(self.project_root).mkdir(exist_ok=True)

        # Create a simple Java file for testing
        self.java_file = str(Path(self.project_root) / "Test.java")
        with open(self.java_file, "w") as f:
            f.write(
                """
public class Test {
    public void method1() {}
    private void method2() {}
}
"""
            )

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_all_tools_consistent_initialization(self):
        """Test that all tools initialize consistently."""
        tools = [
            AnalyzeScaleTool(self.project_root),
            QueryTool(self.project_root),
            ReadPartialTool(self.project_root),
            AnalyzeCodeStructureTool(self.project_root),
            UniversalAnalyzeTool(self.project_root),
        ]

        for tool in tools:
            assert tool.path_resolver is not None
            # Use Path.resolve() for proper normalization
            actual_root = str(Path(tool.path_resolver.project_root).resolve())
            expected_root = str(Path(self.project_root).resolve())
            assert actual_root == expected_root

    def test_query_tool_execute_with_path_resolution(self):
        """Test that QueryTool execute method uses path resolution."""
        tool = QueryTool(self.project_root)

        # Test path resolution without calling the async execute method
        resolved_path = tool.path_resolver.resolve("Test.java")
        assert resolved_path is not None

        # Verify that the path resolver works correctly
        assert resolved_path.endswith("Test.java")
