"""Validation helpers for GitHub Actions workflow structure checks."""

from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: str) -> dict[Any, Any]:
    """Load a YAML file as a mapping."""
    with open(path, encoding="utf-8") as f:
        content = yaml.safe_load(f)
    return content if isinstance(content, dict) else {}


def print_result(label: str, success_message: str, errors: list[str]) -> bool:
    """Print validation errors or the success message."""
    if errors:
        print(f"❌ Errors found in {label}:")
        for error in errors:
            print(f"   - {error}")
        return False

    print(success_message)
    return True


def reusable_test_errors(content: dict[Any, Any]) -> list[str]:
    """Return reusable-test workflow structure errors."""
    errors: list[str] = []
    workflow_call = _workflow_call(content, errors)
    if workflow_call is not None:
        _check_reusable_test_inputs(workflow_call, errors)
        _check_reusable_test_secrets(workflow_call, errors)

    jobs = _jobs(content, errors)
    if jobs is not None:
        _check_test_matrix_job(jobs, errors)

    return errors


def reusable_quality_errors(content: dict[Any, Any]) -> list[str]:
    """Return reusable-quality workflow structure errors."""
    errors: list[str] = []
    workflow_call = _workflow_call(content, errors)
    if workflow_call:
        _check_optional_python_version_input(workflow_call, errors)

    jobs = _jobs(content, errors)
    if jobs is not None:
        _check_quality_jobs(jobs, errors)

    return errors


def composite_action_errors(content: dict[Any, Any]) -> list[str]:
    """Return composite setup action structure errors."""
    errors: list[str] = []
    _check_action_inputs(content, errors)
    _check_action_runs(content, errors)
    return errors


def _workflow_call(content: dict[Any, Any], errors: list[str]) -> dict[str, Any] | None:
    on_config = content.get(True) or content.get("on")
    if not isinstance(on_config, dict) or "workflow_call" not in on_config:
        errors.append("Missing workflow_call trigger")
        return None

    workflow_call = on_config["workflow_call"]
    return workflow_call if isinstance(workflow_call, dict) else {}


def _jobs(content: dict[Any, Any], errors: list[str]) -> dict[str, Any] | None:
    jobs = content.get("jobs")
    if not isinstance(jobs, dict):
        errors.append("Missing jobs")
        return None
    return jobs


def _check_reusable_test_inputs(
    workflow_call: dict[str, Any], errors: list[str]
) -> None:
    inputs = workflow_call.get("inputs")
    if not isinstance(inputs, dict):
        errors.append("Missing inputs in workflow_call")
        return

    _check_input_default_and_type(
        inputs,
        "python-version",
        "3.11",
        "string",
        errors,
    )
    _check_input_default_and_type(
        inputs,
        "upload-coverage",
        True,
        "boolean",
        errors,
    )
    _check_input_default_and_type(
        inputs,
        "matrix-profile",
        "full",
        "string",
        errors,
    )


def _check_input_default_and_type(
    inputs: dict[str, Any],
    name: str,
    expected_default: Any,
    expected_type: str,
    errors: list[str],
) -> None:
    if name not in inputs:
        errors.append(f"Missing {name} input")
        return

    input_config = inputs[name]
    if input_config.get("default") != expected_default:
        errors.append(
            f"{name} default should be {expected_default!r}, got {input_config.get('default')}"
        )
    if input_config.get("type") != expected_type:
        errors.append(
            f"{name} type should be '{expected_type}', got {input_config.get('type')}"
        )


def _check_reusable_test_secrets(
    workflow_call: dict[str, Any], errors: list[str]
) -> None:
    secrets = workflow_call.get("secrets")
    if not isinstance(secrets, dict):
        errors.append("Missing secrets in workflow_call")
        return
    if "CODECOV_TOKEN" not in secrets:
        errors.append("Missing CODECOV_TOKEN secret")


def _check_test_matrix_job(jobs: dict[str, Any], errors: list[str]) -> None:
    full_job = jobs.get("test-matrix-full")
    pr_job = jobs.get("test-matrix-pr")
    if not isinstance(full_job, dict):
        errors.append("Missing test-matrix-full job")
        return
    if not isinstance(pr_job, dict):
        errors.append("Missing test-matrix-pr job")
        return

    _check_test_matrix(full_job, errors)
    _check_pr_test_matrix(pr_job, errors)
    _check_all_extras_step(full_job, errors)
    _check_all_extras_step(pr_job, errors)


