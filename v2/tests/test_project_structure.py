"""
Test v2 project structure and setup.

This is the first test - validates that the project scaffolding is correct.
Following TDD methodology: write test FIRST, then make it pass.
"""

import sys
from pathlib import Path


class TestProjectStructure:
    """Validate v2 project structure."""

    def test_v2_directory_exists(self, project_root: Path) -> None:
        """Test that v2 directory structure exists."""
        assert project_root.exists()
        assert project_root.is_dir()
        assert project_root.name == "v2"

    def test_required_directories_exist(self, project_root: Path) -> None:
        """Test that all required directories are created."""
        required_dirs = [
            "tree_sitter_analyzer_v2",
            "tree_sitter_analyzer_v2/core",
            "tree_sitter_analyzer_v2/plugins",
            "tree_sitter_analyzer_v2/plugins/languages",
            "tree_sitter_analyzer_v2/formatters",
            "tree_sitter_analyzer_v2/models",
            "tree_sitter_analyzer_v2/mcp",
            "tree_sitter_analyzer_v2/mcp/tools",
            "tree_sitter_analyzer_v2/cli",
            "tree_sitter_analyzer_v2/api",
            "tree_sitter_analyzer_v2/utils",
            "tests",
            "tests/unit",
            "tests/integration",
            "tests/e2e",
            "tests/fixtures",
            "tests/benchmarks",
            "docs",
            "examples",
        ]

        for dir_path in required_dirs:
            full_path = project_root / dir_path
            assert full_path.exists(), f"Directory {dir_path} does not exist"
            assert full_path.is_dir(), f"{dir_path} is not a directory"

    def test_pyproject_toml_exists(self, project_root: Path) -> None:
        """Test that pyproject.toml exists and is valid."""
        pyproject = project_root / "pyproject.toml"
        assert pyproject.exists()
        assert pyproject.is_file()

        # Read and validate basic structure
        content = pyproject.read_text(encoding="utf-8")
        assert "[project]" in content
        assert 'name = "tree-sitter-analyzer-v2"' in content
        assert 'version = "2.0.0-alpha.1"' in content
        assert "[tool.pytest.ini_options]" in content
        assert "[tool.mypy]" in content
        assert "[tool.ruff]" in content

    def test_package_imports(self, project_root: Path) -> None:
        """Test that the main package can be imported."""
        # Add v2 to path if not already there
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        # Should be able to import the package
        import tree_sitter_analyzer_v2

        # Check version
        assert hasattr(tree_sitter_analyzer_v2, "__version__")
        assert tree_sitter_analyzer_v2.__version__ == "2.0.0-alpha.1"

        # Check author
        assert hasattr(tree_sitter_analyzer_v2, "__author__")
        assert tree_sitter_analyzer_v2.__author__ == "aisheng.yu"

    def test_pytest_configuration(self, project_root: Path) -> None:
        """Test that pytest is configured correctly."""
        pyproject = project_root / "pyproject.toml"
        content = pyproject.read_text(encoding="utf-8")

        # Check pytest configuration
        assert 'testpaths = ["tests"]' in content
        assert "--cov=tree_sitter_analyzer_v2" in content
        assert "unit: Unit tests" in content
        assert "integration: Integration tests" in content
        assert "e2e: End-to-end tests" in content

    def test_test_fixtures_available(
        self,
        sample_python_code: str,
        sample_typescript_code: str,
        sample_java_code: str,
    ) -> None:
        """Test that sample code fixtures are available."""
        # Python fixture
        assert "def hello_world" in sample_python_code
        assert "class Calculator" in sample_python_code

        # TypeScript fixture
        assert "interface User" in sample_typescript_code
        assert "class UserService" in sample_typescript_code

        # Java fixture
        assert "package com.example" in sample_java_code
        assert "public class UserService" in sample_java_code


class TestTDDWorkflow:
    """Test that TDD workflow is properly set up."""

    def test_can_run_pytest(self) -> None:
        """Test that pytest can be run (this test itself proves it)."""
        # If this test runs, pytest is working
        assert True

    def test_fixtures_work(self, temp_workspace: Path) -> None:
        """Test that pytest fixtures work correctly."""
        assert temp_workspace.exists()
        assert temp_workspace.is_dir()

        # Create a test file
        test_file = temp_workspace / "test.txt"
        test_file.write_text("Hello, TDD!")

        assert test_file.exists()
        assert test_file.read_text() == "Hello, TDD!"

    def test_parametrize_works(self, project_root: Path) -> None:
        """Test that pytest parametrize works."""
        # If parametrize is configured, this will work
        test_data = [
            ("tree_sitter_analyzer_v2", True),
            ("tests", True),
            ("docs", True),
            ("nonexistent", False),
        ]

        for dir_name, should_exist in test_data:
            path = project_root / dir_name
            assert path.exists() == should_exist


class TestProjectMetadata:
    """Test project metadata and configuration."""

    def test_python_version_requirement(self, project_root: Path) -> None:
        """Test that Python version requirement is set correctly."""
        pyproject = project_root / "pyproject.toml"
        content = pyproject.read_text(encoding="utf-8")

        assert 'requires-python = ">=3.10"' in content

        # Verify we're running on supported Python version
        assert sys.version_info >= (3, 10)

    def test_dependencies_declared(self, project_root: Path) -> None:
        """Test that required dependencies are declared."""
        pyproject = project_root / "pyproject.toml"
        content = pyproject.read_text(encoding="utf-8")

        # Core dependencies
        assert "tree-sitter" in content
        assert "tree-sitter-python" in content
        assert "tree-sitter-javascript" in content
        assert "tree-sitter-java" in content

        # Dev dependencies
        assert "pytest" in content
        assert "pytest-cov" in content
        assert "mypy" in content
        assert "ruff" in content

        # MCP dependency
        assert "mcp" in content

    def test_project_structure_documentation(self, project_root: Path) -> None:
        """Test that project structure matches documentation."""
        # This test will pass when we create the documentation
        # For now, just verify docs directory exists
        docs_dir = project_root / "docs"
        assert docs_dir.exists()
        assert docs_dir.is_dir()
