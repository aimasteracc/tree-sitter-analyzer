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
    config.addinivalue_line("markers", "regression: mark test as regression test")
    config.addinivalue_line("markers", "property: mark test as property-based test")


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
    Force garbage collection at end of session to ensure
    asyncio tasks are cleaned up while interpreter is still fully operational.
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
        # Get running loop if possible
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No event loop running
        return

    tasks = asyncio.all_tasks(loop)

    # Cancel all tasks except current one
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
def reset_global_singletons():
    """Reset all global singletons after each test."""
    # Reset analysis engine
    try:
        from tree_sitter_analyzer.core.analysis_engine import UnifiedAnalysisEngine

        UnifiedAnalysisEngine._reset_instance()
    except ImportError:
        pass

    # Reset language detector cache
    try:
        from tree_sitter_analyzer.core.language_detector import LanguageDetector

        if hasattr(LanguageDetector, "_instance"):
            LanguageDetector._instance = None
    except (ImportError, AttributeError):
        pass

    # Reset query executor cache
    try:
        from tree_sitter_analyzer.core.query import QueryExecutor

        if hasattr(QueryExecutor, "_cache"):
            QueryExecutor._cache.clear()
    except (ImportError, AttributeError):
        pass

    # Reset formatter cache
    try:
        from tree_sitter_analyzer.formatters.formatter_selector import FormatterSelector

        if hasattr(FormatterSelector, "_instance"):
            FormatterSelector._instance = None
    except (ImportError, AttributeError):
        pass

    # Reset MCP-related singletons for parallel test safety
    try:
        from tree_sitter_analyzer.mcp.utils.search_cache import clear_cache

        # Clear the cache without importing the singleton variable
        clear_cache()
    except (ImportError, AttributeError):
        pass

    try:
        from tree_sitter_analyzer.mcp.utils import gitignore_detector

        # Reset detector by setting module attribute
        if hasattr(gitignore_detector, "_default_detector"):
            gitignore_detector._default_detector = None  # noqa: SLF001
    except (ImportError, AttributeError):
        pass

    try:
        from tree_sitter_analyzer import language_loader

        # Reset loader by setting module attribute
        if hasattr(language_loader, "_loader_instance"):
            language_loader._loader_instance = None  # noqa: SLF001
    except (ImportError, AttributeError):
        pass

    try:
        from tree_sitter_analyzer import query_loader

        # Reset query loader by setting module attribute
        if hasattr(query_loader, "_query_loader_instance"):
            query_loader._query_loader_instance = None  # noqa: SLF001
    except (ImportError, AttributeError):
        pass

    try:
        from tree_sitter_analyzer.core.engine_manager import EngineManager

        EngineManager.reset_instances()
    except (ImportError, AttributeError):
        pass

    try:
        from tree_sitter_analyzer.mcp.utils.file_output_factory import (
            FileOutputManagerFactory,
        )

        FileOutputManagerFactory._instances.clear()
    except (ImportError, AttributeError):
        pass

    yield

    # Reset after test
    try:
        from tree_sitter_analyzer.core.analysis_engine import UnifiedAnalysisEngine

        UnifiedAnalysisEngine._reset_instance()
    except ImportError:
        pass

    try:
        from tree_sitter_analyzer.core.language_detector import LanguageDetector

        if hasattr(LanguageDetector, "_instance"):
            LanguageDetector._instance = None
    except (ImportError, AttributeError):
        pass

    try:
        from tree_sitter_analyzer.core.query import QueryExecutor

        if hasattr(QueryExecutor, "_cache"):
            QueryExecutor._cache.clear()
    except (ImportError, AttributeError):
        pass

    try:
        from tree_sitter_analyzer.formatters.formatter_selector import FormatterSelector

        if hasattr(FormatterSelector, "_instance"):
            FormatterSelector._instance = None
    except (ImportError, AttributeError):
        pass

    # Reset MCP-related singletons after test
    try:
        from tree_sitter_analyzer.mcp.utils.search_cache import clear_cache

        # Clear the cache without importing the singleton variable
        clear_cache()
    except (ImportError, AttributeError):
        pass

    try:
        from tree_sitter_analyzer.mcp.utils import gitignore_detector

        # Reset detector by setting module attribute
        if hasattr(gitignore_detector, "_default_detector"):
            gitignore_detector._default_detector = None  # noqa: SLF001
    except (ImportError, AttributeError):
        pass

    try:
        from tree_sitter_analyzer import language_loader

        # Reset loader by setting module attribute
        if hasattr(language_loader, "_loader_instance"):
            language_loader._loader_instance = None  # noqa: SLF001
    except (ImportError, AttributeError):
        pass

    try:
        from tree_sitter_analyzer import query_loader

        # Reset query loader by setting module attribute
        if hasattr(query_loader, "_query_loader_instance"):
            query_loader._query_loader_instance = None  # noqa: SLF001
    except (ImportError, AttributeError):
        pass

    try:
        from tree_sitter_analyzer.core.engine_manager import EngineManager

        EngineManager.reset_instances()
    except (ImportError, AttributeError):
        pass

    try:
        from tree_sitter_analyzer.mcp.utils.file_output_factory import (
            FileOutputManagerFactory,
        )

        FileOutputManagerFactory._instances.clear()
    except (ImportError, AttributeError):
        pass


