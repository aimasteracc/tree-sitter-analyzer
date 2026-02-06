"""
Tests for mcp/tools/collaboration.py module.

TDD: Testing collaboration tools.
"""

import json
import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.mcp.tools.collaboration import (
    CodeReviewTool,
    CommentManagerTool,
    TaskManagerTool,
    NotebookEditorTool,
    ShellExecutorTool,
)


class TestCodeReviewTool:
    """Test CodeReviewTool."""

    def test_get_name(self) -> None:
        """Should return correct name."""
        tool = CodeReviewTool()
        assert tool.get_name() == "code_reviewer"

    def test_file_not_found(self) -> None:
        """Should handle missing file."""
        tool = CodeReviewTool()
        result = tool.execute({"file_path": "/nonexistent.py"})
        assert result["success"] is False

    def test_review_naming_conventions(self) -> None:
        """Should check naming conventions."""
        tool = CodeReviewTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("def BadName():\n    pass\n")
            f.flush()
            path = f.name
        
        try:
            result = tool.execute({"file_path": path})
            assert result["success"] is True
            assert len(result["issues"]) >= 1
        finally:
            Path(path).unlink()

    def test_review_class_naming(self) -> None:
        """Should check class naming."""
        tool = CodeReviewTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("class badclass:\n    pass\n")
            f.flush()
            path = f.name
        
        try:
            result = tool.execute({"file_path": path})
            assert result["success"] is True
            # Should flag lowercase class name
            naming_issues = [i for i in result["issues"] if i["type"] == "naming"]
            assert len(naming_issues) >= 1
        finally:
            Path(path).unlink()

    def test_review_clean_code(self) -> None:
        """Should pass clean code."""
        tool = CodeReviewTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("def good_function():\n    pass\n\nclass GoodClass:\n    pass\n")
            f.flush()
            path = f.name
        
        try:
            result = tool.execute({"file_path": path})
            assert result["success"] is True
            assert result["passed"] is True
        finally:
            Path(path).unlink()


class TestCommentManagerTool:
    """Test CommentManagerTool."""

    def test_get_name(self) -> None:
        """Should return correct name."""
        tool = CommentManagerTool()
        assert tool.get_name() == "comment_manager"

    def test_file_not_found(self) -> None:
        """Should handle missing file."""
        tool = CommentManagerTool()
        result = tool.execute({"file_path": "/nonexistent.py", "operation": "extract"})
        assert result["success"] is False

    def test_extract_comments(self) -> None:
        """Should extract comments."""
        tool = CommentManagerTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("x = 1  # first comment\ny = 2  # second comment\n")
            f.flush()
            path = f.name
        
        try:
            result = tool.execute({"file_path": path, "operation": "extract"})
            assert result["success"] is True
            assert result["count"] >= 2
        finally:
            Path(path).unlink()

    def test_analyze_comments(self) -> None:
        """Should analyze comment ratio."""
        tool = CommentManagerTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("# Comment\nx = 1\ny = 2\nz = 3\n")
            f.flush()
            path = f.name
        
        try:
            result = tool.execute({"file_path": path, "operation": "analyze"})
            assert result["success"] is True
            assert "comment_ratio" in result
            assert "quality" in result
        finally:
            Path(path).unlink()

    def test_suggest_comments(self) -> None:
        """Should suggest where to add comments."""
        tool = CommentManagerTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("def no_docstring():\n    pass\n\nclass NoDoc:\n    pass\n")
            f.flush()
            path = f.name
        
        try:
            result = tool.execute({"file_path": path, "operation": "suggest"})
            assert result["success"] is True
            assert len(result["suggestions"]) >= 2
        finally:
            Path(path).unlink()

    def test_unknown_operation(self) -> None:
        """Should handle unknown operation."""
        tool = CommentManagerTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("x = 1\n")
            f.flush()
            path = f.name
        
        try:
            result = tool.execute({"file_path": path, "operation": "unknown"})
            assert result["success"] is False
        finally:
            Path(path).unlink()


