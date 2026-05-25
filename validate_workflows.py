#!/usr/bin/env python3
"""
Validate GitHub Actions workflow YAML syntax and structure.
"""

import sys
from pathlib import Path

import yaml


def _validate_workflow_jobs(jobs: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(jobs, dict):
        return ["'jobs' must be a dictionary"]
    for job_name, job_config in jobs.items():
        if not isinstance(job_config, dict):
            errors.append(f"Job '{job_name}' must be a dictionary")
            continue
        if "runs-on" not in job_config and "uses" not in job_config:
            errors.append(f"Job '{job_name}' must have 'runs-on' or 'uses' field")
        uses = job_config.get("uses", "")
        if uses and (
            not uses.startswith("./.github/workflows/")
            and not uses.startswith("actions/")
            and "@" not in uses
        ):
            errors.append(f"Job '{job_name}' has invalid 'uses' path: {uses}")
    return errors


def _validate_trigger_inputs(on_config: dict) -> list[str]:
    workflow_call = on_config.get("workflow_call") or {}
    inputs = workflow_call.get("inputs")
    if not inputs:
        return []
    if not isinstance(inputs, dict):
        return ["workflow_call.inputs must be a dictionary"]
    errors: list[str] = []
    for input_name, input_config in inputs.items():
        if not isinstance(input_config, dict):
            errors.append(f"Input '{input_name}' must be a dictionary")
        elif "type" not in input_config:
            errors.append(f"Input '{input_name}' must have a 'type' field")
    return errors


def validate_workflow(workflow_path: Path) -> tuple[bool, list[str]]:
    """
    Validate a GitHub Actions workflow file.

    Returns:
        Tuple of (is_valid, errors)
    """
    try:
        with open(workflow_path, encoding="utf-8") as f:
            raw_content = f.read()
        content = yaml.safe_load(raw_content)
    except yaml.YAMLError as e:
        return False, [f"YAML parsing error: {str(e)}"]
    except Exception as e:
        return False, [f"Unexpected error: {str(e)}"]

    errors: list[str] = []
    if "name" not in content:
        errors.append("Missing 'name' field")
    if "on:" not in raw_content and True not in content:
        errors.append("Missing 'on' (trigger) field")
    if "jobs" not in content:
        errors.append("Missing 'jobs' field")
    else:
        errors.extend(_validate_workflow_jobs(content["jobs"]))

    # Note: 'on' gets converted to True by the YAML parser.
    on_config = content.get("on") or content.get(True)
    if isinstance(on_config, dict):
        errors.extend(_validate_trigger_inputs(on_config))

    return len(errors) == 0, errors


def validate_action(action_path: Path) -> tuple[bool, list[str]]:
    """
    Validate a GitHub Actions composite action file.

    Returns:
        Tuple of (is_valid, errors)
    """
    try:
        with open(action_path, encoding="utf-8") as f:
            content = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return False, [f"YAML parsing error: {str(e)}"]
    except Exception as e:
        return False, [f"Unexpected error: {str(e)}"]

    errors: list[str] = []
    for key in ("name", "description", "runs"):
        if key not in content:
            errors.append(f"Missing '{key}' field")

    runs = content.get("runs")
    if isinstance(runs, dict):
        if "using" not in runs:
            errors.append("'runs' must have 'using' field")
        elif runs["using"] != "composite":
            errors.append("'runs.using' must be 'composite' for composite actions")
        if "steps" not in runs:
            errors.append("'runs' must have 'steps' field")
    elif runs is not None:
        errors.append("'runs' must be a dictionary")

    return len(errors) == 0, errors


def main():
    """Main validation function."""
    workflows_dir = Path(".github/workflows")
    actions_dir = Path(".github/actions")
    all_valid = True

    print("Validating reusable workflows...")
    for workflow_name in ["reusable-test.yml", "reusable-quality.yml"]:
        workflow_path = workflows_dir / workflow_name
        if not workflow_path.exists():
            print(f"❌ {workflow_name}: File not found")
            all_valid = False
            continue
        is_valid, errors = validate_workflow(workflow_path)
        if is_valid:
            print(f"✅ {workflow_name}: Valid")
        else:
            print(f"❌ {workflow_name}: Invalid")
            for error in errors:
                print(f"   - {error}")
            all_valid = False

    print("\nValidating composite actions...")
    action_path = actions_dir / "setup-system" / "action.yml"
    if not action_path.exists():
        print("❌ setup-system/action.yml: File not found")
        all_valid = False
    else:
        is_valid, errors = validate_action(action_path)
        if is_valid:
            print("✅ setup-system/action.yml: Valid")
        else:
            print("❌ setup-system/action.yml: Invalid")
            for error in errors:
                print(f"   - {error}")
            all_valid = False

    if all_valid:
        print("\n✅ All workflow files are valid!")
        return 0
    print("\n❌ Some workflow files have errors")
    return 1


if __name__ == "__main__":
    sys.exit(main())
