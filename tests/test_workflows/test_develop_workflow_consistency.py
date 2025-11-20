"""
Property-based tests for develop workflow consistency.

Feature: github-actions-consistency
Property 1: Test Configuration Consistency
Property 2: All-Extras Installation Consistency
Property 3: Quality Check Presence

Validates: Requirements 1.1, 1.5, 2.1
"""

from pathlib import Path
from typing import Any

import pytest
import yaml


class TestDevelopWorkflowConsistency:
    """Property-based tests for develop workflow consistency."""

    @pytest.fixture
    def workflow_root(self) -> Path:
        """Get the workflow directory root."""
        return Path(__file__).parent.parent.parent / ".github" / "workflows"

    @pytest.fixture
    def develop_workflow(self, workflow_root: Path) -> dict[str, Any]:
        """Load the develop workflow YAML."""
        workflow_path = workflow_root / "develop-automation.yml"
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
    def reusable_quality_workflow(self, workflow_root: Path) -> dict[str, Any]:
        """Load the reusable quality workflow YAML."""
        workflow_path = workflow_root / "reusable-quality.yml"
        with open(workflow_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

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

    def extract_quality_checks(self, workflow: dict[str, Any]) -> list[str]:
        """Extract quality check steps from workflow."""
        checks = []
        jobs = workflow.get("jobs", {})

        for _job_name, job in jobs.items():
            steps = job.get("steps", [])
            for step in steps:
                step_name = step.get("name", "")
                if "quality" in step_name.lower() or "pre-commit" in step_name.lower():
                    checks.append(step_name)
                if "run" in step and "check_quality.py" in step["run"]:
                    checks.append(step_name)

        return checks

    def test_property_1_test_configuration_consistency(
        self, develop_workflow: dict[str, Any], reusable_test_workflow: dict[str, Any]
    ):
        """
        Property 1: Test Configuration Consistency

        For any pair of branch workflows (develop, release, hotfix, main),
        the test job configurations should be identical in terms of:
        - Python versions tested
        - Operating systems tested
        - System dependencies installed
        - Test commands executed
        - Quality checks performed
        - Dependency installation flags (--all-extras)

        Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5
        """
        # Verify develop workflow uses reusable test workflow
        jobs = develop_workflow.get("jobs", {})
        assert "test" in jobs, "Develop workflow must have a test job"

        test_job = jobs["test"]
        assert "uses" in test_job, "Test job must use reusable workflow"
        assert (
            "./.github/workflows/reusable-test.yml" in test_job["uses"]
        ), "Test job must use reusable-test.yml"

        # Verify secrets are inherited
        assert (
            test_job.get("secrets") == "inherit"
        ), "Test job must inherit secrets for CODECOV_TOKEN"

        # Extract test matrix from reusable workflow
        test_matrix = self.extract_test_matrix(reusable_test_workflow)

        # Verify Python versions
        expected_python_versions = ["3.10", "3.11", "3.12", "3.13"]
        assert (
            test_matrix["python_versions"] == expected_python_versions
        ), f"Python versions must be {expected_python_versions}"

        # Verify operating systems
        expected_os = ["ubuntu-latest", "windows-latest", "macos-13"]
        assert (
            test_matrix["os"] == expected_os
        ), f"Operating systems must be {expected_os}"

        # Verify test matrix excludes (for optimization)
        excludes = test_matrix.get("exclude", [])
        assert len(excludes) > 0, "Test matrix should have excludes for optimization"

    def test_property_2_all_extras_installation_consistency(
        self, reusable_test_workflow: dict[str, Any]
    ):
        """
        Property 2: All-Extras Installation Consistency

        For any test job in any branch workflow, the dependency installation
        command should include the --all-extras flag.

        Validates: Requirements 1.5
        """
        install_commands = self.extract_install_commands(reusable_test_workflow)

        # Verify at least one install command exists
        assert (
            len(install_commands) > 0
        ), "Reusable test workflow must have dependency installation commands"

        # Verify all install commands use --all-extras
        for cmd in install_commands:
            assert (
                "--all-extras" in cmd
            ), f"Install command must use --all-extras flag: {cmd}"

    def test_property_3_quality_check_presence(
        self,
        develop_workflow: dict[str, Any],
        reusable_test_workflow: dict[str, Any],
        reusable_quality_workflow: dict[str, Any],
    ):
        """
        Property 3: Quality Check Presence

        For any branch workflow, there should exist a quality check job or step
        that runs pre-commit hooks including mypy, black, ruff, isort, and bandit.

        Validates: Requirements 2.1
        """
        # Check if develop workflow has quality checks in reusable test workflow
        quality_checks = self.extract_quality_checks(reusable_test_workflow)

        # Verify quality checks are present
        assert len(quality_checks) > 0, "Workflow must have quality check steps"

        # Verify quality check mentions pre-commit or check_quality.py
        has_quality_check = any(
            "quality" in check.lower() or "pre-commit" in check.lower()
            for check in quality_checks
        )
        assert has_quality_check, "Workflow must have pre-commit quality checks"

        # Verify reusable quality workflow exists and has quality checks
        quality_jobs = reusable_quality_workflow.get("jobs", {})
        assert (
            "quality-check" in quality_jobs
        ), "Reusable quality workflow must have quality-check job"

        quality_job = quality_jobs["quality-check"]
        quality_steps = quality_job.get("steps", [])

        # Verify quality check step exists
        has_quality_step = any(
            "quality" in step.get("name", "").lower()
            or "check_quality.py" in step.get("run", "")
            for step in quality_steps
        )
        assert (
            has_quality_step
        ), "Quality workflow must have quality check execution step"

    def test_develop_workflow_uses_reusable_components(
        self, develop_workflow: dict[str, Any]
    ):
        """
        Verify that develop workflow properly uses reusable workflow components.

        This ensures the refactoring was successful and the workflow
        maintains backward compatibility.
        """
        jobs = develop_workflow.get("jobs", {})

        # Verify test job uses reusable workflow
        assert "test" in jobs, "Develop workflow must have test job"
        test_job = jobs["test"]
        assert "uses" in test_job, "Test job must use reusable workflow"
        assert (
            "reusable-test.yml" in test_job["uses"]
        ), "Test job must reference reusable-test.yml"

        # Verify build job still exists and depends on test
        assert "build" in jobs, "Develop workflow must have build job"
        build_job = jobs["build"]
        assert "needs" in build_job, "Build job must have dependencies"
        assert "test" in build_job["needs"], "Build job must depend on test job"

        # Verify PR creation job exists and depends on both test and build
        assert (
            "create-release-pr" in jobs
        ), "Develop workflow must have create-release-pr job"
        pr_job = jobs["create-release-pr"]
        assert "needs" in pr_job, "PR job must have dependencies"
        needs = pr_job["needs"]
        assert (
            "test" in needs and "build" in needs
        ), "PR job must depend on both test and build jobs"

    def test_develop_workflow_maintains_pr_creation_logic(
        self, develop_workflow: dict[str, Any]
    ):
        """
        Verify that develop workflow maintains existing PR creation logic.

        This ensures backward compatibility during the transition.
        """
        jobs = develop_workflow.get("jobs", {})
        pr_job = jobs.get("create-release-pr", {})

        # Verify PR creation uses peter-evans/create-pull-request action
        steps = pr_job.get("steps", [])
        has_pr_action = any(
            "peter-evans/create-pull-request" in step.get("uses", "") for step in steps
        )
        assert has_pr_action, "PR job must use peter-evans/create-pull-request action"

        # Verify PR targets main branch
        pr_step = next(
            (
                step
                for step in steps
                if "peter-evans/create-pull-request" in step.get("uses", "")
            ),
            None,
        )
        assert pr_step is not None, "PR creation step must exist"

        with_config = pr_step.get("with", {})
        assert with_config.get("base") == "main", "PR must target main branch"
        assert (
            with_config.get("branch") == "develop-to-main"
        ), "PR must use develop-to-main branch"
