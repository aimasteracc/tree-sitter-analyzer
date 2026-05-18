"""Project-aware verification command selection for agent workflows."""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DefaultTestCommand:
    """Default test command detected for a project root."""

    runner: str
    command: str


PYTEST_DEFAULT_COMMAND = "uv run pytest -q"
PYTEST_COMMAND = DefaultTestCommand("pytest", PYTEST_DEFAULT_COMMAND)


def detect_default_test_command(project_root: str | Path | None) -> DefaultTestCommand:
    """Detect a directly runnable default test command for a project root."""
    root = Path(project_root or ".")

    package_json = root / "package.json"
    if package_json.exists() and _package_json_has_test_script(package_json):
        return _node_test_command(root)

    if (root / "go.mod").exists():
        return DefaultTestCommand("go", "go test ./...")

    if (root / "Cargo.toml").exists():
        return DefaultTestCommand("cargo", "cargo test")

    if (root / "gradlew").exists():
        return DefaultTestCommand("gradle", "./gradlew test")

    if (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
        return DefaultTestCommand("gradle", "gradle test")

    if (root / "mvnw").exists():
        return DefaultTestCommand("maven", "./mvnw test")

    if (root / "pom.xml").exists():
        return DefaultTestCommand("maven", "mvn test")

    return PYTEST_COMMAND


def build_test_command(
    default_command: DefaultTestCommand,
    tests_to_run: list[str],
) -> str:
    """Build a verification command, using targeted tests when the runner supports it."""
    if not tests_to_run:
        return default_command.command

    quoted_tests = shlex.join(tests_to_run)
    if default_command.runner == "pytest":
        return f"uv run pytest {quoted_tests} -q"
    if default_command.runner in {"npm", "pnpm"}:
        return f"{default_command.runner} test -- {quoted_tests}"
    if default_command.runner == "yarn":
        return f"yarn test {quoted_tests}"
    if default_command.runner == "bun":
        return f"bun test {quoted_tests}"
    return default_command.command


def _package_json_has_test_script(package_json: Path) -> bool:
    """Return True when package.json has a non-empty scripts.test entry."""
    try:
        data: Any = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return False
    scripts = data.get("scripts")
    return isinstance(scripts, dict) and bool(scripts.get("test"))


def _node_test_command(root: Path) -> DefaultTestCommand:
    """Choose the local Node package manager's test command."""
    if (root / "bun.lockb").exists() or (root / "bun.lock").exists():
        return DefaultTestCommand("bun", "bun test")
    if (root / "pnpm-lock.yaml").exists():
        return DefaultTestCommand("pnpm", "pnpm test")
    if (root / "yarn.lock").exists():
        return DefaultTestCommand("yarn", "yarn test")
    return DefaultTestCommand("npm", "npm test")
