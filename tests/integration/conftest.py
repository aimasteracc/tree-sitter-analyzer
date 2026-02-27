"""Shared fixtures for integration tests."""

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def project_root():
    """Get the real project root directory."""
    return Path(__file__).parent.parent.parent


@pytest.fixture
def real_python_file(project_root):
    """Get a real Python file from the project for integration testing."""
    candidates = [
        project_root / "tree_sitter_analyzer" / "__init__.py",
        project_root / "tree_sitter_analyzer" / "core" / "models.py",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    pytest.skip("No suitable Python file found for integration testing")


@pytest.fixture
def temp_integration_project(tmp_path):
    """Create a temporary project with multiple language files for integration testing."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text(
        'def main():\n    print("hello")\n', encoding="utf-8"
    )
    (tmp_path / "src" / "app.js").write_text(
        'function app() {\n    console.log("hello");\n}\n', encoding="utf-8"
    )
    (tmp_path / "README.md").write_text("# Test Project\n", encoding="utf-8")
    return tmp_path
