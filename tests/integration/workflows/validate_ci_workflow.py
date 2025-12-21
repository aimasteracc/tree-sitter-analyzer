"""
Validation script for CI workflow.

This script validates the ci.yml workflow structure and ensures:
1. CI workflow uses reusable test workflow
2. CI workflow has no deployment logic
3. CI workflow uses composite setup-system action
4. All jobs execute successfully (simulated)
5. No deployment attempts occur

Usage:
    python tests/test_workflows/validate_ci_workflow.py
"""

from pathlib import Path
from typing import Any

import yaml


class CIWorkflowValidator:
    """Validator for CI workflow structure and behavior."""

    def __init__(self):
        self.workflow_root = (
            Path(__file__).parent.parent.parent.parent / ".github" / "workflows"
        )
        self.ci_workflow_path = self.workflow_root / "ci.yml"
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def load_workflow(self) -> dict[str, Any]:
        """Load the CI workflow YAML."""
        with open(self.ci_workflow_path, encoding="utf-8") as f:
            workflow = yaml.safe_load(f)
            # Handle YAML parsing 'on' as boolean True
            if True in workflow and "on" not in workflow:
                workflow["on"] = workflow.pop(True)
            return workflow

    def validate_uses_reusable_test_workflow(self, workflow: dict[str, Any]) -> bool:
        """Validate that CI workflow uses reusable test workflow."""
        print("\n✓ Checking if CI workflow uses reusable test workflow...")

        jobs = workflow.get("jobs", {})
        if "test" not in jobs:
            self.errors.append("CI workflow must have a 'test' job")
            return False

        test_job = jobs["test"]
        if "uses" not in test_job:
            self.errors.append("Test job must use reusable workflow")
            return False

        if "./.github/workflows/reusable-test.yml" not in test_job["uses"]:
            self.errors.append("Test job must use reusable-test.yml")
            return False

        if test_job.get("secrets") != "inherit":
            self.errors.append("Test job must inherit secrets")
            return False

        print("  ✓ CI workflow correctly uses reusable-test.yml")
        print("  ✓ Secrets are properly inherited")
        return True

    def validate_no_deployment_logic(self, workflow: dict[str, Any]) -> bool:
        """Validate that CI workflow has no deployment logic."""
        print("\n✓ Checking for deployment logic...")

        jobs = workflow.get("jobs", {})
        has_deployment = False

        # Check for deployment job names
        deployment_job_names = ["deploy", "deployment", "publish"]
        for job_name in jobs.keys():
            if any(
                deploy_name in job_name.lower() for deploy_name in deployment_job_names
            ):
                self.errors.append(
                    f"CI workflow should not have deployment job: {job_name}"
                )
                has_deployment = True

        # Check for PyPI deployment steps
        for job_name, job in jobs.items():
            steps = job.get("steps", [])
            for step in steps:
                step_name = step.get("name", "").lower()
                run_cmd = step.get("run", "").lower()

                # Check for actual PyPI upload commands
                if "twine upload" in run_cmd or "publish to pypi" in step_name:
                    self.errors.append(
                        f"CI workflow should not have PyPI upload in job: {job_name}"
                    )
                    has_deployment = True

                # Check for PyPI token usage
                env = step.get("env", {})
                if "PYPI_TOKEN" in env or "TWINE_PASSWORD" in env:
                    self.errors.append(
                        f"CI workflow should not use PyPI tokens in job: {job_name}"
                    )
                    has_deployment = True

        if not has_deployment:
            print("  ✓ No deployment logic found in CI workflow")

        return not has_deployment

    def validate_uses_composite_setup_action(self, workflow: dict[str, Any]) -> bool:
        """Validate that CI workflow uses composite setup-system action."""
        print("\n✓ Checking if CI workflow uses composite setup-system action...")

        jobs = workflow.get("jobs", {})
        ci_specific_jobs = ["security-check", "documentation-check", "build-check"]

        all_use_composite = True
        for job_name in ci_specific_jobs:
            if job_name not in jobs:
                self.warnings.append(f"Expected CI-specific job not found: {job_name}")
                continue

            job = jobs[job_name]
            steps = job.get("steps", [])

            has_setup_action = any(
                "./.github/actions/setup-system" in step.get("uses", "")
                for step in steps
            )

            if has_setup_action:
                print(f"  ✓ Job '{job_name}' uses composite setup-system action")
            else:
                self.errors.append(
                    f"Job '{job_name}' should use composite setup-system action"
                )
                all_use_composite = False

        return all_use_composite

    def validate_ci_specific_jobs(self, workflow: dict[str, Any]) -> bool:
        """Validate that CI workflow maintains CI-specific jobs."""
        print("\n✓ Checking CI-specific jobs...")

        jobs = workflow.get("jobs", {})
        required_jobs = ["test", "security-check", "documentation-check", "build-check"]

        all_present = True
        for job_name in required_jobs:
            if job_name in jobs:
                print(f"  ✓ Job '{job_name}' is present")
            else:
                self.errors.append(f"Required job '{job_name}' is missing")
                all_present = False

        return all_present

    def validate_triggers(self, workflow: dict[str, Any]) -> bool:
        """Validate that CI workflow has appropriate triggers."""
        print("\n✓ Checking workflow triggers...")

        triggers = workflow.get("on", {})

        # Check push triggers
        if "push" not in triggers:
            self.errors.append("CI workflow must trigger on push")
            return False

        push_branches = triggers["push"].get("branches", [])
        required_push_branches = ["main", "develop"]
        for branch in required_push_branches:
            if branch in push_branches:
                print(f"  ✓ Triggers on push to '{branch}'")
            else:
                self.errors.append(f"CI workflow must trigger on push to '{branch}'")

        # Check PR triggers
        if "pull_request" not in triggers:
            self.errors.append("CI workflow must trigger on pull requests")
            return False

        pr_branches = triggers["pull_request"].get("branches", [])
        required_pr_branches = ["main", "develop"]
        for branch in required_pr_branches:
            if branch in pr_branches:
                print(f"  ✓ Triggers on PR to '{branch}'")
            else:
                self.errors.append(f"CI workflow must trigger on PR to '{branch}'")

        # Check manual dispatch
        if "workflow_dispatch" in triggers:
            print("  ✓ Supports manual workflow dispatch")
        else:
            self.warnings.append("CI workflow should support manual dispatch")

        return True

    def validate_all_extras_flag(self, workflow: dict[str, Any]) -> bool:
        """Validate that all dependency installations use --all-extras flag."""
        print("\n✓ Checking --all-extras flag usage...")

        jobs = workflow.get("jobs", {})
        all_use_extras = True

        for job_name, job in jobs.items():
            steps = job.get("steps", [])
            for step in steps:
                if "run" in step:
                    run_cmd = step["run"]
                    if "uv sync" in run_cmd or "uv add" in run_cmd:
                        if "--all-extras" not in run_cmd:
                            self.errors.append(
                                f"Job '{job_name}' should use --all-extras flag in: {run_cmd[:50]}..."
                            )
                            all_use_extras = False

        if all_use_extras:
            print("  ✓ All dependency installations use --all-extras flag")

        return all_use_extras

    def run_validation(self) -> bool:
        """Run all validation checks."""
        print("=" * 80)
        print("CI Workflow Validation")
        print("=" * 80)
        print(f"\nValidating: {self.ci_workflow_path}")

        try:
            workflow = self.load_workflow()
        except Exception as e:
            print(f"\n❌ Failed to load workflow: {e}")
            return False

        # Run all validation checks
        # Run all validation checks
        self.validate_uses_reusable_test_workflow(workflow)
        self.validate_no_deployment_logic(workflow)
        self.validate_uses_composite_setup_action(workflow)
        self.validate_ci_specific_jobs(workflow)
        self.validate_triggers(workflow)
        self.validate_all_extras_flag(workflow)

        # Print summary
        print("\n" + "=" * 80)
        print("Validation Summary")
        print("=" * 80)

        if self.warnings:
            print(f"\n⚠️  Warnings ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"  - {warning}")

        if self.errors:
            print(f"\n❌ Errors ({len(self.errors)}):")
            for error in self.errors:
                print(f"  - {error}")
            print("\n❌ CI workflow validation FAILED")
            return False

        print("\n✅ All validation checks passed!")
        print("\nCI workflow is correctly configured:")
        print("  ✓ Uses reusable test workflow")
        print("  ✓ No deployment logic present")
        print("  ✓ Uses composite setup-system action")
        print("  ✓ All CI-specific jobs present")
        print("  ✓ Appropriate triggers configured")
        print("  ✓ Consistent --all-extras flag usage")

        return True


def main():
    """Main entry point."""
    validator = CIWorkflowValidator()
    success = validator.run_validation()

    if not success:
        exit(1)


if __name__ == "__main__":
    main()
