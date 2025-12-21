"""
Validation script for hotfix workflow.

This script validates the hotfix workflow configuration to ensure:
1. Tests run before deployment
2. Deployment logic is correct
3. PR creation to main is configured
4. Workflow matches release workflow structure
"""

from pathlib import Path
from typing import Any

import yaml


def load_workflow(workflow_name: str) -> dict[str, Any]:
    """Load a workflow YAML file."""
    workflow_path = (
        Path(__file__).parent.parent.parent.parent
        / ".github"
        / "workflows"
        / workflow_name
    )
    with open(workflow_path, encoding="utf-8") as f:
        workflow = yaml.safe_load(f)
        # Handle YAML parsing 'on' as boolean True
        if True in workflow and "on" not in workflow:
            workflow["on"] = workflow.pop(True)
        return workflow


def validate_test_job(workflow: dict[str, Any]) -> bool:
    """Validate that test job uses reusable workflow."""
    jobs = workflow.get("jobs", {})

    if "test" not in jobs:
        print("❌ Test job not found")
        return False

    test_job = jobs["test"]

    if "uses" not in test_job:
        print("❌ Test job does not use reusable workflow")
        return False

    if "reusable-test.yml" not in test_job["uses"]:
        print("❌ Test job does not reference reusable-test.yml")
        return False

    if test_job.get("secrets") != "inherit":
        print("❌ Test job does not inherit secrets")
        return False

    print("✅ Test job correctly configured")
    return True


def validate_deployment_job(workflow: dict[str, Any]) -> bool:
    """Validate that deployment job depends on test job."""
    jobs = workflow.get("jobs", {})

    if "build-and-deploy" not in jobs:
        print("❌ Build-and-deploy job not found")
        return False

    deploy_job = jobs["build-and-deploy"]

    if "needs" not in deploy_job:
        print("❌ Deploy job does not have needs dependency")
        return False

    needs = deploy_job["needs"]
    if isinstance(needs, str):
        needs = [needs]

    if "test" not in needs:
        print("❌ Deploy job does not depend on test job")
        return False

    # Check for PyPI deployment steps
    steps = deploy_job.get("steps", [])

    has_build = any(
        "build" in step.get("name", "").lower()
        or "python -m build" in step.get("run", "")
        for step in steps
    )

    has_upload = any(
        "deploy" in step.get("name", "").lower()
        or "twine upload" in step.get("run", "")
        for step in steps
    )

    if not has_build:
        print("❌ Deploy job missing build step")
        return False

    if not has_upload:
        print("❌ Deploy job missing PyPI upload step")
        return False

    print("✅ Deployment job correctly configured")
    return True


def validate_pr_creation_job(workflow: dict[str, Any]) -> bool:
    """Validate that PR creation job depends on test and deploy."""
    jobs = workflow.get("jobs", {})

    if "create-main-pr" not in jobs:
        print("❌ Create-main-pr job not found")
        return False

    pr_job = jobs["create-main-pr"]

    if "needs" not in pr_job:
        print("❌ PR job does not have needs dependency")
        return False

    needs = pr_job["needs"]
    if isinstance(needs, str):
        needs = [needs]

    if "test" not in needs or "build-and-deploy" not in needs:
        print("❌ PR job does not depend on both test and build-and-deploy")
        return False

    # Check for PR creation action
    steps = pr_job.get("steps", [])
    has_pr_action = any(
        "peter-evans/create-pull-request" in step.get("uses", "") for step in steps
    )

    if not has_pr_action:
        print("❌ PR job missing create-pull-request action")
        return False

    # Verify PR targets main branch
    pr_step = next(
        (
            step
            for step in steps
            if "peter-evans/create-pull-request" in step.get("uses", "")
        ),
        None,
    )

    if pr_step:
        with_config = pr_step.get("with", {})
        if with_config.get("base") != "main":
            print("❌ PR does not target main branch")
            return False
        if with_config.get("branch") != "hotfix-to-main":
            print("❌ PR does not use hotfix-to-main branch")
            return False

    print("✅ PR creation job correctly configured")
    return True


def validate_workflow_triggers(workflow: dict[str, Any]) -> bool:
    """Validate that workflow triggers on hotfix branches."""
    on_config = workflow.get("on", {})

    if "push" not in on_config:
        print("❌ Workflow does not have push trigger")
        return False

    push_config = on_config["push"]
    branches = push_config.get("branches", [])

    has_hotfix_trigger = any("hotfix/" in branch for branch in branches)

    if not has_hotfix_trigger:
        print("❌ Workflow does not trigger on hotfix/* branches")
        return False

    if "workflow_dispatch" not in on_config:
        print("❌ Workflow does not support manual dispatch")
        return False

    print("✅ Workflow triggers correctly configured")
    return True


def validate_consistency_with_release(
    hotfix_workflow: dict[str, Any], release_workflow: dict[str, Any]
) -> bool:
    """Validate that hotfix workflow matches release workflow structure."""
    hotfix_jobs = set(hotfix_workflow.get("jobs", {}).keys())
    release_jobs = set(release_workflow.get("jobs", {}).keys())

    if hotfix_jobs != release_jobs:
        print(
            f"❌ Job structure mismatch. Hotfix: {hotfix_jobs}, Release: {release_jobs}"
        )
        return False

    # Check test job configuration
    hotfix_test = hotfix_workflow.get("jobs", {}).get("test", {})
    release_test = release_workflow.get("jobs", {}).get("test", {})

    hotfix_inputs = hotfix_test.get("with", {})
    release_inputs = release_test.get("with", {})

    if hotfix_inputs.get("python-version") != release_inputs.get("python-version"):
        print("❌ Python version mismatch between hotfix and release")
        return False

    if hotfix_inputs.get("upload-coverage") != release_inputs.get("upload-coverage"):
        print("❌ Coverage upload setting mismatch between hotfix and release")
        return False

    print("✅ Hotfix workflow matches release workflow structure")
    return True


def main():
    """Main validation function."""
    print("=" * 70)
    print("Hotfix Workflow Validation")
    print("=" * 70)
    print()

    # Load workflows
    print("Loading workflows...")
    hotfix_workflow = load_workflow("hotfix-automation.yml")
    release_workflow = load_workflow("release-automation.yml")
    print()

    # Run validations
    validations = [
        ("Test Job Configuration", lambda: validate_test_job(hotfix_workflow)),
        (
            "Deployment Job Configuration",
            lambda: validate_deployment_job(hotfix_workflow),
        ),
        (
            "PR Creation Job Configuration",
            lambda: validate_pr_creation_job(hotfix_workflow),
        ),
        ("Workflow Triggers", lambda: validate_workflow_triggers(hotfix_workflow)),
        (
            "Consistency with Release",
            lambda: validate_consistency_with_release(
                hotfix_workflow, release_workflow
            ),
        ),
    ]

    results = []
    for name, validation_func in validations:
        print(f"\n{name}:")
        print("-" * 70)
        result = validation_func()
        results.append(result)
        print()

    # Summary
    print("=" * 70)
    print("Validation Summary")
    print("=" * 70)
    passed = sum(results)
    total = len(results)

    print(f"\nPassed: {passed}/{total}")

    if passed == total:
        print("\n✅ All validations passed! Hotfix workflow is correctly configured.")
        return 0
    else:
        print(
            f"\n❌ {total - passed} validation(s) failed. Please review the errors above."
        )
        return 1


if __name__ == "__main__":
    exit(main())
