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

def test_reusable_test_workflow_has_job_timeout() -> None:
    """The CI matrix must fail fast instead of hanging forever on runner stalls."""
    workflow = PROJECT_ROOT / ".github" / "workflows" / "reusable-test.yml"
    text = workflow.read_text(encoding="utf-8")

    for job_name in ("test-matrix-pr", "test-matrix-full"):
        test_matrix = re.search(
            rf"(?ms)^  {job_name}:\n(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:|\Z)",
            text,
        )

        assert test_matrix is not None, job_name
        assert re.search(
            r"(?m)^    timeout-minutes:\s*15\s*$",
            test_matrix.group("body"),
        ), job_name


def test_pr_ci_uses_fast_matrix_while_release_keeps_full_matrix() -> None:
    """PRs should get fast feedback; release/hotfix keep exhaustive validation."""
    reusable_text = (
        PROJECT_ROOT / ".github" / "workflows" / "reusable-test.yml"
    ).read_text(encoding="utf-8")
    ci_text = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    release_text = (
        PROJECT_ROOT / ".github" / "workflows" / "release-automation.yml"
    ).read_text(encoding="utf-8")
    hotfix_text = (
        PROJECT_ROOT / ".github" / "workflows" / "hotfix-automation.yml"
    ).read_text(encoding="utf-8")

    assert "matrix-profile:" in reusable_text
    assert "test-matrix-pr:" in reusable_text
    assert "test-matrix-full:" in reusable_text
    assert "if: inputs.matrix-profile == 'pr'" in reusable_text
    assert "if: inputs.matrix-profile == 'full'" in reusable_text

    pr_matrix = re.search(
        r"(?ms)^  test-matrix-pr:\n(?P<body>.*?)(?=^  test-matrix-full:)",
        reusable_text,
    )
    assert pr_matrix is not None
    pr_body = pr_matrix.group("body")
    assert pr_body.count("python-version:") == 4
    assert 'python-version: "3.10"' not in pr_body
    assert 'python-version: "3.12"' not in pr_body
    assert 'python-version: "3.13"' in pr_body
    assert "windows-latest" in pr_body
    assert "macos-latest" in pr_body

    assert "github.event_name == 'pull_request' && 'pr' || 'full'" in ci_text
    assert 'matrix-profile: "full"' in release_text
    assert 'matrix-profile: "full"' in hotfix_text


def test_ci_full_language_suite_runs_once_per_reusable_test_matrix() -> None:
    """Exhaustive language golden tests must not run on every OS/Python axis."""
    workflow = PROJECT_ROOT / ".github" / "workflows" / "reusable-test.yml"
    text = workflow.read_text(encoding="utf-8")

    assert (
        '-m "not requires_ripgrep and not requires_fd and not slow and not e2e"' in text
    )
    assert (
        '-m "not requires_ripgrep and not requires_fd and not slow and not e2e and not full_language"'
        in text
    )


def test_standalone_coverage_workflow_is_manual_only() -> None:
    """Avoid duplicate full coverage runs; reusable-test owns PR/push coverage."""
    workflow = PROJECT_ROOT / ".github" / "workflows" / "test-coverage.yml"
    text = workflow.read_text(encoding="utf-8")

    on_block = re.search(r"(?ms)^on:\n(?P<body>.*?)(?=^env:|\Z)", text)
    assert on_block is not None
    body = on_block.group("body")

    assert "workflow_dispatch:" in body
    assert re.search(r"(?m)^  pull_request:", body) is None
    assert re.search(r"(?m)^  push:", body) is None


def test_all_language_golden_tests_are_tier_marked() -> None:
    """All-language suites need an explicit marker so CI can tier them."""
    marker = "pytestmark = pytest.mark.full_language"
    paths = [
        PROJECT_ROOT / "tests" / "golden" / "test_golden_corpus.py",
        PROJECT_ROOT / "tests" / "regression" / "test_plugin_golden_masters.py",
    ]

    for path in paths:
        assert marker in path.read_text(encoding="utf-8"), path


def test_agent_docs_lock_ci_test_tier_contract() -> None:
    """Agents should preserve the CI split between focused and exhaustive gates."""
    agents_text = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "CI Test Tier Contract" in agents_text
    assert "full_language" in agents_text
    assert "reusable-test.yml" in agents_text
    assert "test-coverage.yml" in agents_text
    assert "manual-only" in agents_text
    assert "matrix-profile: pr" in agents_text
    assert "matrix-profile: full" in agents_text


def test_ci_route_job_controls_expensive_optional_jobs() -> None:
    """Main CI should route slow optional jobs instead of always running them."""
    ci_text = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert "route:" in ci_text
    assert "python3 scripts/ci_route.py" in ci_text
    assert "run_e2e_smoke" in ci_text
    assert "run_regression" in ci_text
    assert "run_sql_platform_compat" in ci_text
    assert "check_optional" in ci_text


def test_expensive_workflows_are_not_direct_pr_push_duplicates() -> None:
    """Regression and SQL compatibility run through CI routing, not twice."""
    for workflow_name in ("regression-tests.yml", "sql-platform-compat.yml"):
        text = (PROJECT_ROOT / ".github" / "workflows" / workflow_name).read_text(
            encoding="utf-8"
        )
        on_block = re.search(r"(?ms)^on:\n(?P<body>.*?)(?=^env:|^jobs:|\Z)", text)
        assert on_block is not None
        body = on_block.group("body")

        assert "workflow_call:" in body, workflow_name
        assert re.search(r"(?m)^  pull_request:", body) is None, workflow_name
        assert re.search(r"(?m)^  push:", body) is None, workflow_name


def test_benchmarks_are_path_filtered_for_pr_and_push() -> None:
    """Benchmarks should not run for unrelated PRs."""
    text = (PROJECT_ROOT / ".github" / "workflows" / "benchmarks.yml").read_text(
        encoding="utf-8"
    )

    assert "paths:" in text
    assert "tests/benchmarks/**" in text
    assert "tree_sitter_analyzer/ast_cache.py" in text


def test_bandit_security_scan_is_blocking_and_configured() -> None:
    """The reusable quality workflow must not paper over Bandit failures."""
    text = (PROJECT_ROOT / ".github" / "workflows" / "reusable-quality.yml").read_text(
        encoding="utf-8"
    )
    security_job = re.search(
        r"(?ms)^  security:\n(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:|\Z)",
        text,
    )

    assert security_job is not None
    body = security_job.group("body")

    assert "continue-on-error" not in body
    assert "bandit -c pyproject.toml -r tree_sitter_analyzer/" in body
    assert "|| true" not in body
    assert 'exit "$BANDIT_STATUS"' in body
