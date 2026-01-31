#!/usr/bin/env python
"""Check for misplaced planning files in project root.

This script ensures all planning-related markdown files are stored in the
proper location under .kiro/specs/ directory.

Features:
    - Detects common planning file patterns in project root
    - Provides clear error messages with remediation steps
    - Returns appropriate exit codes for pre-commit integration

Usage:
    python scripts/check_planning_structure.py

Exit Codes:
    0: All planning files are in correct location
    1: Found planning files in project root (violation)

Note:
    This script is designed to be used as a pre-commit hook to enforce
    the project's planning file structure convention.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Final

# Planning file patterns that should NOT be in project root
FORBIDDEN_ROOT_FILES: Final[list[str]] = [
    "task_plan.md",
    "progress.md",
    "findings.md",
    "task.md",
    "tasks.md",
    "design.md",
    "requirements.md",
]

# These are documentation files, not planning files - allowed in root
ALLOWED_ROOT_PATTERNS: Final[list[str]] = [
    "README",
    "CHANGELOG",
    "SECURITY",
    "CODE_OF_CONDUCT",
    "CONTRIBUTING",
    "GITFLOW",
    "LICENSE",
    "CLAUDE",
    "CODING_STANDARDS",
    "AI_BEST_PRACTICES",
    "CHANGE_MANAGEMENT",
    "DESIGN_ISSUES_REPORT",
]


def is_allowed_root_file(filename: str) -> bool:
    """Check if a markdown file is allowed in project root.

    Args:
        filename: Name of the file to check

    Returns:
        bool: True if file is allowed in root, False otherwise

    Note:
        Files starting with allowed patterns (case-insensitive) are permitted.
    """
    upper_name = filename.upper()
    return any(upper_name.startswith(pattern) for pattern in ALLOWED_ROOT_PATTERNS)


def check_planning_files() -> int:
    """Check for misplaced planning files in project root.

    Args:
        None

    Returns:
        int: Exit code (0 for success, 1 for violations found)

    Note:
        This function scans the project root for forbidden planning files
        and reports violations with remediation guidance.
    """
    root = Path(".")
    violations: list[str] = []

    # Check for explicitly forbidden files
    for filename in FORBIDDEN_ROOT_FILES:
        if (root / filename).exists():
            violations.append(filename)

    # Check for any .md files that look like planning files
    for md_file in root.glob("*.md"):
        name = md_file.name.lower()
        # Skip allowed files
        if is_allowed_root_file(md_file.name):
            continue
        # Check for planning-related patterns
        if any(pattern in name for pattern in ["task", "progress", "finding", "plan"]):
            if md_file.name not in violations:
                violations.append(md_file.name)

    if violations:
        print("=" * 60)
        print("ERROR: Planning files found in project root")
        print("=" * 60)
        print()
        print("The following planning files must be moved to .kiro/specs/:")
        for v in sorted(violations):
            print(f"  - {v}")
        print()
        print("REMEDIATION:")
        print("  1. Create feature directory: mkdir -p .kiro/specs/{feature-name}/")
        print("  2. Move files: mv {file} .kiro/specs/{feature-name}/")
        print()
        print("STRUCTURE EXAMPLE:")
        print("  .kiro/specs/")
        print("    └── my-feature/")
        print("        ├── requirements.md")
        print("        ├── design.md")
        print("        ├── tasks.md")
        print("        └── progress.md")
        print()
        print("=" * 60)
        return 1

    return 0


def main() -> None:
    """Main entry point for the planning structure checker.

    Args:
        None

    Returns:
        None (exits with appropriate code)

    Note:
        Designed to be called from pre-commit hooks or command line.
    """
    sys.exit(check_planning_files())


if __name__ == "__main__":
    main()
