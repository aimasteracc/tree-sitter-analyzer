"""Contract tests split from the former agent workflow monolith."""
# ruff: noqa: F401

from __future__ import annotations

import ast
import configparser
import os
import re
import shlex
from pathlib import Path

import pytest

try:
    import tomllib  # Python 3.11+ stdlib
except ImportError:  # Python 3.10 — fall back to the tomli back-port
    import tomli as tomllib
from hypothesis import settings as hypothesis_settings

from tree_sitter_analyzer.cli_main import create_argument_parser
from tree_sitter_analyzer.mcp.server import _create_tool_registry

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QUICK_TESTPATHS = (
    "tests/contracts",
    "tests/governance",
    "tests/unit/test_ast_cache.py",
    "tests/unit/test_call_graph_cached.py",
    "tests/unit/test_change_impact_analysis.py",
    "tests/unit/test_codegraph_context_tool.py",
    "tests/unit/test_codegraph_pr_review_tool.py",
    "tests/unit/test_constraint_dsl.py",
    "tests/unit/test_knowledge_graph.py",
    "tests/unit/test_symbol_resolver.py",
    "tests/unit/test_tool_registry.py",
    "tests/unit/test_xref.py",
    "tests/unit/cli/test_codegraph_index_commands.py",
    "tests/unit/cli/test_doctor_command.py",
    "tests/unit/cli/test_mcp_commands.py",
    "tests/unit/core/test_engine.py",
    "tests/unit/core/test_language_detector.py",
    "tests/unit/core/test_parser.py",
    "tests/unit/languages/test_plugin_base_contract.py",
    "tests/unit/languages/test_queries_module_contract.py",
    "tests/unit/mcp/test_base_mcp_tool_contract.py",
    "tests/unit/mcp/test_facade_envelope_contract.py",
    "tests/unit/security/test_validator.py",
)
COMPREHENSIVE_COMMAND = (
    'uv run pytest tests/ -q --timeout=120 '
    '-m "not e2e and not network and not benchmark"'
)
SKIPPED_SCAN_DIRS = {
    ".git",
    ".benchmark-repos",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".uv-cache",
    ".venv",
}


def test_default_pytest_runtime_contract_is_locked() -> None:
    """The default quick gate must stay parallel and bounded under 5 minutes."""
    config = configparser.ConfigParser()
    config.read(PROJECT_ROOT / "pytest.ini")
    testpaths = tuple(
        line.strip()
        for line in config["pytest"]["testpaths"].splitlines()
        if line.strip()
    )

    assert testpaths == DEFAULT_QUICK_TESTPATHS
    _assert_pytest_runtime_contract(
        config["pytest"]["addopts"],
        config["pytest"]["filterwarnings"],
    )


def test_pyproject_does_not_define_pytest_ini_options() -> None:
    """pytest.ini is the single source of truth for pytest runtime config."""
    data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert "pytest" not in data.get("tool", {})


def test_uv_version_is_new_enough_for_committed_lockfile() -> None:
    """Old uv releases silently rewrite modern lockfiles before pytest starts."""
    data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert data["tool"]["uv"]["required-version"] == ">=0.11.0"


def test_comprehensive_command_overrides_quick_marker_exclusions() -> None:
    """Explicit tests/ discovery alone must not inherit the quick marker tier."""
    docs = (
        "AGENTS.md",
        "README.md",
        "docs/TESTING.md",
        "docs/agent-tooling-gap-report.md",
        "docs/developer_guide.md",
    )

    for relative_path in docs:
        text = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert COMPREHENSIVE_COMMAND in text, relative_path


def _assert_pytest_runtime_contract(
    addopts: str | list[str],
    warning_filters: str | list[str],
) -> None:
    if isinstance(addopts, str):
        addopts_list = shlex.split(addopts)
    else:
        addopts_list = addopts
    if isinstance(warning_filters, str):
        warning_filter_list = [
            line.strip() for line in warning_filters.splitlines() if line.strip()
        ]
    else:
        warning_filter_list = warning_filters
    required = {
        "--numprocesses=4",
        "--dist=worksteal",
        "--timeout=30",
        "--session-timeout=900",
        "--benchmark-disable",
    }

    missing = [option for option in sorted(required) if option not in addopts_list]
    assert missing == []
    marker_index = addopts_list.index("-m")
    assert (
        addopts_list[marker_index + 1]
        == "not e2e and not slow and not network and not full_language and not benchmark"
    )
    assert warning_filter_list[0] == "error"
    assert "ignore::DeprecationWarning" not in warning_filter_list
    assert "ignore::PendingDeprecationWarning" not in warning_filter_list


def test_pytest_runtime_dependencies_are_declared() -> None:
    """The runtime contract depends on xdist and timeout being installed."""
    data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependency_groups = data["dependency-groups"]
    dev_dependencies = set(dependency_groups["dev"])

    assert "pytest-xdist>=3.8.0" in dev_dependencies
    assert "pytest-timeout>=2.4.0" in dev_dependencies


