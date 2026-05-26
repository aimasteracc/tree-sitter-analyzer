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
from hypothesis import settings as hypothesis_settings  # noqa: E402

# TEST-P3 root-cause fix: under pytest-xdist's load balancer, multiple
# worker processes share the on-disk Hypothesis example database
# (.hypothesis/examples), which produces flaky failures on text-generative
# `@given` tests (notably test_invalid_query_name and
# test_property_1_analysis_result_to_json_roundtrip) when shrinking races
# across workers. Setting database=None makes example generation purely
# in-process and removes the contention entirely. The trade-off — losing
# cross-run shrink replay — is acceptable in CI; local debuggers can opt
# back in via HYPOTHESIS_DATABASE=… if needed.
hypothesis_settings.register_profile(
    "tree_sitter_analyzer", deadline=None, database=None
)
hypothesis_settings.load_profile("tree_sitter_analyzer")


def pytest_configure(config):
    """Configure pytest with custom markers and safety checks."""
    # Suppress SQLite connection finalizer warnings that fire when gc.collect()
    # in one xdist worker collects objects from other workers. These are benign
    # resource cleanup events, not actual test failures.
    # Must be added here (not pytest.ini) so the pytest.ini contract
    # (filterwarnings[0] == "error") stays valid.
    config.addinivalue_line(
        "filterwarnings",
        "ignore:Exception ignored while finalizing database connection"
        ":pytest.PytestUnraisableExceptionWarning",
    )
    config.addinivalue_line(
        "markers", "requires_ripgrep: mark test as requiring ripgrep (rg) command"
    )
    config.addinivalue_line("markers", "requires_fd: mark test as requiring fd command")
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "performance: mark test as performance test")
    config.addinivalue_line("markers", "regression: mark test as regression test")
    config.addinivalue_line("markers", "property: mark test as property-based test")
    # Tests that legitimately need >SLOW_TEST_BUDGET_S of real wall time
    # (file watcher polling, large-fixture parsers, etc.) must opt out
    # explicitly. Without the marker the runtime gate below fails them.
    config.addinivalue_line(
        "markers",
        "slow_ok: test legitimately exceeds SLOW_TEST_BUDGET_S; "
        "opt-out of the unit-suite per-test perf budget (use sparingly)",
    )

    # HARD BLOCK: detect duplicate --cov arguments that cause memory blowup.
    # Only count --cov and --cov= (NOT --cov-report, --cov-fail-under, etc.)
    import re

    cli_cov_count = 0
    for arg in config.invocation_params.args:
        arg_str = str(arg)
        if re.match(r"^--cov(=|$)", arg_str):
            cli_cov_count += 1
    if cli_cov_count > 1:
        raise SystemExit(
            "FATAL: --cov specified multiple times on the command line. "
            "This causes double coverage tracking and can exhaust system memory. "
            "Use --cov exactly once. Example: uv run pytest --cov=tree_sitter_analyzer --cov-report=json"
        )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to skip tests based on missing dependencies."""
    # Check for external dependencies
    has_ripgrep = shutil.which("rg") is not None
    has_fd = shutil.which("fd") is not None

    skip_ripgrep = pytest.mark.skip(
        reason="ripgrep (rg) not available; tracked: optional local CLI dependency"
    )
    skip_fd = pytest.mark.skip(
        reason="fd not available; tracked: optional local CLI dependency"
    )

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


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Warn if memory usage is dangerously high at end of session."""
    try:
        import os

        import psutil

        process = psutil.Process(os.getpid())
        rss_gb = process.memory_info().rss / (1024**3)
        system_total_gb = psutil.virtual_memory().total / (1024**3)
        usage_pct = process.memory_info().rss / psutil.virtual_memory().total * 100

        if rss_gb > 2.0:
            terminalreporter.write_sep(
                "!",
                f"MEMORY WARNING: pytest RSS = {rss_gb:.1f} GB "
                f"({usage_pct:.0f}% of {system_total_gb:.0f} GB system RAM). "
                f"Consider running fewer tests or using -x.",
            )
        if rss_gb > 4.0:
            terminalreporter.write_sep(
                "!",
                f"MEMORY CRITICAL: pytest RSS = {rss_gb:.1f} GB! "
                f"This can crash the system. Reduce test batch size.",
            )
    except ImportError:
        pass


@pytest.fixture(autouse=True)
def cleanup_asyncio_tasks():
    """
    Clean up asyncio tasks after each test to prevent 'NoneType' object has no attribute '_PENDING'
    error on Python 3.10 during shutdown.

    Python 3.12 deprecates ``asyncio.get_event_loop()`` when there is no
    running loop and no policy-bound loop. Use the running-loop probe
    (``get_running_loop``) and fall back silently when no loop is bound —
    the cleanup is only meaningful when an in-flight loop actually
    exists.
    """
    yield

    import asyncio
    import contextlib

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            # Fall back to the policy-bound loop; ``get_event_loop_policy``
            # is stable across 3.10–3.13. ``_get_loop()`` returns None if
            # no loop is bound, so we don't trip the deprecation warning
            # ``asyncio.get_event_loop()`` emits on 3.12+.
            policy = asyncio.get_event_loop_policy()
            loop = policy._local._loop  # type: ignore[attr-defined]
        except Exception:
            return
        if loop is None:
            return

    if loop.is_closed() or loop.is_running():
        return

    tasks = [task for task in asyncio.all_tasks(loop) if not task.done()]

    if not tasks:
        return

    for task in tasks:
        task.cancel()

    with contextlib.suppress(asyncio.TimeoutError):
        loop.run_until_complete(
            asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True), timeout=2.0
            )
        )


