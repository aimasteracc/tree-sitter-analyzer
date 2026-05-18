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
