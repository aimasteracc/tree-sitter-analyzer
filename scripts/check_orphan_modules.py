#!/usr/bin/env python3
"""TEST-P2 guard rail: list source files that have no name-matched test file.

A "name-matched" test is any file under ``tests/`` whose stem starts
with ``test_<basename>`` where ``<basename>`` is the source file's stem
(with any leading underscore stripped — ``_api_helpers.py`` matches
``test_api_helpers*.py``).

The script supports two modes:

  * ``check``   — print orphans, return non-zero if the count grew
                  beyond a baseline (committed at scripts/orphan_baseline.txt).
                  Use this as a CI gate.

  * ``snapshot`` — write the current orphan list to the baseline.
                   Run this after intentionally landing new source files
                   that you plan to cover in a follow-up.

The default invocation is ``check``. Pure stdlib — no extra deps.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "tree_sitter_analyzer"
TESTS_DIR = ROOT / "tests"
BASELINE = Path(__file__).parent / "orphan_baseline.txt"


def _tracked_source_files() -> list[Path]:
    """Tracked .py files under tree_sitter_analyzer/. Excludes __init__.py."""
    out = subprocess.run(
        ["git", "ls-files", "tree_sitter_analyzer/*.py"],
        cwd=str(ROOT),
        check=True,
        capture_output=True,
        text=True,
    )
    paths: list[Path] = []
    for line in out.stdout.splitlines():
        p = ROOT / line.strip()
        if p.name == "__init__.py":
            continue
        if p.exists():
            paths.append(p)
    return paths


def _test_stems() -> set[str]:
    """All test_*.py stems under tests/, lowercased."""
    stems: set[str] = set()
    for p in TESTS_DIR.rglob("test_*.py"):
        stems.add(p.stem.lower())
    return stems


def _expected_test_basename(source: Path) -> str:
    """E.g. ``tree_sitter_analyzer/_api_helpers.py`` -> ``test_api_helpers``."""
    stem = source.stem.lstrip("_")
    return f"test_{stem.lower()}"


def find_orphans() -> list[Path]:
    test_stems = _test_stems()
    orphans: list[Path] = []
    for src in _tracked_source_files():
        prefix = _expected_test_basename(src)
        # Match either the exact stem or any test that starts with the
        # expected prefix (covers tests like ``test_route_detector_edge_cases``).
        if any(stem.startswith(prefix) for stem in test_stems):
            continue
        orphans.append(src.relative_to(ROOT))
    return sorted(orphans)


def _read_baseline() -> set[str]:
    if not BASELINE.exists():
        return set()
    return {
        line.strip()
        for line in BASELINE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def cmd_snapshot() -> int:
    orphans = find_orphans()
    BASELINE.write_text(
        "# TEST-P2 orphan baseline — source files without a name-matched test.\n"
        "# Update with: uv run python scripts/check_orphan_modules.py snapshot\n"
        "# Reviewers should not let this list grow.\n\n"
        + "\n".join(str(p) for p in orphans)
        + "\n",
        encoding="utf-8",
    )
    print(f"snapshot: {len(orphans)} orphans written to {BASELINE.relative_to(ROOT)}")
    return 0


def cmd_check() -> int:
    current = {str(p) for p in find_orphans()}
    baseline = _read_baseline()
    if not baseline:
        print(
            "check: no baseline yet — run "
            "`uv run python scripts/check_orphan_modules.py snapshot` first.",
            file=sys.stderr,
        )
        return 2
    new_orphans = sorted(current - baseline)
    if new_orphans:
        print(
            f"check: {len(new_orphans)} NEW orphan(s) — source files added without "
            "a name-matched test:",
            file=sys.stderr,
        )
        for path in new_orphans:
            print(f"  {path}", file=sys.stderr)
        print(
            "\nFix by adding a tests/.../test_<basename>*.py file, OR run "
            "`snapshot` if the new orphans are intentional and will be covered "
            "in a follow-up.",
            file=sys.stderr,
        )
        return 1
    healed = sorted(baseline - current)
    if healed:
        print(f"check: {len(healed)} orphan(s) gained coverage 🎉:")
        for path in healed:
            print(f"  {path}")
        print(
            "Consider snapshotting to lock in the improvement: "
            "`uv run python scripts/check_orphan_modules.py snapshot`."
        )
    print(f"check: {len(current)} orphan(s), no regressions vs baseline.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=["check", "snapshot"],
        nargs="?",
        default="check",
    )
    args = parser.parse_args(argv)
    if args.mode == "snapshot":
        return cmd_snapshot()
    return cmd_check()


if __name__ == "__main__":
    raise SystemExit(main())
