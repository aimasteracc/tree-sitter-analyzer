"""
Property-based tests for hotfix workflow consistency.

Feature: github-actions-consistency
Property 5: Deployment Dependency on Tests
Property 8: Test Matrix Consistency

Validates: Requirements 2.3, 3.1, 3.2, 5.3
"""

from pathlib import Path
from typing import Any

import pytest
import yaml


class TestHotfixWorkflowConsistency:
    """Property-based tests for hotfix workflow consistency."""

    @pytest.fixture
    def workflow_root(self) -> Path:
        """Get the workflow directory root."""
        return Path(__file__).parent.parent.parent / ".github" / "workflows"

    @pytest.fixture
    def hotfix_workflow(self, workflow_root: Path) -> dict[str, Any]:
        """Load the hotfix workflow YAML."""
        workflow_path = workflow_root / "hotfix-automation.yml"
        with open(workflow_path, encoding="utf-8") as f:
            workflow = yaml.safe_load(f)
            # Handle YAML parsing 'on' as boolean True
            if True in workflow and "on" not in workflow:
                workflow["on"] = workflow.pop(True)
            return workflow

    @pytest.fixture
    def release_workflow(self, workflow_root: Path) -> dict[str, Any]:
        """Load the release workflow YAML for comparison."""
        workflow_path = workflow_root / "release-automation.yml"
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
        self, hotfix_workflow: dict[str, Any]
    ):
        """
        **Feature: github-actions-consistency, Property 5: Deployment Dependency on Tests**

        For any workflow that contains a deployment job, that deployment job
        should have a `needs` dependency on the test job, ensuring tests must
        pass before deployment.

        **Validates: Requirements 2.3, 5.3**
        """
        jobs = hotfix_workflow.get("jobs", {})

        # Find deployment jobs
        deployment_jobs = self.extract_deployment_jobs(hotfix_workflow)

        # Verify at least one deployment job exists in hotfix workflow
        assert (
            len(deployment_jobs) > 0
        ), "Hotfix workflow must have at least one deployment job"

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
        assert "test" in jobs, "Hotfix workflow must have test job"
        test_job = jobs["test"]
        assert "uses" in test_job, "Test job must use reusable workflow"
        assert (
            "reusable-test.yml" in test_job["uses"]
        ), "Test job must use reusable-test.yml"

    def test_property_8_test_matrix_consistency(
        self,
        hotfix_workflow: dict[str, Any],
        release_workflow: dict[str, Any],
        reusable_test_workflow: dict[str, Any],
    ):
        """
        **Feature: github-actions-consistency, Property 8: Test Matrix Consistency**

        For any pair of branch workflows, the test matrix (Python versions and
        operating systems) should be identical.

        **Validates: Requirements 3.1, 3.2**
        """
        # Both hotfix and release workflows should use the same reusable test workflow
        hotfix_test_job = hotfix_workflow.get("jobs", {}).get("test", {})
        release_test_job = release_workflow.get("jobs", {}).get("test", {})

        # Verify both use reusable-test.yml
        assert "reusable-test.yml" in hotfix_test_job.get(
            "uses", ""
        ), "Hotfix workflow must use reusable-test.yml"
        assert "reusable-test.yml" in release_test_job.get(
            "uses", ""
        ), "Release workflow must use reusable-test.yml"

        # Since both use the same reusable workflow, they inherit the same test matrix
        # Verify the reusable workflow has the expected test matrix
        reusable_jobs = reusable_test_workflow.get("jobs", {})
        test_matrix_job = reusable_jobs.get("test-matrix", {})

        assert (
            "strategy" in test_matrix_job
        ), "Reusable test workflow must have strategy configuration"

        strategy = test_matrix_job["strategy"]
        assert (
            "matrix" in strategy
        ), "Reusable test workflow must have matrix configuration"

        matrix = strategy["matrix"]

        # Verify Python versions
        expected_python_versions = ["3.10", "3.11", "3.12", "3.13"]
        actual_python_versions = matrix.get("python-version", [])
        assert (
            actual_python_versions == expected_python_versions
        ), f"Test matrix must include Python versions {expected_python_versions}"

        # Verify operating systems
        expected_os = ["ubuntu-latest", "windows-latest", "macos-latest"]
        actual_os = matrix.get("os", [])
        assert (
            actual_os == expected_os
        ), f"Test matrix must include operating systems {expected_os}"

    def test_hotfix_workflow_uses_reusable_components(
        self, hotfix_workflow: dict[str, Any]
    ):
        """
        Verify that hotfix workflow properly uses reusable workflow components.

        This ensures the refactoring was successful and the workflow
        maintains backward compatibility.
        """
        jobs = hotfix_workflow.get("jobs", {})

        # Verify test job uses reusable workflow
        assert "test" in jobs, "Hotfix workflow must have test job"
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
        ), "Hotfix workflow must have build-and-deploy job"
        deploy_job = jobs["build-and-deploy"]
        assert "needs" in deploy_job, "Deploy job must have dependencies"
        assert "test" in deploy_job["needs"], "Deploy job must depend on test job"

        # Verify PR creation job exists and depends on both test and deploy
        assert "create-main-pr" in jobs, "Hotfix workflow must have create-main-pr job"
        pr_job = jobs["create-main-pr"]
        assert "needs" in pr_job, "PR job must have dependencies"
        needs = pr_job["needs"]
        assert (
            "test" in needs and "build-and-deploy" in needs
        ), "PR job must depend on both test and build-and-deploy jobs"

    def test_hotfix_workflow_maintains_pypi_deployment(
        self, hotfix_workflow: dict[str, Any]
    ):
        """
        Verify that hotfix workflow maintains PyPI deployment logic.

        This ensures backward compatibility during the transition.
        """
        jobs = hotfix_workflow.get("jobs", {})
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

    def test_hotfix_workflow_maintains_pr_creation_logic(
        self, hotfix_workflow: dict[str, Any]
    ):
        """
        Verify that hotfix workflow maintains PR creation to main logic.

        This ensures backward compatibility during the transition.
        """
        jobs = hotfix_workflow.get("jobs", {})
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
            with_config.get("branch") == "hotfix-to-main"
        ), "PR must use hotfix-to-main branch"

    def test_hotfix_workflow_consistency_with_release(
        self, hotfix_workflow: dict[str, Any], release_workflow: dict[str, Any]
    ):
        """
        Verify that hotfix workflow configuration matches release workflow.

        This ensures consistency between hotfix and release workflows as per
        Requirement 1.3.
        """
        # Both workflows should use the same reusable test workflow
        hotfix_test_job = hotfix_workflow.get("jobs", {}).get("test", {})
        release_test_job = release_workflow.get("jobs", {}).get("test", {})

        # Verify both use reusable-test.yml
        assert "reusable-test.yml" in hotfix_test_job.get(
            "uses", ""
        ), "Hotfix workflow must use reusable-test.yml"
        assert "reusable-test.yml" in release_test_job.get(
            "uses", ""
        ), "Release workflow must use reusable-test.yml"

        # Verify both inherit secrets
        assert (
            hotfix_test_job.get("secrets") == "inherit"
        ), "Hotfix test job must inherit secrets"
        assert (
            release_test_job.get("secrets") == "inherit"
        ), "Release test job must inherit secrets"

        # Verify both use the same Python version for coverage
        hotfix_inputs = hotfix_test_job.get("with", {})
        release_inputs = release_test_job.get("with", {})

        assert hotfix_inputs.get("python-version") == release_inputs.get(
            "python-version"
        ), "Hotfix and release workflows must use same Python version"

        assert hotfix_inputs.get("upload-coverage") == release_inputs.get(
            "upload-coverage"
        ), "Hotfix and release workflows must have same coverage upload setting"

        # Verify both have the same job structure
        hotfix_jobs = set(hotfix_workflow.get("jobs", {}).keys())
        release_jobs = set(release_workflow.get("jobs", {}).keys())

        assert (
            hotfix_jobs == release_jobs
        ), f"Hotfix and release workflows must have same jobs. Hotfix: {hotfix_jobs}, Release: {release_jobs}"

    def test_hotfix_workflow_triggers_on_hotfix_branches(
        self, hotfix_workflow: dict[str, Any]
    ):
        """
        Verify that hotfix workflow triggers on hotfix/* branches.

        This ensures the workflow is properly configured for hotfix branches.
        """
        on_config = hotfix_workflow.get("on", {})
        push_config = on_config.get("push", {})
        branches = push_config.get("branches", [])

        # Check if hotfix branches are in triggers
        has_hotfix_trigger = any("hotfix/" in branch for branch in branches)
        assert has_hotfix_trigger, "Hotfix workflow must trigger on hotfix/* branches"

        # Verify workflow_dispatch is also available
        assert (
            "workflow_dispatch" in on_config
        ), "Hotfix workflow must support manual dispatch"
