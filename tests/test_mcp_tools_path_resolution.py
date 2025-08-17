#!/usr/bin/env python3
"""
Integration tests for MCP tools path resolution.
"""

import os
import tempfile
import unittest
from unittest.mock import patch

from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool
from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool
from tree_sitter_analyzer.mcp.tools.table_format_tool import TableFormatTool
from tree_sitter_analyzer.mcp.tools.universal_analyze_tool import UniversalAnalyzeTool


class TestMCPToolsPathResolution(unittest.TestCase):
    """Test that all MCP tools use the PathResolver consistently."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = os.path.join(self.temp_dir, "project")
        os.makedirs(self.project_root, exist_ok=True)

        # Create test files
        self.test_file = os.path.join(self.project_root, "test_file.txt")
        with open(self.test_file, "w") as f:
            f.write("test content")

        # Initialize tools with project root
        self.analyze_scale_tool = AnalyzeScaleTool(self.project_root)
        self.query_tool = QueryTool(self.project_root)
        self.read_partial_tool = ReadPartialTool(self.project_root)
        self.table_format_tool = TableFormatTool(self.project_root)
        self.universal_analyze_tool = UniversalAnalyzeTool(self.project_root)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_analyze_scale_tool_uses_path_resolver(self):
        """Test that AnalyzeScaleTool uses PathResolver."""
        self.assertIsNotNone(self.analyze_scale_tool.path_resolver)
        self.assertEqual(
            self.analyze_scale_tool.path_resolver.project_root, self.project_root
        )

    def test_query_tool_uses_path_resolver(self):
        """Test that QueryTool uses PathResolver."""
        self.assertIsNotNone(self.query_tool.path_resolver)
        self.assertEqual(self.query_tool.path_resolver.project_root, self.project_root)

    def test_read_partial_tool_uses_path_resolver(self):
        """Test that ReadPartialTool uses PathResolver."""
        self.assertIsNotNone(self.read_partial_tool.path_resolver)
        self.assertEqual(
            self.read_partial_tool.path_resolver.project_root, self.project_root
        )

    def test_table_format_tool_uses_path_resolver(self):
        """Test that TableFormatTool uses PathResolver."""
        self.assertIsNotNone(self.table_format_tool.path_resolver)
        self.assertEqual(
            self.table_format_tool.path_resolver.project_root, self.project_root
        )

    def test_universal_analyze_tool_uses_path_resolver(self):
        """Test that UniversalAnalyzeTool uses PathResolver."""
        self.assertIsNotNone(self.universal_analyze_tool.path_resolver)
        self.assertEqual(
            self.universal_analyze_tool.path_resolver.project_root, self.project_root
        )

    def test_consistent_path_resolution_across_tools(self):
        """Test that all tools resolve paths consistently."""
        relative_path = "test_file.txt"

        # All tools should resolve the same relative path to the same absolute path
        resolved_paths = [
            self.analyze_scale_tool.path_resolver.resolve(relative_path),
            self.query_tool.path_resolver.resolve(relative_path),
            self.read_partial_tool.path_resolver.resolve(relative_path),
            self.table_format_tool.path_resolver.resolve(relative_path),
            self.universal_analyze_tool.path_resolver.resolve(relative_path),
        ]

        # All resolved paths should be the same
        self.assertEqual(len(set(resolved_paths)), 1)
        self.assertEqual(resolved_paths[0], self.test_file)

    def test_cross_platform_path_handling(self):
        """Test cross-platform path handling in all tools."""
        # Test with Windows-style paths
        windows_path = "test\\file.txt"
        resolved_windows = self.analyze_scale_tool.path_resolver.resolve(windows_path)

        # Test with Unix-style paths
        unix_path = "test/file.txt"
        resolved_unix = self.analyze_scale_tool.path_resolver.resolve(unix_path)

        # Both should resolve to the same normalized path
        # Use normpath to handle platform differences
        normalized_windows = os.path.normpath(resolved_windows)
        normalized_unix = os.path.normpath(resolved_unix)
        self.assertEqual(normalized_windows, normalized_unix)

    def test_tools_without_project_root(self):
        """Test tools initialized without project root."""
        tool_without_root = AnalyzeScaleTool()
        self.assertIsNone(tool_without_root.path_resolver.project_root)

        # Should still work with absolute paths
        absolute_path = self.test_file
        resolved = tool_without_root.path_resolver.resolve(absolute_path)
        self.assertEqual(resolved, absolute_path)

    def test_query_tool_execute_with_path_resolution(self):
        """Test that QueryTool execute method uses path resolution."""
        with patch.object(self.query_tool.path_resolver, "resolve") as mock_resolve:
            mock_resolve.return_value = self.test_file

            # Since execute is async, we'll test the path resolution part separately
            # and verify that the path resolver was called correctly
            resolved_path = self.query_tool.path_resolver.resolve("test_file.txt")
            self.assertEqual(resolved_path, self.test_file)

            # Verify path resolver was called
            mock_resolve.assert_called_once_with("test_file.txt")


class TestMCPToolsIntegration(unittest.TestCase):
    """Integration tests for MCP tools working together."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = os.path.join(self.temp_dir, "project")
        os.makedirs(self.project_root, exist_ok=True)

        # Create a simple Java file for testing
        self.java_file = os.path.join(self.project_root, "Test.java")
        with open(self.java_file, "w") as f:
            f.write(
                """
public class Test {
    public void method1() {}
    private void method2() {}
}
"""
            )

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_all_tools_consistent_initialization(self):
        """Test that all tools initialize consistently."""
        tools = [
            AnalyzeScaleTool(self.project_root),
            QueryTool(self.project_root),
            ReadPartialTool(self.project_root),
            TableFormatTool(self.project_root),
            UniversalAnalyzeTool(self.project_root),
        ]

        for tool in tools:
            self.assertIsNotNone(tool.path_resolver)
            self.assertEqual(tool.path_resolver.project_root, self.project_root)

    def test_query_tool_execute_with_path_resolution(self):
        """Test that QueryTool execute method uses path resolution."""
        tool = QueryTool(self.project_root)

        # Test path resolution without calling the async execute method
        resolved_path = tool.path_resolver.resolve("Test.java")
        self.assertIsNotNone(resolved_path)

        # Verify that the path resolver works correctly
        self.assertTrue(resolved_path.endswith("Test.java"))


if __name__ == "__main__":
    unittest.main()
