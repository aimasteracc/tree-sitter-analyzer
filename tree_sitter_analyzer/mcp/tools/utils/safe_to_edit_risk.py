"""Risk scoring and checklist helpers for safe-to-edit reports."""

from __future__ import annotations

from pathlib import Path

from .verification_command import build_test_command, detect_default_test_command

RiskFactor = dict[str, str]


def compute_risk(
    forward_count: int,
    dep_count: int,
    health_grade: str,
    has_tests: bool,
    edit_type: str,
    is_init_file: bool,
) -> tuple[str, list[RiskFactor]]:
    """Compute risk level and contributing factors."""
    score = 0
    factors: list[RiskFactor] = []

    score += _add_downstream_factor(factors, forward_count)
    score += _add_health_factor(factors, health_grade)
    score += _add_test_factor(factors, has_tests)
    score += _add_init_factor(factors, is_init_file)
    score += _add_edit_type_factor(factors, edit_type, forward_count)
    score += _add_dependency_factor(factors, dep_count)

    return _classify_risk(score), factors


def build_checklist(
    risk: str,
    downstream_count: int,
    has_tests: bool,
    test_files: list[str],
    edit_type: str,
    health_grade: str = "",
    file_path: str = "",
    project_root: str | Path | None = None,
) -> list[str]:
    """Build a pre-edit checklist for the AI agent.

    Items are numbered sequentially (1, 2, 3, …) after filtering — items whose
    condition is False are simply absent, so the remaining items are always
    contiguous. Previously items 4/5/6 were hardcoded, causing gaps like
    [1, 2, 3, 5] when downstream_count == 0 (issue #641).
    """
    raw: list[str] = [_risk_instruction(risk)]
    raw.extend(_test_instructions(has_tests, test_files, project_root))

    if downstream_count > 0:
        raw.append(
            f"{downstream_count} downstream file(s) - verify imports still resolve"
        )
    if edit_type == "rename":
        raw.append("After rename: run find_and_grep(old_name) to find all references")
    if edit_type == "refactor":
        raw.append("Keep public API signatures unchanged during refactor")
    if health_grade in ("D", "F") and file_path:
        raw.append(
            f"File is grade {health_grade} - run refactoring_suggestions(file_path='{file_path}') for extraction plans"
        )

    # Strip any pre-existing leading "N. " prefixes from helper functions so
    # renumbering is idempotent, then apply sequential 1-based numbers.
    import re as _re

    def _strip_number(text: str) -> str:
        return _re.sub(r"^\d+\.\s*", "", text)

    return [f"{i}. {_strip_number(item)}" for i, item in enumerate(raw, start=1)]


def _add_downstream_factor(factors: list[RiskFactor], forward_count: int) -> int:
    """Add downstream blast-radius risk."""
    if forward_count > 20:
        factors.append(
            {
                "factor": "high_downstream",
                "detail": f"{forward_count} files depend on this - high blast radius",
                "severity": "dangerous",
            }
        )
        return 3
    if forward_count > 5:
        factors.append(
            {
                "factor": "moderate_downstream",
                "detail": f"{forward_count} files depend on this",
                "severity": "caution",
            }
        )
        return 2
    if forward_count > 0:
        factors.append(
            {
                "factor": "low_downstream",
                "detail": f"{forward_count} file(s) depend on this",
                "severity": "info",
            }
        )
        return 1
    return 0


def _add_health_factor(factors: list[RiskFactor], health_grade: str) -> int:
    """Add risk for files that are already fragile."""
    if health_grade in ("D", "F"):
        factors.append(
            {
                "factor": "poor_health",
                "detail": f"Grade {health_grade} - file already has issues, edits may compound them",
                "severity": "caution",
            }
        )
        return 2
    if health_grade == "C":
        factors.append(
            {
                "factor": "fair_health",
                "detail": f"Grade {health_grade} - moderate technical debt",
                "severity": "info",
            }
        )
        return 1
    return 0


def _add_test_factor(factors: list[RiskFactor], has_tests: bool) -> int:
    """Add risk or confidence based on nearby tests."""
    if has_tests:
        factors.append(
            {
                "factor": "has_tests",
                "detail": "Nearby test files found - run them before and after editing",
                "severity": "good",
            }
        )
        return 0
    factors.append(
        {
            "factor": "no_tests",
            "detail": "No nearby test files found - changes won't be automatically verified",
            "severity": "caution",
        }
    )
    return 2


def _add_init_factor(factors: list[RiskFactor], is_init_file: bool) -> int:
    """Add risk for package boundary files."""
    if not is_init_file:
        return 0
    factors.append(
        {
            "factor": "init_file",
            "detail": "Editing __init__.py affects package exports and all importers",
            "severity": "caution",
        }
    )
    return 2


def _add_edit_type_factor(
    factors: list[RiskFactor], edit_type: str, forward_count: int
) -> int:
    """Add risk based on the planned edit type."""
    if edit_type == "rename":
        factors.append(
            {
                "factor": "rename_risk",
                "detail": "Rename requires updating all importers - use find_and_grep first",
                "severity": "caution",
            }
        )
        return 2
    if edit_type == "refactor" and forward_count > 5:
        factors.append(
            {
                "factor": "refactor_risk",
                "detail": "Refactoring a widely-imported file - keep the public API stable",
                "severity": "caution",
            }
        )
        return 1
    return 0


def _add_dependency_factor(factors: list[RiskFactor], dep_count: int) -> int:
    """Add risk for files with a broad interaction surface."""
    if dep_count <= 10:
        return 0
    factors.append(
        {
            "factor": "high_dependencies",
            "detail": f"File imports {dep_count} modules - complex interaction surface",
            "severity": "info",
        }
    )
    return 1


def _classify_risk(score: int) -> str:
    """Map numeric risk score to safe/caution/dangerous."""
    if score >= 6:
        return "dangerous"
    if score >= 3:
        return "caution"
    return "safe"


def _risk_instruction(risk: str) -> str:
    """Return the first checklist item for a risk level."""
    if risk == "dangerous":
        return "1. HIGH RISK - consider breaking changes into smaller, atomic edits"
    if risk == "caution":
        return "1. MODERATE RISK - proceed with caution, test after each change"
    return "1. LOW RISK - file is relatively safe to edit"


def _test_instructions(
    has_tests: bool,
    test_files: list[str],
    project_root: str | Path | None,
) -> list[str]:
    """Return checklist items for test coverage."""
    default_command = detect_default_test_command(project_root)
    if has_tests:
        test_command = build_test_command(default_command, test_files[:3])
        return [
            f"2. Run existing tests FIRST: {test_command}",
            f"3. Run same verification AFTER editing: {test_command}",
        ]
    return [
        "2. No tests found nearby - write tests BEFORE editing (TDD)",
        f"3. Run default test command after editing: {default_command.command}",
    ]
