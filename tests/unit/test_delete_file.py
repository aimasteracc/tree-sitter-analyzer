"""Unit tests for delete_file tool."""
import pytest
from pathlib import Path
import tempfile
import shutil


class TestDeleteFileTool:
    """Test cases for delete_file tool."""
    
    @pytest.fixture
    def tool(self):
        """Create DeleteFileTool instance."""
        from tree_sitter_analyzer_v2.mcp.tools.delete import DeleteFileTool
        return DeleteFileTool()
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        temp_path = Path(tempfile.mkdtemp())
        yield temp_path
        # Cleanup
        if temp_path.exists():
            shutil.rmtree(temp_path)
    
    def test_delete_file_basic(self, tool, temp_dir):
        """Test basic file deletion."""
        test_file = temp_dir / "test.txt"
        test_file.write_text("test content", encoding="utf-8")
        
        result = tool.execute({
            "path": str(test_file),
        })
        
        assert result["success"]
        assert not test_file.exists()
    
    def test_delete_file_not_found(self, tool, temp_dir):
        """Test deleting non-existent file."""
        result = tool.execute({
            "path": str(temp_dir / "notfound.txt"),
        })
        
        assert not result["success"]
        assert "not found" in result["error"].lower() or "does not exist" in result["error"].lower()
    
    def test_delete_directory(self, tool, temp_dir):
        """Test deleting directory."""
        test_dir = temp_dir / "subdir"
        test_dir.mkdir()
        
        result = tool.execute({
            "path": str(test_dir),
        })
        
        assert result["success"]
        assert not test_dir.exists()
    
    def test_delete_directory_with_files(self, tool, temp_dir):
        """Test deleting directory with files."""
        test_dir = temp_dir / "subdir"
        test_dir.mkdir()
        (test_dir / "file1.txt").write_text("content1")
        (test_dir / "file2.txt").write_text("content2")
        
        result = tool.execute({
            "path": str(test_dir),
            "recursive": True,
        })
        
        assert result["success"]
        assert not test_dir.exists()
    
    def test_delete_directory_without_recursive(self, tool, temp_dir):
        """Test deleting non-empty directory without recursive flag."""
        test_dir = temp_dir / "subdir"
        test_dir.mkdir()
        (test_dir / "file1.txt").write_text("content1")
        
        result = tool.execute({
            "path": str(test_dir),
            "recursive": False,
        })
        
        assert not result["success"]
        assert "not empty" in result["error"].lower() or "recursive" in result["error"].lower()
    
    def test_delete_returns_path(self, tool, temp_dir):
        """Test that delete returns the deleted path."""
        test_file = temp_dir / "test.txt"
        test_file.write_text("test")
        
        result = tool.execute({
            "path": str(test_file),
        })
        
        assert result["success"]
        assert "path" in result
        assert Path(result["path"]) == test_file.absolute()
    
    def test_delete_with_confirmation(self, tool, temp_dir):
        """Test delete with confirmation flag."""
        test_file = temp_dir / "test.txt"
        test_file.write_text("test")
        
        result = tool.execute({
            "path": str(test_file),
            "confirm": True,
        })
        
        assert result["success"]
        assert not test_file.exists()
    
    def test_delete_multiple_files(self, tool, temp_dir):
        """Test deleting multiple files."""
        files = [temp_dir / f"file{i}.txt" for i in range(3)]
        for f in files:
            f.write_text("content")
        
        result = tool.execute({
            "paths": [str(f) for f in files],
        })
        
        assert result["success"]
        assert result["deleted_count"] == 3
        for f in files:
            assert not f.exists()

    def test_delete_without_confirm(self, tool, temp_dir):
        """Test delete without confirmation."""
        test_file = temp_dir / "test.txt"
        test_file.write_text("test")
        
        result = tool.execute({
            "path": str(test_file),
            "confirm": False,
        })
        
        assert not result["success"]
        assert "confirmation" in result["error"].lower()
        # File should still exist
        assert test_file.exists()

    def test_delete_no_path_or_paths(self, tool, temp_dir):
        """Test delete without path or paths."""
        result = tool.execute({
            "confirm": True,
        })
        
        assert not result["success"]
        assert "path" in result["error"].lower()

    def test_delete_multiple_with_errors(self, tool, temp_dir):
        """Test batch delete with some failures."""
        # Create one real file
        real_file = temp_dir / "real.txt"
        real_file.write_text("content")
        
        # Try to delete real file and non-existent file
        result = tool.execute({
            "paths": [str(real_file), str(temp_dir / "nonexistent.txt")],
        })
        
        assert not result["success"]
        assert result["deleted_count"] == 1
        assert "errors" in result
        assert len(result["errors"]) == 1

    def test_delete_tool_name(self, tool):
        """Test tool name."""
        assert tool.get_name() == "delete_file"

    def test_delete_tool_description(self, tool):
        """Test tool description."""
        desc = tool.get_description()
        assert "delete" in desc.lower()

    def test_delete_tool_schema(self, tool):
        """Test tool schema."""
        schema = tool.get_schema()
        assert schema["type"] == "object"
        assert "path" in schema["properties"]
        assert "paths" in schema["properties"]
        assert "recursive" in schema["properties"]
