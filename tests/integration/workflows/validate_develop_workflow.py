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
        workflow = yaml.safe_load(f)
        if True in workflow and "on" not in workflow:
            workflow["on"] = workflow.pop(True)
        return workflow


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

    # Validate build job
    print("  ✓ Checking build job...")
    assert "build" in jobs, "Must have build job"
    build_job = jobs["build"]
    assert "uses" in build_job, "Build job must use reusable workflow"
    assert "reusable-build.yml" in build_job["uses"], "Must use reusable-build.yml"

    # Validate PR creation job
    print("  ✓ Checking PR creation job...")
    assert "create-release-pr" in jobs, "Must have PR creation job"
    pr_job = jobs["create-release-pr"]
    assert "needs" in pr_job, "PR job must have dependencies"
    needs = pr_job["needs"]
    assert "build" in needs, "PR must depend on build"

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
    print("     - CI workflow covers quality checks and tests for develop pushes")
    print("     - Build job executes using reusable-build.yml")
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
