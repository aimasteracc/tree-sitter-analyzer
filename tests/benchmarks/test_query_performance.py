#!/usr/bin/env python3
"""
Query Performance Tests.

Tests performance characteristics of query operations.
"""

import tempfile
import time
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool


class TestQueryPerformance:
    """Tests for query performance."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_python_file(self, content: str) -> Path:
        """Create a Python file for testing."""
        file_path = Path(self.temp_dir) / "test.py"
        file_path.write_text(content)
        return file_path

    @pytest.mark.asyncio
    async def test_query_simple_pattern_performance(self):
        """Test performance of simple query pattern."""
        content = "\n".join([f"def func_{i}(): pass" for i in range(100)])
        file_path = self._create_python_file(content)
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

        duration = end_time - start_time
        assert duration < 5.0, f"Simple query took too long: {duration:.2f}s"

    @pytest.mark.asyncio
    async def test_query_complex_pattern_performance(self):
        """Test performance of complex query pattern."""
        content = (
            """
class MyClass:
    def method1(self):
        pass

    def method2(self):
        pass
"""
            * 50
        )
        file_path = self._create_python_file(content)
        tool = QueryTool(project_root=self.temp_dir)

        start_time = time.time()
        result = await tool.execute(
            {
                "file_path": str(file_path),
                "language": "python",
                "query_key": "methods",
                "result_format": "json",
            }
        )
        end_time = time.time()

        assert "query_result" in result or "success" in result

        duration = end_time - start_time
        assert duration < 5.0, f"Complex query took too long: {duration:.2f}s"

    @pytest.mark.asyncio
    async def test_query_with_filter_performance(self):
        """Test performance of query with filter."""
        content = "\n".join([f"def func_{i}(): return {i}" for i in range(100)])
        file_path = self._create_python_file(content)
        tool = QueryTool(project_root=self.temp_dir)

        start_time = time.time()
        result = await tool.execute(
            {
                "file_path": str(file_path),
                "language": "python",
                "query_key": "functions",
                "filter": "name=~func_5",
                "result_format": "json",
            }
        )
        end_time = time.time()

        assert "query_result" in result or "success" in result

        duration = end_time - start_time
        assert duration < 5.0, f"Query with filter took too long: {duration:.2f}s"

    @pytest.mark.asyncio
    async def test_query_multiple_files_performance(self):
        """Test performance of querying multiple files."""
        files = []
        for i in range(10):
            content = "\n".join([f"def func_{j}(): pass" for j in range(10)])
            file_path = Path(self.temp_dir) / f"file_{i}.py"
            file_path.write_text(content)
            files.append(str(file_path))

        tool = QueryTool(project_root=self.temp_dir)

        start_time = time.time()
        results = []
        for file_path in files:
            result = await tool.execute(
                {
                    "file_path": file_path,
                    "language": "python",
                    "query_key": "functions",
                    "result_format": "json",
                }
            )
            results.append(result)
        end_time = time.time()

        assert all("query_result" in r or "success" in r for r in results)

        duration = end_time - start_time
        assert duration < 15.0, f"Multiple file queries took too long: {duration:.2f}s"

    @pytest.mark.asyncio
    async def test_query_custom_query_performance(self):
        """Test performance of custom tree-sitter query."""
        content = "\n".join([f"def func_{i}(): pass" for i in range(50)])
        file_path = self._create_python_file(content)
        tool = QueryTool(project_root=self.temp_dir)

        start_time = time.time()
        result = await tool.execute(
            {
                "file_path": str(file_path),
                "language": "python",
                "query_string": "(function_definition) @func",
                "result_format": "json",
            }
        )
        end_time = time.time()

        assert "query_result" in result or "success" in result

        duration = end_time - start_time
        assert duration < 5.0, f"Custom query took too long: {duration:.2f}s"

    @pytest.mark.asyncio
    async def test_query_summary_format_performance(self):
        """Test performance of summary format output."""
        content = "\n".join([f"def func_{i}(): pass" for i in range(100)])
        file_path = self._create_python_file(content)
        tool = QueryTool(project_root=self.temp_dir)

        start_time = time.time()
        result = await tool.execute(
            {
                "file_path": str(file_path),
                "language": "python",
                "query_key": "functions",
                "result_format": "summary",
            }
        )
        end_time = time.time()

        assert "query_result" in result or "success" in result

        duration = end_time - start_time
        assert duration < 5.0, f"Summary format query took too long: {duration:.2f}s"

    @pytest.mark.asyncio
    async def test_query_json_format_performance(self):
        """Test performance of JSON format output."""
        content = "\n".join([f"def func_{i}(): pass" for i in range(100)])
        file_path = self._create_python_file(content)
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

        duration = end_time - start_time
        assert duration < 5.0, f"JSON format query took too long: {duration:.2f}s"

    @pytest.mark.asyncio
    async def test_query_with_max_count_performance(self):
        """Test performance of query with max_count limit."""
        content = "\n".join([f"def func_{i}(): pass" for i in range(100)])
        file_path = self._create_python_file(content)
        tool = QueryTool(project_root=self.temp_dir)

        start_time = time.time()
        result = await tool.execute(
            {
                "file_path": str(file_path),
                "language": "python",
                "query_key": "functions",
                "max_count": 10,
                "result_format": "json",
            }
        )
        end_time = time.time()

        assert "query_result" in result or "success" in result

        duration = end_time - start_time
        assert duration < 5.0, f"Query with max_count took too long: {duration:.2f}s"

    @pytest.mark.asyncio
    async def test_query_repeated_performance(self):
        """Test performance of repeated queries on same file."""
        content = "\n".join([f"def func_{i}(): pass" for i in range(50)])
        file_path = self._create_python_file(content)
        tool = QueryTool(project_root=self.temp_dir)

        start_time = time.time()
        for _ in range(5):
            result = await tool.execute(
                {
                    "file_path": str(file_path),
                    "language": "python",
                    "query_key": "functions",
                    "result_format": "json",
                }
            )
            assert "query_result" in result or "success" in result
        end_time = time.time()

        duration = end_time - start_time
        assert duration < 10.0, f"Repeated queries took too long: {duration:.2f}s"

    @pytest.mark.asyncio
    async def test_query_different_languages_performance(self):
        """Test performance of querying different languages."""
        python_content = "\n".join([f"def func_{i}(): pass" for i in range(20)])
        python_path = self._create_python_file(python_content)
        python_path.rename(Path(self.temp_dir) / "test.py")

        javascript_content = "\n".join([f"function func{i}() {{}}" for i in range(20)])
        js_path = Path(self.temp_dir) / "test.js"
        js_path.write_text(javascript_content)

        tool = QueryTool(project_root=self.temp_dir)

        start_time = time.time()
        python_result = await tool.execute(
            {
                "file_path": str(Path(self.temp_dir) / "test.py"),
                "language": "python",
                "query_key": "functions",
                "result_format": "json",
            }
        )
        js_result = await tool.execute(
            {
                "file_path": str(js_path),
                "language": "javascript",
                "query_key": "functions",
                "result_format": "json",
            }
        )
        end_time = time.time()

        assert "query_result" in python_result or "success" in python_result
        assert "query_result" in js_result or "success" in js_result

        duration = end_time - start_time
        assert (
            duration < 10.0
        ), f"Different language queries took too long: {duration:.2f}s"
