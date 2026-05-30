"""
Validation script for release workflow.

This script validates the release workflow configuration and can be used
to verify the workflow before pushing to a test release branch.

Usage:
    python tests/test_workflows/validate_release_workflow.py
"""

from pathlib import Path
from typing import Any

import yaml


class ReleaseWorkflowValidator:
    """Validator for release workflow configuration."""

    def __init__(self):
        self.workflow_root = (
            Path(__file__).parent.parent.parent.parent / ".github" / "workflows"
        )
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.successes: list[str] = []

    def load_workflow(self, filename: str) -> dict[str, Any]:
        """Load a workflow YAML file."""
        workflow_path = self.workflow_root / filename
        with open(workflow_path, encoding="utf-8") as f:
            workflow = yaml.safe_load(f)
            # Handle YAML parsing 'on' as boolean True
            if True in workflow and "on" not in workflow:
                workflow["on"] = workflow.pop(True)
            return workflow

    def validate_reusable_workflow_usage(self, workflow: dict[str, Any]) -> bool:
        """Validate that workflow uses reusable components."""
        jobs = workflow.get("jobs", {})

        if "test" not in jobs:
            self.errors.append("❌ Missing 'test' job")
            return False

        test_job = jobs["test"]
        if "uses" not in test_job:
            self.errors.append("❌ Test job does not use reusable workflow")
            return False

        if "reusable-test.yml" not in test_job["uses"]:
            self.errors.append("❌ Test job does not reference reusable-test.yml")
            return False

        if test_job.get("secrets") != "inherit":
            self.warnings.append("⚠️  Test job should inherit secrets")

        self.successes.append("✅ Test job uses reusable workflow correctly")
        return True

    def validate_deployment_dependency(self, workflow: dict[str, Any]) -> bool:
        """Validate that deployment depends on tests."""
        jobs = workflow.get("jobs", {})

        build_job = jobs.get("build")
        publish_job = jobs.get("publish")
        if not build_job:
            self.errors.append("❌ Missing 'build' job")
            return False
        if not publish_job:
            self.errors.append("❌ Missing 'publish' job")
            return False

        build_needs = build_job.get("needs")
        if isinstance(build_needs, str):
            build_needs = [build_needs]
        if "test" not in (build_needs or []):
            self.errors.append("❌ Build job does not depend on 'test' job")
            return False

        publish_needs = publish_job.get("needs")
        if isinstance(publish_needs, str):
            publish_needs = [publish_needs]
        if "build" not in (publish_needs or []):
            self.errors.append("❌ Publish job does not depend on 'build' job")
            return False

        self.successes.append("✅ Build/publish chain depends on test job")
        return True

    def validate_pypi_deployment(self, workflow: dict[str, Any]) -> bool:
        """Validate PyPI deployment configuration."""
        jobs = workflow.get("jobs", {})
        build_job = jobs.get("build", {})
        publish_job = jobs.get("publish", {})

        if "reusable-build.yml" not in build_job.get("uses", ""):
            self.errors.append("❌ Build job does not reference reusable-build.yml")
            return False

        if "reusable-publish.yml" not in publish_job.get("uses", ""):
            self.errors.append("❌ Publish job does not reference reusable-publish.yml")
            return False

        if "PYPI_API_TOKEN" not in str(publish_job.get("secrets", {})):
            self.errors.append("❌ Publish job does not receive PYPI_API_TOKEN")
            return False

        self.successes.append("✅ PyPI deployment configured correctly")
        return True

    def validate_pr_creation(self, workflow: dict[str, Any]) -> bool:
        """Validate PR creation to main."""
        jobs = workflow.get("jobs", {})
        pr_job = jobs.get("create-main-pr")

        if not pr_job:
            self.errors.append("❌ Missing 'create-main-pr' job")
            return False

        # Check needs dependency
        needs = pr_job.get("needs")
        if not needs:
            self.errors.append("❌ PR job missing 'needs' dependency")
            return False

        if isinstance(needs, str):
            needs = [needs]

        for required_job in ("test", "build", "publish"):
            if required_job not in needs:
                self.errors.append(f"❌ PR job must depend on {required_job!r}")
                return False

        run_blocks = "\n".join(
            str(step.get("run", "")) for step in pr_job.get("steps", [])
        )
        if "gh pr create" not in run_blocks:
            self.errors.append("❌ PR job missing gh pr create command")
            return False

        if "--base main" not in run_blocks:
            self.errors.append("❌ PR must target main branch")
            return False

        if '--head "${GITHUB_REF_NAME}"' not in run_blocks:
            self.errors.append("❌ PR must use the current release branch as head")
            return False

        if "peter-evans/create-pull-request" in str(pr_job):
            self.errors.append(
                "❌ PR job must not create a synthetic release-to-main branch"
            )
            return False

        self.successes.append("✅ PR creation configured correctly")
        return True

    def validate_branch_triggers(self, workflow: dict[str, Any]) -> bool:
        """Validate workflow triggers on release branches."""
        on_config = workflow.get("on", {})
        push_config = on_config.get("push", {})
        branches = push_config.get("branches", [])

        has_release_trigger = any("release/" in branch for branch in branches)

        if not has_release_trigger:
            self.errors.append("❌ Workflow must trigger on release/* branches")
            return False

        self.successes.append("✅ Workflow triggers on release branches")
        return True

    def validate(self) -> bool:
        """Run all validations."""
        print("=" * 70)
        print("Release Workflow Validation")
        print("=" * 70)
        print()

        try:
            workflow = self.load_workflow("release-automation.yml")
        except Exception as e:
            print(f"❌ Failed to load workflow: {e}")
            return False

        print("Running validations...")
        print()

        # Run all validations
        validations = [
            self.validate_reusable_workflow_usage(workflow),
            self.validate_deployment_dependency(workflow),
            self.validate_pypi_deployment(workflow),
            self.validate_pr_creation(workflow),
            self.validate_branch_triggers(workflow),
        ]

        # Print results
        print("Results:")
        print("-" * 70)

        for success in self.successes:
            print(success)

        if self.warnings:
            print()
            for warning in self.warnings:
                print(warning)

        if self.errors:
            print()
            for error in self.errors:
                print(error)

        print()
        print("=" * 70)

        all_passed = all(validations) and len(self.errors) == 0

        if all_passed:
            print("✅ All validations passed!")
            print()
            print("Next steps:")
            print(
                "1. Create a test release branch: git checkout -b release/v0.0.0-test"
            )
            print("2. Push changes: git push origin release/v0.0.0-test")
            print("3. Monitor workflow execution in GitHub Actions")
            print("4. Verify:")
            print("   - Tests run successfully")
            print("   - Deployment logic executes (check for build steps)")
            print("   - PR to main is created")
        else:
            print("❌ Validation failed!")
            print()
            print("Please fix the errors above before proceeding.")

        print("=" * 70)

        return all_passed


def main():
    """Main entry point."""
    validator = ReleaseWorkflowValidator()
    success = validator.validate()
    exit(0 if success else 1)


if __name__ == "__main__":
    main()
