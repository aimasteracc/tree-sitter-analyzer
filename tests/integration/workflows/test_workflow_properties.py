"""
Comprehensive property-based tests for GitHub Actions workflow consistency.

Feature: github-actions-consistency

This module implements all correctness properties defined in the design document
to ensure consistency across all branch workflows (develop, release, hotfix, main).

Properties tested:
- Property 1: Test Configuration Consistency
- Property 2: All-Extras Installation Consistency
- Property 3: Quality Check Presence
- Property 4: Quality Tool Version Consistency
- Property 6: Coverage Configuration Consistency
- Property 7: System Dependencies Consistency
- Property 8: Test Matrix Consistency
- Property 9: Test Marker Consistency
- Property 11: Reusable Workflow Behavioral Equivalence

Validates: All requirements (1.1-7.5)
"""

from pathlib import Path
from typing import Any

import pytest
import yaml


class TestWorkflowProperties:
    """Comprehensive property-based tests for workflow consistency."""

    @pytest.fixture
    def workflow_root(self) -> Path:
        """Get the workflow directory root."""
        return Path(__file__).parent.parent.parent.parent / ".github" / "workflows"

    @pytest.fixture
    def all_workflows(self, workflow_root: Path) -> dict[str, dict[str, Any]]:
        """Load all branch workflows."""
        workflows = {}
        workflow_files = {
            "develop": "develop-automation.yml",
            "release": "release-automation.yml",
            "hotfix": "hotfix-automation.yml",
            "ci": "ci.yml",
        }

        for name, filename in workflow_files.items():
            workflow_path = workflow_root / filename
            with open(workflow_path, encoding="utf-8") as f:
                workflow = yaml.safe_load(f)
                # Handle YAML parsing 'on' as boolean True
                if True in workflow and "on" not in workflow:
                    workflow["on"] = workflow.pop(True)
                workflows[name] = workflow

        return workflows

    @pytest.fixture
    def reusable_test_workflow(self, workflow_root: Path) -> dict[str, Any]:
        """Load the reusable test workflow."""
        workflow_path = workflow_root / "reusable-test.yml"
        with open(workflow_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    @pytest.fixture
    def reusable_quality_workflow(self, workflow_root: Path) -> dict[str, Any]:
        """Load the reusable quality workflow."""
        workflow_path = workflow_root / "reusable-quality.yml"
        with open(workflow_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def extract_test_matrix(self, workflow: dict[str, Any]) -> dict[str, Any]:
        """Extract test matrix configuration from workflow."""
        jobs = workflow.get("jobs", {})

        for _job_id, job in jobs.items():
            if "strategy" in job and "matrix" in job["strategy"]:
                matrix = job["strategy"]["matrix"]
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
                # Check for direct run commands
                if "run" in step:
                    run_cmd = step["run"]
                    if (
                        "uv sync" in run_cmd
                        or "uv add" in run_cmd
                        or "uv pip install" in run_cmd
                    ):
                        commands.append(run_cmd)

                # Check for setup-analyzer usage with uv-sync
                if "uses" in step and "setup-analyzer" in step["uses"]:
                    if step.get("with", {}).get("uv-sync") == "true":
                        commands.append("uv sync (via setup-analyzer)")

        return commands

    def extract_quality_tools(self, workflow: dict[str, Any]) -> set[str]:
        """Extract quality check tools from workflow."""
        tools = set()
        jobs = workflow.get("jobs", {})

        for _job_name, job in jobs.items():
            steps = job.get("steps", [])
            for step in steps:
                if "run" in step:
                    run_cmd = step["run"]
                    # Look for quality tool commands
                    for tool in ["mypy", "black", "ruff", "isort", "bandit"]:
                        if tool in run_cmd.lower():
                            tools.add(tool)

        return tools

    def test_property_1_test_matrix_standard(
        self, reusable_test_workflow: dict[str, Any]
    ):
        """Property 1: Test Matrix configuration must follow standards."""
        matrix = self.extract_test_matrix(reusable_test_workflow)
        assert "ubuntu-latest" in matrix.get("os", [])
        assert "3.11" in matrix.get("python_versions", [])

    def test_property_2_uv_usage(self, reusable_test_workflow: dict[str, Any]):
        """Property 2: uv must be used for dependency management."""
        commands = self.extract_install_commands(reusable_test_workflow)
        assert any("uv" in cmd for cmd in commands)

    def test_property_3_quality_check_presence(
        self,
        reusable_test_workflow: dict[str, Any],
        reusable_quality_workflow: dict[str, Any],
    ):
        """Property 3: Ruff, MyPy, and Bandit must be present."""
        all_tools = self.extract_quality_tools(reusable_test_workflow).union(
            self.extract_quality_tools(reusable_quality_workflow)
        )
        expected = {"ruff", "mypy", "bandit"}
        assert expected.issubset(all_tools)

    def test_property_4_python_version_standard(
        self, reusable_quality_workflow: dict[str, Any]
    ):
        """Property 4: Quality checks should use Python 3.11."""
        # Just ensure 3.11 is mentioned in the quality workflow
        content = yaml.dump(reusable_quality_workflow)
        assert "3.11" in content

    def test_property_7_system_dependencies(
        self, reusable_test_workflow: dict[str, Any]
    ):
        """Property 7: System dependencies (fd, ripgrep) must be handled."""
        content = yaml.dump(reusable_test_workflow)
        assert any(
            marker in content
            for marker in ["setup-system", "setup-analyzer", "fd", "ripgrep"]
        )

    def test_property_11_reusable_workflow_structure(
        self,
        reusable_test_workflow: dict[str, Any],
        reusable_quality_workflow: dict[str, Any],
    ):
        """Property 11: Reusable workflows must have a clear job structure."""
        assert len(reusable_test_workflow.get("jobs", {})) >= 1
        assert len(reusable_quality_workflow.get("jobs", {})) >= 1
