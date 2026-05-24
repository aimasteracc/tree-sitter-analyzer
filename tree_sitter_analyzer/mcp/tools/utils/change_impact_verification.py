"""Verification-plan builders for change-impact analysis."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .verification_command import (
    PYTEST_COMMAND,
    DefaultTestCommand,
    build_test_command,
)

AUTO_DISCOVER_TEST_HINT = "(auto-discover: run full suite)"
DOCS_ONLY_TEST_HINT = "(docs-only: run git diff --check)"


def _build_pytest_command(tests_to_run: list[str]) -> str:
    """Build a copy-pasteable fast validation command."""
    return build_test_command(PYTEST_COMMAND, tests_to_run)


def _requires_pytest(changed_files: list[str]) -> bool:
    """Return False for changes that cannot affect executable behavior."""
    if not changed_files:
        return False
    return any(not _is_docs_only_change(path) for path in changed_files)


def _is_docs_only_change(path: str) -> bool:
    """Return True for documentation-only files that do not need pytest."""
    normalized = path.replace("\\", "/").lower()
    parsed = Path(normalized)
    if parsed.suffix in {".md", ".rst", ".adoc"}:
        return True
    if parsed.suffix == ".txt":
        return normalized.startswith("docs/") or parsed.name in {
            "changelog.txt",
            "license.txt",
            "notice.txt",
            "readme.txt",
        }
    return False


def _build_verification_plan(
    changed_files: list[str],
    tests_to_run: list[str],
    test_mapping: dict[str, list[str]] | None = None,
    default_test_command: DefaultTestCommand = PYTEST_COMMAND,
) -> dict[str, Any]:
    """Build the smallest recommended verification command for the diff."""
    if not _requires_pytest(changed_files):
        return {
            "test_required": False,
            "test_runner": default_test_command.runner,
            "default_test_command": default_test_command.command,
            "pytest_required": False,
            "pytest_command": "",
            "test_command": "",
            "verification_command": "git diff --check",
            "verification_reason": "docs-only changes; pytest is not required",
        }

    if _has_runtime_auto_discovery(test_mapping or {}):
        test_command = build_test_command(default_test_command, [])
        return {
            "test_required": True,
            "test_runner": default_test_command.runner,
            "default_test_command": default_test_command.command,
            "pytest_required": default_test_command.runner == "pytest",
            "pytest_command": test_command
            if default_test_command.runner == "pytest"
            else "",
            "test_command": test_command,
            "verification_command": test_command,
            "verification_reason": "unmapped runtime changes remain; run the default test command",
        }

    test_command = build_test_command(default_test_command, tests_to_run)
    reason = (
        "targeted tests cover mapped runtime changes"
        if tests_to_run
        else "no targeted tests found; run the default test command"
    )
    return {
        "test_required": True,
        "test_runner": default_test_command.runner,
        "default_test_command": default_test_command.command,
        "pytest_required": default_test_command.runner == "pytest",
        "pytest_command": test_command
        if default_test_command.runner == "pytest"
        else "",
        "test_command": test_command,
        "verification_command": test_command,
        "verification_reason": reason,
    }


def _has_runtime_auto_discovery(test_mapping: dict[str, list[str]]) -> bool:
    """Return True when runtime changes lack a targeted test mapping."""
    return any(AUTO_DISCOVER_TEST_HINT in tests for tests in test_mapping.values())
