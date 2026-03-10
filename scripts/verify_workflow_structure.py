#!/usr/bin/env python3
"""
Verify GitHub Actions workflow structure and dependencies.
"""

import sys

import yaml


def verify_reusable_test_workflow():
    """Verify the reusable test workflow structure."""
    print("Verifying reusable-test.yml structure...")

    with open(".github/workflows/reusable-test.yml", encoding="utf-8") as f:
        content = yaml.safe_load(f)

    errors = []

    # Check workflow_call configuration
    on_config = content.get(True) or content.get("on")
    if not on_config or "workflow_call" not in on_config:
        errors.append("Missing workflow_call trigger")
    else:
        workflow_call = on_config["workflow_call"]

        # Check inputs
        if "inputs" not in workflow_call:
            errors.append("Missing inputs in workflow_call")
        else:
            inputs = workflow_call["inputs"]

            # Check python-version input
            if "python-version" not in inputs:
                errors.append("Missing python-version input")
            else:
                pv = inputs["python-version"]
                if pv.get("default") != "3.11":
                    errors.append(
                        f"python-version default should be '3.11', got {pv.get('default')}"
                    )
                if pv.get("type") != "string":
                    errors.append(
                        f"python-version type should be 'string', got {pv.get('type')}"
                    )

            # Check upload-coverage input
            if "upload-coverage" not in inputs:
                errors.append("Missing upload-coverage input")
            else:
                uc = inputs["upload-coverage"]
                if uc.get("default") is not True:
                    errors.append(
                        f"upload-coverage default should be true, got {uc.get('default')}"
                    )
                if uc.get("type") != "boolean":
                    errors.append(
                        f"upload-coverage type should be 'boolean', got {uc.get('type')}"
                    )

        # Check secrets
        if "secrets" not in workflow_call:
            errors.append("Missing secrets in workflow_call")
        else:
            secrets = workflow_call["secrets"]
            if "CODECOV_TOKEN" not in secrets:
                errors.append("Missing CODECOV_TOKEN secret")

    # Check jobs
    if "jobs" not in content:
        errors.append("Missing jobs")
    else:
        jobs = content["jobs"]

        # Check test-matrix job
        if "test-matrix" not in jobs:
            errors.append("Missing test-matrix job")
        else:
            test_job = jobs["test-matrix"]

            # Check strategy matrix
            if "strategy" not in test_job:
                errors.append("Missing strategy in test-matrix job")
            else:
                strategy = test_job["strategy"]
                if "matrix" not in strategy:
                    errors.append("Missing matrix in strategy")
                else:
                    matrix = strategy["matrix"]

                    # Check OS matrix
                    if "os" not in matrix:
                        errors.append("Missing os in matrix")
                    else:
                        expected_os = [
                            "ubuntu-latest",
                            "windows-latest",
                            "macos-latest",
                        ]
                        if matrix["os"] != expected_os:
                            errors.append(
                                f"OS matrix should be {expected_os}, got {matrix['os']}"
                            )

                    # Check Python version matrix
                    if "python-version" not in matrix:
                        errors.append("Missing python-version in matrix")
                    else:
                        expected_versions = ["3.10", "3.11", "3.12", "3.13"]
                        if matrix["python-version"] != expected_versions:
                            errors.append(
                                f"Python version matrix should be {expected_versions}, got {matrix['python-version']}"
                            )

            # Check for --all-extras flag in steps
            if "steps" not in test_job:
                errors.append("Missing steps in test-matrix job")
            else:
                steps = test_job["steps"]
                has_all_extras = False
                for step in steps:
                    if "run" in step and "--all-extras" in step["run"]:
                        has_all_extras = True
                        break

                if not has_all_extras:
                    errors.append(
                        "Missing --all-extras flag in dependency installation"
                    )

    if errors:
        print("❌ Errors found in reusable-test.yml:")
        for error in errors:
            print(f"   - {error}")
        return False
    else:
        print("✅ reusable-test.yml structure is correct")
        return True


