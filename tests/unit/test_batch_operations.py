"""
Tests for mcp/tools/batch.py module.

TDD: Testing batch file operations.
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.mcp.tools.batch import BatchOperationsTool


class TestBatchOperationsTool:
    """Test BatchOperationsTool."""

    def test_get_name(self) -> None:
        """Should return correct name."""
        tool = BatchOperationsTool()
        assert tool.get_name() == "batch_operations"

    def test_get_description(self) -> None:
        """Should return description."""
        tool = BatchOperationsTool()
        assert "batch" in tool.get_description().lower()

    def test_get_schema(self) -> None:
        """Should return correct schema."""
        tool = BatchOperationsTool()
        schema = tool.get_schema()
        
        assert "operation" in schema["properties"]
        assert "files" in schema["properties"]
        assert "operation" in schema["required"]

    def test_rename_operation(self) -> None:
        """Should rename files."""
        tool = BatchOperationsTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = Path(tmpdir) / "test_old.py"
            file1.write_text("content")
            
            result = tool.execute({
                "operation": "rename",
                "files": [str(file1)],
                "pattern": "old",
                "replacement": "new"
            })
            
            assert result["success"] is True
            assert (Path(tmpdir) / "test_new.py").exists()

    def test_move_operation(self) -> None:
        """Should move files."""
        tool = BatchOperationsTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "src"
            dst = Path(tmpdir) / "dst"
            src.mkdir()
            dst.mkdir()
            
            file1 = src / "test.py"
            file1.write_text("content")
            
            result = tool.execute({
                "operation": "move",
                "files": [str(file1)],
                "target_dir": str(dst)
            })
            
            assert result["success"] is True
            assert (dst / "test.py").exists()
            assert not file1.exists()

    def test_copy_operation(self) -> None:
        """Should copy files."""
        tool = BatchOperationsTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "src"
            dst = Path(tmpdir) / "dst"
            src.mkdir()
            dst.mkdir()
            
            file1 = src / "test.py"
            file1.write_text("content")
            
            result = tool.execute({
                "operation": "copy",
                "files": [str(file1)],
                "target_dir": str(dst)
            })
            
            assert result["success"] is True
            assert (dst / "test.py").exists()
            assert file1.exists()  # Original still exists

    def test_change_extension_operation(self) -> None:
        """Should change file extension."""
        tool = BatchOperationsTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = Path(tmpdir) / "test.txt"
            file1.write_text("content")
            
            result = tool.execute({
                "operation": "change_extension",
                "files": [str(file1)],
                "new_extension": ".md"
            })
            
            assert result["success"] is True
            assert (Path(tmpdir) / "test.md").exists()

    def test_add_prefix_operation(self) -> None:
        """Should add prefix to files."""
        tool = BatchOperationsTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = Path(tmpdir) / "test.py"
            file1.write_text("content")
            
            result = tool.execute({
                "operation": "add_prefix",
                "files": [str(file1)],
                "prefix": "new_"
            })
            
            assert result["success"] is True
            assert (Path(tmpdir) / "new_test.py").exists()

    def test_add_suffix_operation(self) -> None:
        """Should add suffix to files."""
        tool = BatchOperationsTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = Path(tmpdir) / "test.py"
            file1.write_text("content")
            
            result = tool.execute({
                "operation": "add_suffix",
                "files": [str(file1)],
                "suffix": "_backup"
            })
            
            assert result["success"] is True
            assert (Path(tmpdir) / "test_backup.py").exists()

    def test_move_without_target_dir(self) -> None:
        """Should fail without target directory."""
        tool = BatchOperationsTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = Path(tmpdir) / "test.py"
            file1.write_text("content")
            
            result = tool.execute({
                "operation": "move",
                "files": [str(file1)]
            })
            
            assert result["success"] is False

    def test_copy_without_target_dir(self) -> None:
        """Should fail without target directory."""
        tool = BatchOperationsTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = Path(tmpdir) / "test.py"
            file1.write_text("content")
            
            result = tool.execute({
                "operation": "copy",
                "files": [str(file1)]
            })
            
            assert result["success"] is False

    def test_rename_without_pattern(self) -> None:
        """Should fail without pattern for rename."""
        tool = BatchOperationsTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = Path(tmpdir) / "test.py"
            file1.write_text("content")
            
            result = tool.execute({
                "operation": "rename",
                "files": [str(file1)]
            })
            
            assert result["success"] is False

    def test_add_prefix_without_prefix(self) -> None:
        """Should fail without prefix."""
        tool = BatchOperationsTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = Path(tmpdir) / "test.py"
            file1.write_text("content")
            
            result = tool.execute({
                "operation": "add_prefix",
                "files": [str(file1)]
            })
            
            assert result["success"] is False

    def test_multiple_files(self) -> None:
        """Should handle multiple files."""
        tool = BatchOperationsTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = Path(tmpdir) / "test1.py"
            file2 = Path(tmpdir) / "test2.py"
            file1.write_text("content1")
            file2.write_text("content2")
            
            result = tool.execute({
                "operation": "add_prefix",
                "files": [str(file1), str(file2)],
                "prefix": "new_"
            })
            
            assert result["success"] is True
            assert result["processed"] == 2

    def test_nonexistent_file(self) -> None:
        """Should handle nonexistent files."""
        tool = BatchOperationsTool()
        
        result = tool.execute({
            "operation": "add_prefix",
            "files": ["/nonexistent/file.py"],
            "prefix": "new_"
        })
        
        assert result["processed"] == 0
