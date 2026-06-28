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


def test_gitflow_documentation_is_present() -> None:
    """The GitFlow mandate must remain documented + machine-enforced.

    Three artifacts are required so the rule survives both casual edits
    and CI bypass attempts:
      1. ``GITFLOW.md`` at repo root — the source of truth.
      2. ``AGENTS.md`` references it from the "GitFlow Branching Mandate"
         section so any agent reading AGENTS.md sees the rule.
      3. ``.github/workflows/gitflow-guard.yml`` enforces head→base
         naming on every PR — the CI safety net.

    If you intentionally restructure how GitFlow is documented, update
    this test in the same commit and explain why in the PR description.
    """
    gitflow_md = PROJECT_ROOT / "GITFLOW.md"
    agents_md = PROJECT_ROOT / "AGENTS.md"
    guard_yml = PROJECT_ROOT / ".github" / "workflows" / "gitflow-guard.yml"

    assert gitflow_md.exists(), "GITFLOW.md must exist at repo root"
    assert agents_md.exists(), "AGENTS.md must exist at repo root"
    assert guard_yml.exists(), (
        ".github/workflows/gitflow-guard.yml must exist — the CI "
        "enforcement layer for the GitFlow branching mandate"
    )

    agents_text = agents_md.read_text(encoding="utf-8")
    assert "GitFlow Branching Mandate" in agents_text, (
        "AGENTS.md must contain a 'GitFlow Branching Mandate' section "
        "linking to GITFLOW.md"
    )
    assert "GITFLOW.md" in agents_text, (
        "AGENTS.md's GitFlow section must link to GITFLOW.md by name"
    )

    guard_text = guard_yml.read_text(encoding="utf-8")
    # The guard must check both main and develop as protected bases,
    # otherwise an agent could open a stray PR against either branch.
    for required_check in ("main", "develop", "release/v", "hotfix/"):
        assert required_check in guard_text, (
            f"gitflow-guard.yml must reference {required_check!r} in its "
            "validation logic — see AGENTS.md 'GitFlow Branching Mandate'"
        )


def test_gitflow_guard_does_not_allow_bot_prs_to_main() -> None:
    """Bot branch shortcuts must not bypass the protected main release flow."""
    guard_text = (
        PROJECT_ROOT / ".github" / "workflows" / "gitflow-guard.yml"
    ).read_text(encoding="utf-8")
    bot_case = re.search(
        r"(?ms)dependabot/\*\|renovate/\*\|github-actions/\*\).*?;;",
        guard_text,
    )

    assert bot_case is not None
    body = bot_case.group(0)
    assert '[ "${BASE}" = "main" ]' in body
    assert "Bot PRs to main MUST come from release/v* or hotfix/*" in body
    assert "exit 0" in body


def test_release_and_hotfix_prs_use_gitflow_branch_heads() -> None:
    """Release/hotfix automation must open main PRs from GitFlow branches."""
    release_text = (
        PROJECT_ROOT / ".github" / "workflows" / "release-automation.yml"
    ).read_text(encoding="utf-8")
    hotfix_text = (
        PROJECT_ROOT / ".github" / "workflows" / "hotfix-automation.yml"
    ).read_text(encoding="utf-8")

    for workflow_name, text, trigger in (
        ("release-automation.yml", release_text, "release/v*"),
        ("hotfix-automation.yml", hotfix_text, "hotfix/*"),
    ):
        assert trigger in text, workflow_name
        assert "--base main" in text, workflow_name
        assert '--head "${GITHUB_REF_NAME}"' in text, workflow_name

    assert "release-to-main" not in release_text
    assert "hotfix-to-main" not in hotfix_text


def test_release_and_hotfix_finalize_prs_do_not_mask_closed_prs() -> None:
    """A closed, unmerged finalize PR means the release/hotfix is not landed."""
    workflows = {
        "release-automation.yml": PROJECT_ROOT
        / ".github"
        / "workflows"
        / "release-automation.yml",
        "hotfix-automation.yml": PROJECT_ROOT
        / ".github"
        / "workflows"
        / "hotfix-automation.yml",
    }

    for workflow_name, workflow_path in workflows.items():
        text = workflow_path.read_text(encoding="utf-8")
        create_pr = re.search(
            r"(?ms)^      - name: Create Pull Request to main\n(?P<body>.*?)(?=^      - name:|\Z)",
            text,
        )

        assert create_pr is not None, workflow_name
        body = create_pr.group("body")
        assert "--state all" in body, workflow_name
        assert "closed without merge" in body, workflow_name
        assert "refusing to treat finalization as successful" in body, workflow_name
        assert "exit 1" in body, workflow_name
        assert "|| gh pr view" not in body, workflow_name