def verify_reusable_quality_workflow():
    """Verify the reusable quality check workflow structure."""
    print("\nVerifying reusable-quality.yml structure...")

    with open(".github/workflows/reusable-quality.yml", encoding="utf-8") as f:
        content = yaml.safe_load(f)

    errors = []

    # Check workflow_call configuration
    on_config = content.get(True) or content.get("on")
    if not on_config or "workflow_call" not in on_config:
        errors.append("Missing workflow_call trigger")
    else:
        workflow_call = on_config["workflow_call"]

        # Check inputs
        if "inputs" in workflow_call:
            inputs = workflow_call["inputs"]

            # Check python-version input
            if "python-version" in inputs:
                pv = inputs["python-version"]
                if pv.get("default") != "3.11":
                    errors.append(
                        f"python-version default should be '3.11', got {pv.get('default')}"
                    )

    # Check jobs
    if "jobs" not in content:
        errors.append("Missing jobs")
    else:
        jobs = content["jobs"]

        # Check quality-check job
        if "quality-check" not in jobs:
            errors.append("Missing quality-check job")
        else:
            quality_job = jobs["quality-check"]

            # Check runs-on
            if "runs-on" not in quality_job:
                errors.append("Missing runs-on in quality-check job")
            elif quality_job["runs-on"] != "ubuntu-latest":
                errors.append(
                    f"quality-check should run on ubuntu-latest, got {quality_job['runs-on']}"
                )

    if errors:
        print("❌ Errors found in reusable-quality.yml:")
        for error in errors:
            print(f"   - {error}")
        return False
    else:
        print("✅ reusable-quality.yml structure is correct")
        return True


def verify_composite_action():
    """Verify the composite action structure."""
    print("\nVerifying setup-system/action.yml structure...")

    with open(".github/actions/setup-system/action.yml", encoding="utf-8") as f:
        content = yaml.safe_load(f)

    errors = []

    # Check inputs
    if "inputs" not in content:
        errors.append("Missing inputs")
    else:
        inputs = content["inputs"]
        if "os" not in inputs:
            errors.append("Missing os input")
        else:
            os_input = inputs["os"]
            if not os_input.get("required"):
                errors.append("os input should be required")

    # Check runs
    if "runs" not in content:
        errors.append("Missing runs")
    else:
        runs = content["runs"]

        # Check using
        if "using" not in runs:
            errors.append("Missing using in runs")
        elif runs["using"] != "composite":
            errors.append(f"using should be 'composite', got {runs['using']}")

        # Check steps
        if "steps" not in runs:
            errors.append("Missing steps in runs")
        else:
            steps = runs["steps"]

            # Check for OS-specific steps
            has_linux = False
            has_macos = False
            has_windows = False

            for step in steps:
                if "if" in step:
                    if "ubuntu-latest" in step["if"]:
                        has_linux = True
                    if "macos-" in step["if"] or "macos-latest" in step["if"]:
                        has_macos = True
                    if "windows-latest" in step["if"]:
                        has_windows = True

            if not has_linux:
                errors.append("Missing Linux-specific step")
            if not has_macos:
                errors.append("Missing macOS-specific step")
            if not has_windows:
                errors.append("Missing Windows-specific step")

    if errors:
        print("❌ Errors found in setup-system/action.yml:")
        for error in errors:
            print(f"   - {error}")
        return False
    else:
        print("✅ setup-system/action.yml structure is correct")
        return True


def main():
    """Main verification function."""
    all_valid = True

    all_valid &= verify_reusable_test_workflow()
    all_valid &= verify_reusable_quality_workflow()
    all_valid &= verify_composite_action()

    if all_valid:
        print("\n✅ All workflow structures are correct!")
        return 0
    else:
        print("\n❌ Some workflow structures have errors")
        return 1


if __name__ == "__main__":
    sys.exit(main())