def _reset_all_singletons():
    """Reset all global singletons. Called before and after each test for isolation."""
    # Reset analysis engine
    try:
        from tree_sitter_analyzer.core.analysis_engine import UnifiedAnalysisEngine

        UnifiedAnalysisEngine._reset_instance()
    except (ImportError, AttributeError):
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

    # Reset formatter registry
    try:
        from tree_sitter_analyzer.formatters.formatter_registry import FormatterRegistry

        FormatterRegistry.clear()
        FormatterRegistry.register_builtin_formatters()
    except (ImportError, AttributeError):
        pass

    # Reset MCP-related singletons
    try:
        from tree_sitter_analyzer.mcp.utils.search_cache import clear_cache

        clear_cache()
    except (ImportError, AttributeError):
        pass

    try:
        from tree_sitter_analyzer.mcp.utils import gitignore_detector

        if hasattr(gitignore_detector, "_default_detector"):
            gitignore_detector._default_detector = None
    except (ImportError, AttributeError):
        pass

    # Reset language and query loaders
    try:
        from tree_sitter_analyzer import language_loader

        if hasattr(language_loader, "_loader_instance"):
            language_loader._loader_instance = None
    except (ImportError, AttributeError):
        pass

    try:
        from tree_sitter_analyzer import query_loader

        if hasattr(query_loader, "_query_loader_instance"):
            query_loader._query_loader_instance = None
    except (ImportError, AttributeError):
        pass

    # Reset engine manager
    try:
        from tree_sitter_analyzer.core.engine_manager import EngineManager

        EngineManager.reset_instances()
    except (ImportError, AttributeError):
        pass

    # Reset file output factory
    try:
        from tree_sitter_analyzer.mcp.utils.file_output_factory import (
            FileOutputManagerFactory,
        )

        FileOutputManagerFactory._instances.clear()
    except (ImportError, AttributeError):
        pass


@pytest.fixture(autouse=True)
def reset_global_singletons():
    """Reset all global singletons before and after each test for isolation."""
    _reset_all_singletons()
    yield
    _reset_all_singletons()


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_databases():
    """Clean up test databases once per session instead of per-test."""
    yield

    import glob
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
        for db_file in glob.glob(os.path.join(temp_dir, pattern)):
            try:
                os.remove(db_file)
            except (OSError, PermissionError):
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


# ---------------------------------------------------------------------------
# Per-test runtime budget (regression prevention 2026-05-23)
# ---------------------------------------------------------------------------
#
# Two real bugs cost us ~62s of unit-suite latency (91s → 29s) before
# they were caught:
#
#   1. ``import_extractors._node_text`` accidentally encoded the full
#      source-file UTF-8 buffer on every call (217k calls / 7.5s pure
#      encoding overhead per run).
#   2. Five tests used ``project_root="/tmp"`` or ``project_root=None``
#      and silently triggered a full DependencyGraph + CallGraph build
#      against the 1100-file repo via cwd fallback (each test 9-37s).
#
# Both classes of regression have the same fingerprint at the unit
# layer: a single test crossing the 5-second mark. The hook below
# fails any unit test that exceeds ``SLOW_TEST_BUDGET_S`` unless it
# explicitly opts out via ``@pytest.mark.slow_ok`` — forcing the author
# to either fix the perf or document why the cost is real.
#
# We deliberately fail the test (not just warn) so the regression
# blocks CI. ``slow_ok`` is the escape hatch for known-slow tests
# (file_watcher polling, real-process file_output, etc.).

SLOW_TEST_BUDGET_S: float = 5.0


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    """Enforce per-test wall-time budget for unit tests.

    Skipped under integration / performance markers and when the test
    is explicitly tagged ``slow_ok``. Integration tests have their own
    looser thresholds; performance tests are timed elsewhere.
    """
    import time

    opted_out = (
        "slow_ok" in item.keywords
        or "performance" in item.keywords
        or "integration" in item.keywords
    )
    started = time.monotonic()
    outcome = yield
    elapsed = time.monotonic() - started

    # Only enforce on unit tests (tests/unit/...). Other suites are
    # allowed to take longer.
    is_unit = "/tests/unit/" in str(item.fspath).replace("\\", "/")

    if (
        is_unit
        and not opted_out
        and outcome.excinfo is None  # don't double-fail on already-failing tests
        and elapsed > SLOW_TEST_BUDGET_S
    ):
        pytest.fail(
            f"Unit test exceeded per-test budget: {elapsed:.2f}s > "
            f"{SLOW_TEST_BUDGET_S:.1f}s.\n"
            f"Common causes (see tests/conftest.py for the full history):\n"
            f"  • Accidentally scanning the whole repo "
            f"(project_root='/tmp' or =None when cwd is the repo)\n"
            f"  • Per-call O(file_size) work in a tight loop "
            f"(e.g. source.encode() inside a node-text helper)\n"
            f"  • Real subprocess / network / sleep without a mock\n"
            f"Fix the perf, or — if the cost is real and documented — add "
            f"@pytest.mark.slow_ok with a justifying comment.",
            pytrace=False,
        )
