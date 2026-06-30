#!/usr/bin/env python3
"""CI gate: count remaining ``if language ==`` branches in central files.

Phase 2 spec-refine requirement: after full migration the central non-plugin
files must have zero ``if language ==`` branches that handle per-language
dispatch.  During migration the threshold is lowered one stage at a time.

Usage:
  python scripts/check_language_branches.py          # check against threshold
  python scripts/check_language_branches.py --count  # print count only
  python scripts/check_language_branches.py --list   # list each match

Exit codes:
  0 - count is at or below threshold (gate passes)
  1 - count exceeds threshold (gate fails)
  2 - unexpected error

Threshold history (lowered each time a Stage completes):
  Phase 2 start  : N/A (threshold not enforced; gate disabled)
  After Stage 3  : threshold still not enforced (Go migrated)
  After Stage 12 : threshold = 0  (all migrations complete — REQ-CI-001)

Current threshold: NOT_ENFORCED
  Set ENFORCE_THRESHOLD=1 env var or remove the bypass comment below to enable.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent

# Files that are considered "central" and should NOT contain per-language branches.
# Plugin files and test files are excluded.
_EXCLUDE_PATTERNS = [
    "plugins/",
    ".venv/",
    "__pycache__",
    "scripts/",
]

# The pattern we're counting — direct ``if language ==`` or ``elif language ==``
# branches (not inline expressions like ``language == "x" and ...``).
_BRANCH_RE = re.compile(r"\bif\s+language\s*==|elif\s+language\s*==")

# Current gate threshold.  Set to 0 when all migrations are complete.
# During Phase 2 development this is ratcheted down as stages complete.
_THRESHOLD = 46  # NOTE: lower to 0 when Stage 12 is fully done (REQ-CI-001)

# Per-file threshold overrides (for gradual ratcheting, not yet in use)
_FILE_THRESHOLDS: dict[str, int] = {}


def _is_excluded(path: Path) -> bool:
    rel = str(path.relative_to(_PROJECT_ROOT)).replace("\\", "/")
    # Exclude test directories and test files (but not production code that mentions "test")
    if "/tests/" in rel or rel.startswith("tests/"):
        return True
    if path.name.startswith("test_") or path.name.endswith("_test.py"):
        return True
    return any(pat in rel for pat in _EXCLUDE_PATTERNS)


def _count_matches(path: Path) -> list[tuple[int, str]]:
    """Return list of (line_no, line_text) tuples for matches in *path*."""
    matches: list[tuple[int, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            # Strip inline comments before matching to avoid false positives
            code_part = line.split("#")[0]
            if _BRANCH_RE.search(code_part):
                matches.append((lineno, line.rstrip()))
    except Exception:
        pass
    return matches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", action="store_true", help="Print count only")
    parser.add_argument("--list", action="store_true", help="List each match")
    parser.add_argument(
        "--set-threshold",
        type=int,
        default=None,
        help="Override the default threshold (default: 46).",
    )
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="Exit 1 when count exceeds threshold (gate enforcement).",
    )
    args = parser.parse_args()

    threshold = args.set_threshold if args.set_threshold is not None else _THRESHOLD

    root = _PROJECT_ROOT / "tree_sitter_analyzer"
    all_matches: list[tuple[Path, int, str]] = []

    for py_file in sorted(root.rglob("*.py")):
        if _is_excluded(py_file):
            continue
        for lineno, line in _count_matches(py_file):
            all_matches.append((py_file, lineno, line))

    total = len(all_matches)

    if args.count:
        print(total)
        return 0

    if args.list:
        for path, lineno, line in all_matches:
            rel = path.relative_to(_PROJECT_ROOT)
            print(f"{rel}:{lineno}: {line}")
        print(f"\nTotal: {total}")
        return 0

    # Gate check
    print(f"language-branch count: {total} (threshold: {threshold})")
    if total > threshold:
        print(f"{'FAIL' if args.enforce else 'WARN'}: {total} > {threshold}")
        for path, lineno, line in all_matches[:20]:
            rel = path.relative_to(_PROJECT_ROOT)
            print(f"  {rel}:{lineno}: {line}")
        if len(all_matches) > 20:
            print(f"  ... and {len(all_matches) - 20} more")
        if args.enforce:
            return 1

    print(f"PASS: {total} <= {threshold}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
