"""Regression tests for the workflow structure verification script."""

import verify_workflow_structure as verifier
from _verify_workflow_structure_helpers import (
    load_yaml,
    reusable_quality_errors,
    workflow_path,
)


def test_reusable_quality_workflow_empty_call_is_valid() -> None:
    """An empty workflow_call is a valid reusable workflow trigger."""
    content = load_yaml(workflow_path("workflows", "reusable-quality.yml"))

    assert reusable_quality_errors(content) == []


def test_verify_workflow_structure_main_succeeds(capsys) -> None:
    """The repository workflow verification script should be executable."""
    assert verifier.main() == 0

    output = capsys.readouterr().out
    assert "All workflow structures are correct" in output


def test_system_setup_requires_unconditional_git_verification() -> None:
    """统一 Git 检查不能因条件分支而漏掉某个平台。"""
    from _verify_workflow_structure_helpers import composite_action_errors

    content = load_yaml(workflow_path("actions", "setup-system", "action.yml"))
    content["runs"]["steps"][0]["if"] = "runner.os == 'Linux'"
    assert composite_action_errors(content) == [
        "Missing unconditional Git verification step"
    ]
