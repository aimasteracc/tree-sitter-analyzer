"""Shared fixtures for MCP tests."""

from pathlib import Path

import pytest


@pytest.fixture
def temp_project(tmp_path):
    """Create a temporary project directory with sample files for MCP testing."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    (src_dir / "main.py").write_text(
        'def main():\n    print("hello")\n', encoding="utf-8"
    )
    (src_dir / "utils.py").write_text(
        "def helper(x):\n    return x + 1\n", encoding="utf-8"
    )
    (tmp_path / "README.md").write_text("# Test Project\n", encoding="utf-8")

    return tmp_path


@pytest.fixture
def project_root():
    """Get the real project root for integration-style MCP tests."""
    return Path(__file__).parent.parent.parent.parent
