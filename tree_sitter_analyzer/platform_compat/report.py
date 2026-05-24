import json
from pathlib import Path

from .profiles import BehaviorProfile, ParsingBehavior


def _load_profile_from_path(path: Path) -> BehaviorProfile | None:
    """Load one ``profile.json`` from disk, returning ``None`` on any error.

    r37bh (dogfood): extracted from ``generate_compatibility_matrix`` —
    the inline try/with/json.load/validate/build chain was the body of
    a deep-nested (depth 7) loop. Failure modes (missing file, invalid
    JSON, missing platform_key) all collapse to ``None`` so the caller
    just filters.
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:  # nosec
        return None
    if "platform_key" not in data:
        return None
    behaviors: dict[str, object] = {}
    for key, b_data in data.get("behaviors", {}).items():
        if isinstance(b_data, dict):
            behaviors[key] = ParsingBehavior(**b_data)
        else:
            behaviors[key] = b_data
    return BehaviorProfile(
        schema_version=data.get("schema_version", "1.0.0"),
        platform_key=data["platform_key"],
        behaviors=behaviors,  # type: ignore[arg-type]
        adaptation_rules=data.get("adaptation_rules", []),
    )


def generate_compatibility_matrix(profiles_dir: Path) -> str:
    """Generates a compatibility matrix report from a directory of profiles.

    Args:
        profiles_dir: Directory containing profile JSON files (recursively).

    Returns:
        str: Markdown formatted report.

    r37bh (dogfood): tool flagged the profile-load block at nesting
    depth 7 (L30). Loading moved into ``_load_profile_from_path``; this
    function now just walks + filters + renders.
    """
    profiles: list[BehaviorProfile] = []
    for path in profiles_dir.rglob("profile.json"):
        profile = _load_profile_from_path(path)
        if profile is not None:
            profiles.append(profile)

    if not profiles:
        return "No profiles found."

    # Sort profiles
    profiles.sort(key=lambda p: p.platform_key)

    # Collect all constructs
    all_constructs: set[str] = set()
    for p in profiles:
        all_constructs.update(p.behaviors.keys())
    sorted_constructs = sorted(all_constructs)

    # Build Matrix
    # Rows: Constructs
    # Cols: Platforms

    lines = ["# SQL Compatibility Matrix", "", "| Construct |"]

    # Header row
    for p in profiles:
        lines[0] += f" {p.platform_key} |"
    lines.append("|" + "---|" * (len(profiles) + 1))

    # Data rows
    for construct in sorted_constructs:
        row = f"| {construct} |"
        for p in profiles:
            behavior = p.behaviors.get(construct)
            if not behavior:
                status = "❌ Missing"
            elif behavior.has_error:
                status = "⚠️ Error"
            else:
                status = "✅ OK"
            row += f" {status} |"
        lines.append(row)

    return "\n".join(lines)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate compatibility matrix")
    parser.add_argument("profiles_dir", type=str, help="Directory containing profiles")
    args = parser.parse_args()

    report = generate_compatibility_matrix(Path(args.profiles_dir))
    print(report)
