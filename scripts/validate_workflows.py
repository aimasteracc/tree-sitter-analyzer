#!/usr/bin/env python3
"""
Validate GitHub Actions workflow YAML syntax and structure.
"""

import sys
from pathlib import Path

import yaml


def validate_workflow(workflow_path: Path) -> tuple[bool, list[str]]:
    """
    Validate a GitHub Actions workflow file.

    Returns:
        Tuple of (is_valid, errors)
    """
    errors = []

    try:
        with open(workflow_path, encoding="utf-8") as f:
            raw_content = f.read()

        # Parse YAML - note that 'on' gets converted to True by YAML parser
        content = yaml.safe_load(raw_content)

        # Check required top-level keys
        if "name" not in content:
            errors.append("Missing 'name' field")

        # Check for 'on' in raw content since YAML parser converts it to True
        if "on:" not in raw_content and True not in content:
            errors.append("Missing 'on' (trigger) field")

        if "jobs" not in content:
            errors.append("Missing 'jobs' field")

        # Validate jobs structure
        if "jobs" in content:
            jobs = content["jobs"]
            if not isinstance(jobs, dict):
                errors.append("'jobs' must be a dictionary")
            else:
                for job_name, job_config in jobs.items():
                    if not isinstance(job_config, dict):
                        errors.append(f"Job '{job_name}' must be a dictionary")
                        continue

                    # Check for required job fields
                    if "runs-on" not in job_config and "uses" not in job_config:
                        errors.append(
                            f"Job '{job_name}' must have 'runs-on' or 'uses' field"
                        )

                    # If it's a reusable workflow call, check for 'uses'
                    if "uses" in job_config:
                        if (
                            not job_config["uses"].startswith("./.github/workflows/")
                            and not job_config["uses"].startswith("actions/")
                            and "@" not in job_config["uses"]
                        ):
                            errors.append(
                                f"Job '{job_name}' has invalid 'uses' path: {job_config['uses']}"
                            )

        # Validate workflow_call inputs for reusable workflows
        # Note: 'on' gets converted to True by YAML parser
        on_config = content.get("on") or content.get(True)
        if on_config and isinstance(on_config, dict):
            if "workflow_call" in on_config:
                workflow_call = on_config["workflow_call"]
                if "inputs" in workflow_call:
                    inputs = workflow_call["inputs"]
                    if not isinstance(inputs, dict):
                        errors.append("workflow_call.inputs must be a dictionary")
                    else:
                        for input_name, input_config in inputs.items():
                            if not isinstance(input_config, dict):
                                errors.append(
                                    f"Input '{input_name}' must be a dictionary"
                                )
                            elif "type" not in input_config:
                                errors.append(
                                    f"Input '{input_name}' must have a 'type' field"
                                )

        return len(errors) == 0, errors

    except yaml.YAMLError as e:
        return False, [f"YAML parsing error: {str(e)}"]
    except Exception as e:
        return False, [f"Unexpected error: {str(e)}"]


def validate_action(action_path: Path) -> tuple[bool, list[str]]:
    """
    Validate a GitHub Actions composite action file.

    Returns:
        Tuple of (is_valid, errors)
    """
    errors = []

    try:
        with open(action_path, encoding="utf-8") as f:
            # Use yaml.load with FullLoader to handle 'on' keyword properly
            content = yaml.safe_load(f)

        # Check required top-level keys for composite actions
        if "name" not in content:
            errors.append("Missing 'name' field")

        if "description" not in content:
            errors.append("Missing 'description' field")

        if "runs" not in content:
            errors.append("Missing 'runs' field")

        # Validate runs structure for composite actions
        if "runs" in content:
            runs = content["runs"]
            if not isinstance(runs, dict):
                errors.append("'runs' must be a dictionary")
            else:
                if "using" not in runs:
                    errors.append("'runs' must have 'using' field")
                elif runs["using"] != "composite":
                    errors.append(
                        "'runs.using' must be 'composite' for composite actions"
                    )

                if "steps" not in runs:
                    errors.append("'runs' must have 'steps' field")

        return len(errors) == 0, errors

    except yaml.YAMLError as e:
        return False, [f"YAML parsing error: {str(e)}"]
    except Exception as e:
        return False, [f"Unexpected error: {str(e)}"]


def main():
    """Main validation function."""
    workflows_dir = Path(".github/workflows")
    actions_dir = Path(".github/actions")

    all_valid = True

    # Validate new reusable workflows
    new_workflows = ["reusable-test.yml", "reusable-quality.yml"]

    print("Validating reusable workflows...")
    for workflow_name in new_workflows:
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

    # Validate composite action
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
    else:
        print("\n❌ Some workflow files have errors")
        return 1


if __name__ == "__main__":
    sys.exit(main())
