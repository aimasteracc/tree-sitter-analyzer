"""Diagnostic checks for TSA installation health (--doctor)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Literal


@dataclass
class CheckResult:
    name: str
    status: Literal["PASS", "WARN", "FAIL"]
    message: str


MINIMUM_UV_VERSION = (0, 11, 0)


def _check_uv() -> CheckResult:
    path = shutil.which("uv")
    if not path:
        return CheckResult(
            "uv", "FAIL", "not found — install from https://docs.astral.sh/uv/"
        )

    try:
        completed = subprocess.run(  # noqa: S603 - resolved executable, fixed argument
            [path, "--version"],
            capture_output=True,
            check=False,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        return CheckResult("uv", "FAIL", f"timed out running {path} --version")
    except OSError as exc:
        return CheckResult("uv", "FAIL", f"cannot run {path}: {exc}")

    try:
        stdout = (
            completed.stdout.decode("utf-8", errors="strict")
            if isinstance(completed.stdout, bytes)
            else completed.stdout
        )
    except UnicodeDecodeError:
        return CheckResult(
            "uv", "FAIL", f"undecodable version output from {path} --version"
        )

    match = re.fullmatch(r"uv (\d+)\.(\d+)\.(\d+)(?:[ \t]+.*)?", stdout.rstrip("\n"))
    if completed.returncode != 0 or match is None:
        return CheckResult(
            "uv",
            "FAIL",
            f"cannot determine version at {path} — required uv >= 0.11.0",
        )

    try:
        version = tuple(int(part) for part in match.groups())
    except ValueError:
        return CheckResult(
            "uv",
            "FAIL",
            f"cannot determine version at {path} — required uv >= 0.11.0",
        )
    if version < MINIMUM_UV_VERSION:
        version_text = ".".join(str(part) for part in version)
        return CheckResult(
            "uv",
            "FAIL",
            f"{version_text} at {path} is too old — required uv >= 0.11.0; "
            "rerun install.sh or update uv manually",
        )
    return CheckResult("uv", "PASS", f"{path} ({'.'.join(match.groups())})")


def _check_uvx() -> CheckResult:
    path = shutil.which("uvx")
    if path:
        return CheckResult("uvx", "PASS", path)
    return CheckResult(
        "uvx",
        "WARN",
        "uvx is installed with uv; if uvx is missing, reinstall uv",
    )


def _check_fd() -> CheckResult:
    path = shutil.which("fd")
    if path:
        return CheckResult("fd", "PASS", path)
    return CheckResult(
        "fd",
        "WARN",
        "not found — required for text search (brew install fd / apt install fd-find)",
    )


def _check_rg() -> CheckResult:
    path = shutil.which("rg")
    if path:
        return CheckResult("rg (ripgrep)", "PASS", path)
    return CheckResult(
        "rg (ripgrep)",
        "WARN",
        "not found — required for text search (brew install ripgrep / apt install ripgrep)",
    )


def _check_project_root() -> CheckResult:
    value = os.environ.get("TREE_SITTER_PROJECT_ROOT")
    if not value:
        return CheckResult(
            "TREE_SITTER_PROJECT_ROOT",
            "FAIL",
            "env var is not set — set it to the absolute path of your project",
        )
    if not os.path.isabs(value):
        return CheckResult(
            "TREE_SITTER_PROJECT_ROOT",
            "FAIL",
            f"value is a relative path: {value!r} — use an absolute path (e.g. $(pwd))",
        )
    if not os.path.isdir(value):
        return CheckResult(
            "TREE_SITTER_PROJECT_ROOT",
            "FAIL",
            f"directory does not exist: {value}",
        )
    return CheckResult("TREE_SITTER_PROJECT_ROOT", "PASS", value)


def _agent_config_paths() -> list[tuple[str, str]]:
    """Return (agent_label, expanded_path) pairs to check."""
    home = os.path.expanduser("~")
    cwd = os.getcwd()
    is_macos = sys.platform == "darwin"

    paths = []
    if is_macos:
        paths.append(
            (
                "Claude Desktop (macOS)",
                os.path.join(
                    home,
                    "Library",
                    "Application Support",
                    "Claude",
                    "claude_desktop_config.json",
                ),
            )
        )
    else:
        paths.append(
            (
                "Claude Desktop (Linux)",
                os.path.join(home, ".config", "claude", "claude_desktop_config.json"),
            )
        )

    paths.append(("Claude Code (global)", os.path.join(home, ".claude", ".mcp.json")))
    paths.append(
        ("Claude Code (project-local)", os.path.join(cwd, ".claude", ".mcp.json"))
    )
    paths.append(("Cursor", os.path.join(home, ".cursor", "mcp.json")))

    if is_macos:
        paths.append(
            (
                "VS Code (macOS)",
                os.path.join(
                    home, "Library", "Application Support", "Code", "User", "mcp.json"
                ),
            )
        )
    else:
        paths.append(
            (
                "VS Code (Linux)",
                os.path.join(home, ".config", "Code", "User", "mcp.json"),
            )
        )

    return paths


def _check_agent_configs() -> list[CheckResult]:
    results = []
    for label, path in _agent_config_paths():
        name = f"agent config: {label}"
        if not os.path.isfile(path):
            results.append(CheckResult(name, "WARN", f"not found: {path}"))
            continue

        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (ValueError, RecursionError):
            results.append(
                CheckResult(name, "WARN", f"cannot read {path}: invalid JSON content")
            )
            continue
        except OSError as exc:
            results.append(CheckResult(name, "WARN", f"cannot read {path}: {exc}"))
            continue

        if not isinstance(data, dict):
            results.append(
                CheckResult(name, "WARN", f"config root must be a JSON object: {path}")
            )
            continue

        mcp_servers = data.get("mcpServers", {})
        if not isinstance(mcp_servers, dict):
            results.append(
                CheckResult(name, "WARN", f"mcpServers must be a JSON object: {path}")
            )
            continue

        tsa_entry = mcp_servers.get("tree-sitter-analyzer")
        if tsa_entry is None:
            results.append(
                CheckResult(
                    name,
                    "WARN",
                    f"MCP entry 'tree-sitter-analyzer' not found in {path}",
                )
            )
            continue
        if not isinstance(tsa_entry, dict):
            results.append(
                CheckResult(
                    name,
                    "WARN",
                    f"MCP entry 'tree-sitter-analyzer' must be a JSON object: {path}",
                )
            )
            continue

        env = tsa_entry.get("env", {})
        if not isinstance(env, dict):
            results.append(
                CheckResult(
                    name,
                    "WARN",
                    f"MCP entry 'tree-sitter-analyzer'.env must be a JSON object: {path}",
                )
            )
            continue
        root = env.get("TREE_SITTER_PROJECT_ROOT", "")
        if not isinstance(root, str):
            results.append(
                CheckResult(
                    name,
                    "WARN",
                    "TREE_SITTER_PROJECT_ROOT must be a string "
                    f"in MCP entry 'tree-sitter-analyzer': {path}",
                )
            )
            continue
        if root and not os.path.isabs(root):
            results.append(
                CheckResult(
                    name,
                    "WARN",
                    f"TREE_SITTER_PROJECT_ROOT is a relative path {root!r} in {path}",
                )
            )
        else:
            results.append(CheckResult(name, "PASS", path))

    return results


def run_doctor(json_output: bool = False) -> int:
    """Run all diagnostic checks and print results.

    Returns 0 if no FAIL checks, 1 otherwise.
    """
    results: list[CheckResult] = [
        _check_uv(),
        _check_uvx(),
        _check_fd(),
        _check_rg(),
        _check_project_root(),
        *_check_agent_configs(),
    ]

    fail_count = sum(1 for r in results if r.status == "FAIL")
    warn_count = sum(1 for r in results if r.status == "WARN")
    pass_count = sum(1 for r in results if r.status == "PASS")

    if json_output:
        output = {
            "checks": [
                {"name": r.name, "status": r.status, "message": r.message}
                for r in results
            ],
            "summary": {"pass": pass_count, "warn": warn_count, "fail": fail_count},
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        icons = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}  # nosec B105
        for r in results:
            print(f"{r.status} {icons[r.status]} {r.name}: {r.message}")
        print()
        print(f"Summary: {pass_count} PASS, {warn_count} WARN, {fail_count} FAIL")

    return 0 if fail_count == 0 else 1
