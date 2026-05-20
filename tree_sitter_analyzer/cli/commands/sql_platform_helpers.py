"""SQL platform compatibility CLI helpers."""

import json
import pathlib
from typing import Any


def handle_sql_platform_info(output_list_fn: Any) -> int:
    """Display SQL platform detection details."""
    from tree_sitter_analyzer.platform_compat.detector import PlatformDetector
    from tree_sitter_analyzer.platform_compat.profiles import BehaviorProfile

    info = PlatformDetector.detect()
    output_list_fn(
        [
            "SQL Platform Information:",
            f"  OS Name: {info.os_name}",
            f"  OS Version: {info.os_version}",
            f"  Python Version: {info.python_version}",
            f"  Platform Key: {info.platform_key}",
            "",
        ]
    )

    profile = BehaviorProfile.load(info.platform_key)
    if profile:
        output_list_fn(
            [
                f"Loaded Profile: {info.platform_key}",
                f"  Schema Version: {profile.schema_version}",
                f"  Behaviors Recorded: {len(profile.behaviors)}",
                f"  Adaptation Rules: {', '.join(profile.adaptation_rules) if profile.adaptation_rules else 'None'}",
            ]
        )
    else:
        output_list_fn(
            [
                f"No profile found for {info.platform_key}",
                "  Using default adaptation rules.",
            ]
        )
    return 0


def handle_record_sql_profile(output_info_fn: Any, output_error_fn: Any) -> int:
    """Record a SQL behavior profile for the current platform."""
    from tree_sitter_analyzer.platform_compat.recorder import BehaviorRecorder

    output_info_fn("Starting SQL behavior recording...")
    try:
        recorder = BehaviorRecorder()
        profile = recorder.record_all()

        output_dir = pathlib.Path("tests/platform_profiles")
        output_dir.mkdir(parents=True, exist_ok=True)

        profile.save(output_dir)
        output_info_fn(f"Recorded profile for {profile.platform_key}")
        output_info_fn(f"Saved to {output_dir}")
    except Exception as e:
        output_error_fn(f"Failed to record profile: {e}")
        return 1
    return 0


def handle_compare_sql_profiles(
    profile_paths: list[str],
    output_error_fn: Any,
) -> int | None:
    """Compare two SQL behavior profiles."""
    from tree_sitter_analyzer.platform_compat.compare import (
        compare_profiles,
        generate_diff_report,
    )

    p1_path = pathlib.Path(profile_paths[0])
    p2_path = pathlib.Path(profile_paths[1])

    if not p1_path.exists():
        output_error_fn(f"Profile not found: {p1_path}")
        return 1
    if not p2_path.exists():
        output_error_fn(f"Profile not found: {p2_path}")
        return 1

    try:
        p1 = _load_profile(p1_path)
        p2 = _load_profile(p2_path)

        comparison = compare_profiles(p1, p2)
        report = generate_diff_report(comparison)
        print(report)
    except Exception as e:
        output_error_fn(f"Error comparing profiles: {e}")
        return 1
    return 0


def _load_profile(path: pathlib.Path) -> Any:
    """Load a BehaviorProfile from a JSON file."""
    from tree_sitter_analyzer.platform_compat.profiles import (
        BehaviorProfile,
        ParsingBehavior,
    )

    with open(path, encoding="utf-8") as f:
        data = json.load(f)
        behaviors: dict[str, ParsingBehavior] = {}
        for key, b_data in data.get("behaviors", {}).items():
            if isinstance(b_data, dict):
                behaviors[key] = ParsingBehavior(**b_data)

        return BehaviorProfile(
            schema_version=data.get("schema_version", "1.0.0"),
            platform_key=data["platform_key"],
            behaviors=behaviors,
            adaptation_rules=data.get("adaptation_rules", []),
        )