class TestTaskManagerTool:
    """Test TaskManagerTool."""

    def test_get_name(self) -> None:
        """Should return correct name."""
        tool = TaskManagerTool()
        assert tool.get_name() == "task_manager"

    def test_directory_not_found(self) -> None:
        """Should handle missing directory."""
        tool = TaskManagerTool()
        result = tool.execute({"directory": "/nonexistent"})
        assert result["success"] is False

    def test_find_todo_markers(self) -> None:
        """Should find TODO markers."""
        tool = TaskManagerTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "test.py").write_text("# TODO: fix this\n# FIXME: urgent\n")
            
            result = tool.execute({"directory": tmpdir})
            
            assert result["success"] is True
            assert result["total"] >= 2

    def test_custom_task_types(self) -> None:
        """Should support custom task types."""
        tool = TaskManagerTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "test.py").write_text("# NOTE: remember this\n")
            
            result = tool.execute({
                "directory": tmpdir,
                "task_types": ["NOTE"]
            })
            
            assert result["success"] is True
            assert result["total"] >= 1


class TestNotebookEditorTool:
    """Test NotebookEditorTool."""

    def test_get_name(self) -> None:
        """Should return correct name."""
        tool = NotebookEditorTool()
        assert tool.get_name() == "notebook_editor"

    def test_read_nonexistent(self) -> None:
        """Should handle non-existent notebook."""
        tool = NotebookEditorTool()
        result = tool.execute({"notebook_path": "/nonexistent.ipynb", "operation": "read"})
        assert result["success"] is False

    def test_read_notebook(self) -> None:
        """Should read notebook."""
        tool = NotebookEditorTool()
        
        with tempfile.NamedTemporaryFile(suffix=".ipynb", delete=False, mode="w") as f:
            f.write(json.dumps({
                "cells": [
                    {"cell_type": "code", "source": ["x = 1"], "metadata": {}, "outputs": [], "execution_count": None}
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 4
            }))
            f.flush()
            path = f.name
        
        try:
            result = tool.execute({"notebook_path": path, "operation": "read"})
            assert result["success"] is True
            assert result["cells"] == 1
        finally:
            Path(path).unlink()

    def test_add_cell(self) -> None:
        """Should add cell to notebook."""
        tool = NotebookEditorTool()
        
        with tempfile.NamedTemporaryFile(suffix=".ipynb", delete=False, mode="w") as f:
            f.write(json.dumps({
                "cells": [],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 4
            }))
            f.flush()
            path = f.name
        
        try:
            result = tool.execute({
                "notebook_path": path,
                "operation": "add_cell",
                "cell_content": "print('hello')",
                "cell_type": "code"
            })
            assert result["success"] is True
            
            # Verify cell was added
            content = json.loads(Path(path).read_text())
            assert len(content["cells"]) == 1
        finally:
            Path(path).unlink()

    def test_delete_cell(self) -> None:
        """Should delete cell from notebook."""
        tool = NotebookEditorTool()
        
        with tempfile.NamedTemporaryFile(suffix=".ipynb", delete=False, mode="w") as f:
            f.write(json.dumps({
                "cells": [
                    {"cell_type": "code", "source": ["x = 1"], "metadata": {}, "outputs": [], "execution_count": None},
                    {"cell_type": "code", "source": ["y = 2"], "metadata": {}, "outputs": [], "execution_count": None}
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 4
            }))
            f.flush()
            path = f.name
        
        try:
            result = tool.execute({
                "notebook_path": path,
                "operation": "delete_cell",
                "cell_index": 0
            })
            assert result["success"] is True
            
            content = json.loads(Path(path).read_text())
            assert len(content["cells"]) == 1
        finally:
            Path(path).unlink()


class TestShellExecutorTool:
    """Test ShellExecutorTool."""

    def test_get_name(self) -> None:
        """Should return correct name."""
        tool = ShellExecutorTool()
        assert tool.get_name() == "shell_executor"

    def test_execute_safe_command(self) -> None:
        """Should execute safe commands."""
        tool = ShellExecutorTool()
        
        result = tool.execute({"command": "echo hello"})
        
        assert result["success"] is True
        assert "hello" in result["stdout"]

    def test_block_dangerous_commands(self) -> None:
        """Should block dangerous commands."""
        tool = ShellExecutorTool()
        
        result = tool.execute({"command": "rm -rf /"})
        
        assert result["success"] is False
        assert "Dangerous" in result["error"]

    def test_respect_timeout(self) -> None:
        """Should respect timeout."""
        tool = ShellExecutorTool()
        
        # This test should complete quickly on most systems
        result = tool.execute({
            "command": "echo quick",
            "timeout": 5
        })
        
        assert result["success"] is True
