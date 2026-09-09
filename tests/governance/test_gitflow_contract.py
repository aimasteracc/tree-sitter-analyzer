"""Contract tests split from the former agent workflow monolith."""
# ruff: noqa: F401

from __future__ import annotations

import ast
import configparser
import json
import os
import re
import subprocess
import sys
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


def test_release_registry_versions_match_package_version() -> None:
    """2026-09-09 发布审计：注册表不能继续指向旧 PyPI 版本。"""
    project = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    registry = json.loads((PROJECT_ROOT / "server.json").read_text(encoding="utf-8"))
    version = project["project"]["version"]
    assert registry["version"] == version
    assert [
        package["version"]
        for package in registry["packages"]
        if package["registryType"] == "pypi"
        and package["identifier"] == "tree-sitter-analyzer"
    ] == [version]


@pytest.fixture
def version_sync_project(tmp_path: Path) -> Path:
    """在隔离目录执行真实版本脚本，避免写入工作区。"""
    (tmp_path / "scripts").mkdir()
    for filename in ("sync_version.py", "sync_version_minimal.py"):
        (tmp_path / "scripts" / filename).write_bytes(
            (PROJECT_ROOT / "scripts" / filename).read_bytes()
        )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nversion = "1.29.5"\n[tool.mcp]\nserver_version = "1.29.5"\n',
        encoding="utf-8",
    )
    (tmp_path / "tree_sitter_analyzer").mkdir()
    (tmp_path / "tree_sitter_analyzer" / "__init__.py").write_text(
        '__version__ = "1.29.5"\n', encoding="utf-8"
    )
    (tmp_path / "server.json").write_text(
        json.dumps(
            {
                "version": "1.29.5",
                "description": "保留描述",
                "packages": [
                    {
                        "registryType": "pypi",
                        "identifier": "tree-sitter-analyzer",
                        "version": "1.29.5",
                        "transport": {"type": "stdio"},
                    },
                    {
                        "registryType": "npm",
                        "identifier": "other-tool",
                        "version": "0.1.0",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


@pytest.mark.parametrize("script", ["sync_version.py", "sync_version_minimal.py"])
@pytest.mark.parametrize("field", ["server", "package"])
def test_version_check_rejects_registry_drift_without_writing(
    version_sync_project: Path, script: str, field: str
) -> None:
    """2026-09-09 发布审计：任一注册表版本漂移都必须让检查失败。"""
    root = version_sync_project
    path = root / "server.json"
    metadata = json.loads(path.read_text(encoding="utf-8"))
    target = metadata if field == "server" else metadata["packages"][0]
    target["version"] = "1.29.0"
    path.write_text(json.dumps(metadata), encoding="utf-8")
    before = path.read_bytes()
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / script), "--check"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=15,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert path.read_bytes() == before


@pytest.mark.parametrize("script", ["sync_version.py", "sync_version_minimal.py"])
def test_version_sync_updates_only_owned_registry_versions(
    version_sync_project: Path, script: str
) -> None:
    """同步两个归属版本，保留其他包和元数据，再次同步不改字节。"""
    root = version_sync_project
    path = root / "server.json"
    expected = json.loads(path.read_text(encoding="utf-8"))
    stale = json.loads(path.read_text(encoding="utf-8"))
    stale["version"] = "1.29.0"
    stale["packages"][0]["version"] = "1.29.1"
    path.write_text(json.dumps(stale), encoding="utf-8")
    command = [sys.executable, str(root / "scripts" / script)]
    synchronized_bytes = None
    for args in (command, command + ["--check"], command):
        result = subprocess.run(
            args,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=15,
            encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(path.read_text(encoding="utf-8")) == expected
        if synchronized_bytes is None:
            synchronized_bytes = path.read_bytes()
        else:
            assert path.read_bytes() == synchronized_bytes
    assert (
        path.read_text(encoding="utf-8")
        == json.dumps(expected, indent=2, ensure_ascii=False) + "\n"
    )


@pytest.mark.parametrize("script", ["sync_version.py", "sync_version_minimal.py"])
def test_version_sync_rejects_missing_registry_package(
    version_sync_project: Path, script: str
) -> None:
    """缺失本项目包时同步失败，不能输出成功却留下不完整注册表。"""
    root = version_sync_project
    path = root / "server.json"
    metadata = json.loads(path.read_text(encoding="utf-8"))
    metadata["packages"] = metadata["packages"][1:]
    path.write_text(json.dumps(metadata), encoding="utf-8")
    before = path.read_bytes()
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / script)],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=15,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert path.read_bytes() == before


@pytest.mark.parametrize("sync_succeeds", [False, True])
def test_release_preparation_requires_synced_and_staged_registry(
    version_sync_project: Path, monkeypatch: pytest.MonkeyPatch, sync_succeeds: bool
) -> None:
    """2026-09-09 发布审计：同步失败停止准备；成功时提交注册表。"""
    from unittest.mock import Mock

    from scripts.gitflow_release_automation import GitFlowReleaseAutomation

    root = version_sync_project
    changelog = root / "CHANGELOG.md"
    changelog.write_text("# Changelog\n", encoding="utf-8")
    release = GitFlowReleaseAutomation("v1.29.5")
    release.project_root = root
    run_git = Mock(
        return_value=subprocess.CompletedProcess([], 0, stdout="", stderr="")
    )
    monkeypatch.setattr(release, "run_command", run_git)
    sync = Mock(
        return_value=subprocess.CompletedProcess([], 0),
        side_effect=None if sync_succeeds else subprocess.CalledProcessError(1, "sync"),
    )
    monkeypatch.setattr("scripts.gitflow_release_automation.subprocess.run", sync)
    assert release.create_release_branch() is sync_succeeds
    sync.assert_called_once_with(
        ["uv", "run", "python", "scripts/sync_version_minimal.py"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    commands = [call.args[0] for call in run_git.call_args_list]
    expected = [["git", "checkout", "-b", "release/v1.29.5"]]
    if sync_succeeds:
        expected.extend(
            [
                ["git", "add", "pyproject.toml", "server.json", "CHANGELOG.md"],
                ["git", "add", "tree_sitter_analyzer/"],
                ["git", "commit", "-m", "chore: Prepare release v1.29.5"],
            ]
        )
    else:
        assert changelog.read_text(encoding="utf-8") == "# Changelog\n"
    assert commands == expected


@pytest.mark.parametrize("check_only", [False, True])
@pytest.mark.parametrize("missing", ["package_file", "package_version", "mcp_version"])
def test_essential_version_sync_rejects_missing_version_fields(
    version_sync_project: Path, missing: str, check_only: bool
) -> None:
    """必需文件或版本字段缺失时，同步和检查都不能报告成功。"""
    root = version_sync_project
    package = root / "tree_sitter_analyzer" / "__init__.py"
    if missing == "package_file":
        package.unlink()
    elif missing == "package_version":
        package.write_text("", encoding="utf-8")
    else:
        (root / "pyproject.toml").write_text(
            '[project]\nversion = "1.29.5"\n[tool.mcp]\n', encoding="utf-8"
        )
    command = [sys.executable, str(root / "scripts" / "sync_version_minimal.py")]
    if check_only:
        command.append("--check")
    result = subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        timeout=15,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode == 1, result.stdout + result.stderr


def test_essential_version_sync_propagates_package_write_failure(
    version_sync_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """包版本写入失败必须向发布调用方传播，不能被当作无需同步。"""
    from scripts.sync_version_minimal import check_versions

    root = version_sync_project
    package = root / "tree_sitter_analyzer" / "__init__.py"
    package.write_text('__version__ = "1.29.0"\n', encoding="utf-8")
    before = package.read_bytes()
    monkeypatch.chdir(root)
    write_text = Path.write_text

    def deny_package_write(path: Path, *args: object, **kwargs: object) -> int:
        if path.name == "__init__.py":
            raise PermissionError("package write denied")
        return write_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", deny_package_write)
    with pytest.raises(OSError, match="Failed to write.*package write denied"):
        check_versions()
    assert package.read_bytes() == before
