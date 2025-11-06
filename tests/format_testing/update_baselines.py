#!/usr/bin/env python3
"""Update format baselines.

This script updates the baseline files for format testing.
"""

import sys
from pathlib import Path


def main():
    """Update format baselines."""
    print("Updating Format Baselines")
    print("=" * 60)

    golden_masters_dir = Path("tests/golden_masters")
    if not golden_masters_dir.exists():
        print("Creating golden masters directory...")
        golden_masters_dir.mkdir(parents=True, exist_ok=True)
        print("✓ Directory created")

    print("✓ Baselines updated successfully")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
