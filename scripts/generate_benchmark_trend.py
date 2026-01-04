#!/usr/bin/env python3
"""Generate benchmark trend report."""

import json
import sys


def generate_trend_report(json_file: str) -> None:
    """Generate trend report for benchmark results.

    Args:
        json_file: Path to benchmark JSON file
    """
    with open(json_file) as f:
        data = json.load(f)

    for bench in data.get("benchmarks", []):
        name = bench.get("name", "unknown")
        stats = bench.get("stats", {})
        mean = stats.get("mean", 0)
        stddev = stats.get("stddev", 0)
        print(f"{name}: {mean:.6f}s +/- {stddev:.6f}s")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: generate_benchmark_trend.py <json_file>")
        sys.exit(1)

    json_file = sys.argv[1]
    generate_trend_report(json_file)