@pytest.fixture(autouse=True)
def cleanup_test_databases():
    """Clean up test databases after each test."""
    yield

    # Clean up any test databases
    import os
    import tempfile

    temp_dir = tempfile.gettempdir()
    test_db_patterns = [
        "test_*.db",
        "test_*.sqlite",
        "test_*.sqlite3",
        "*_test.db",
        "*_test.sqlite",
        "*_test.sqlite3",
    ]

    for pattern in test_db_patterns:
        import glob

        db_files = glob.glob(os.path.join(temp_dir, pattern))
        for db_file in db_files:
            try:
                if os.path.exists(db_file):
                    os.remove(db_file)
            except (OSError, PermissionError):
                # Ignore permission errors or file not found
                pass


@pytest.fixture
def temp_test_file(tmp_path):
    """Create a temporary test file with cleanup."""
    created_files = []

    def _create_temp_file(filename: str, content: str = "") -> Path:
        """Create a temporary test file.

        Args:
            filename: File name
            content: File content

        Returns:
            Path to created file
        """
        file_path = tmp_path / filename
        file_path.write_text(content, encoding="utf-8")
        created_files.append(file_path)
        return file_path

    yield _create_temp_file

    # Cleanup
    for file_path in created_files:
        try:
            if file_path.exists():
                file_path.unlink()
        except (OSError, PermissionError):
            # Ignore cleanup errors
            pass


@pytest.fixture
def temp_test_dir(tmp_path):
    """Create a temporary test directory with cleanup."""
    created_dirs = []

    def _create_temp_dir(dirname: str) -> Path:
        """Create a temporary test directory.

        Args:
            dirname: Directory name

        Returns:
            Path to created directory
        """
        dir_path = tmp_path / dirname
        dir_path.mkdir(parents=True, exist_ok=True)
        created_dirs.append(dir_path)
        return dir_path

    yield _create_temp_dir

    # Cleanup
    for dir_path in created_dirs:
        try:
            if dir_path.exists():
                import shutil

                shutil.rmtree(dir_path)
        except (OSError, PermissionError):
            # Ignore cleanup errors
            pass


@pytest.fixture
def verify_test_isolation():
    """Verify test isolation by checking for leaked resources."""
    import gc

    # Get initial state
    initial_objects = len(gc.get_objects())

    yield

    # Force garbage collection
    gc.collect()

    # Get final state
    final_objects = len(gc.get_objects())

    # Check for significant object growth (allow some tolerance)
    object_growth = final_objects - initial_objects
    max_allowed_growth = 1000  # Allow up to 1000 new objects

    if object_growth > max_allowed_growth:
        # Log warning but don't fail test
        import warnings

        warnings.warn(
            f"Potential resource leak detected: {object_growth} objects created during test "
            f"(allowed: {max_allowed_growth})",
            ResourceWarning,
            stacklevel=2,
        )
