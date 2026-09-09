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
    """The CI matrix must be bounded while leaving time for post-test cleanup."""
    workflow = PROJECT_ROOT / ".github" / "workflows" / "reusable-test.yml"
    text = workflow.read_text(encoding="utf-8")

    for job_name in ("test-matrix-pr", "test-matrix-full"):
        test_matrix = re.search(
            rf"(?ms)^  {job_name}:\n(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:|\Z)",
            text,
        )

        assert test_matrix is not None, job_name
        assert re.search(
            r"(?m)^    timeout-minutes:\s*20\s*$",
            test_matrix.group("body"),
        ), job_name


def test_pr_no_coverage_suite_has_runtime_headroom() -> None:
    """The 25k-test cross-platform step needs bounded runner-variance headroom."""
    workflow = PROJECT_ROOT / ".github" / "workflows" / "reusable-test.yml"
    text = workflow.read_text(encoding="utf-8")
    pr_matrix = re.search(
        r"(?ms)^  test-matrix-pr:\n(?P<body>.*?)(?=^  test-matrix-full:)",
        text,
    )

    assert pr_matrix is not None
    no_coverage = re.search(
        r"(?ms)^    - name: Run Tests \(no coverage\)\n"
        r"(?P<body>.*?)(?=^    - name:|\Z)",
        pr_matrix.group("body"),
    )
    assert no_coverage is not None
    assert re.search(
        r"(?m)^      timeout-minutes:\s*15\s*$",
        no_coverage.group("body"),
    )


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

    assert '-m "not slow and not e2e and not network and not benchmark"' in text
    assert (
        '-m "not slow and not e2e and not network and not benchmark and not full_language"'
        in text
    )


def test_slow_suite_runs_once_per_reusable_test_matrix() -> None:
    """Default exclusions need one explicit slow-test lane per profile."""
    workflow = PROJECT_ROOT / ".github" / "workflows" / "reusable-test.yml"
    text = workflow.read_text(encoding="utf-8")
    slow_marker = (
        '-m "slow and not network and not e2e and not benchmark and not full_language"'
    )

    assert text.count(slow_marker) == 2


def test_budget_retry_is_bounded_and_budget_only() -> None:
    """A retry may only follow a measured runner stall, never a real failure.

    The platform gate this test used to pin (RUNNER_OS != Windows) was removed
    deliberately: it decided *who got the mitigation*, not whether a functional
    failure could be retried. The fence is the classifier, which exits non-zero
    unless EVERY failure was a per-test wall-clock budget overrun. These
    assertions therefore pin the fence rather than the scope. Five of six budget
    overruns observed on 2026-08-19/20 were macOS, where the gate meant no
    mitigation ran at all.
    """
    workflow = PROJECT_ROOT / ".github" / "workflows" / "reusable-test.yml"
    lines = workflow.read_text(encoding="utf-8").splitlines()

    classifier = "scripts/classify_windows_pytest_failure.py"
    sites = [i for i, line in enumerate(lines) if classifier in line]
    assert len(sites) == 2

    # Each call is guarded, and a non-zero verdict aborts before any retry.
    for i in sites:
        assert lines[i].lstrip().startswith("if !")
        window = " ".join(lines[i : i + 4])
        assert 'exit "$test_status"' in window

    # The retry is scoped to the classifier node ids, never a blanket re-run.
    joined = " ".join(lines)
    assert joined.count('uv run pytest "${retry_nodeids[@]}" -n auto') == 2
    assert joined.count("retrying budget-only failures once") == 2

    # And it never runs on a green suite.
    assert joined.count('if [ "$test_status" -eq 0 ]; then') == 2


def test_default_gate_has_a_real_five_minute_ci_deadline() -> None:
    """The documented local quick-gate budget must be enforced in CI."""
    workflow = PROJECT_ROOT / ".github" / "workflows" / "reusable-test.yml"
    text = workflow.read_text(encoding="utf-8")

    assert text.count("- name: Run bounded default gate") == 2
    assert text.count("timeout-minutes: 5") == 2
    assert text.count("run: uv run pytest -q") == 2


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


