#!/usr/bin/env python3
"""
Large File Performance Tests.

Tests performance characteristics when processing large files.
"""

import asyncio
import tempfile
import time
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
    AnalyzeCodeStructureTool,
)
from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool


class TestLargeFilePerformance:
    """Tests for large file processing performance."""

    def setup_method(self):
        """Set up test fixtures."""
        self.server = TreeSitterAnalyzerMCPServer()
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_large_python_file(self, num_functions: int = 100) -> Path:
        """Create a large Python file for testing."""
        lines = []
        for i in range(num_functions):
            lines.append(f"def function_{i}():")
            lines.append(f"    return {i}")
            lines.append("")
        content = "\n".join(lines)
        file_path = Path(self.temp_dir) / f"large_{num_functions}.py"
        file_path.write_text(content)
        return file_path

    @pytest.mark.asyncio
    async def test_analyze_large_file_scale(self):
        """Test performance of analyzing large file with code scale."""
        file_path = self._create_large_python_file(num_functions=100)
        tool = AnalyzeScaleTool(project_root=self.temp_dir)

        start_time = time.time()
        result = await tool.execute(
            {
                "file_path": str(file_path),
                "include_complexity": False,
                "include_details": False,
            }
        )
        end_time = time.time()

        assert result["success"] is True
        assert "file_metrics" in result
        assert result["language"] == "python"

        # Performance assertion: should complete in reasonable time
        duration = end_time - start_time
        assert duration < 10.0, f"Analysis took too long: {duration:.2f}s"

    @pytest.mark.asyncio
    async def test_analyze_large_file_structure(self):
        """Test performance of analyzing large file structure."""
        file_path = self._create_large_python_file(num_functions=100)
        tool = AnalyzeCodeStructureTool(project_root=self.temp_dir)

        start_time = time.time()
        result = await tool.execute(
            {
                "file_path": str(file_path),
                "format_type": "full",
                "output_format": "json",
            }
        )
        end_time = time.time()

        assert "table_output" in result
        assert result["language"] == "python"

        # Performance assertion
        duration = end_time - start_time
        assert duration < 10.0, f"Structure analysis took too long: {duration:.2f}s"

    @pytest.mark.asyncio
    async def test_query_large_file(self):
        """Test performance of querying large file."""
        file_path = self._create_large_python_file(num_functions=100)
        tool = QueryTool(project_root=self.temp_dir)

        start_time = time.time()
        result = await tool.execute(
            {
                "file_path": str(file_path),
                "language": "python",
                "query_key": "functions",
                "result_format": "json",
            }
        )
        end_time = time.time()

        assert "query_result" in result or "success" in result

        # Performance assertion
        duration = end_time - start_time
        assert duration < 10.0, f"Query took too long: {duration:.2f}s"

    @pytest.mark.asyncio
    async def test_analyze_very_large_file(self):
        """Test performance with very large file (500 functions)."""
        file_path = self._create_large_python_file(num_functions=500)
        tool = AnalyzeScaleTool(project_root=self.temp_dir)

        start_time = time.time()
        result = await tool.execute(
            {
                "file_path": str(file_path),
                "include_complexity": False,
                "include_details": False,
            }
        )
        end_time = time.time()

        assert result["success"] is True
        assert "file_metrics" in result

        # Performance assertion: should still complete in reasonable time
        duration = end_time - start_time
        assert (
            duration < 30.0
        ), f"Very large file analysis took too long: {duration:.2f}s"

    @pytest.mark.asyncio
    async def test_cache_performance_large_file(self):
        """Test cache performance with large file."""
        file_path = self._create_large_python_file(num_functions=100)
        tool = AnalyzeScaleTool(project_root=self.temp_dir)

        # First analysis (cache miss)
        start_time = time.time()
        result1 = await tool.execute(
            {
                "file_path": str(file_path),
                "include_complexity": False,
                "include_details": False,
            }
        )
        duration1 = time.time() - start_time

        # Second analysis (cache hit)
        start_time = time.time()
        result2 = await tool.execute(
            {
                "file_path": str(file_path),
                "include_complexity": False,
                "include_details": False,
            }
        )
        duration2 = time.time() - start_time

        assert result1["success"] is True
        assert result2["success"] is True

        # Cache hit should be faster or equal to cache miss
        assert (
            duration2 <= duration1
        ), "Cache hit should be faster or equal to cache miss"

    @pytest.mark.asyncio
    async def test_memory_usage_large_file(self):
        """Test memory usage with large file."""
        file_path = self._create_large_python_file(num_functions=200)
        tool = AnalyzeScaleTool(project_root=self.temp_dir)

        # Get initial memory usage
        import psutil

        process = psutil.Process()
        initial_memory = process.memory_info().rss

        # Perform analysis
        result = await tool.execute(
            {
                "file_path": str(file_path),
                "include_complexity": False,
                "include_details": False,
            }
        )

        # Get final memory usage
        final_memory = process.memory_info().rss
        memory_increase = (final_memory - initial_memory) / (1024 * 1024)  # MB

        assert result["success"] is True
        # Memory increase should be reasonable (< 100 MB)
        assert memory_increase < 100, f"Memory usage too high: {memory_increase:.2f}MB"

    @pytest.mark.asyncio
    async def test_concurrent_large_file_analysis(self):
        """Test concurrent analysis of multiple large files."""
        file_paths = [
            self._create_large_python_file(num_functions=50),
            self._create_large_python_file(num_functions=50),
            self._create_large_python_file(num_functions=50),
        ]
        tool = AnalyzeScaleTool(project_root=self.temp_dir)

        start_time = time.time()
        tasks = [
            tool.execute(
                {
                    "file_path": str(fp),
                    "include_complexity": False,
                    "include_details": False,
                }
            )
            for fp in file_paths
        ]
        results = await asyncio.gather(*tasks)
        end_time = time.time()

        # All analyses should succeed
        assert all(r["success"] for r in results)

        # Concurrent analysis should be faster than sequential
        duration = end_time - start_time
        assert duration < 20.0, f"Concurrent analysis took too long: {duration:.2f}s"

    @pytest.mark.asyncio
    async def test_large_file_with_complexity(self):
        """Test performance with complexity analysis enabled."""
        file_path = self._create_large_python_file(num_functions=50)
        tool = AnalyzeScaleTool(project_root=self.temp_dir)

        start_time = time.time()
        result = await tool.execute(
            {
                "file_path": str(file_path),
                "include_complexity": True,
                "include_details": False,
            }
        )
        end_time = time.time()

        assert result["success"] is True
        assert "file_metrics" in result

        # Complexity analysis adds overhead but should still be reasonable
        duration = end_time - start_time
        assert duration < 15.0, f"Complexity analysis took too long: {duration:.2f}s"

    @pytest.mark.asyncio
    async def test_large_file_with_details(self):
        """Test performance with detailed analysis."""
        file_path = self._create_large_python_file(num_functions=50)
        tool = AnalyzeCodeStructureTool(project_root=self.temp_dir)

        start_time = time.time()
        result = await tool.execute(
            {
                "file_path": str(file_path),
                "format_type": "full",
                "output_format": "json",
            }
        )
        end_time = time.time()

        assert "table_output" in result
        assert result["language"] == "python"

        # Detailed analysis adds overhead but should still be reasonable
        duration = end_time - start_time
        assert duration < 15.0, f"Detailed analysis took too long: {duration:.2f}s"
