import json
from pathlib import Path

from .profiles import BehaviorProfile, ParsingBehavior


def generate_compatibility_matrix(profiles_dir: Path) -> str:
    """
    Generates a compatibility matrix report from a directory of profiles.

    Args:
        profiles_dir: Directory containing profile JSON files (recursively).

    Returns:
        str: Markdown formatted report.
    """
    profiles: list[BehaviorProfile] = []

    # Find all profile.json files
    for path in profiles_dir.rglob("profile.json"):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                # Basic validation
                if "platform_key" in data:
                    # Manual deserialization of nested objects
                    behaviors = {}
                    for key, b_data in data.get("behaviors", {}).items():
                        if isinstance(b_data, dict):
                            behaviors[key] = ParsingBehavior(**b_data)
                        else:
                            behaviors[key] = b_data

                    profile = BehaviorProfile(
                        schema_version=data.get("schema_version", "1.0.0"),
                        platform_key=data["platform_key"],
                        behaviors=behaviors,
                        adaptation_rules=data.get("adaptation_rules", []),
                    )
                    profiles.append(profile)
        except Exception:  # nosec
            continue

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
