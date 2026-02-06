"""
Tests for mcp/tools/git_tools.py module.

TDD: Testing Git operation tools.
"""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from tree_sitter_analyzer_v2.mcp.tools.git_tools import (
    GitStatusTool,
    GitDiffTool,
    GitCommitTool,
)


class TestGitStatusTool:
    """Test GitStatusTool."""

    def test_get_name(self) -> None:
        """Should return correct name."""
        tool = GitStatusTool()
        assert tool.get_name() == "git_status"

    def test_get_description(self) -> None:
        """Should return description."""
        tool = GitStatusTool()
        assert "status" in tool.get_description().lower()

    def test_get_schema(self) -> None:
        """Should return correct schema."""
        tool = GitStatusTool()
        schema = tool.get_schema()
        
        assert "directory" in schema["properties"]
        assert "directory" in schema["required"]

    @patch("subprocess.run")
    def test_execute_clean_repo(self, mock_run) -> None:
        """Should report clean repo."""
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        
        tool = GitStatusTool()
        result = tool.execute({"directory": "/some/repo"})
        
        assert result["success"] is True
        assert result["clean"] is True

    @patch("subprocess.run")
    def test_execute_dirty_repo(self, mock_run) -> None:
        """Should report dirty repo."""
        mock_run.return_value = MagicMock(stdout=" M file.py\n", returncode=0)
        
        tool = GitStatusTool()
        result = tool.execute({"directory": "/some/repo"})
        
        assert result["success"] is True
        assert result["clean"] is False

    def test_execute_invalid_directory(self) -> None:
        """Should handle invalid directory."""
        tool = GitStatusTool()
        result = tool.execute({"directory": "/nonexistent"})
        
        assert result["success"] is False
        assert "error" in result


class TestGitDiffTool:
    """Test GitDiffTool."""

    def test_get_name(self) -> None:
        """Should return correct name."""
        tool = GitDiffTool()
        assert tool.get_name() == "git_diff"

    def test_get_schema(self) -> None:
        """Should return correct schema."""
        tool = GitDiffTool()
        schema = tool.get_schema()
        
        assert "directory" in schema["properties"]
        assert "file_path" in schema["properties"]
        assert "staged" in schema["properties"]

    @patch("subprocess.run")
    def test_execute_basic_diff(self, mock_run) -> None:
        """Should get basic diff."""
        mock_run.return_value = MagicMock(stdout="diff content", returncode=0)
        
        tool = GitDiffTool()
        result = tool.execute({"directory": "/repo"})
        
        assert result["success"] is True
        assert "diff" in result

    @patch("subprocess.run")
    def test_execute_staged_diff(self, mock_run) -> None:
        """Should get staged diff."""
        mock_run.return_value = MagicMock(stdout="staged diff", returncode=0)
        
        tool = GitDiffTool()
        result = tool.execute({"directory": "/repo", "staged": True})
        
        assert result["success"] is True
        # Verify --staged was passed
        call_args = mock_run.call_args[0][0]
        assert "--staged" in call_args

    @patch("subprocess.run")
    def test_execute_file_diff(self, mock_run) -> None:
        """Should get diff for specific file."""
        mock_run.return_value = MagicMock(stdout="file diff", returncode=0)
        
        tool = GitDiffTool()
        result = tool.execute({"directory": "/repo", "file_path": "test.py"})
        
        assert result["success"] is True


class TestGitCommitTool:
    """Test GitCommitTool."""

    def test_get_name(self) -> None:
        """Should return correct name."""
        tool = GitCommitTool()
        assert tool.get_name() == "git_commit"

    def test_get_schema(self) -> None:
        """Should return correct schema."""
        tool = GitCommitTool()
        schema = tool.get_schema()
        
        assert "directory" in schema["properties"]
        assert "message" in schema["properties"]
        assert "files" in schema["properties"]
        assert "message" in schema["required"]

    @patch("subprocess.run")
    def test_execute_commit(self, mock_run) -> None:
        """Should create commit."""
        mock_run.return_value = MagicMock(stdout="commit output", returncode=0)
        
        tool = GitCommitTool()
        result = tool.execute({
            "directory": "/repo",
            "message": "Test commit"
        })
        
        assert result["success"] is True
        assert result["committed"] is True

    @patch("subprocess.run")
    def test_execute_commit_with_files(self, mock_run) -> None:
        """Should add files before commit."""
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        
        tool = GitCommitTool()
        result = tool.execute({
            "directory": "/repo",
            "message": "Add files",
            "files": ["file1.py", "file2.py"]
        })
        
        # Should have called git add for each file
        assert mock_run.call_count >= 3  # 2 adds + 1 commit

    @patch("subprocess.run")
    def test_execute_commit_failure(self, mock_run) -> None:
        """Should handle commit failure."""
        mock_run.return_value = MagicMock(stdout="", returncode=1)
        
        tool = GitCommitTool()
        result = tool.execute({
            "directory": "/repo",
            "message": "Failing commit"
        })
        
        assert result["committed"] is False