def _check_test_matrix(test_job: dict[str, Any], errors: list[str]) -> None:
    strategy = test_job.get("strategy")
    if not isinstance(strategy, dict):
        errors.append("Missing strategy in test-matrix job")
        return

    matrix = strategy.get("matrix")
    if not isinstance(matrix, dict):
        errors.append("Missing matrix in strategy")
        return

    expected_os = ["ubuntu-latest", "windows-latest", "macos-latest"]
    if matrix.get("os") != expected_os:
        errors.append(f"OS matrix should be {expected_os}, got {matrix.get('os')}")

    expected_versions = ["3.10", "3.11", "3.12", "3.13"]
    if matrix.get("python-version") != expected_versions:
        errors.append(
            "Python version matrix should be "
            f"{expected_versions}, got {matrix.get('python-version')}"
        )


def _check_pr_test_matrix(test_job: dict[str, Any], errors: list[str]) -> None:
    strategy = test_job.get("strategy")
    if not isinstance(strategy, dict):
        errors.append("Missing strategy in test-matrix-pr job")
        return

    matrix = strategy.get("matrix")
    if not isinstance(matrix, dict):
        errors.append("Missing matrix in PR strategy")
        return

    entries = matrix.get("include")
    if not isinstance(entries, list):
        errors.append("Missing include matrix in test-matrix-pr job")
        return

    axes = {(entry.get("os"), entry.get("python-version")) for entry in entries}
    expected_axes = {
        ("ubuntu-latest", "3.11"),
        ("ubuntu-latest", "3.13"),
        ("windows-latest", "3.11"),
        ("macos-latest", "3.11"),
    }
    if axes != expected_axes:
        errors.append(f"PR matrix should be {expected_axes}, got {axes}")


def _check_all_extras_step(test_job: dict[str, Any], errors: list[str]) -> None:
    steps = test_job.get("steps")
    if not isinstance(steps, list):
        errors.append("Missing steps in test-matrix job")
        return

    has_all_extras = any(
        isinstance(step, dict) and "--all-extras" in str(step.get("run", ""))
        for step in steps
    )
    if not has_all_extras:
        errors.append("Missing --all-extras flag in dependency installation")


def _check_optional_python_version_input(
    workflow_call: dict[str, Any], errors: list[str]
) -> None:
    inputs = workflow_call.get("inputs")
    if not isinstance(inputs, dict) or "python-version" not in inputs:
        return

    default = inputs["python-version"].get("default")
    if default != "3.11":
        errors.append(f"python-version default should be '3.11', got {default}")


def _check_quality_jobs(jobs: dict[str, Any], errors: list[str]) -> None:
    expected_jobs = {"lint", "type-check", "security"}
    missing_jobs = sorted(expected_jobs - set(jobs))
    for job_name in missing_jobs:
        errors.append(f"Missing {job_name} job")

    for job_name in sorted(expected_jobs & set(jobs)):
        job = jobs[job_name]
        if not isinstance(job, dict):
            errors.append(f"{job_name} job should be a mapping")
        elif job.get("runs-on") != "ubuntu-latest":
            errors.append(
                f"{job_name} should run on ubuntu-latest, got {job.get('runs-on')}"
            )


def _check_action_inputs(content: dict[Any, Any], errors: list[str]) -> None:
    inputs = content.get("inputs")
    if not isinstance(inputs, dict):
        errors.append("Missing inputs")
        return

    os_input = inputs.get("os")
    if not isinstance(os_input, dict):
        errors.append("Missing os input")
    elif not os_input.get("required"):
        errors.append("os input should be required")


def _check_action_runs(content: dict[Any, Any], errors: list[str]) -> None:
    runs = content.get("runs")
    if not isinstance(runs, dict):
        errors.append("Missing runs")
        return

    if runs.get("using") != "composite":
        errors.append(f"using should be 'composite', got {runs.get('using')}")

    steps = runs.get("steps")
    if not isinstance(steps, list):
        errors.append("Missing steps in runs")
        return

    _check_os_specific_steps(steps, errors)


def _check_os_specific_steps(steps: list[dict[str, Any]], errors: list[str]) -> None:
    step_conditions = [
        str(step.get("if", "")) for step in steps if isinstance(step, dict)
    ]
    if not any("ubuntu-latest" in condition for condition in step_conditions):
        errors.append("Missing Linux-specific step")
    if not any(
        "macos-" in condition or "macos-latest" in condition
        for condition in step_conditions
    ):
        errors.append("Missing macOS-specific step")
    if not any("windows-latest" in condition for condition in step_conditions):
        errors.append("Missing Windows-specific step")


def workflow_path(*parts: str) -> str:
    """Return a repository-relative GitHub workflow/action path."""
    return str(Path(".github", *parts))