def test_docs_check_fetches_history_for_contract_subjects() -> None:
    """Regression for PR #1255: docs contracts require a non-shallow clone."""
    ci_text = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    _, marker, remainder = ci_text.partition("\n  docs-check:\n")
    docs_job, next_marker, _ = remainder.partition("\n  quality-check:\n")

    assert marker == "\n  docs-check:\n"
    assert next_marker == "\n  quality-check:\n"
    checkout_start = docs_job.index("      - uses: actions/checkout@v7\n")
    checkout_end = docs_job.index("\n      - name:", checkout_start)
    checkout_step = docs_job[checkout_start:checkout_end]
    assert checkout_step.splitlines().count("          fetch-depth: 0") == 1


def test_dogfood_reads_complete_pr_diff_instead_of_output_files(tmp_path: Path) -> None:
    """PR 分析覆盖全部提交，且不把自己的报告当作源码变更。"""
    # 2026-09-08：#1418 的文档 PR 被报告为两个输出文件，真实提交完全遗漏。
    import shlex
    import subprocess

    import yaml

    from tree_sitter_analyzer.mcp.tools.utils.change_impact_git import (
        _get_changed_files,
    )

    workflow = yaml.safe_load(
        (PROJECT_ROOT / ".github/workflows/dogfood-pr-check.yml").read_text(
            encoding="utf-8"
        )
    )
    steps = workflow["jobs"]["claim-invariants"]["steps"]
    checkout = next(
        step for step in steps if "uses" in step and "checkout@" in step["uses"]
    )
    impact = next(step["run"] for step in steps if step.get("id") == "impact")
    command = next(
        line.strip() for line in impact.splitlines() if "uv run python -m" in line
    )
    argv = shlex.split(command.rstrip("\\").strip())[5:]
    args = create_argument_parser().parse_args(argv)
    source = tmp_path / "source"
    source.mkdir()

    def git(root: Path, *arguments: str) -> None:
        subprocess.run(["git", *arguments], cwd=root, check=True, capture_output=True)

    git(source, "init", "-b", "base")
    git(source, "config", "user.name", "TSA Test")
    git(source, "config", "user.email", "tsa@example.invalid")
    (source / "README.md").write_text("base\n", encoding="utf-8")
    git(source, "add", ".")
    git(source, "commit", "-m", "base")
    git(source, "checkout", "-b", "feature")
    for name in ("first.py", "second.py"):
        (source / name).write_text("value = 1\n", encoding="utf-8")
        git(source, "add", name)
        git(source, "commit", "-m", name)
    git(source, "checkout", "base")
    git(source, "merge", "--no-ff", "feature", "-m", "PR merge")
    checkout_root = tmp_path / "checkout"
    depth = str(checkout.get("with", {}).get("fetch-depth", 1))
    git(tmp_path, "clone", "--depth", depth, source.as_uri(), str(checkout_root))
    artifacts = checkout_root / "dogfood-artifacts"
    artifacts.mkdir()
    for suffix in ("json", "txt"):
        (artifacts / f"change-impact.{suffix}").write_text("", encoding="utf-8")
    assert _get_changed_files(args.change_impact_mode, str(checkout_root)) == [
        "first.py",
        "second.py",
    ]
    assert checkout["with"]["ref"] == "${{ github.sha }}"


