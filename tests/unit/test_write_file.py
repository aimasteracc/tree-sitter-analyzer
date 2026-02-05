"""Unit tests for write_file tool."""
import pytest
from pathlib import Path
import tempfile
import shutil


class TestWriteFileTool:
    """Test cases for write_file tool."""
    
    @pytest.fixture
    def tool(self):
        """Create WriteFileTool instance."""
        from tree_sitter_analyzer_v2.mcp.tools.write import WriteFileTool
        return WriteFileTool()
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        temp_path = Path(tempfile.mkdtemp())
        yield temp_path
        # Cleanup
        if temp_path.exists():
            shutil.rmtree(temp_path)
    
    def test_write_file_basic(self, tool, temp_dir):
        """Test basic file writing."""
        test_file = temp_dir / "test.txt"
        result = tool.execute({
            "path": str(test_file),
            "contents": "test content",
        })
        
        assert result["success"]
        assert test_file.exists()
        assert test_file.read_text(encoding="utf-8") == "test content"
    
    def test_write_file_creates_directory(self, tool, temp_dir):
        """Test that write_file creates parent directories."""
        test_file = temp_dir / "subdir" / "test.txt"
        result = tool.execute({
            "path": str(test_file),
            "contents": "test content",
        })
        
        assert result["success"]
        assert test_file.exists()
        assert test_file.read_text(encoding="utf-8") == "test content"
    
    def test_write_file_overwrites_existing(self, tool, temp_dir):
        """Test that write_file overwrites existing files."""
        test_file = temp_dir / "test.txt"
        test_file.write_text("old content", encoding="utf-8")
        
        result = tool.execute({
            "path": str(test_file),
            "contents": "new content",
        })
        
        assert result["success"]
        assert test_file.read_text(encoding="utf-8") == "new content"
    
    def test_write_file_with_encoding(self, tool, temp_dir):
        """Test writing file with specific encoding."""
        test_file = temp_dir / "test.txt"
        result = tool.execute({
            "path": str(test_file),
            "contents": "test content with unicode: 中文",
            "encoding": "utf-8",
        })
        
        assert result["success"]
        assert test_file.exists()
        content = test_file.read_text(encoding="utf-8")
        assert "中文" in content
    
    def test_write_file_empty_content(self, tool, temp_dir):
        """Test writing empty file."""
        test_file = temp_dir / "empty.txt"
        result = tool.execute({
            "path": str(test_file),
            "contents": "",
        })
        
        assert result["success"]
        assert test_file.exists()
        assert test_file.read_text(encoding="utf-8") == ""
    
    def test_write_file_multiline_content(self, tool, temp_dir):
        """Test writing multiline content."""
        test_file = temp_dir / "multiline.txt"
        content = "line 1\nline 2\nline 3"
        result = tool.execute({
            "path": str(test_file),
            "contents": content,
        })
        
        assert result["success"]
        assert test_file.read_text(encoding="utf-8") == content
    
    def test_write_file_returns_path(self, tool, temp_dir):
        """Test that write_file returns the file path."""
        test_file = temp_dir / "test.txt"
        result = tool.execute({
            "path": str(test_file),
            "contents": "test",
        })
        
        assert result["success"]
        assert "path" in result
        assert Path(result["path"]) == test_file
    
    def test_write_file_invalid_path(self, tool):
        """Test writing to invalid path."""
        # Try to write to a path that can't be created (e.g., root of a non-existent drive)
        if Path("Z:/").exists():
            pytest.skip("Z: drive exists, skipping test")
        
        result = tool.execute({
            "path": "Z:/invalid/path/test.txt",
            "contents": "test",
        })
        
        assert not result["success"]
        assert "error" in result
