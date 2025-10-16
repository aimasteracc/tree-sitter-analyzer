#!/usr/bin/env python3
"""
Global test configuration and fixtures.
"""

import shutil
from pathlib import Path

import pytest


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "requires_ripgrep: mark test as requiring ripgrep (rg) command"
    )
    config.addinivalue_line("markers", "requires_fd: mark test as requiring fd command")
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "performance: mark test as performance test")


def pytest_collection_modifyitems(config, items):
    """Modify test collection to skip tests based on missing dependencies."""
    # Check for external dependencies
    has_ripgrep = shutil.which("rg") is not None
    has_fd = shutil.which("fd") is not None

    skip_ripgrep = pytest.mark.skip(reason="ripgrep (rg) not available")
    skip_fd = pytest.mark.skip(reason="fd not available")

    for item in items:
        # Skip tests that require ripgrep if not available
        if "requires_ripgrep" in item.keywords and not has_ripgrep:
            item.add_marker(skip_ripgrep)

        # Skip tests that require fd if not available
        if "requires_fd" in item.keywords and not has_fd:
            item.add_marker(skip_fd)


@pytest.fixture(scope="session")
def has_external_tools():
    """Check availability of external tools."""
    return {
        "ripgrep": shutil.which("rg") is not None,
        "fd": shutil.which("fd") is not None,
    }


@pytest.fixture(scope="session")
def test_data_dir():
    """Get test data directory."""
    return Path(__file__).parent / "test_data"


@pytest.fixture
def temp_project_dir(tmp_path):
    """Create a temporary project directory with sample files."""
    # Create sample Python files
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "__init__.py").write_text("")
    (tmp_path / "src" / "main.py").write_text("""
import os
import sys

def main():
    print("Hello, World!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
""")

    # Create sample Java files
    (tmp_path / "java").mkdir()
    (tmp_path / "java" / "Main.java").write_text("""
public class Main {
    public static void main(String[] args) {
        System.out.println("Hello, World!");
    }
}
""")

    # Create sample JavaScript files
    (tmp_path / "js").mkdir()
    (tmp_path / "js" / "index.js").write_text("""
const express = require('express');
const app = express();

app.get('/', (req, res) => {
    res.send('Hello, World!');
});

app.listen(3000, () => {
    console.log('Server running on port 3000');
});
""")

    # Create README
    (tmp_path / "README.md").write_text("""
# Test Project

This is a test project for tree-sitter-analyzer.

## Features

- Python support
- Java support
- JavaScript support
""")

    return tmp_path
