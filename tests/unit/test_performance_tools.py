"""
Tests for mcp/tools/performance.py module.

TDD: Testing performance monitoring tools.
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.mcp.tools.performance import (
    PerformanceMonitorTool,
    ProfileCodeTool,
)


class TestPerformanceMonitorTool:
    """Test PerformanceMonitorTool."""

    def test_get_name(self) -> None:
        """Should return correct name."""
        tool = PerformanceMonitorTool()
        assert tool.get_name() == "monitor_performance"

    def test_get_description(self) -> None:
        """Should return description."""
        tool = PerformanceMonitorTool()
        assert "performance" in tool.get_description().lower()

    def test_monitor_all_metrics(self) -> None:
        """Should monitor all metrics."""
        tool = PerformanceMonitorTool()
        
        result = tool.execute({"metric": "all"})
        
        assert result["success"] is True
        assert "cpu_percent" in result
        assert "memory_percent" in result
        assert "disk_percent" in result

    def test_monitor_cpu_only(self) -> None:
        """Should monitor CPU only."""
        tool = PerformanceMonitorTool()
        
        result = tool.execute({"metric": "cpu"})
        
        assert result["success"] is True
        assert "cpu_percent" in result
        assert "cpu_count" in result

    def test_monitor_memory_only(self) -> None:
        """Should monitor memory only."""
        tool = PerformanceMonitorTool()
        
        result = tool.execute({"metric": "memory"})
        
        assert result["success"] is True
        assert "memory_percent" in result
        assert "memory_available_gb" in result

    def test_monitor_disk_only(self) -> None:
        """Should monitor disk only."""
        tool = PerformanceMonitorTool()
        
        result = tool.execute({"metric": "disk"})
        
        assert result["success"] is True
        assert "disk_percent" in result
        assert "disk_free_gb" in result

    def test_default_metric(self) -> None:
        """Should default to all metrics."""
        tool = PerformanceMonitorTool()
        
        result = tool.execute({})
        
        assert result["success"] is True
        assert "cpu_percent" in result


class TestProfileCodeTool:
    """Test ProfileCodeTool."""

    def test_get_name(self) -> None:
        """Should return correct name."""
        tool = ProfileCodeTool()
        assert tool.get_name() == "profile_code"

    def test_file_not_found(self) -> None:
        """Should handle missing file."""
        tool = ProfileCodeTool()
        
        result = tool.execute({"file_path": "/nonexistent.py"})
        
        assert result["success"] is False
        assert "error" in result

    def test_profile_file(self) -> None:
        """Should profile Python file."""
        tool = ProfileCodeTool()
        
        code = '''
def func1():
    pass

def func2():
    pass

class MyClass:
    def method(self):
        pass
'''
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()
            path = f.name
        
        try:
            result = tool.execute({"file_path": path})
            
            assert result["success"] is True
            assert result["functions"] == 3  # func1, func2, method
            assert "func1" in result["function_names"]
        finally:
            Path(path).unlink()

    def test_profile_counts_lines(self) -> None:
        """Should count lines correctly."""
        tool = ProfileCodeTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("x = 1\ny = 2\nz = 3\n")
            f.flush()
            path = f.name
        
        try:
            result = tool.execute({"file_path": path})
            
            assert result["success"] is True
            assert result["lines"] == 3
        finally:
            Path(path).unlink()