def test_ci_routing_uses_merge_parent_when_event_base_is_stale(tmp_path: Path) -> None:
    """基线分支前进后，路由只看到 PR 自身的变更。"""
    # 2026-09-09：#1412 事件中的旧 base SHA 把 develop 后续代码误计入文档 PR。
    import shlex
    import subprocess

    import yaml

    workflow = yaml.safe_load(
        (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["route"]["steps"]
    detect = next(
        step["run"] for step in steps if step.get("name") == "Detect changed files"
    )
    command = next(
        line.strip() for line in detect.splitlines() if "git diff --name-only" in line
    )

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.strip()

    git("init", "-b", "base")
    git("config", "user.name", "TSA Test")
    git("config", "user.email", "tsa@example.invalid")
    (tmp_path / "README.md").write_text("base\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "base")
    old_base = git("rev-parse", "HEAD")
    git("checkout", "-b", "docs")
    (tmp_path / "proposal.md").write_text("proposal\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "proposal")
    git("checkout", "base")
    (tmp_path / "unrelated.py").write_text("value = 1\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "advance base")
    git("merge", "--no-ff", "docs", "-m", "PR merge")
    merge_sha = git("rev-parse", "HEAD")
    command = command.replace("${{ github.event.pull_request.base.sha }}", old_base)
    command = command.replace("${{ github.sha }}", merge_sha)
    argv = shlex.split(command)
    assert git(*argv[1 : argv.index(">")]).splitlines() == ["proposal.md"]
    assert steps[0]["with"]["ref"] == "${{ github.sha }}"


@pytest.mark.parametrize("force_full", [False, True])
@pytest.mark.parametrize("path", ["README.md", "tree_sitter_analyzer/formatters/x.py"])
def test_manual_full_validation_routes_real_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], force_full: bool, path: str
) -> None:
    """手动完整验证绕过文档跳过和子范围，同时保留普通路径路由。"""
    # 2026-09-09：CI 34340908809 的文档路由跳过了待补验的完整矩阵。
    import json

    from scripts.ci_route import main

    output = tmp_path / "outputs"
    args = [path, "--github-output", str(output)]
    if force_full:
        args.append("--force-full")
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    docs_only = path == "README.md" and not force_full
    assert result["run_docs_check"] is docs_only
    assert result["full_suite_required"] is force_full
    for key in ("run_quality", "run_test_matrix", "run_build", "upload_coverage"):
        assert result[key] is (not docs_only)
    assert result["regression_scope"] == (
        "format" if not force_full and not docs_only else "all"
    )
    if force_full:
        assert {
            key for key, value in result.items() if key.startswith("run_") and value
        } == {
            "run_quality",
            "run_test_matrix",
            "run_build",
            "run_e2e_smoke",
            "run_regression",
            "run_sql_platform_compat",
            "run_benchmarks",
            "run_grammar_coverage",
        }
        assert result["benchmark_scope"] == "all"
        assert "manual-full-validation" in result["reason_codes"]
    assert f"run_test_matrix={str(not docs_only).lower()}\n" in output.read_text(
        encoding="utf-8"
    )


def test_manual_validation_is_non_publishing_and_concurrency_isolated() -> None:
    """固定 SHA 的手动验证不被推送取消，且不调用发布工作流。"""
    # 2026-09-09：CI 34340202847 被同分支的后续文档推送取消。
    import yaml

    workflow = yaml.safe_load(
        (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    inputs = workflow[True]["workflow_dispatch"]["inputs"]
    assert inputs["full-validation"]["type"] == "boolean"
    assert inputs["full-validation"]["default"] is False
    assert workflow["concurrency"]["group"] == (
        "${{ github.workflow }}-${{ github.event_name == 'workflow_dispatch' "
        "&& format('manual-{0}', github.run_id) || github.ref }}"
    )
    jobs = workflow["jobs"]
    route = next(step for step in jobs["route"]["steps"] if step.get("id") == "route")
    assert route["env"]["FORCE_FULL"] == (
        "${{ github.event_name == 'workflow_dispatch' && inputs.full-validation "
        "&& 'true' || 'false' }}"
    )
    assert 'if [[ "$FORCE_FULL" == "true" ]]; then' in route["run"]
    assert "args+=(--force-full)" in route["run"]
    assert '"${args[@]}"' in route["run"]
    assert jobs["test"]["with"]["matrix-profile"] == (
        "${{ github.event_name == 'pull_request' && 'pr' || 'full' }}"
    )
    assert {job["uses"] for job in jobs.values() if "uses" in job} == {
        "./.github/workflows/reusable-quality.yml",
        "./.github/workflows/reusable-test.yml",
        "./.github/workflows/reusable-build.yml",
        "./.github/workflows/regression-tests.yml",
        "./.github/workflows/sql-platform-compat.yml",
    }
