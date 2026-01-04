#!/usr/bin/env python3
"""Check for performance regression in benchmark results."""

import json
import sys


def check_regression(json_file: str, threshold: float) -> int:
    """Check benchmark results for performance regression.

    Args:
        json_file: Path to benchmark JSON file
        threshold: Regression threshold as decimal (e.g., 0.10 for 10%)

    Returns:
        1 if regression detected, 0 otherwise
    """
    with open(json_file) as f:
        data = json.load(f)

    regressions = []
    for benchmark in data.get("benchmarks", []):
        if "stats" in benchmark and "baseline" in benchmark["stats"]:
            current = benchmark["stats"]["mean"]
            baseline = benchmark["stats"]["baseline"]
            if baseline > 0:
                change = (current - baseline) / baseline
                if change > threshold:
                    regressions.append(
                        {
                            "name": benchmark["name"],
                            "change": f"{change * 100:.1f}%",
                            "current": f"{current:.6f}s",
                            "baseline": f"{baseline:.6f}s",
                        }
                    )

    if regressions:
        print("Performance regressions detected:")
        for r in regressions:
            print(
                f"  - {r['name']}: {r['change']} (current: {r['current']}, baseline: {r['baseline']})"
            )
        return 1
    else:
        print("No performance regression detected.")
        return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: check_performance_regression.py <json_file> [threshold]")
        sys.exit(1)

    json_file = sys.argv[1]
    threshold = float(sys.argv[2]) if len(sys.argv) > 2 else 0.10

    sys.exit(check_regression(json_file, threshold))
