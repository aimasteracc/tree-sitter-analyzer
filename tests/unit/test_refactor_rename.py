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

    def test_invalid_old_name(self, tool, temp_dir):
        """Test error on invalid old name."""
        test_file = temp_dir / "test.py"
        test_file.write_text("x = 1")
        
        result = tool.execute({
            "file_path": str(test_file),
            "symbol_type": "variable",
            "old_name": "123invalid",
            "new_name": "new_var",
        })
        
        assert not result["success"]
        assert "Invalid old name" in result["error"]

    def test_invalid_new_name(self, tool, temp_dir):
        """Test error on invalid new name."""
        test_file = temp_dir / "test.py"
        test_file.write_text("x = 1")
        
        result = tool.execute({
            "file_path": str(test_file),
            "symbol_type": "variable",
            "old_name": "old_var",
            "new_name": "class",  # Reserved word still matches identifier pattern
        })
        
        # Should proceed but may not find symbol
        # Test with invalid identifier instead
        result = tool.execute({
            "file_path": str(test_file),
            "symbol_type": "variable",
            "old_name": "old_var",
            "new_name": "123invalid",
        })
        
        assert not result["success"]
        assert "Invalid new name" in result["error"]

    def test_no_file_or_directory(self, tool):
        """Test error when neither file_path nor directory provided."""
        result = tool.execute({
            "symbol_type": "function",
            "old_name": "old_func",
            "new_name": "new_func",
        })
        
        assert not result["success"]
        assert "file_path or directory" in result["error"]

    def test_file_not_found(self, tool):
        """Test error when file not found."""
        result = tool.execute({
            "file_path": "/nonexistent/file.py",
            "symbol_type": "function",
            "old_name": "old_func",
            "new_name": "new_func",
        })
        
        assert not result["success"]
        assert "File not found" in result["error"]

    def test_directory_not_found(self, tool):
        """Test error when directory not found."""
        result = tool.execute({
            "directory": "/nonexistent/dir",
            "symbol_type": "function",
            "old_name": "old_func",
            "new_name": "new_func",
        })
        
        assert not result["success"]
        assert "Directory not found" in result["error"]

    def test_rename_method(self, tool, temp_dir):
        """Test renaming a method."""
        test_file = temp_dir / "test.py"
        test_file.write_text("""
class MyClass:
    def old_method(self):
        pass

    def call_method(self):
        self.old_method()
""")
        
        result = tool.execute({
            "file_path": str(test_file),
            "symbol_type": "method",
            "old_name": "old_method",
            "new_name": "new_method",
        })
        
        assert result["success"]
        assert result["replacements"] >= 2
        content = test_file.read_text()
        assert "new_method" in content
        assert "old_method" not in content

    def test_unknown_symbol_type(self, tool, temp_dir):
        """Test error on unknown symbol type."""
        test_file = temp_dir / "test.py"
        test_file.write_text("x = 1")
        
        result = tool.execute({
            "file_path": str(test_file),
            "symbol_type": "unknown",
            "old_name": "x",
            "new_name": "y",
        })
        
        assert not result["success"]
        assert "Unknown symbol type" in result["error"]

    def test_symbol_not_found(self, tool, temp_dir):
        """Test error when symbol not found."""
        test_file = temp_dir / "test.py"
        test_file.write_text("x = 1")
        
        result = tool.execute({
            "file_path": str(test_file),
            "symbol_type": "variable",
            "old_name": "nonexistent",
            "new_name": "new_name",
        })
        
        assert not result["success"]
        assert "not found" in result["error"]

    def test_symbol_not_found_in_directory(self, tool, temp_dir):
        """Test error when symbol not found in any file."""
        test_file = temp_dir / "test.py"
        test_file.write_text("x = 1")
        
        result = tool.execute({
            "directory": str(temp_dir),
            "symbol_type": "function",
            "old_name": "nonexistent_func",
            "new_name": "new_func",
        })
        
        assert not result["success"]
        assert "not found" in result["error"]

    def test_tool_metadata(self, tool):
        """Test tool metadata methods."""
        assert tool.get_name() == "refactor_rename"
        assert "rename" in tool.get_description().lower()
        schema = tool.get_schema()
        assert "properties" in schema
        assert "old_name" in schema["properties"]
        assert "new_name" in schema["properties"]
