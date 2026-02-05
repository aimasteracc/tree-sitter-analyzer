"""Unit tests for replace_in_file tool."""
import pytest
from pathlib import Path
import tempfile
import shutil


class TestReplaceInFileTool:
    """Test cases for replace_in_file tool."""
    
    @pytest.fixture
    def tool(self):
        """Create ReplaceInFileTool instance."""
        from tree_sitter_analyzer_v2.mcp.tools.replace import ReplaceInFileTool
        return ReplaceInFileTool()
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        temp_path = Path(tempfile.mkdtemp())
        yield temp_path
        # Cleanup
        if temp_path.exists():
            shutil.rmtree(temp_path)
    
    def test_replace_first_occurrence(self, tool, temp_dir):
        """Test replacing first occurrence only."""
        test_file = temp_dir / "test.txt"
        test_file.write_text("old old old", encoding="utf-8")
        
        result = tool.execute({
            "path": str(test_file),
            "old_string": "old",
            "new_string": "new",
            "replace_all": False,
        })
        
        assert result["success"]
        assert result["replacements"] == 1
        assert test_file.read_text(encoding="utf-8") == "new old old"
    
    def test_replace_all_occurrences(self, tool, temp_dir):
        """Test replacing all occurrences."""
        test_file = temp_dir / "test.txt"
        test_file.write_text("old old old", encoding="utf-8")
        
        result = tool.execute({
            "path": str(test_file),
            "old_string": "old",
            "new_string": "new",
            "replace_all": True,
        })
        
        assert result["success"]
        assert result["replacements"] == 3
        assert test_file.read_text(encoding="utf-8") == "new new new"
    
    def test_replace_string_not_found(self, tool, temp_dir):
        """Test replacing string that doesn't exist."""
        test_file = temp_dir / "test.txt"
        test_file.write_text("test content", encoding="utf-8")
        
        result = tool.execute({
            "path": str(test_file),
            "old_string": "notfound",
            "new_string": "new",
        })
        
        assert not result["success"]
        assert "not found" in result["error"].lower()
        # File should be unchanged
        assert test_file.read_text(encoding="utf-8") == "test content"
    
    def test_replace_multiline_string(self, tool, temp_dir):
        """Test replacing multiline string."""
        test_file = temp_dir / "test.txt"
        content = "line 1\nold text\nline 3"
        test_file.write_text(content, encoding="utf-8")
        
        result = tool.execute({
            "path": str(test_file),
            "old_string": "old text",
            "new_string": "new text",
        })
        
        assert result["success"]
        assert result["replacements"] == 1
        assert test_file.read_text(encoding="utf-8") == "line 1\nnew text\nline 3"
    
    def test_replace_with_empty_string(self, tool, temp_dir):
        """Test replacing with empty string (deletion)."""
        test_file = temp_dir / "test.txt"
        test_file.write_text("before DELETE after", encoding="utf-8")
        
        result = tool.execute({
            "path": str(test_file),
            "old_string": "DELETE ",
            "new_string": "",
        })
        
        assert result["success"]
        assert result["replacements"] == 1
        assert test_file.read_text(encoding="utf-8") == "before after"
    
    def test_replace_empty_old_string(self, tool, temp_dir):
        """Test replacing empty old_string (should fail)."""
        test_file = temp_dir / "test.txt"
        test_file.write_text("test", encoding="utf-8")
        
        result = tool.execute({
            "path": str(test_file),
            "old_string": "",
            "new_string": "new",
        })
        
        assert not result["success"]
        assert "empty" in result["error"].lower() or "not found" in result["error"].lower()
    
    def test_replace_file_not_found(self, tool, temp_dir):
        """Test replacing in non-existent file."""
        result = tool.execute({
            "path": str(temp_dir / "notfound.txt"),
            "old_string": "old",
            "new_string": "new",
        })
        
        assert not result["success"]
        assert "not found" in result["error"].lower() or "does not exist" in result["error"].lower()
    
    def test_replace_returns_path(self, tool, temp_dir):
        """Test that replace returns the file path."""
        test_file = temp_dir / "test.txt"
        test_file.write_text("old", encoding="utf-8")
        
        result = tool.execute({
            "path": str(test_file),
            "old_string": "old",
            "new_string": "new",
        })
        
        assert result["success"]
        assert "path" in result
        assert Path(result["path"]) == test_file.absolute()
    
    def test_replace_with_special_characters(self, tool, temp_dir):
        """Test replacing strings with special characters."""
        test_file = temp_dir / "test.txt"
        test_file.write_text("print(\"hello\")", encoding="utf-8")
        
        result = tool.execute({
            "path": str(test_file),
            "old_string": "print(\"hello\")",
            "new_string": "logging.info(\"hello\")",
        })
        
        assert result["success"]
        assert result["replacements"] == 1
        assert test_file.read_text(encoding="utf-8") == "logging.info(\"hello\")"
