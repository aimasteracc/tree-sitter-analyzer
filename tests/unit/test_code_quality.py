"""Unit tests for code quality checking tools."""
import pytest
from pathlib import Path
import tempfile
import shutil


class TestCodeQualityTool:
    """Test cases for code quality tool."""
    
    @pytest.fixture
    def tool(self):
        """Create CodeQualityTool instance."""
        from tree_sitter_analyzer_v2.mcp.tools.quality import CodeQualityTool
        return CodeQualityTool()
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        temp_path = Path(tempfile.mkdtemp())
        yield temp_path
        if temp_path.exists():
            shutil.rmtree(temp_path)
    
    def test_check_complexity(self, tool, temp_dir):
        """Test checking code complexity."""
        test_file = temp_dir / "test.py"
        test_file.write_text("""
def complex_function(x):
    if x > 0:
        if x > 10:
            if x > 20:
                return "high"
            return "medium"
        return "low"
    return "negative"
""")
        
        result = tool.execute({
            "file_path": str(test_file),
            "check_type": "complexity",
        })
        
        assert result["success"]
        assert "complexity" in result
        assert "functions" in result["complexity"]
        assert len(result["complexity"]["functions"]) > 0
        assert result["complexity"]["functions"][0]["cyclomatic"] > 1
    
    def test_check_duplicates(self, tool, temp_dir):
        """Test detecting duplicate code."""
        test_file = temp_dir / "test.py"
        test_file.write_text("""
def func1():
    x = 1
    y = 2
    return x + y

def func2():
    x = 1
    y = 2
    return x + y
""")
        
        result = tool.execute({
            "file_path": str(test_file),
            "check_type": "duplicates",
        })
        
        assert result["success"]
        assert "duplicates" in result
    
    def test_check_code_smells(self, tool, temp_dir):
        """Test detecting code smells."""
        test_file = temp_dir / "test.py"
        test_file.write_text("""
def long_function(a, b, c, d, e, f, g):
    x = a + b + c + d + e + f + g
    return x
""")
        
        result = tool.execute({
            "file_path": str(test_file),
            "check_type": "smells",
        })
        
        assert result["success"]
        assert "smells" in result
