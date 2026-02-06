"""
Tests for mcp/tools/formatter.py module.

TDD: Testing formatter tool.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from tree_sitter_analyzer_v2.mcp.tools.formatter import FormatterTool


class TestFormatterTool:
    """Test FormatterTool."""

    def test_get_name(self) -> None:
        """Should return correct name."""
        tool = FormatterTool()
        assert tool.get_name() == "format_code"

    def test_get_description(self) -> None:
        """Should return description."""
        tool = FormatterTool()
        assert "format" in tool.get_description().lower()

    def test_get_schema(self) -> None:
        """Should return correct schema."""
        tool = FormatterTool()
        schema = tool.get_schema()
        
        assert "path" in schema["properties"]
        assert "check_only" in schema["properties"]
        assert "path" in schema["required"]

    def test_path_not_found(self) -> None:
        """Should handle missing path."""
        tool = FormatterTool()
        result = tool.execute({"path": "/nonexistent/file.py"})
        
        assert result["success"] is False
        assert "not found" in result["error"]

    @patch("subprocess.run")
    def test_format_success(self, mock_run) -> None:
        """Should format successfully."""
        mock_run.return_value = MagicMock(
            stdout="Formatted",
            stderr="",
            returncode=0
        )
        
        tool = FormatterTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("x=1\n")
            f.flush()
            path = f.name
        
        try:
            result = tool.execute({"path": path})
            
            assert result["success"] is True
            assert result["formatted"] is True
        finally:
            Path(path).unlink()

    @patch("subprocess.run")
    def test_format_check_only(self, mock_run) -> None:
        """Should check without formatting."""
        mock_run.return_value = MagicMock(
            stdout="",
            stderr="",
            returncode=0
        )
        
        tool = FormatterTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("x = 1\n")
            f.flush()
            path = f.name
        
        try:
            result = tool.execute({"path": path, "check_only": True})
            
            # Verify --check was passed
            call_args = mock_run.call_args[0][0]
            assert "--check" in call_args
            assert result["formatted"] is False
        finally:
            Path(path).unlink()

    @patch("subprocess.run")
    def test_format_needs_formatting(self, mock_run) -> None:
        """Should report when formatting needed."""
        mock_run.return_value = MagicMock(
            stdout="Would reformat",
            stderr="",
            returncode=1
        )
        
        tool = FormatterTool()
        
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("x=1\n")
            f.flush()
            path = f.name
        
        try:
            result = tool.execute({"path": path, "check_only": True})
            
            assert result["success"] is False
        finally:
            Path(path).unlink()

    @patch("subprocess.run")
    def test_format_error_handling(self, mock_run) -> None:
        """Should handle subprocess errors."""
        mock_run.side_effect = Exception("Subprocess error")
        
        tool = FormatterTool()
        
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
