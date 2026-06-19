"""Contract tests split from the former agent workflow monolith."""
# ruff: noqa: F401

from __future__ import annotations

import ast
import configparser
import os
import re
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
    """The default full suite must stay parallel and bounded under 5 minutes."""
    config = configparser.ConfigParser()
    config.read(PROJECT_ROOT / "pytest.ini")
    _assert_pytest_runtime_contract(
        config["pytest"]["addopts"],
        config["pytest"]["filterwarnings"],
    )


def test_pyproject_does_not_define_pytest_ini_options() -> None:
    """pytest.ini is the single source of truth for pytest runtime config."""
    data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert "pytest" not in data.get("tool", {})


def _assert_pytest_runtime_contract(
    addopts: str | list[str],
    warning_filters: str | list[str],
) -> None:
    if isinstance(addopts, str):
        addopts_list = addopts.split()
    else:
        addopts_list = addopts
    if isinstance(warning_filters, str):
        warning_filter_list = [
            line.strip() for line in warning_filters.splitlines() if line.strip()
        ]
    else:
        warning_filter_list = warning_filters
    required = {
        "--numprocesses=auto",
        "--dist=loadfile",
        "--timeout=180",
        # 600s ceiling: the suite passes in ~5 min on CI but the
        # old 300s budget left zero headroom and caused intermittent
        # session-timeout kills on slower runners.
        "--session-timeout=600",
        "--benchmark-disable",
    }

    missing = [option for option in sorted(required) if option not in addopts_list]
    assert missing == []
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
