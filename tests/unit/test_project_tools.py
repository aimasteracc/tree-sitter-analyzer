"""
Tests for mcp/tools/project.py module.

TDD: Testing project management tools.
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.mcp.tools.project import (
    ProjectInitTool,
    ProjectAnalyzerTool,
)


class TestProjectInitTool:
    """Test ProjectInitTool."""

    def test_get_name(self) -> None:
        """Should return correct tool name."""
        tool = ProjectInitTool()
        assert tool.get_name() == "init_project"

    def test_get_description(self) -> None:
        """Should return description."""
        tool = ProjectInitTool()
        assert "project" in tool.get_description().lower()

    def test_get_schema(self) -> None:
        """Should return valid schema."""
        tool = ProjectInitTool()
        schema = tool.get_schema()
        
        assert schema["type"] == "object"
        assert "directory" in schema["properties"]
        assert "name" in schema["properties"]
        assert "template" in schema["properties"]
        assert set(schema["required"]) == {"directory", "name"}

    def test_init_project_creates_structure(self) -> None:
        """Should create project structure."""
        tool = ProjectInitTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "my_project"
            
            result = tool.execute({
                "directory": str(project_dir),
                "name": "myapp"
            })
            
            assert result["success"] is True
            assert result["files_created"] == 5
            
            # Verify structure
            assert project_dir.exists()
            assert (project_dir / "myapp").is_dir()
            assert (project_dir / "myapp" / "__init__.py").exists()
            assert (project_dir / "tests").is_dir()
            assert (project_dir / "tests" / "__init__.py").exists()
            assert (project_dir / "pyproject.toml").exists()
            assert (project_dir / "README.md").exists()

    def test_init_project_creates_pyproject(self) -> None:
        """Should create valid pyproject.toml."""
        tool = ProjectInitTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            
            result = tool.execute({
                "directory": str(project_dir),
                "name": "testpkg"
            })
            
            assert result["success"] is True
            
            pyproject = (project_dir / "pyproject.toml").read_text()
            assert 'name = "testpkg"' in pyproject
            assert 'version = "0.1.0"' in pyproject

    def test_init_project_creates_readme(self) -> None:
        """Should create README with project name."""
        tool = ProjectInitTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            
            result = tool.execute({
                "directory": str(project_dir),
                "name": "awesome"
            })
            
            assert result["success"] is True
            
            readme = (project_dir / "README.md").read_text()
            assert "# awesome" in readme
            assert "import awesome" in readme

    def test_init_existing_directory(self) -> None:
        """Should work with existing directory."""
        tool = ProjectInitTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "existing"
            project_dir.mkdir()
            
            result = tool.execute({
                "directory": str(project_dir),
                "name": "myapp"
            })
            
            assert result["success"] is True


class TestProjectAnalyzerTool:
    """Test ProjectAnalyzerTool."""

    def test_get_name(self) -> None:
        """Should return correct tool name."""
        tool = ProjectAnalyzerTool()
        assert tool.get_name() == "analyze_project"

    def test_get_description(self) -> None:
        """Should return description."""
        tool = ProjectAnalyzerTool()
        assert "project" in tool.get_description().lower()

    def test_get_schema(self) -> None:
        """Should return valid schema."""
        tool = ProjectAnalyzerTool()
        schema = tool.get_schema()
        
        assert schema["type"] == "object"
        assert "directory" in schema["properties"]
        assert "directory" in schema["required"]

    def test_directory_not_found(self) -> None:
        """Should return error for non-existent directory."""
        tool = ProjectAnalyzerTool()
        result = tool.execute({"directory": "/nonexistent/path"})
        
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_analyze_project_counts_files(self) -> None:
        """Should count Python files."""
        tool = ProjectAnalyzerTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create source files
            (Path(tmpdir) / "app.py").write_text("def app(): pass")
            (Path(tmpdir) / "utils.py").write_text("def util(): pass")
            
            # Create test files
            (Path(tmpdir) / "test_app.py").write_text("def test(): pass")
            
            result = tool.execute({"directory": tmpdir})
            
            assert result["success"] is True
            assert result["total_files"] == 3
            assert result["source_files"] == 2
            assert result["test_files"] == 1

    def test_analyze_project_counts_lines(self) -> None:
        """Should count total lines."""
        tool = ProjectAnalyzerTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "app.py").write_text("line1\nline2\nline3")
            
            result = tool.execute({"directory": tmpdir})
            
            assert result["success"] is True
            assert result["total_lines"] == 3

    def test_analyze_project_calculates_test_ratio(self) -> None:
        """Should calculate test ratio."""
        tool = ProjectAnalyzerTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # 2 source files, 1 test file = 0.5 ratio
            (Path(tmpdir) / "app.py").write_text("")
            (Path(tmpdir) / "utils.py").write_text("")
            (Path(tmpdir) / "test_app.py").write_text("")
            
            result = tool.execute({"directory": tmpdir})
            
            assert result["success"] is True
            assert result["test_ratio"] == 0.5

    def test_analyze_empty_project(self) -> None:
        """Should handle empty project."""
        tool = ProjectAnalyzerTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            result = tool.execute({"directory": tmpdir})
            
            assert result["success"] is True
            assert result["total_files"] == 0
            assert result["test_ratio"] == 0

    def test_analyze_nested_files(self) -> None:
        """Should analyze files in nested directories."""
        tool = ProjectAnalyzerTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = Path(tmpdir) / "src" / "module"
            subdir.mkdir(parents=True)
            (subdir / "core.py").write_text("def core(): pass")
            
            result = tool.execute({"directory": tmpdir})
            
            assert result["success"] is True
            assert result["total_files"] >= 1

    def test_handle_unreadable_files(self) -> None:
        """Should handle files that can't be read."""
        tool = ProjectAnalyzerTool()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            good_file = Path(tmpdir) / "good.py"
            good_file.write_text("x = 1\ny = 2")
            
            result = tool.execute({"directory": tmpdir})
            
            assert result["success"] is True
            # Should still count lines from readable files
            assert result["total_lines"] >= 2
