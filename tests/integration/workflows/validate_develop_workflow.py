"""
Validation script for develop workflow structure.

This script validates that the develop workflow is properly configured
and ready for testing on a feature branch.
"""

from pathlib import Path
from typing import Any

import yaml


def load_workflow(workflow_path: Path) -> dict[str, Any]:
    """Load a workflow YAML file."""
    with open(workflow_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate_develop_workflow():
    """Validate the develop workflow configuration."""
    workflow_root = Path(__file__).parent.parent.parent.parent / ".github" / "workflows"
    develop_workflow = load_workflow(workflow_root / "develop-automation.yml")

    print("🔍 Validating develop-automation.yml...")

    # Check workflow structure
    assert "name" in develop_workflow, "Workflow must have a name"
    # Note: YAML parsers may convert 'on' to boolean True
    assert (
        "on" in develop_workflow or True in develop_workflow
    ), "Workflow must have triggers"
    assert "jobs" in develop_workflow, "Workflow must have jobs"

    jobs = develop_workflow["jobs"]
    triggers = develop_workflow.get("on") or develop_workflow.get(True)

    # Validate test job
    print("  ✓ Checking test job...")
    assert "test" in jobs, "Must have test job"
    test_job = jobs["test"]
    assert "uses" in test_job, "Test job must use reusable workflow"
    assert "reusable-test.yml" in test_job["uses"], "Must use reusable-test.yml"
    assert test_job.get("secrets") == "inherit", "Must inherit secrets"

    # Validate build job
    print("  ✓ Checking build job...")
    assert "build" in jobs, "Must have build job"
    build_job = jobs["build"]
    assert "needs" in build_job, "Build job must have dependencies"
    assert "test" in build_job["needs"], "Build must depend on test"

    # Validate PR creation job
    print("  ✓ Checking PR creation job...")
    assert "create-release-pr" in jobs, "Must have PR creation job"
    pr_job = jobs["create-release-pr"]
    assert "needs" in pr_job, "PR job must have dependencies"
    needs = pr_job["needs"]
    assert "test" in needs and "build" in needs, "PR must depend on test and build"

    # Validate triggers
    print("  ✓ Checking triggers...")
    assert triggers is not None, "Must have trigger configuration"
    assert "push" in triggers, "Must trigger on push"
    assert "develop" in triggers["push"]["branches"], "Must trigger on develop branch"
    assert "workflow_dispatch" in triggers, "Must support manual dispatch"

    print("\n✅ All validations passed!")
    print("\n📋 Next steps for testing:")
    print("  1. Create a test feature branch")
    print("  2. Push changes to trigger the workflow")
    print("  3. Verify in GitHub Actions that:")
    print("     - Test job executes using reusable-test.yml")
    print("     - All quality checks run")
    print("     - Test matrix executes on all platforms (ubuntu, windows, macos)")
    print("     - Coverage uploads successfully to Codecov")
    print("     - Build job runs after tests pass")
    print("     - PR creation job runs after build passes")

    return True


if __name__ == "__main__":
    try:
        validate_develop_workflow()
    except AssertionError as e:
        print(f"\n❌ Validation failed: {e}")
        exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        exit(1)
