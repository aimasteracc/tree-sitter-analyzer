#!/usr/bin/env python3
"""Brain Circuit — self-diagnosis and impact analysis for the project.

Uses the ProjectBrain impact graph to answer:
  "If I change X, what breaks? Which tests should I run?"

Usage:
    # Diagnose: what are the most fragile files?
    uv run python scripts/brain-diagnosis.py

    # Impact: what's affected if I change these files?
    uv run python scripts/brain-diagnosis.py --impact tree_sitter_analyzer/analysis/base.py

    # Tests: which tests should I run for these files?
    uv run python scripts/brain-diagnosis.py --tests tree_sitter_analyzer/analysis/health_score.py

    # Depends: what does this file depend on?
    uv run python scripts/brain-diagnosis.py --deps tree_sitter_analyzer/analysis/health_score.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tree_sitter_analyzer.analysis.project_brain import ProjectBrain  # noqa: E402


def build_brain() -> ProjectBrain:
    """Build the impact graph for this project."""
    print("Building impact graph...", end="", flush=True)
    brain = ProjectBrain(str(PROJECT_ROOT))
    brain._build_impact_graph()
    stats = (
        f"\rGraph: {len(brain._source_stems)} files, "
        f"{len(brain._import_graph)} import edges, "
        f"{len(brain._test_to_source)} test mappings, "
        f"{len(brain._tool_refs)} tool references"
    )
    print(stats)
    return brain


def cmd_diagnose(brain: ProjectBrain) -> None:
    """Show the most fragile files — highest blast radius."""
    print("\n=== FRAGILITY ANALYSIS ===")
    print("Files with the most dependents (change them → big blast radius):\n")

    scored: list[tuple[int, str]] = []
    for _stem, rel in brain._source_stems.items():
        if "/tests/" in rel or rel.startswith("tests/"):
            continue
        dep_count = len(brain.dependents(rel))
        test_count = len(brain.affected_tests([rel]))
        if dep_count > 0:
            scored.append((dep_count * 10 + test_count, rel))

    scored.sort(reverse=True)
    for score, rel in scored[:30]:
        deps = len(brain.dependents(rel))
        tests = len(brain.affected_tests([rel]))
        short = rel.replace("tree_sitter_analyzer/", "")
        print(f"  {deps:3d} deps, {tests:2d} tests | {short} (fragility={score})")

    # Orphan files: no test coverage
    print("\n=== ORPHANS (source files with NO test coverage) ===\n")
    orphans: list[str] = []
    for _stem, rel in brain._source_stems.items():
        if "/tests/" in rel or rel.startswith("tests/"):
            continue
        if not brain.affected_tests([rel]):
            short = rel.replace("tree_sitter_analyzer/", "")
            if short.startswith("analysis/") or short.startswith("core/"):
                orphans.append(short)
    orphans.sort()
    for o in orphans[:20]:
        print(f"  - {o}")
    if len(orphans) > 20:
        print(f"  ... +{len(orphans) - 20} more")

    # Test coverage density: which tests test the most source files
    print("\n=== HUB TESTS (test files covering the most source files) ===\n")
    hub_tests: list[tuple[int, str]] = []
    for test_rel, sources in brain._test_to_source.items():
        if len(sources) > 1:
            hub_tests.append((len(sources), test_rel))
    hub_tests.sort(reverse=True)
    for count, rel in hub_tests[:15]:
        short = rel.replace("tree_sitter_analyzer/", "").replace("tests/", "")
        print(f"  {count:2d} sources | {short}")


def cmd_impact(brain: ProjectBrain, files: list[str]) -> None:
    """Show blast radius for given files."""
    report = brain.blast_radius(files)
    print(report.to_text())


def cmd_tests(brain: ProjectBrain, files: list[str]) -> None:
    """Show which tests to run for given files."""
    tests = brain.affected_tests(files)
    print(f"Tests to run ({len(tests)}) for: {', '.join(files)}\n")
    for t in tests:
        print(f"  {t}")
    if tests:
        cmd = " ".join(f"tests/{t.split('tests/')[-1]}" for t in tests[:20])
        print(f"\nCommand: uv run pytest {cmd} -q")


def cmd_deps(brain: ProjectBrain, file_path: str) -> None:
    """Show dependency tree for a file."""
    deps = brain.dependencies(file_path)
    dependents = brain.dependents(file_path)
    print(f"File: {file_path}")
    print(f"\n  Imports ({len(deps)}):")
    for d in deps:
        print(f"    - {d}")
    print(f"\n  Imported by ({len(dependents)}):")
    for d in dependents[:20]:
        print(f"    - {d}")
    if len(dependents) > 20:
        print(f"    ... +{len(dependents) - 20} more")


def main() -> None:
    parser = argparse.ArgumentParser(description="Brain Circuit — project self-diagnosis")
    parser.add_argument("--impact", nargs="+", help="Show blast radius for files")
    parser.add_argument("--tests", nargs="+", help="Show tests to run for files")
    parser.add_argument("--deps", type=str, help="Show dependencies for a file")
    parser.add_argument("--dependents", type=str, help="Show files that import this file")
    args = parser.parse_args()

    brain = build_brain()

    if args.impact:
        cmd_impact(brain, args.impact)
    elif args.tests:
        cmd_tests(brain, args.tests)
    elif args.deps:
        cmd_deps(brain, args.deps)
    elif args.dependents:
        deps = brain.dependents(args.dependents)
        print(f"Files importing {args.dependents} ({len(deps)}):")
        for d in deps:
            print(f"  - {d}")
    else:
        cmd_diagnose(brain)


if __name__ == "__main__":
    main()
