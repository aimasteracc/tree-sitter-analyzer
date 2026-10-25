#!/usr/bin/env python3
"""
Global test configuration and fixtures.
"""

import os
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

from tests import (  # noqa: E402
    pytest_crash_guard,
    pytest_hang_watchdog,
    pytest_tool_response_guard,
)
from tests.pytest_temp_hygiene import (  # noqa: E402
    cleanup_pytest_temp_root,
    configure_pytest_temp_root,
)
from tests.unit_time_budget import (  # noqa: E402
    EXCUSED_PROPERTY,
    budget_for,
    budget_violation,
    excused_summary_lines,
    is_excused,
)

QUARANTINED_TESTS: list[str] = []

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


def _cleanup_pytest_git_repos() -> None:
    """Best-effort cleanup for project-local git repos used by subprocess tests."""
    git_repos_root = PROJECT_ROOT / "_pytest_git_repos"
    if git_repos_root.exists():
        shutil.rmtree(git_repos_root, ignore_errors=True)


def pytest_xdist_auto_num_workers(config) -> int:
    """Cap automatic xdist worker sizing on Windows."""
    if sys.platform == "win32":
        return 4
    return os.cpu_count() or 4


def pytest_addoption(parser):
    pytest_hang_watchdog.add_options(parser)


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    """Configure pytest with custom markers and safety checks."""
    configure_pytest_temp_root(config)
    from tests import _seal_probe_plugin  # TEMPORARY #1821 diagnostic

    _seal_probe_plugin.install()
    # #1675: the tools/list definition cache writes under the user's home; the
    # suite builds definitions live unless a test opts in with its own dir.
    os.environ.setdefault("TSA_TOOL_DEFINITION_CACHE_DIR", "off")
    # #1700: the index fingerprint store also lives under the user's home; tests
    # opt in with their own directory.
    os.environ.setdefault("TSA_INDEX_FINGERPRINT_CACHE_DIR", "off")
    # #1710: likewise for the remembered certification timeouts.
    os.environ.setdefault("TSA_CERTIFICATION_TIMEOUT_DIR", "off")
    # #1691: likewise for the persisted index-file facts.
    os.environ.setdefault("TSA_INDEX_FACTS_DIR", "off")
    # RFC-0039 slice 2: every stamp in the suite also recomputes the full
    # certification root; an incremental root that differs fails closed and is
    # reported by the ``_certification_tree_verified`` fixture below.
    os.environ.setdefault("TSA_CERTIFICATION_VERIFY", "full")
    if not hasattr(config, "workerinput"):
        _cleanup_pytest_git_repos()
    # #1638: a test stuck past the hard deadline dumps every thread stack and
    # fails fast instead of holding the CI step until its timeout.
    pytest_hang_watchdog.install(config)
    # #1779: a per-test timeout stays a normal failed report naming the test,
    # never a worker INTERNALERROR (exit 3) or a context-free worker crash.
    pytest_crash_guard.install(config)
    # Every MCP tool response produced in a test is checked against the
    # envelope contract; a violation fails the test that produced it.
    pytest_tool_response_guard.install(config)

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
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "performance: mark test as performance test")
    config.addinivalue_line("markers", "regression: mark test as regression test")
    config.addinivalue_line("markers", "property: mark test as property-based test")
    config.addinivalue_line(
        "markers",
        "full_language: exhaustive all-language golden/regression tests; "
        "CI runs these once on the Linux coverage axis",
    )
    # Tests that legitimately need >SLOW_TEST_BUDGET_S of real wall time
    # (file watcher polling, large-fixture parsers, etc.) must opt out
    # explicitly. Without the marker the runtime gate below fails them.
    config.addinivalue_line(
        "markers",
        "slow_ok: test legitimately exceeds SLOW_TEST_BUDGET_S; "
        "opt-out of the unit-suite per-test perf budget (use sparingly)",
    )
    config.addinivalue_line(
        "markers",
        "quarantine: test is known unstable; reruns are disabled for it",
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
    """只对已登记的不稳定测试禁用重跑。"""
    for item in items:
        if "quarantine" in item.keywords:
            item.add_marker(pytest.mark.flaky(reruns=0, reruns_delay=0))
            QUARANTINED_TESTS.append(item.nodeid)


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

    if not hasattr(session.config, "workerinput"):
        _cleanup_pytest_git_repos()


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):
    """Reclaim this process's managed pytest temp directory."""
    cleanup_pytest_temp_root(config)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Warn if memory usage is dangerously high at end of session."""
    if _BUDGET_EXCUSED:
        terminalreporter.write_sep("-", "unit time budget: excused wall-time overruns")
        for line in excused_summary_lines(UNIT_TIME_BUDGET, _BUDGET_EXCUSED):
            terminalreporter.write_line(line)
    try:
        import psutil
    except ImportError:
        psutil = None

    if psutil is not None:
        try:
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
        except psutil.Error:
            pass

    if QUARANTINED_TESTS:
        terminalreporter.write_sep(
            "=",
            f"quarantined tests ({len(QUARANTINED_TESTS)})",
        )
        for nodeid in QUARANTINED_TESTS:
            terminalreporter.write_line(nodeid)


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
    """Reset all global singletons. Called before and after each test for isolation.

    Uses importlib.import_module() with string paths so static call-graph tools
    (mycelium, codegraph) do not record a direct conftest→module edge for every
    singleton reset — those phantom edges made every test file appear to call 50+
    production methods (issue #220). Behaviour is identical; only the static edge
    is removed.
    """
    import importlib

    # (module_path, attr_name, reset_callable)
    # reset_callable receives the resolved attribute and calls the reset method.
    _RESETS: list[tuple[str, str, object]] = [
        (
            "tree_sitter_analyzer.core.analysis_engine",
            "UnifiedAnalysisEngine",
            lambda cls: cls._reset_instance(),
        ),
        (
            "tree_sitter_analyzer.core.language_detector",
            "LanguageDetector",
            lambda cls: (
                setattr(cls, "_instance", None) if hasattr(cls, "_instance") else None
            ),
        ),
        (
            "tree_sitter_analyzer.core.query",
            "QueryExecutor",
            lambda cls: cls._cache.clear() if hasattr(cls, "_cache") else None,
        ),
        (
            "tree_sitter_analyzer.formatters.formatter_registry",
            "FormatterRegistry",
            lambda cls: (
                cls.clear_registry(),
                importlib.import_module(
                    "tree_sitter_analyzer.formatters.formatter_registry"
                ).register_builtin_formatters(),
            ),
        ),
        (
            "tree_sitter_analyzer.core.engine_manager",
            "EngineManager",
            lambda cls: cls.reset_instances(),
        ),
        (
            "tree_sitter_analyzer.mcp.utils.file_output_factory",
            "FileOutputManagerFactory",
            lambda cls: cls._instances.clear() if hasattr(cls, "_instances") else None,
        ),
        # RFC-0027 L6.1: the answer cache is process-local, so an entry stored
        # by one test would be served to the next. A leaked verdict is worse
        # than a leaked engine — it makes an unrelated test pass on a stale
        # answer.
        (
            "tree_sitter_analyzer.cache.answer_cache",
            "reset_answer_cache",
            lambda fn: fn(),
        ),
        # #1657：内存调用图按输入内容摘要记忆。代码不在键里，测试会替换解析
        # 规则（monkeypatch），因此每个测试都从空记忆开始。
        (
            "tree_sitter_analyzer.call_graph_memo",
            "clear",
            lambda fn: fn(),
        ),
        # #1710：调用图标记复核按库文件 stat 证据记忆。
        (
            "tree_sitter_analyzer.cache.call_graph_built_memo",
            "clear",
            lambda fn: fn(),
        ),
        # #1710：认证捕获超时的记忆按项目根留在进程内。
        (
            "tree_sitter_analyzer.mcp.tools.certification_timeouts",
            "clear",
            lambda fn: fn(),
        ),
        # #1691：非调用引用扫描的词表按项目根留在进程内；每个测试如同新进程。
        (
            "tree_sitter_analyzer.mcp.tools.reference_vocab",
            "clear",
            lambda fn: fn(),
        ),
        # #1708：调用 MCP 服务器 main() 的测试会启用发布后预构图；每个测试从关闭开始。
        (
            "tree_sitter_analyzer.call_graph_warm",
            "disable",
            lambda fn: fn(),
        ),
    ]

    for module_path, attr_name, reset_fn in _RESETS:
        try:
            mod = importlib.import_module(module_path)
            attr = getattr(mod, attr_name)
            reset_fn(attr)  # type: ignore[operator]
        except (ImportError, AttributeError, Exception):
            pass

    # Module-level attribute resets (no class attribute to look up)
    _MODULE_ATTR_RESETS: list[tuple[str, str, str]] = [
        ("tree_sitter_analyzer.language_loader", "_loader_instance", "set_none"),
        ("tree_sitter_analyzer.query_loader", "_query_loader_instance", "set_none"),
        # RFC-0025 Layer 5: the latency recorder is process-global and every
        # facade call feeds it. Without this reset, a test asserting the
        # honest NO_OBSERVATIONS empty state would see another test's samples.
        ("tree_sitter_analyzer.latency", "_recorder", "set_none"),
    ]

    for module_path, attr_name, action in _MODULE_ATTR_RESETS:
        try:
            mod = importlib.import_module(module_path)
            if action == "call":
                fn = getattr(mod, attr_name, None)
                if fn is not None:
                    fn()
            elif action == "set_none":
                if hasattr(mod, attr_name):
                    setattr(mod, attr_name, None)
        except (ImportError, AttributeError, Exception):
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

# The limit, its CI scaling and the CPU-time rule live in one place:
# tests/unit_time_budget.py (read it before changing the budget). GitHub
# Actions sets CI=true; local runs keep the strict wall-clock limit.
UNIT_TIME_BUDGET = budget_for(sys.platform, on_ci=bool(os.environ.get("CI")))
SLOW_TEST_BUDGET_S: float = UNIT_TIME_BUDGET.limit_s


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    """Enforce per-test wall-time budget for unit tests.

    Skipped under integration / performance markers and when the test
    is explicitly tagged ``slow_ok``. Integration tests have their own
    looser thresholds; performance tests are timed elsewhere.

    Implemented as a *new-style* ``wrapper=True`` hook (not the legacy
    ``hookwrapper=True``). The distinction is load-bearing for CI
    stability: with the old style, calling ``pytest.fail()`` in the
    post-``yield`` block raises *inside* an old-style hookwrapper
    teardown, which pluggy reports as ``PluggyTeardownRaisedWarning``.
    Because ``pytest.ini`` runs with ``filterwarnings = error`` that
    warning is escalated to a hard error that ``--reruns`` cannot clear
    — producing intermittent failures on slow CI workers where an
    otherwise-fast unit test brushes past the budget under xdist
    scheduling contention. New-style wrappers raise the failure
    directly through the normal call outcome (no pluggy warning), so the
    budget failure is a clean, rerunnable test failure.
    """
    import time

    opted_out = (
        "slow_ok" in item.keywords
        or "performance" in item.keywords
        or "integration" in item.keywords
    )
    started = time.monotonic()
    cpu_started = time.process_time()
    # With wrapper=True, ``yield`` returns the wrapped hook's result and
    # re-raises the test's own exception here if the test failed. When
    # the test already failed, that exception propagates straight out of
    # ``yield`` (skipping the budget check below), so we never double-fail
    # a test that raised on its own.
    result = yield
    elapsed = time.monotonic() - started
    cpu_elapsed = time.process_time() - cpu_started

    # Only enforce on unit tests (tests/unit/...). Other suites are
    # allowed to take longer.
    is_unit = "/tests/unit/" in str(item.fspath).replace("\\", "/")

    if is_unit and not opted_out:
        violation = budget_violation(
            UNIT_TIME_BUDGET, wall_s=elapsed, cpu_s=cpu_elapsed
        )
        if violation is not None:
            pytest.fail(violation, pytrace=False)
        if is_excused(UNIT_TIME_BUDGET, wall_s=elapsed, cpu_s=cpu_elapsed):
            # user_properties travel with the report to the xdist controller.
            item.user_properties.append((EXCUSED_PROPERTY, (elapsed, cpu_elapsed)))

    # New-style wrappers must return the wrapped hook's result.
    return result


_BUDGET_EXCUSED: list[tuple[str, float, float]] = []


def pytest_runtest_logreport(report):
    if report.when != "call":
        return
    for key, value in report.user_properties:
        if key == EXCUSED_PROPERTY:
            wall, cpu = value
            _BUDGET_EXCUSED.append((report.nodeid, float(wall), float(cpu)))


@pytest.fixture(autouse=True)
def _certification_tree_verified():
    """RFC-0039 gate: no stamp in this test produced an incremental root that
    differs from a full recompute (such a stamp already failed closed)."""
    from tree_sitter_analyzer.cache import certification_tracking

    certification_tracking.clear_mismatches()
    yield
    mismatches = certification_tracking.mismatches()
    certification_tracking.clear_mismatches()
    assert mismatches == [], f"CERTIFICATION_TREE_MISMATCH: {mismatches}"
