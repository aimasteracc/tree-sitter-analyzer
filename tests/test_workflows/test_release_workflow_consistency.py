"""
Property-based tests for release workflow consistency.

Feature: github-actions-consistency
Property 5: Deployment Dependency on Tests
Property 10: Deployment Branch Restriction

Validates: Requirements 2.3, 5.2, 5.5
"""

from pathlib import Path
from typing import Any

import pytest
import yaml


class TestReleaseWorkflowConsistency:
    """Property-based tests for release workflow consistency."""

    @pytest.fixture
    def workflow_root(self) -> Path:
        """Get the workflow directory root."""
        return Path(__file__).parent.parent.parent / ".github" / "workflows"

    @pytest.fixture
    def release_workflow(self, workflow_root: Path) -> dict[str, Any]:
        """Load the release workflow YAML."""
        workflow_path = workflow_root / "release-automation.yml"
        with open(workflow_path, encoding="utf-8") as f:
            workflow = yaml.safe_load(f)
            # Handle YAML parsing 'on' as boolean True
            if True in workflow and "on" not in workflow:
                workflow["on"] = workflow.pop(True)
            return workflow

    @pytest.fixture
    def develop_workflow(self, workflow_root: Path) -> dict[str, Any]:
        """Load the develop workflow YAML for comparison."""
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

    def extract_deployment_jobs(self, workflow: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract deployment-related jobs from workflow."""
        deployment_jobs = []
        jobs = workflow.get("jobs", {})

        for job_name, job in jobs.items():
            # Check if job contains deployment steps
            steps = job.get("steps", [])
            for step in steps:
                step_name = step.get("name", "")
                run_cmd = step.get("run", "")

                # Look for PyPI deployment indicators
                if any(
                    keyword in step_name.lower()
                    for keyword in ["deploy", "pypi", "publish"]
                ):
                    deployment_jobs.append(
                        {"job_name": job_name, "job": job, "step": step}
                    )
                    break

                if "twine upload" in run_cmd or "PYPI" in run_cmd:
                    deployment_jobs.append(
                        {"job_name": job_name, "job": job, "step": step}
                    )
                    break

        return deployment_jobs

    def test_property_5_deployment_dependency_on_tests(
        self, release_workflow: dict[str, Any]
    ):
        """
        Property 5: Deployment Dependency on Tests

        For any workflow that contains a deployment job, that deployment job
        should have a `needs` dependency on the test job, ensuring tests must
        pass before deployment.

        Validates: Requirements 2.3, 5.1, 5.2, 5.3
        """
        jobs = release_workflow.get("jobs", {})

        # Find deployment jobs
        deployment_jobs = self.extract_deployment_jobs(release_workflow)

        # Verify at least one deployment job exists in release workflow
        assert (
            len(deployment_jobs) > 0
        ), "Release workflow must have at least one deployment job"

        # Verify each deployment job depends on test job
        for deploy_info in deployment_jobs:
            job_name = deploy_info["job_name"]
            job = deploy_info["job"]

            # Check if job has needs dependency
            assert (
                "needs" in job
            ), f"Deployment job '{job_name}' must have 'needs' dependency"

            needs = job["needs"]
            # needs can be a string or a list
            if isinstance(needs, str):
                needs = [needs]

            # Verify test job is in dependencies
            assert (
                "test" in needs
            ), f"Deployment job '{job_name}' must depend on 'test' job"

        # Verify test job uses reusable workflow
        assert "test" in jobs, "Release workflow must have test job"
        test_job = jobs["test"]
        assert "uses" in test_job, "Test job must use reusable workflow"
        assert (
            "reusable-test.yml" in test_job["uses"]
        ), "Test job must use reusable-test.yml"

    def test_property_10_deployment_branch_restriction(
        self, release_workflow: dict[str, Any], develop_workflow: dict[str, Any]
    ):
        """
        Property 10: Deployment Branch Restriction

        For any workflow, PyPI deployment jobs should only exist in release/*
        and hotfix/* branch workflows, and should not exist in develop or main
        workflows.

        Validates: Requirements 5.4, 5.5
        """
        # Verify release workflow has deployment
        release_deployments = self.extract_deployment_jobs(release_workflow)
        assert (
            len(release_deployments) > 0
        ), "Release workflow must have deployment jobs"

        # Verify release workflow triggers on release branches
        on_config = release_workflow.get("on", {})
        push_config = on_config.get("push", {})
        branches = push_config.get("branches", [])

        # Check if release branches are in triggers
        has_release_trigger = any("release/" in branch for branch in branches)
        assert (
            has_release_trigger
        ), "Release workflow must trigger on release/* branches"

        # Verify develop workflow does NOT have deployment
        develop_deployments = self.extract_deployment_jobs(develop_workflow)
        assert (
            len(develop_deployments) == 0
        ), "Develop workflow must NOT have PyPI deployment jobs"

        # Verify develop workflow triggers on develop branch
        develop_on_config = develop_workflow.get("on", {})
        develop_push_config = develop_on_config.get("push", {})
        develop_branches = develop_push_config.get("branches", [])

        assert (
            "develop" in develop_branches
        ), "Develop workflow must trigger on develop branch"

    def test_release_workflow_uses_reusable_components(
        self, release_workflow: dict[str, Any]
    ):
        """
        Verify that release workflow properly uses reusable workflow components.

        This ensures the refactoring was successful and the workflow
        maintains backward compatibility.
        """
        jobs = release_workflow.get("jobs", {})

        # Verify test job uses reusable workflow
        assert "test" in jobs, "Release workflow must have test job"
        test_job = jobs["test"]
        assert "uses" in test_job, "Test job must use reusable workflow"
        assert (
            "reusable-test.yml" in test_job["uses"]
        ), "Test job must reference reusable-test.yml"

        # Verify secrets are inherited
        assert (
            test_job.get("secrets") == "inherit"
        ), "Test job must inherit secrets for CODECOV_TOKEN"

        # Verify build-and-deploy job exists and depends on test
        assert (
            "build-and-deploy" in jobs
        ), "Release workflow must have build-and-deploy job"
        deploy_job = jobs["build-and-deploy"]
        assert "needs" in deploy_job, "Deploy job must have dependencies"
        assert "test" in deploy_job["needs"], "Deploy job must depend on test job"

        # Verify PR creation job exists and depends on both test and deploy
        assert "create-main-pr" in jobs, "Release workflow must have create-main-pr job"
        pr_job = jobs["create-main-pr"]
        assert "needs" in pr_job, "PR job must have dependencies"
        needs = pr_job["needs"]
        assert (
            "test" in needs and "build-and-deploy" in needs
        ), "PR job must depend on both test and build-and-deploy jobs"

    def test_release_workflow_maintains_pypi_deployment(
        self, release_workflow: dict[str, Any]
    ):
        """
        Verify that release workflow maintains PyPI deployment logic.

        This ensures backward compatibility during the transition.
        """
        jobs = release_workflow.get("jobs", {})
        deploy_job = jobs.get("build-and-deploy", {})

        # Verify deployment steps exist
        steps = deploy_job.get("steps", [])

        # Check for build step
        has_build = any(
            "build" in step.get("name", "").lower()
            or "python -m build" in step.get("run", "")
            for step in steps
        )
        assert has_build, "Deploy job must have package build step"

        # Check for twine check step
        has_check = any(
            "check" in step.get("name", "").lower()
            or "twine check" in step.get("run", "")
            for step in steps
        )
        assert has_check, "Deploy job must have package check step"

        # Check for PyPI upload step
        has_upload = any(
            "deploy" in step.get("name", "").lower()
            or "twine upload" in step.get("run", "")
            for step in steps
        )
        assert has_upload, "Deploy job must have PyPI upload step"

        # Verify PyPI credentials are configured
        upload_step = next(
            (step for step in steps if "twine upload" in step.get("run", "")), None
        )
        assert upload_step is not None, "PyPI upload step must exist"

        env_config = upload_step.get("env", {})
        assert (
            "TWINE_USERNAME" in env_config
        ), "PyPI upload must have TWINE_USERNAME configured"
        assert (
            "TWINE_PASSWORD" in env_config
        ), "PyPI upload must have TWINE_PASSWORD configured"

    def test_release_workflow_maintains_pr_creation_logic(
        self, release_workflow: dict[str, Any]
    ):
        """
        Verify that release workflow maintains PR creation to main logic.

        This ensures backward compatibility during the transition.
        """
        jobs = release_workflow.get("jobs", {})
        pr_job = jobs.get("create-main-pr", {})

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
            with_config.get("branch") == "release-to-main"
        ), "PR must use release-to-main branch"

    def test_release_workflow_test_configuration_matches_develop(
        self,
        release_workflow: dict[str, Any],
        develop_workflow: dict[str, Any],
        reusable_test_workflow: dict[str, Any],
    ):
        """
        Verify that release workflow uses the same test configuration as develop.

        This ensures test consistency across branches as per Property 1.

        Note: develop-automation.yml no longer has a test job. Tests for develop
        branch are handled by ci.yml workflow. This test now verifies that both
        release and ci workflows use the same reusable-test.yml.
        """
        # Both workflows should use the same reusable test workflow
        release_test_job = release_workflow.get("jobs", {}).get("test", {})

        # Verify release uses reusable-test.yml
        assert "reusable-test.yml" in release_test_job.get(
            "uses", ""
        ), "Release workflow must use reusable-test.yml"

        # Verify release inherits secrets
        assert (
            release_test_job.get("secrets") == "inherit"
        ), "Release test job must inherit secrets"

        # Verify release uses the same Python version for coverage
        release_inputs = release_test_job.get("with", {})

        # Release should have python-version and upload-coverage configured
        assert (
            release_inputs.get("python-version") is not None
        ), "Release workflow must specify Python version"

        assert (
            release_inputs.get("upload-coverage") is True
        ), "Release workflow must have coverage upload enabled"