def test_pytest_runtime_declares_quarantine_marker() -> None:
    """Quarantined tests must be declared so strict-markers accepts them."""
    config = configparser.ConfigParser()
    config.read(PROJECT_ROOT / "pytest.ini")

    assert (
        "quarantine: mark test as known unstable; reruns disabled"
        in config["pytest"]["markers"]
    )


def test_local_runtime_artifacts_are_gitignored_without_global_results_trap() -> None:
    """Dogfood/cache output must stay local without hiding every results dir."""
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    lines = {
        line.strip()
        for line in gitignore.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert ".ast-cache/" in lines
    assert "**/.ast-cache/" in lines
    assert ".omm/" in lines
    assert "ruvector.db" in lines
    assert "/results/" in lines
    assert "results/" not in lines
    assert "benchmarks/codegraph_compare/results/*" in lines
    assert "!benchmarks/codegraph_compare/results/.gitkeep" in lines


def test_cli_fixtures_do_not_create_collectable_python_inside_tests_tree() -> None:
    """Runtime CLI inputs must not become tests after an interrupted worker."""
    source = (
        PROJECT_ROOT / "tests/integration/cli/test_cli_async.py"
    ).read_text(encoding="utf-8")

    assert 'Path("tests") / "temp_cli_test"' not in source
    assert 'Path("tests") / "temp_cli_test_large"' not in source


def test_cli_subprocess_integration_suite_is_outside_default_gate() -> None:
    """The 19-process CLI suite belongs to the explicit slow lane."""
    source = (
        PROJECT_ROOT / "tests/integration/cli/test_cli_async.py"
    ).read_text(encoding="utf-8")

    assert "pytestmark = pytest.mark.slow" in source


def test_imported_test_mixins_are_not_collected_as_concrete_tests() -> None:
    """Imported Test* mixins need private aliases to avoid duplicate collection."""
    violations: list[str] = []
    paths = (
        PROJECT_ROOT / "tests/unit/cli/test_cli_main_module.py",
        PROJECT_ROOT / "tests/unit/formatters/test_html_formatter_basic.py",
        PROJECT_ROOT / "tests/unit/mcp/test_query_tool.py",
    )
    for path in paths:
        module = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(module):
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.module is None or "mixin" not in node.module:
                continue
            for alias in node.names:
                if alias.name.startswith("Test") and not (
                    alias.asname and alias.asname.startswith("_")
                ):
                    violations.append(f"{path.relative_to(PROJECT_ROOT)}:{alias.name}")

    assert violations == []


def test_hypothesis_deadlines_are_disabled_for_parallel_suite_stability() -> None:
    """xdist load variance is bounded by pytest-timeout, not Hypothesis deadlines."""
    assert hypothesis_settings.default.deadline is None


def test_default_sustained_load_check_stays_fast_and_configurable() -> None:
    """Default performance checks use short configurable waits."""
    path = PROJECT_ROOT / "tests/integration/test_phase7_performance_integration.py"
    module = ast.parse(path.read_text(encoding="utf-8"))
    constants = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in module.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id.startswith("DEFAULT_")
    }

    assert constants["DEFAULT_SUSTAINED_LOAD_ITERATIONS"] <= 20
    assert constants["DEFAULT_SUSTAINED_LOAD_INTERVAL_SECONDS"] <= 0.1
    assert constants["DEFAULT_SCALABILITY_RECOVERY_SECONDS"] <= 0.1
    assert constants["DEFAULT_RESOURCE_CLEANUP_SETTLE_SECONDS"] <= 0.1
    assert constants["DEFAULT_MEMORY_EFFICIENCY_FILES"] <= 10

    source = path.read_text(encoding="utf-8")
    assert "TSA_SUSTAINED_LOAD_ITERATIONS" in source
    assert "TSA_SUSTAINED_LOAD_INTERVAL_SECONDS" in source
    assert "TSA_SCALABILITY_RECOVERY_SECONDS" in source
    assert "TSA_RESOURCE_CLEANUP_SETTLE_SECONDS" in source
    assert "TSA_MEMORY_EFFICIENCY_FILES" in source
    assert "while time.time() - start_time" not in source
    assert "asyncio.sleep(1)" not in source


def test_phase7_suite_simulated_work_stays_fast_and_configurable() -> None:
    """Summary-style integration checks should not spend seconds sleeping."""
    path = PROJECT_ROOT / "tests/integration/test_phase7_integration_suite.py"
    module = ast.parse(path.read_text(encoding="utf-8"))
    constants = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in module.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    }

    assert constants["DEFAULT_PHASE7_SUITE_SIMULATION_SECONDS"] <= 0.05

    source = path.read_text(encoding="utf-8")
    assert "TSA_PHASE7_SUITE_SIMULATION_SECONDS" in source
    assert "asyncio.sleep(0.2)" not in source
    assert "asyncio.sleep(0.15)" not in source
    assert "asyncio.sleep(0.1)" not in source
