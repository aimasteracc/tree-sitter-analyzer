"""Unit tests for symbol rename refactoring."""
import pytest
from pathlib import Path
import tempfile
import shutil


class TestRefactorRenameTool:
    """Test cases for symbol rename tool."""
    
    @pytest.fixture
    def tool(self):
        """Create RefactorRenameTool instance."""
        from tree_sitter_analyzer_v2.mcp.tools.refactor import RefactorRenameTool
        return RefactorRenameTool()
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        temp_path = Path(tempfile.mkdtemp())
        yield temp_path
        if temp_path.exists():
            shutil.rmtree(temp_path)
    
    def test_rename_function(self, tool, temp_dir):
        """Test renaming a function."""
        test_file = temp_dir / "test.py"
        test_file.write_text("""
def old_function():
    return 42

result = old_function()
""")
        
        result = tool.execute({
            "file_path": str(test_file),
            "symbol_type": "function",
            "old_name": "old_function",
            "new_name": "new_function",
        })
        
        assert result["success"]
        assert result["replacements"] >= 2
        content = test_file.read_text()
        assert "new_function" in content
        assert "old_function" not in content
    
    def test_rename_class(self, tool, temp_dir):
        """Test renaming a class."""
        test_file = temp_dir / "test.py"
        test_file.write_text("""
class OldClass:
    pass

obj = OldClass()
""")
        
        result = tool.execute({
            "file_path": str(test_file),
            "symbol_type": "class",
            "old_name": "OldClass",
            "new_name": "NewClass",
        })
        
        assert result["success"]
        assert result["replacements"] >= 2
        content = test_file.read_text()
        assert "NewClass" in content
        assert "OldClass" not in content
    
    def test_rename_variable(self, tool, temp_dir):
        """Test renaming a variable."""
        test_file = temp_dir / "test.py"
        test_file.write_text("""
old_var = 42
print(old_var)
""")
        
        result = tool.execute({
            "file_path": str(test_file),
            "symbol_type": "variable",
            "old_name": "old_var",
            "new_name": "new_var",
        })
        
        assert result["success"]
        assert result["replacements"] >= 2
        content = test_file.read_text()
        assert "new_var" in content
        assert "old_var" not in content
    
    def test_rename_cross_file(self, tool, temp_dir):
        """Test renaming across multiple files."""
        file1 = temp_dir / "module1.py"
        file1.write_text("""
def shared_function():
    return 42
""")
        
        file2 = temp_dir / "module2.py"
        file2.write_text("""
from module1 import shared_function

result = shared_function()
""")
        
        result = tool.execute({
            "directory": str(temp_dir),
            "symbol_type": "function",
            "old_name": "shared_function",
            "new_name": "renamed_function",
        })
        
        assert result["success"]
        assert result["files_modified"] >= 2
        assert "renamed_function" in file1.read_text()
        assert "renamed_function" in file2.read_text()
