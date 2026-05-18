#!/usr/bin/env python3
"""
Verify GitHub Actions workflow structure and dependencies.
"""

import sys

from _verify_workflow_structure_helpers import (
    composite_action_errors,
    load_yaml,
    print_result,
    reusable_quality_errors,
    reusable_test_errors,
    workflow_path,
)


def verify_reusable_test_workflow() -> bool:
    """Verify the reusable test workflow structure."""
    print("Verifying reusable-test.yml structure...")

    content = load_yaml(workflow_path("workflows", "reusable-test.yml"))
    return print_result(
        "reusable-test.yml",
        "✅ reusable-test.yml structure is correct",
        reusable_test_errors(content),
    )


def verify_reusable_quality_workflow() -> bool:
    """Verify the reusable quality check workflow structure."""
    print("\nVerifying reusable-quality.yml structure...")

    content = load_yaml(workflow_path("workflows", "reusable-quality.yml"))
    return print_result(
        "reusable-quality.yml",
        "✅ reusable-quality.yml structure is correct",
        reusable_quality_errors(content),
    )


def verify_composite_action() -> bool:
    """Verify the composite action structure."""
    print("\nVerifying setup-system/action.yml structure...")

    content = load_yaml(workflow_path("actions", "setup-system", "action.yml"))
    return print_result(
        "setup-system/action.yml",
        "✅ setup-system/action.yml structure is correct",
        composite_action_errors(content),
    )


def main() -> int:
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
