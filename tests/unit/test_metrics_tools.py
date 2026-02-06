"""
Tests for mcp/tools/metrics.py module.

TDD: Testing code metrics tools.
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.mcp.tools.metrics import CodeMetricsTool


class TestCodeMetricsTool:
    """Test CodeMetricsTool."""

    def test_get_name(self) -> None:
        """Should return correct tool name."""
        tool = CodeMetricsTool()
        assert tool.get_name() == "calculate_metrics"

    def test_get_description(self) -> None:
        """Should return description."""
        tool = CodeMetricsTool()
        desc = tool.get_description()
        assert "metrics" in desc.lower()

    def test_get_schema(self) -> None:
        """Should return valid schema."""
        tool = CodeMetricsTool()
        schema = tool.get_schema()
        
        assert schema["type"] == "object"
        assert "path" in schema["properties"]
        assert "path" in schema["required"]

    def test_path_not_found(self) -> None:
        """Should return error for non-existent path."""
        tool = CodeMetricsTool()
        result = tool.execute({"path": "/nonexistent/path"})
        
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_analyze_single_file(self) -> None:
        """Should analyze single file."""
        tool = CodeMetricsTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write('''# This is a comment
def hello():
    """Docstring."""
    pass

def world():
    pass

class MyClass:
    pass
''')
            f.flush()
            file_path = f.name
        
        try:
            result = tool.execute({"path": file_path})
            
            assert result["success"] is True
            assert "lines" in result
            assert "elements" in result
            assert result["elements"]["functions"] >= 2
            assert result["elements"]["classes"] >= 1
        finally:
            Path(file_path).unlink()

    def test_count_line_types(self) -> None:
        """Should count different line types."""
        tool = CodeMetricsTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("# Comment line\ncode_line = 1\n\n# Another comment\n")
            f.flush()
            file_path = f.name
        
        try:
            result = tool.execute({"path": file_path})
            
            assert result["success"] is True
            assert result["lines"]["total"] == 4
            assert result["lines"]["comments"] >= 2
            assert result["lines"]["code"] >= 1
            assert result["lines"]["blank"] >= 1
        finally:
            Path(file_path).unlink()

    def test_maintainability_index(self) -> None:
        """Should calculate maintainability index."""
        tool = CodeMetricsTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("def test(): pass\n")
            f.flush()
            file_path = f.name
        
        try:
            result = tool.execute({"path": file_path})
            
            assert result["success"] is True
            assert "maintainability_index" in result
            assert isinstance(result["maintainability_index"], float)
        finally:
            Path(file_path).unlink()

    def test_analyze_directory(self) -> None:
        """Should analyze directory."""
        tool = CodeMetricsTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = Path(tmpdir) / "module1.py"
            file1.write_text("def func1(): pass\n")
            
            file2 = Path(tmpdir) / "module2.py"
            file2.write_text("class Class1: pass\n")
            
            result = tool.execute({"path": tmpdir})
            
            assert result["success"] is True
            assert result["files"] == 2
            assert result["total_functions"] >= 1
            assert result["total_classes"] >= 1
            assert "avg_lines_per_file" in result

    def test_analyze_nested_directory(self) -> None:
        """Should analyze files in nested directories."""
        tool = CodeMetricsTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = Path(tmpdir) / "src" / "module"
            subdir.mkdir(parents=True)
            
            py_file = subdir / "core.py"
            py_file.write_text("def core_func(): pass\n")
            
            result = tool.execute({"path": tmpdir})
            
            assert result["success"] is True
            assert result["files"] >= 1
            assert result["total_functions"] >= 1

    def test_handle_empty_directory(self) -> None:
        """Should handle empty directory."""
        tool = CodeMetricsTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            result = tool.execute({"path": tmpdir})
            
            assert result["success"] is True
            assert result["files"] == 0
            assert result["avg_lines_per_file"] == 0

    def test_handle_syntax_errors(self) -> None:
        """Should skip files with syntax errors in directory."""
        tool = CodeMetricsTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            good_file = Path(tmpdir) / "good.py"
            good_file.write_text("def good(): pass\n")
            
            bad_file = Path(tmpdir) / "bad.py"
            bad_file.write_text("{{{ invalid syntax")
            
            result = tool.execute({"path": tmpdir})
            
            assert result["success"] is True
            # Should still count good file
            assert result["total_functions"] >= 1

    def test_handle_syntax_error_single_file(self) -> None:
        """Should return error for syntax error in single file."""
        tool = CodeMetricsTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("{{{ invalid")
            f.flush()
            file_path = f.name
        
        try:
            result = tool.execute({"path": file_path})
            
            assert result["success"] is False
            assert "error" in result
        finally:
            Path(file_path).unlink()
