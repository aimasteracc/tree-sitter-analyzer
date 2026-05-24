"""SQL platform compatibility CLI helpers."""

import json
import pathlib
from typing import Any


def _sql_platform_profile_payload(profile: Any) -> dict[str, Any] | None:
    """Project the loaded ``BehaviorProfile`` into the JSON envelope shape."""
    if not profile:
        return None
    return {
        "schema_version": profile.schema_version,
        "behaviors_recorded": len(profile.behaviors),
        "adaptation_rules": list(profile.adaptation_rules),
    }


def _emit_sql_platform_json(output_json_fn: Any, info: Any, profile: Any) -> None:
    """Emit the canonical JSON envelope for ``sql_platform_info``."""
    summary_line = (
        f"sql_platform_info: {info.platform_key} "
        f"({'profile loaded' if profile else 'no profile (defaults)'})"
    )
    output_json_fn(
        {
            "success": True,
            "platform": {
                "os_name": info.os_name,
                "os_version": info.os_version,
                "python_version": info.python_version,
                "platform_key": info.platform_key,
            },
            "profile": _sql_platform_profile_payload(profile),
            "summary_line": summary_line,
            "verdict": "INFO",
            "agent_summary": {
                "summary_line": summary_line,
                "next_step": (
                    "Use --record-sql-profile to capture behavior on a new "
                    "platform, or --compare-sql-profiles to diff two."
                ),
                "verdict": "INFO",
            },
        }
    )


def _emit_sql_platform_text(output_list_fn: Any, info: Any, profile: Any) -> None:
    """Emit the legacy human-readable text output (multi-line list)."""
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
    if profile:
        rules = (
            ", ".join(profile.adaptation_rules) if profile.adaptation_rules else "None"
        )
        output_list_fn(
            [
                f"Loaded Profile: {info.platform_key}",
                f"  Schema Version: {profile.schema_version}",
                f"  Behaviors Recorded: {len(profile.behaviors)}",
                f"  Adaptation Rules: {rules}",
            ]
        )
        return
    output_list_fn(
        [
            f"No profile found for {info.platform_key}",
            "  Using default adaptation rules.",
        ]
    )


def handle_sql_platform_info(
    output_list_fn: Any,
    output_json_fn: Any = None,
    args: Any = None,
) -> int:
    """Display SQL platform detection details.

    r37ak (dogfood): JSON envelope path added. When the caller passes
    ``--format=json`` (or default ``--output-format=json``), emit a
    canonical envelope instead of plain text. The legacy text path
    (``output_list_fn``) is preserved for backward compatibility.

    r37eu (dogfood): 88→15 lines. JSON envelope + text output moved to
    ``_emit_sql_platform_json`` / ``_emit_sql_platform_text``.
    """
    from tree_sitter_analyzer.cli.output_format import wants_json_output
    from tree_sitter_analyzer.platform_compat.detector import PlatformDetector
    from tree_sitter_analyzer.platform_compat.profiles import BehaviorProfile

    info = PlatformDetector.detect()
    profile = BehaviorProfile.load(info.platform_key)

    if args is not None and wants_json_output(args) and output_json_fn is not None:
        _emit_sql_platform_json(output_json_fn, info, profile)
        return 0

    _emit_sql_platform_text(output_list_fn, info, profile)
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
