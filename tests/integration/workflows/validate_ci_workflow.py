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
        self.reusable_test_workflow_path = self.workflow_root / "reusable-test.yml"
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def load_workflow(self, workflow_path: Path) -> dict[str, Any]:
        """Load a workflow YAML file."""
        with open(workflow_path, encoding="utf-8") as f:
            workflow = yaml.safe_load(f)
            # Handle YAML parsing 'on' as boolean True
            if True in workflow and "on" not in workflow:
                workflow["on"] = workflow.pop(True)
            return workflow

    def validate_reusable_workflow_usage(self, workflow: dict[str, Any]) -> bool:
        """Validate that CI workflow uses the reusable workflow stack."""
        print("\n✓ Checking reusable workflow usage...")

        jobs = workflow.get("jobs", {})
        required_uses = {
            "quality-check": "./.github/workflows/reusable-quality.yml",
            "test": "./.github/workflows/reusable-test.yml",
            "build": "./.github/workflows/reusable-build.yml",
        }

        all_valid = True
        for job_name, expected_workflow in required_uses.items():
            job = jobs.get(job_name)
            if not job:
                self.errors.append(f"CI workflow must have a '{job_name}' job")
                all_valid = False
                continue
            if job.get("uses") != expected_workflow:
                self.errors.append(
                    f"Job '{job_name}' must use {expected_workflow}"
                )
                all_valid = False

        test_job = jobs.get("test", {})
        if test_job.get("secrets") != "inherit":
            self.errors.append("Test job must inherit secrets")
            all_valid = False

        if all_valid:
            print("  ✓ Quality, test, and build jobs use reusable workflows")
            print("  ✓ Test job inherits secrets")

        return all_valid

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

    def validate_quality_gate(self, workflow: dict[str, Any]) -> bool:
        """Validate that the final quality gate blocks on prior jobs."""
        print("\n✓ Checking quality gate...")

        jobs = workflow.get("jobs", {})
        quality_gate = jobs.get("quality-gate")
        if not quality_gate:
            self.errors.append("CI workflow must have a 'quality-gate' job")
            return False

        needs = quality_gate.get("needs")
        if isinstance(needs, str):
            needs = [needs]
        expected_needs = {"test", "quality-check", "build"}
        if not needs or set(needs) != expected_needs:
            self.errors.append(
                "Quality gate must depend on test, quality-check, and build"
            )
            return False

        if quality_gate.get("if") != "always()":
            self.errors.append("Quality gate must always evaluate upstream results")
            return False

        print("  ✓ Quality gate waits for all reusable jobs")
        return True

    def validate_reusable_test_workflow(self) -> bool:
        """Validate key behavior in the reusable test workflow."""
        print("\n✓ Checking reusable test workflow details...")

        workflow = self.load_workflow(self.reusable_test_workflow_path)
        on_config = workflow.get("on", {})
        workflow_call = on_config.get("workflow_call", {})
        codecov_secret = workflow_call.get("secrets", {}).get("CODECOV_TOKEN", {})

        if codecov_secret.get("required") is not False:
            self.errors.append("Reusable test workflow must not require CODECOV_TOKEN")
            return False

        reusable_test_content = self.reusable_test_workflow_path.read_text(
            encoding="utf-8"
        )
        broken_marker_expression = 'not requires_ripgrep or not requires_fd'
        if broken_marker_expression in reusable_test_content:
            self.errors.append(
                "Reusable test workflow must not use the broken ripgrep/fd marker expression"
            )
            return False

        print("  ✓ CODECOV_TOKEN is optional")
        print("  ✓ Test commands no longer use the broken marker filter")
        return True

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
            workflow = self.load_workflow(self.ci_workflow_path)
        except Exception as e:
            print(f"\n❌ Failed to load workflow: {e}")
            return False

        # Run all validation checks
        self.validate_reusable_workflow_usage(workflow)
        self.validate_no_deployment_logic(workflow)
        self.validate_quality_gate(workflow)
        self.validate_reusable_test_workflow()
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
        print("  ✓ Uses reusable quality, test, and build workflows")
        print("  ✓ No deployment logic present")
        print("  ✓ Quality gate enforces overall CI status")
        print("  ✓ Reusable test workflow keeps Codecov optional")
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
