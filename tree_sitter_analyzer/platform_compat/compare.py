from dataclasses import dataclass
from typing import Any

from deepdiff import DeepDiff

from .profiles import (
    BehaviorProfile,
    ParsingBehavior,
    migrate_profile_schema,
    validate_profile,
)


@dataclass
class BehaviorDifference:
    """Represents a difference in behavior for a specific construct."""

    construct_id: str
    diff_type: (
        str  # "missing", "attribute_mismatch", "error_mismatch", "count_mismatch"
    )
    details: str
    platform_a_value: Any
    platform_b_value: Any


@dataclass
class ProfileComparison:
    """Result of comparing two profiles."""

    platform_a: str
    platform_b: str
    differences: list[BehaviorDifference]

    @property
    def has_differences(self) -> bool:
        return len(self.differences) > 0


def compare_profiles(
    profile_a: BehaviorProfile, profile_b: BehaviorProfile
) -> ProfileComparison:
    """
    Compares two behavior profiles and identifies differences.

    Args:
        profile_a: First profile.
        profile_b: Second profile.

    Returns:
        ProfileComparison: The comparison result.
    """
    differences = []

    # Check for missing constructs
    keys_a = set(profile_a.behaviors.keys())
    keys_b = set(profile_b.behaviors.keys())

    for key in keys_a - keys_b:
        differences.append(
            BehaviorDifference(
                construct_id=key,
                diff_type="missing",
                details=f"Construct {key} missing in {profile_b.platform_key}",
                platform_a_value="present",
                platform_b_value="missing",
            )
        )

    for key in keys_b - keys_a:
        differences.append(
            BehaviorDifference(
                construct_id=key,
                diff_type="missing",
                details=f"Construct {key} missing in {profile_a.platform_key}",
                platform_a_value="missing",
                platform_b_value="present",
            )
        )

    # Compare common constructs
    for key in keys_a.intersection(keys_b):
        beh_a = profile_a.behaviors[key]
        beh_b = profile_b.behaviors[key]

        # Compare error status
        if beh_a.has_error != beh_b.has_error:
            differences.append(
                BehaviorDifference(
                    construct_id=key,
                    diff_type="error_mismatch",
                    details=f"Error status mismatch for {key}",
                    platform_a_value=beh_a.has_error,
                    platform_b_value=beh_b.has_error,
                )
            )

        # Compare element count
        if beh_a.element_count != beh_b.element_count:
            differences.append(
                BehaviorDifference(
                    construct_id=key,
                    diff_type="count_mismatch",
                    details=f"Element count mismatch for {key}",
                    platform_a_value=beh_a.element_count,
                    platform_b_value=beh_b.element_count,
                )
            )

        # Compare attributes
        # We use DeepDiff for detailed comparison if needed, or just set comparison
        if beh_a.attributes != beh_b.attributes:
            # Use DeepDiff to get readable diff
            diff = DeepDiff(beh_a.attributes, beh_b.attributes, ignore_order=True)
            if diff:
                differences.append(
                    BehaviorDifference(
                        construct_id=key,
                        diff_type="attribute_mismatch",
                        details=f"Attributes mismatch for {key}",
                        platform_a_value=beh_a.attributes,
                        platform_b_value=beh_b.attributes,
                    )
                )

    return ProfileComparison(
        platform_a=profile_a.platform_key,
        platform_b=profile_b.platform_key,
        differences=differences,
    )


def generate_diff_report(comparison: ProfileComparison) -> str:
    """
    Generates a human-readable report of the differences.

    Args:
        comparison: The comparison result.

    Returns:
        str: The report text.
    """
    if not comparison.has_differences:
        return f"No differences found between {comparison.platform_a} and {comparison.platform_b}."

    lines = [
        f"Comparison Report: {comparison.platform_a} vs {comparison.platform_b}",
        "=" * 60,
        f"Total differences: {len(comparison.differences)}",
        "",
    ]

    for diff in comparison.differences:
        lines.append(f"Construct: {diff.construct_id}")
        lines.append(f"Type: {diff.diff_type}")
        lines.append(f"Details: {diff.details}")
        lines.append(f"  {comparison.platform_a}: {diff.platform_a_value}")
        lines.append(f"  {comparison.platform_b}: {diff.platform_b_value}")
        lines.append("-" * 40)

    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Compare two SQL behavior profiles")
    parser.add_argument("profile_a", type=str, help="Path to first profile")
    parser.add_argument("profile_b", type=str, help="Path to second profile")
    parser.add_argument(
        "--fail-on-diff",
        action="store_true",
        help="Exit with error code if differences found",
    )

    args = parser.parse_args()

    try:
        path_a = Path(args.profile_a)
        path_b = Path(args.profile_b)

        if not path_a.exists():
            print(f"Error: Profile not found: {path_a}")
            sys.exit(1)

        if not path_b.exists():
            print(f"Error: Profile not found: {path_b}")
            sys.exit(1)

        # Load profiles manually since BehaviorProfile.load expects a platform key
        # We need to load from specific files
        import json

        def load_profile_from_file(path: Path) -> BehaviorProfile:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)

            # Validate and migrate schema
            validate_profile(data)
            data = migrate_profile_schema(data)

            # Convert behaviors dict to ParsingBehavior objects
            behaviors = {}
            for key, b_data in data.get("behaviors", {}).items():
                if isinstance(b_data, dict):
                    behaviors[key] = ParsingBehavior(**b_data)
                else:
                    behaviors[key] = b_data

            return BehaviorProfile(
                schema_version=data.get("schema_version", "1.0.0"),
                platform_key=data["platform_key"],
                behaviors=behaviors,
                adaptation_rules=data.get("adaptation_rules", []),
            )

        profile_a = load_profile_from_file(path_a)
        profile_b = load_profile_from_file(path_b)

        comparison = compare_profiles(profile_a, profile_b)
        report = generate_diff_report(comparison)
        print(report)

        if args.fail_on_diff and comparison.has_differences:
            sys.exit(1)

    except Exception as e:
        print(f"Error comparing profiles: {e}")
        sys.exit(1)
