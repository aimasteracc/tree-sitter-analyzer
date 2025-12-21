#!/usr/bin/env python3
"""
Global test configuration and fixtures.
"""

import shutil
import sys
from pathlib import Path

# Explicitly add project root to sys.path to ensure strict import resolution
# regardless of where pytest is invoked from
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest  # noqa: E402


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
    (tmp_path / "src" / "main.py").write_text(
        """
import os
import sys

def main():
    print("Hello, World!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
"""
    )

    # Create sample Java files
    (tmp_path / "java").mkdir()
    (tmp_path / "java" / "Main.java").write_text(
        """
public class Main {
    public static void main(String[] args) {
        System.out.println("Hello, World!");
    }
}
"""
    )

    # Create sample JavaScript files
    (tmp_path / "js").mkdir()
    (tmp_path / "js" / "index.js").write_text(
        """
const express = require('express');
const app = express();

app.get('/', (req, res) => {
    res.send('Hello, World!');
});

app.listen(3000, () => {
    console.log('Server running on port 3000');
});
"""
    )

    # Create README
    (tmp_path / "README.md").write_text(
        """
# Test Project

This is a test project for tree-sitter-analyzer.

## Features

- Python support
- Java support
- JavaScript support
"""
    )

    return tmp_path


def pytest_sessionfinish(session, exitstatus):
    """
    Force garbage collection at the end of the session to ensure
    asyncio tasks are cleaned up while the interpreter is still fully operational.
    """
    import gc

    gc.collect()


@pytest.fixture(autouse=True)
async def cleanup_asyncio_tasks():
    """
    Clean up asyncio tasks after each test to prevent 'NoneType' object has no attribute '_PENDING'
    error on Python 3.10 during shutdown.
    """
    yield

    # Get all tasks
    import asyncio

    try:
        # Get the running loop if possible
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No event loop running
        return

    tasks = asyncio.all_tasks(loop)

    # Cancel all tasks except the current one
    current_task = asyncio.current_task(loop)
    tasks = [t for t in tasks if t is not current_task]

    if not tasks:
        return

    # Cancel tasks
    for task in tasks:
        task.cancel()

    # Wait for tasks to complete
    # We use a timeout to avoid hanging if a task ignores cancellation
    try:
        await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True), timeout=2.0
        )
    except asyncio.TimeoutError:
        pass


@pytest.fixture(autouse=True)
def reset_analysis_engine():
    """Reset the UnifiedAnalysisEngine singleton after each test."""
    from tree_sitter_analyzer.core.analysis_engine import UnifiedAnalysisEngine

    # Reset before test
    UnifiedAnalysisEngine._reset_instance()
    yield
    # Reset after test
    UnifiedAnalysisEngine._reset_instance()
