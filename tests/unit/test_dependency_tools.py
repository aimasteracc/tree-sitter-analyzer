"""
Tests for mcp/tools/dependencies.py module.

TDD: Testing dependency analysis and graph generation tools.
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.mcp.tools.dependencies import (
    DependencyAnalyzerTool,
    DependencyGraphTool,
)


class TestDependencyAnalyzerTool:
    """Test DependencyAnalyzerTool."""

    def test_get_name(self) -> None:
        """Should return correct tool name."""
        tool = DependencyAnalyzerTool()
        assert tool.get_name() == "analyze_dependencies"

    def test_get_description(self) -> None:
        """Should return description."""
        tool = DependencyAnalyzerTool()
        assert "dependencies" in tool.get_description().lower()

    def test_get_schema(self) -> None:
        """Should return valid schema."""
        tool = DependencyAnalyzerTool()
        schema = tool.get_schema()
        
        assert schema["type"] == "object"
        assert "directory" in schema["properties"]
        assert "directory" in schema["required"]

    def test_directory_not_found(self) -> None:
        """Should return error for non-existent directory."""
        tool = DependencyAnalyzerTool()
        result = tool.execute({"directory": "/nonexistent/path"})
        
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_analyze_empty_directory(self) -> None:
        """Should handle empty directory."""
        tool = DependencyAnalyzerTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            result = tool.execute({"directory": tmpdir})
            
            assert result["success"] is True
            assert result["count"] == 0
            assert result["files_analyzed"] == 0

    def test_analyze_simple_imports(self) -> None:
        """Should extract imports from Python files."""
        tool = DependencyAnalyzerTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            py_file = Path(tmpdir) / "test.py"
            py_file.write_text("""
import os
import sys
from pathlib import Path
from typing import List
""")
            
            result = tool.execute({"directory": tmpdir})
            
            assert result["success"] is True
            assert result["files_analyzed"] == 1
            assert "os" in result["dependencies"]
            assert "sys" in result["dependencies"]
            assert "pathlib" in result["dependencies"]
            assert "typing" in result["dependencies"]

    def test_analyze_multiple_files(self) -> None:
        """Should analyze multiple Python files."""
        tool = DependencyAnalyzerTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = Path(tmpdir) / "app.py"
            file1.write_text("import flask")
            
            file2 = Path(tmpdir) / "utils.py"
            file2.write_text("import requests")
            
            result = tool.execute({"directory": tmpdir})
            
            assert result["success"] is True
            assert result["files_analyzed"] == 2
            assert "flask" in result["dependencies"]
            assert "requests" in result["dependencies"]

    def test_analyze_nested_directories(self) -> None:
        """Should analyze files in nested directories."""
        tool = DependencyAnalyzerTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = Path(tmpdir) / "src" / "module"
            subdir.mkdir(parents=True)
            
            py_file = subdir / "core.py"
            py_file.write_text("import json")
            
            result = tool.execute({"directory": tmpdir})
            
            assert result["success"] is True
            assert result["files_analyzed"] == 1
            assert "json" in result["dependencies"]

    def test_handle_syntax_errors(self) -> None:
        """Should skip files with syntax errors."""
        tool = DependencyAnalyzerTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            good_file = Path(tmpdir) / "good.py"
            good_file.write_text("import os")
            
            bad_file = Path(tmpdir) / "bad.py"
            bad_file.write_text("this is not valid python {{{")
            
            result = tool.execute({"directory": tmpdir})
            
            assert result["success"] is True
            assert "os" in result["dependencies"]

    def test_deduplicate_imports(self) -> None:
        """Should deduplicate imports from multiple files."""
        tool = DependencyAnalyzerTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = Path(tmpdir) / "a.py"
            file1.write_text("import os")
            
            file2 = Path(tmpdir) / "b.py"
            file2.write_text("import os")
            
            result = tool.execute({"directory": tmpdir})
            
            assert result["dependencies"].count("os") == 1


class TestDependencyGraphTool:
    """Test DependencyGraphTool."""

    def test_get_name(self) -> None:
        """Should return correct tool name."""
        tool = DependencyGraphTool()
        assert tool.get_name() == "dependency_graph"

    def test_get_description(self) -> None:
        """Should return description."""
        tool = DependencyGraphTool()
        assert "graph" in tool.get_description().lower()

    def test_get_schema(self) -> None:
        """Should return valid schema."""
        tool = DependencyGraphTool()
        schema = tool.get_schema()
        
        assert schema["type"] == "object"
        assert "directory" in schema["properties"]
        assert "format" in schema["properties"]

    def test_directory_not_found(self) -> None:
        """Should return error for non-existent directory."""
        tool = DependencyGraphTool()
        result = tool.execute({"directory": "/nonexistent/path"})
        
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_generate_mermaid_graph(self) -> None:
        """Should generate Mermaid graph format."""
        tool = DependencyGraphTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create files that import each other
            app_file = Path(tmpdir) / "app.py"
            app_file.write_text("from utils import helper")
            
            utils_file = Path(tmpdir) / "utils.py"
            utils_file.write_text("import config")
            
            config_file = Path(tmpdir) / "config.py"
            config_file.write_text("")
            
            result = tool.execute({"directory": tmpdir})
            
            assert result["success"] is True
            assert "graph TD" in result["graph"]
            assert result["modules"] >= 3

    def test_empty_directory(self) -> None:
        """Should handle empty directory."""
        tool = DependencyGraphTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            result = tool.execute({"directory": tmpdir})
            
            assert result["success"] is True
            assert "graph TD" in result["graph"]
            assert result["modules"] == 0

    def test_single_file_no_internal_deps(self) -> None:
        """Should handle file with only external deps."""
        tool = DependencyGraphTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            py_file = Path(tmpdir) / "main.py"
            py_file.write_text("import os\nimport sys")
            
            result = tool.execute({"directory": tmpdir})
            
            assert result["success"] is True
            # External deps (os, sys) won't appear in graph
            assert result["modules"] == 1

    def test_handle_syntax_errors(self) -> None:
        """Should skip files with syntax errors."""
        tool = DependencyGraphTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            good_file = Path(tmpdir) / "good.py"
            good_file.write_text("import bad")
            
            bad_file = Path(tmpdir) / "bad.py"
            bad_file.write_text("{{{ invalid syntax")
            
            result = tool.execute({"directory": tmpdir})
            
            assert result["success"] is True
            # good.py should still be processed
            assert result["modules"] >= 1
