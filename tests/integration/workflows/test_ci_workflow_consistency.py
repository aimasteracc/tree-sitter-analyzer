"""
Property-based tests for CI workflow consistency.

Feature: github-actions-consistency
Property 1: Test Configuration Consistency
Property 10: Deployment Branch Restriction

Validates: Requirements 1.4, 5.4
"""

from pathlib import Path
from typing import Any

import pytest
import yaml


class TestCIWorkflowConsistency:
    """Property-based tests for CI workflow consistency."""

    @pytest.fixture
    def workflow_root(self) -> Path:
        """Get the workflow directory root."""
        return Path(__file__).parent.parent.parent.parent / ".github" / "workflows"

    @pytest.fixture
    def ci_workflow(self, workflow_root: Path) -> dict[str, Any]:
        """Load the CI workflow YAML."""
        workflow_path = workflow_root / "ci.yml"
        with open(workflow_path, encoding="utf-8") as f:
            workflow = yaml.safe_load(f)
            # Handle YAML parsing 'on' as boolean True
            if True in workflow and "on" not in workflow:
                workflow["on"] = workflow.pop(True)
            return workflow

    @pytest.fixture
    def reusable_test_workflow(self, workflow_root: Path) -> dict[str, Any]:
        """Load the reusable test workflow YAML."""
        workflow_path = workflow_root / "reusable-test.yml"
        with open(workflow_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    @pytest.fixture
    def security_scan_workflow(self, workflow_root: Path) -> dict[str, Any]:
        """Load the security scan workflow YAML."""
        workflow_path = workflow_root / "security-scan.yml"
        with open(workflow_path, encoding="utf-8") as f:
            workflow = yaml.safe_load(f)
            # Handle YAML parsing 'on' as boolean True
            if True in workflow and "on" not in workflow:
                workflow["on"] = workflow.pop(True)
            return workflow

    @pytest.fixture
    def develop_workflow(self, workflow_root: Path) -> dict[str, Any]:
        """Load the develop workflow for comparison."""
        workflow_path = workflow_root / "develop-automation.yml"
        with open(workflow_path, encoding="utf-8") as f:
            workflow = yaml.safe_load(f)
            # Handle YAML parsing 'on' as boolean True
            if True in workflow and "on" not in workflow:
                workflow["on"] = workflow.pop(True)
            return workflow

    @pytest.fixture
    def release_workflow(self, workflow_root: Path) -> dict[str, Any]:
        """Load the release workflow for comparison."""
        workflow_path = workflow_root / "release-automation.yml"
        with open(workflow_path, encoding="utf-8") as f:
            workflow = yaml.safe_load(f)
            # Handle YAML parsing 'on' as boolean True
            if True in workflow and "on" not in workflow:
                workflow["on"] = workflow.pop(True)
            return workflow

    def extract_test_matrix(self, workflow: dict[str, Any]) -> dict[str, Any]:
        """Extract test matrix configuration from workflow."""
        jobs = workflow.get("jobs", {})

        # Check for test-matrix job in reusable workflow
        if "test-matrix" in jobs:
            job = jobs["test-matrix"]
            strategy = job.get("strategy", {})
            matrix = strategy.get("matrix", {})
            return {
                "os": matrix.get("os", []),
                "python_versions": matrix.get("python-version", []),
                "exclude": matrix.get("exclude", []),
            }

        return {}

    def extract_install_commands(self, workflow: dict[str, Any]) -> list[str]:
        """Extract dependency installation commands from workflow."""
        commands = []
        jobs = workflow.get("jobs", {})

        for _job_name, job in jobs.items():
            steps = job.get("steps", [])
            for step in steps:
                if "run" in step:
                    run_cmd = step["run"]
                    if (
                        "uv sync" in run_cmd
                        or "uv add" in run_cmd
                        or "Install dependencies" in step.get("name", "")
                    ):
                        commands.append(run_cmd)

        return commands

    def has_deployment_job(self, workflow: dict[str, Any]) -> bool:
        """Check if workflow has actual PyPI deployment jobs (not just build checks)."""
        jobs = workflow.get("jobs", {})

        # Check for explicit deployment jobs
        deployment_job_names = ["deploy", "deployment", "publish"]
        for job_name in jobs.keys():
            if any(
                deploy_name in job_name.lower() for deploy_name in deployment_job_names
            ):
                return True

        # Check for actual PyPI deployment steps (twine upload, not just twine check)
        for _job_name, job in jobs.items():
            steps = job.get("steps", [])
            for step in steps:
                step_name = step.get("name", "").lower()
                run_cmd = step.get("run", "").lower()

                # Check for actual PyPI upload commands (not just checks)
                if "twine upload" in run_cmd or "publish to pypi" in step_name:
                    return True

                # Check for PyPI token usage (indicates actual deployment)
                env = step.get("env", {})
                if "PYPI_TOKEN" in env or "TWINE_PASSWORD" in env:
                    return True

        return False

    def test_property_1_test_configuration_consistency(
        self,
        ci_workflow: dict[str, Any],
        develop_workflow: dict[str, Any],
        release_workflow: dict[str, Any],
        reusable_test_workflow: dict[str, Any],
    ):
        """
        **Feature: github-actions-consistency, Property 1: Test Configuration Consistency**

        For any pair of branch workflows (develop, release, hotfix, main),
        the test job configurations should be identical in terms of:
        - Python versions tested
        - Operating systems tested
        - System dependencies installed
        - Test commands executed
        - Quality checks performed
        - Dependency installation flags (--all-extras)

        **Validates: Requirements 1.1, 1.2, 1.3, 1.4**
        """
        # Verify CI workflow uses reusable test workflow
        jobs = ci_workflow.get("jobs", {})
        assert "test" in jobs, "CI workflow must have a test job"

        test_job = jobs["test"]
        assert "uses" in test_job, "Test job must use reusable workflow"
        assert (
            "./.github/workflows/reusable-test.yml" in test_job["uses"]
        ), "Test job must use reusable-test.yml"

        # Verify secrets are inherited
        assert (
            test_job.get("secrets") == "inherit"
        ), "Test job must inherit secrets for CODECOV_TOKEN"

        # Note: develop-automation.yml no longer has a test job.
        # Tests for develop branch are handled by ci.yml which runs on push to develop.
        # Only verify that ci.yml runs on develop branch.
        ci_on = ci_workflow.get("on", ci_workflow.get(True, {}))
        push_branches = ci_on.get("push", {}).get("branches", [])
        assert "develop" in push_branches, "CI workflow must run on develop branch"

        # Verify release workflow also uses the same reusable workflow
        release_jobs = release_workflow.get("jobs", {})
        assert "test" in release_jobs, "Release workflow must have a test job"
        release_test_job = release_jobs["test"]
        assert release_test_job.get("uses") == test_job.get(
            "uses"
        ), "CI and release workflows must use the same reusable test workflow"

        # Extract test matrix from reusable workflow
        test_matrix = self.extract_test_matrix(reusable_test_workflow)

        # Verify Python versions
        expected_python_versions = ["3.10", "3.11", "3.12", "3.13"]
        assert (
            test_matrix["python_versions"] == expected_python_versions
        ), f"Python versions must be {expected_python_versions}"

        # Verify operating systems
        expected_os = ["ubuntu-latest", "windows-latest", "macos-latest"]
        assert (
            test_matrix["os"] == expected_os
        ), f"Operating systems must be {expected_os}"

        # Verify test matrix excludes (for optimization)
        excludes = test_matrix.get("exclude", [])
        assert len(excludes) > 0, "Test matrix should have excludes for optimization"

        # Verify --all-extras flag is used
        install_commands = self.extract_install_commands(reusable_test_workflow)
        assert (
            len(install_commands) > 0
        ), "Reusable test workflow must have dependency installation commands"

        for cmd in install_commands:
            assert (
                "--all-extras" in cmd
            ), f"Install command must use --all-extras flag: {cmd}"

    def test_property_10_deployment_branch_restriction(
        self,
        ci_workflow: dict[str, Any],
        develop_workflow: dict[str, Any],
        release_workflow: dict[str, Any],
    ):
        """
        **Feature: github-actions-consistency, Property 10: Deployment Branch Restriction**

        For any workflow, PyPI deployment jobs should only exist in release/*
        and hotfix/* branch workflows, and should not exist in develop or main workflows.

        **Validates: Requirements 5.4, 5.5**
        """
        # Verify CI workflow does NOT have deployment jobs
        assert not self.has_deployment_job(
            ci_workflow
        ), "CI workflow must NOT have deployment jobs"

        # Verify develop workflow does NOT have deployment jobs
        assert not self.has_deployment_job(
            develop_workflow
        ), "Develop workflow must NOT have deployment jobs"

        # Verify release workflow DOES have deployment jobs
        assert self.has_deployment_job(
            release_workflow
        ), "Release workflow must have deployment jobs"

        # Additional verification: Check that CI workflow has no PyPI-related secrets
        jobs = ci_workflow.get("jobs", {})
        for job_name, job in jobs.items():
            steps = job.get("steps", [])
            for step in steps:
                env = step.get("env", {})
                # Verify no PYPI_TOKEN or similar secrets
                assert (
                    "PYPI_TOKEN" not in env
                ), f"CI workflow job '{job_name}' must not use PYPI_TOKEN"
                assert (
                    "TWINE_PASSWORD" not in env
                ), f"CI workflow job '{job_name}' must not use TWINE_PASSWORD"

    def test_ci_workflow_uses_reusable_components(self, ci_workflow: dict[str, Any]):
        """
        Verify that CI workflow properly uses reusable workflow components.

        This ensures the refactoring was successful and the workflow
        maintains consistency with other branch workflows.
        """
        jobs = ci_workflow.get("jobs", {})

        # Verify test job uses reusable workflow
        assert "test" in jobs, "CI workflow must have test job"
        test_job = jobs["test"]
        assert "uses" in test_job, "Test job must use reusable workflow"
        assert (
            "reusable-test.yml" in test_job["uses"]
        ), "Test job must reference reusable-test.yml"

        # Verify CI-specific jobs still exist
        # Note: security-check moved to independent workflow
        assert (
            "documentation-check" in jobs
        ), "CI workflow must have documentation-check job"
        assert "build-check" in jobs, "CI workflow must have build-check job"

    def test_ci_workflow_uses_composite_setup_action(self, ci_workflow: dict[str, Any]):
        """
        Verify that CI workflow uses the composite setup-system action
        for system dependency installation.

        This ensures consistency with other workflows.
        """
        jobs = ci_workflow.get("jobs", {})

        # Check documentation-check job
        doc_job = jobs.get("documentation-check", {})
        doc_steps = doc_job.get("steps", [])
        has_setup_action = any(
            "./.github/actions/setup-system" in step.get("uses", "")
            for step in doc_steps
        )
        assert (
            has_setup_action
        ), "Documentation-check job must use setup-system composite action"

        # Check build-check job
        build_job = jobs.get("build-check", {})
        build_steps = build_job.get("steps", [])
        has_setup_action = any(
            "./.github/actions/setup-system" in step.get("uses", "")
            for step in build_steps
        )
        assert (
            has_setup_action
        ), "Build-check job must use setup-system composite action"

    def test_security_workflow_consistency(
        self, security_scan_workflow: dict[str, Any]
    ):
        """
        Verify that security scan workflow is consistent with project standards.
        """
        jobs = security_scan_workflow.get("jobs", {})
        assert (
            "security-check" in jobs
        ), "Security workflow must have security-check job"

        # Check security-check job uses setup-system action
        security_job = jobs.get("security-check", {})
        security_steps = security_job.get("steps", [])
        has_setup_action = any(
            "./.github/actions/setup-system" in step.get("uses", "")
            for step in security_steps
        )
        assert (
            has_setup_action
        ), "Security-check job must use setup-system composite action"

    def test_ci_workflow_all_extras_consistency(self, ci_workflow: dict[str, Any]):
        """
        Verify that all dependency installation commands in CI workflow
        use the --all-extras flag for consistency.

        **Validates: Requirements 1.5**
        """
        install_commands = self.extract_install_commands(ci_workflow)

        # Verify at least one install command exists
        assert (
            len(install_commands) > 0
        ), "CI workflow must have dependency installation commands"

        # Verify all install commands use --all-extras
        for cmd in install_commands:
            assert (
                "--all-extras" in cmd
            ), f"Install command must use --all-extras flag: {cmd}"

    def test_ci_workflow_triggers_correctly(self, ci_workflow: dict[str, Any]):
        """
        Verify that CI workflow has appropriate triggers for continuous integration.

        CI should trigger on:
        - Push to main, develop, and feature branches
        - Pull requests to main and develop
        - Manual workflow dispatch
        """
        triggers = ci_workflow.get("on", {})

        # Verify push triggers
        assert "push" in triggers, "CI workflow must trigger on push"
        push_branches = triggers["push"].get("branches", [])
        assert "main" in push_branches, "CI must trigger on push to main"
        assert "develop" in push_branches, "CI must trigger on push to develop"

        # Verify PR triggers
        assert "pull_request" in triggers, "CI workflow must trigger on pull requests"
        pr_branches = triggers["pull_request"].get("branches", [])
        assert "main" in pr_branches, "CI must trigger on PRs to main"
        assert "develop" in pr_branches, "CI must trigger on PRs to develop"

        # Verify manual dispatch
        assert (
            "workflow_dispatch" in triggers
        ), "CI workflow must support manual dispatch"
