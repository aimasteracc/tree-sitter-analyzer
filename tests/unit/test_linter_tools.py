"""
Tests for mcp/tools/linter.py module.

TDD: Testing linter tool.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from tree_sitter_analyzer_v2.mcp.tools.linter import LinterTool


class TestLinterTool:
    """Test LinterTool."""

    def test_get_name(self) -> None:
        """Should return correct name."""
        tool = LinterTool()
        assert tool.get_name() == "run_linter"

    def test_get_description(self) -> None:
        """Should return description."""
        tool = LinterTool()
        assert "lint" in tool.get_description().lower()

    def test_get_schema(self) -> None:
        """Should return correct schema."""
        tool = LinterTool()
        schema = tool.get_schema()
        
        assert "path" in schema["properties"]
        assert "fix" in schema["properties"]
        assert "path" in schema["required"]

    def test_path_not_found(self) -> None:
        """Should handle missing path."""
        tool = LinterTool()
        result = tool.execute({"path": "/nonexistent/file.py"})
        
        assert result["success"] is False
        assert "not found" in result["error"]

    @patch("subprocess.run")
    def test_lint_success(self, mock_run) -> None:
        """Should lint successfully."""
        mock_run.return_value = MagicMock(
            stdout="",
            stderr="",
            returncode=0
        )
        
        tool = LinterTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("x = 1\n")
            f.flush()
            path = f.name
        
        try:
            result = tool.execute({"path": path})
            
            assert result["success"] is True
        finally:
            Path(path).unlink()

    @patch("subprocess.run")
    def test_lint_with_issues(self, mock_run) -> None:
        """Should report lint issues."""
        mock_run.return_value = MagicMock(
            stdout="file.py:1:1: E501 line too long",
            stderr="",
            returncode=1
        )
        
        tool = LinterTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("x = 1\n")
            f.flush()
            path = f.name
        
        try:
            result = tool.execute({"path": path})
            
            assert result["success"] is False
            assert "E501" in result["issues"]
        finally:
            Path(path).unlink()

    @patch("subprocess.run")
    def test_lint_with_fix(self, mock_run) -> None:
        """Should pass --fix flag."""
        mock_run.return_value = MagicMock(
            stdout="",
            stderr="",
            returncode=0
        )
        
        tool = LinterTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("x = 1\n")
            f.flush()
            path = f.name
        
        try:
            result = tool.execute({"path": path, "fix": True})
            
            # Verify --fix was passed
            call_args = mock_run.call_args[0][0]
            assert "--fix" in call_args
        finally:
            Path(path).unlink()

    @patch("subprocess.run")
    def test_lint_error_handling(self, mock_run) -> None:
        """Should handle subprocess errors."""
        mock_run.side_effect = Exception("Subprocess error")
        
        tool = LinterTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("x = 1\n")
            f.flush()
            path = f.name
        
        try:
            result = tool.execute({"path": path})
            
            assert result["success"] is False
            assert "error" in result
        finally:
            Path(path).unlink()
