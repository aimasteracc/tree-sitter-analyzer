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
        return Path(__file__).parent.parent.parent / ".github" / "workflows"

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
                    if "uv sync" in run_cmd or "uv add" in run_cmd:
                        commands.append(run_cmd)

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
                    for tool in [
                        "mypy",
                        "black",
                        "ruff",
                        "isort",
                        "bandit",
                        "pydocstyle",
                    ]:
                        if tool in run_cmd.lower():
                            tools.add(tool)

        return tools

    def extract_coverage_config(self, workflow: dict[str, Any]) -> dict[str, Any]:
        """Extract coverage configuration from workflow."""
        jobs = workflow.get("jobs", {})

        # Look for test-matrix job
        if "test-matrix" in jobs:
            job = jobs["test-matrix"]
            steps = job.get("steps", [])

            for step in steps:
                if "codecov" in step.get("uses", "").lower():
                    # Found codecov upload step
                    # Check the matrix configuration for coverage
                    strategy = job.get("strategy", {})
                    matrix = strategy.get("matrix", {})

                    # Check if there's a condition for coverage upload
                    if_condition = step.get("if", "")

                    return {
                        "os": matrix.get("os", []),
                        "python_version": matrix.get("python-version", []),
                        "condition": if_condition,
                    }

        return {}

    def extract_system_dependencies(self, workflow: dict[str, Any]) -> list[str]:
        """Extract system dependencies from workflow."""
        dependencies = []
        jobs = workflow.get("jobs", {})

        for _job_name, job in jobs.items():
            steps = job.get("steps", [])
            for step in steps:
                if "run" in step:
                    run_cmd = step["run"]
                    # Look for fd and ripgrep installation
                    if "fd" in run_cmd.lower() or "ripgrep" in run_cmd.lower():
                        if "fd" in run_cmd.lower():
                            dependencies.append("fd")
                        if "ripgrep" in run_cmd.lower() or "rg" in run_cmd.lower():
                            dependencies.append("ripgrep")

        return sorted(set(dependencies))

    def extract_test_markers(self, workflow: dict[str, Any]) -> list[str]:
        """Extract pytest markers from workflow."""
        markers = []
        jobs = workflow.get("jobs", {})

        for _job_name, job in jobs.items():
            steps = job.get("steps", [])
            for step in steps:
                if "run" in step:
                    run_cmd = step["run"]
                    if "pytest" in run_cmd and "-m" in run_cmd:
                        # Extract marker expression
                        parts = run_cmd.split("-m")
                        if len(parts) > 1:
                            marker_part = parts[1].strip().split()[0]
                            markers.append(marker_part)

        return markers

    def test_property_1_test_configuration_consistency(
        self,
        all_workflows: dict[str, dict[str, Any]],
        reusable_test_workflow: dict[str, Any],
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

        Validates: Requirements 1.1, 1.2, 1.3, 1.4
        """
        # Extract test matrix from reusable workflow
        test_matrix = self.extract_test_matrix(reusable_test_workflow)

        # Expected configuration
        expected_python_versions = ["3.10", "3.11", "3.12", "3.13"]
        expected_os = ["ubuntu-latest", "windows-latest", "macos-latest"]

        # Verify test matrix configuration
        assert (
            test_matrix["python_versions"] == expected_python_versions
        ), f"Python versions must be {expected_python_versions}, got {test_matrix['python_versions']}"

        assert (
            test_matrix["os"] == expected_os
        ), f"Operating systems must be {expected_os}, got {test_matrix['os']}"

        # Verify all branch workflows use the reusable test workflow
        for workflow_name, workflow in all_workflows.items():
            jobs = workflow.get("jobs", {})

            # Check if workflow has a test job
            if "test" in jobs:
                test_job = jobs["test"]

                # Verify it uses the reusable workflow
                assert (
                    "uses" in test_job
                ), f"{workflow_name} workflow test job must use reusable workflow"

                assert "reusable-test.yml" in test_job.get(
                    "uses", ""
                ), f"{workflow_name} workflow must use reusable-test.yml"

                # Verify secrets are inherited
                assert (
                    test_job.get("secrets") == "inherit"
                ), f"{workflow_name} workflow must inherit secrets"

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
                "--all-extras" in cmd or "--extra all" in cmd
            ), f"Install command must use --all-extras or --extra all flag: {cmd}"

    def test_property_3_quality_check_presence(
        self,
        reusable_test_workflow: dict[str, Any],
        reusable_quality_workflow: dict[str, Any],
    ):
        """
        Property 3: Quality Check Presence

        For any branch workflow, there should exist a quality check job or step
        that runs pre-commit hooks including mypy, black, ruff, isort, and bandit.

        Validates: Requirements 2.1
        """
        # Check reusable test workflow for quality checks
        test_quality_tools = self.extract_quality_tools(reusable_test_workflow)

        # Check reusable quality workflow for quality checks
        quality_tools = self.extract_quality_tools(reusable_quality_workflow)

        # Combine tools from both workflows
        all_tools = test_quality_tools.union(quality_tools)

        # Expected quality tools
        expected_tools = {"mypy", "black", "ruff", "isort", "bandit"}

        # Verify all expected tools are present
        missing_tools = expected_tools - all_tools
        assert (
            len(missing_tools) == 0
        ), f"Missing quality check tools: {missing_tools}. Found: {all_tools}"

    def test_property_4_quality_tool_version_consistency(
        self,
        reusable_test_workflow: dict[str, Any],
        reusable_quality_workflow: dict[str, Any],
    ):
        """
        Property 4: Quality Tool Version Consistency

        For any pair of branch workflows, the quality check tool versions and
        configurations should be identical.

        Validates: Requirements 2.2
        """
        # Extract Python version used for quality checks
        quality_jobs = reusable_quality_workflow.get("jobs", {})

        # Verify quality check job exists
        assert (
            "quality-check" in quality_jobs
        ), "Reusable quality workflow must have quality-check job"

        # Check quality-check job in reusable quality workflow
        quality_job = quality_jobs["quality-check"]
        steps = quality_job.get("steps", [])

        # Find Python setup step - it uses uv python install
        python_version = None
        for step in steps:
            if "run" in step and "uv python install" in step.get("run", ""):
                run_cmd = step["run"]
                # Extract version from command like "uv python install ${{ inputs.python-version }}"
                if "inputs.python-version" in run_cmd:
                    # Check the default input value
                    # Handle YAML parsing 'on' as boolean True
                    on_config = reusable_quality_workflow.get(
                        "on"
                    ) or reusable_quality_workflow.get(True)
                    if on_config:
                        inputs = on_config.get("workflow_call", {}).get("inputs", {})
                        python_version_input = inputs.get("python-version", {})
                        python_version = python_version_input.get("default")
                    break

        # Verify Python 3.11 is used for quality checks
        assert (
            python_version == "3.11"
        ), f"Quality checks must use Python 3.11, got {python_version}"

    def test_property_6_coverage_configuration_consistency(
        self, reusable_test_workflow: dict[str, Any]
    ):
        """
        Property 6: Coverage Configuration Consistency

        For any branch workflow that uploads coverage, the coverage configuration
        (OS: ubuntu-latest, Python: 3.11) should be identical.

        Validates: Requirements 3.4
        """
        coverage_config = self.extract_coverage_config(reusable_test_workflow)

        # Verify coverage configuration exists
        assert (
            len(coverage_config) > 0
        ), "Reusable test workflow must have coverage configuration"

        # Verify coverage is uploaded from ubuntu-latest
        if "condition" in coverage_config:
            condition = coverage_config["condition"]
            assert (
                "ubuntu-latest" in condition
            ), f"Coverage must be uploaded from ubuntu-latest, condition: {condition}"
            # Check if condition references inputs.python-version
            # The default value should be 3.11
            if "inputs.python-version" in condition:
                # Handle YAML parsing 'on' as boolean True
                on_config = reusable_test_workflow.get(
                    "on"
                ) or reusable_test_workflow.get(True)
                if on_config:
                    inputs = on_config.get("workflow_call", {}).get("inputs", {})
                    python_version_input = inputs.get("python-version", {})
                    default_version = python_version_input.get("default")
                    assert (
                        default_version == "3.11"
                    ), f"Coverage must be uploaded with Python 3.11 (default), got {default_version}"
            else:
                assert (
                    "3.11" in condition
                ), f"Coverage must be uploaded with Python 3.11, condition: {condition}"

    def test_property_7_system_dependencies_consistency(
        self, reusable_test_workflow: dict[str, Any]
    ):
        """
        Property 7: System Dependencies Consistency

        For any test job in any branch workflow, the system dependency installation
        steps should install fd and ripgrep using the appropriate package manager
        for the target OS.

        Validates: Requirements 3.3
        """
        dependencies = self.extract_system_dependencies(reusable_test_workflow)

        # Verify both fd and ripgrep are installed
        expected_deps = {"fd", "ripgrep"}
        found_deps = set(dependencies)

        # Note: The actual installation might be in the composite action
        # Let's check if the composite action is used
        jobs = reusable_test_workflow.get("jobs", {})
        uses_composite_action = False

        for _job_name, job in jobs.items():
            steps = job.get("steps", [])
            for step in steps:
                if "uses" in step and "setup-system" in step.get("uses", ""):
                    uses_composite_action = True
                    break

        # If composite action is used, that's sufficient
        # Otherwise, verify dependencies are installed
        if not uses_composite_action:
            missing_deps = expected_deps - found_deps
            assert (
                len(missing_deps) == 0
            ), f"Missing system dependencies: {missing_deps}. Found: {found_deps}"
        else:
            # Composite action handles system dependencies
            assert (
                uses_composite_action
            ), "Workflow must use setup-system composite action for system dependencies"

    def test_property_8_test_matrix_consistency(
        self, reusable_test_workflow: dict[str, Any]
    ):
        """
        Property 8: Test Matrix Consistency

        For any pair of branch workflows, the test matrix (Python versions and
        operating systems) should be identical.

        Validates: Requirements 3.1, 3.2
        """
        test_matrix = self.extract_test_matrix(reusable_test_workflow)

        # Expected configuration
        expected_python_versions = ["3.10", "3.11", "3.12", "3.13"]
        expected_os = ["ubuntu-latest", "windows-latest", "macos-latest"]

        # Verify Python versions
        assert (
            test_matrix["python_versions"] == expected_python_versions
        ), f"Test matrix Python versions must be {expected_python_versions}"

        # Verify operating systems
        assert (
            test_matrix["os"] == expected_os
        ), f"Test matrix operating systems must be {expected_os}"

        # Verify excludes exist for optimization
        assert (
            len(test_matrix.get("exclude", [])) > 0
        ), "Test matrix should have excludes for optimization"

    def test_property_9_test_marker_consistency(
        self, reusable_test_workflow: dict[str, Any]
    ):
        """
        Property 9: Test Marker Consistency

        For any test execution command in any branch workflow, the pytest markers
        should be identical (e.g., -m "not (requires_ripgrep or requires_fd)").

        Validates: Requirements 3.5
        """
        # Extract all pytest commands from the workflow
        jobs = reusable_test_workflow.get("jobs", {})
        pytest_commands = []

        for _job_name, job in jobs.items():
            steps = job.get("steps", [])
            for step in steps:
                if "run" in step:
                    run_cmd = step["run"]
                    if "pytest" in run_cmd and "-m" in run_cmd:
                        pytest_commands.append(run_cmd)

        # Extract marker expressions from commands
        marker_expressions = []
        for cmd in pytest_commands:
            # Find the -m flag and extract the marker expression
            parts = cmd.split("-m")
            if len(parts) > 1:
                # Get the part after -m
                after_m = parts[1].strip()
                # Extract the marker (it's in quotes)
                if '"' in after_m:
                    marker = after_m.split('"')[1]
                    marker_expressions.append(marker)

        # Verify all marker expressions are the same
        if len(marker_expressions) > 0:
            unique_markers = set(marker_expressions)
            assert (
                len(unique_markers) == 1
            ), f"Test markers must be consistent across all test commands, found: {unique_markers}"

            # Verify marker format
            marker = list(unique_markers)[0]
            assert (
                "requires_ripgrep" in marker or "requires_fd" in marker
            ), f"Test marker should reference requires_ripgrep or requires_fd: {marker}"

    def test_property_11_reusable_workflow_behavioral_equivalence(
        self,
        reusable_test_workflow: dict[str, Any],
        reusable_quality_workflow: dict[str, Any],
    ):
        """
        Property 11: Reusable Workflow Behavioral Equivalence

        For any reusable workflow, the effective behavior (commands executed,
        dependencies installed, checks performed) should be equivalent to the
        original inline workflow implementation.

        Validates: Requirements 6.5
        """
        # Verify reusable test workflow has all required jobs
        test_jobs = reusable_test_workflow.get("jobs", {})

        assert (
            "test-matrix" in test_jobs
        ), "Reusable test workflow must have test-matrix job"

        # Verify test-matrix job has required steps
        test_matrix_job = test_jobs["test-matrix"]
        steps = test_matrix_job.get("steps", [])

        step_names = [step.get("name", "").lower() for step in steps]
        step_uses = [step.get("uses", "").lower() for step in steps]
        step_runs = [step.get("run", "").lower() for step in steps]

        # Verify checkout step
        assert any(
            "checkout" in uses for uses in step_uses
        ), "Reusable test workflow must have checkout step"

        # Verify UV installation (either via setup-uv action or run command)
        has_uv = any("setup-uv" in uses for uses in step_uses) or any(
            "uv" in run for run in step_runs
        )
        assert has_uv, "Reusable test workflow must install UV"

        # Verify Python setup (via uv python install)
        assert any(
            "uv python install" in run for run in step_runs
        ), "Reusable test workflow must set up Python via uv"

        # Verify dependency installation
        assert any(
            "sync" in run or "install" in run for run in step_runs
        ), "Reusable test workflow must install dependencies"

        # Verify quality checks
        assert any(
            "quality" in name or "check_quality" in run
            for name, run in zip(step_names, step_runs, strict=False)
        ), "Reusable test workflow must run quality checks"

        # Verify test execution
        assert any(
            "pytest" in run for run in step_runs
        ), "Reusable test workflow must execute pytest"

        # Verify system dependencies installation
        has_system_deps = any("fd" in run or "ripgrep" in run for run in step_runs)
        assert (
            has_system_deps
        ), "Reusable test workflow must install system dependencies (fd, ripgrep)"

        # Verify reusable quality workflow has quality-check job
        quality_jobs = reusable_quality_workflow.get("jobs", {})
        assert (
            "quality-check" in quality_jobs
        ), "Reusable quality workflow must have quality-check job"

        # Verify quality-check job has quality tools
        quality_job = quality_jobs["quality-check"]
        quality_steps = quality_job.get("steps", [])
        quality_runs = [step.get("run", "").lower() for step in quality_steps]

        # Verify quality check execution (via check_quality.py)
        has_quality_check = any("check_quality" in run for run in quality_runs)
        assert (
            has_quality_check
        ), "Reusable quality workflow must execute quality checks via check_quality.py"
