"""Unit tests for batch file operations."""
import pytest
from pathlib import Path
import tempfile
import shutil


class TestBatchOperationsTool:
    """Test cases for batch operations tool."""
    
    @pytest.fixture
    def tool(self):
        """Create BatchOperationsTool instance."""
        from tree_sitter_analyzer_v2.mcp.tools.batch import BatchOperationsTool
        return BatchOperationsTool()
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        temp_path = Path(tempfile.mkdtemp())
        yield temp_path
        # Cleanup
        if temp_path.exists():
            shutil.rmtree(temp_path)
    
    def test_batch_rename(self, tool, temp_dir):
        """Test batch renaming files."""
        # Create test files
        files = [temp_dir / f"file{i}.txt" for i in range(3)]
        for f in files:
            f.write_text("content")
        
        result = tool.execute({
            "operation": "rename",
            "files": [str(f) for f in files],
            "pattern": r"file(\d+)",
            "replacement": r"renamed\1",
        })
        
        assert result["success"]
        assert result["processed"] == 3
        # Check renamed files exist
        for i in range(3):
            assert (temp_dir / f"renamed{i}.txt").exists()
    
    def test_batch_move(self, tool, temp_dir):
        """Test batch moving files."""
        # Create source files
        source_dir = temp_dir / "source"
        source_dir.mkdir()
        files = [source_dir / f"file{i}.txt" for i in range(3)]
        for f in files:
            f.write_text("content")
        
        # Create target directory
        target_dir = temp_dir / "target"
        target_dir.mkdir()
        
        result = tool.execute({
            "operation": "move",
            "files": [str(f) for f in files],
            "target_dir": str(target_dir),
        })
        
        assert result["success"]
        assert result["processed"] == 3
        # Check files moved
        for i in range(3):
            assert (target_dir / f"file{i}.txt").exists()
            assert not (source_dir / f"file{i}.txt").exists()
    
    def test_batch_copy(self, tool, temp_dir):
        """Test batch copying files."""
        # Create source files
        source_dir = temp_dir / "source"
        source_dir.mkdir()
        files = [source_dir / f"file{i}.txt" for i in range(3)]
        for f in files:
            f.write_text("content")
        
        # Create target directory
        target_dir = temp_dir / "target"
        target_dir.mkdir()
        
        result = tool.execute({
            "operation": "copy",
            "files": [str(f) for f in files],
            "target_dir": str(target_dir),
        })
        
        assert result["success"]
        assert result["processed"] == 3
        # Check files copied (originals still exist)
        for i in range(3):
            assert (target_dir / f"file{i}.txt").exists()
            assert (source_dir / f"file{i}.txt").exists()
    
    def test_batch_change_extension(self, tool, temp_dir):
        """Test batch changing file extensions."""
        # Create test files
        files = [temp_dir / f"file{i}.txt" for i in range(3)]
        for f in files:
            f.write_text("content")
        
        result = tool.execute({
            "operation": "change_extension",
            "files": [str(f) for f in files],
            "new_extension": ".md",
        })
        
        assert result["success"]
        assert result["processed"] == 3
        # Check extensions changed
        for i in range(3):
            assert (temp_dir / f"file{i}.md").exists()
            assert not (temp_dir / f"file{i}.txt").exists()
    
    def test_batch_add_prefix(self, tool, temp_dir):
        """Test batch adding prefix to filenames."""
        # Create test files
        files = [temp_dir / f"file{i}.txt" for i in range(3)]
        for f in files:
            f.write_text("content")
        
        result = tool.execute({
            "operation": "add_prefix",
            "files": [str(f) for f in files],
            "prefix": "test_",
        })
        
        assert result["success"]
        assert result["processed"] == 3
        # Check prefix added
        for i in range(3):
            assert (temp_dir / f"test_file{i}.txt").exists()
    
    def test_batch_add_suffix(self, tool, temp_dir):
        """Test batch adding suffix to filenames."""
        # Create test files
        files = [temp_dir / f"file{i}.txt" for i in range(3)]
        for f in files:
            f.write_text("content")
        
        result = tool.execute({
            "operation": "add_suffix",
            "files": [str(f) for f in files],
            "suffix": "_backup",
        })
        
        assert result["success"]
        assert result["processed"] == 3
        # Check suffix added
        for i in range(3):
            assert (temp_dir / f"file{i}_backup.txt").exists()
