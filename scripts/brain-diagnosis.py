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

    # Test health overview
    health = brain.test_health()
    print("\n=== TEST HEALTH ===")
    print(f"  Test functions: {health['total_test_functions']}")
    print(f"  Total asserts: {health['total_asserts']} (density: {health['assert_density']})")
    print(f"  Mock ratio: {health['mock_ratio']}")
    print(f"  Zero-assert tests: {len(health['zero_assert_tests'])}")
    print(f"  Orphan sources: {len(health['orphan_sources'])}")

    # Zero-assert tests by file
    if health["zero_assert_tests"]:
        from collections import Counter
        file_counts = Counter(t["file"] for t in health["zero_assert_tests"])
        print("\n  Zero-assert tests by file (top 10):")
        for f, c in file_counts.most_common(10):
            short = f.replace("tests/", "")
            print(f"    {c:3d} | {short}")

    # Assertion quality
    aq = brain.assertion_quality()
    print("\n=== ASSERTION QUALITY ===")
    print(f"  Effective ratio: {aq['effective_ratio']} ({aq['total_weak']} weak / {aq['total_asserts']} total)")
    if aq["files"][:5]:
        print("  Weakest files:")
        for f in aq["files"][:5]:
            short = f["file"].replace("tests/", "")
            print(f"    {f['weak_asserts']:4d} weak / {f['total_asserts']:4d} total ({f['weak_ratio']:.0%}) | {short}")

    # Test fragility
    frag = brain.test_fragility()
    if frag["fragile_files"]:
        print(f"\n=== FRAGILE TESTS ({len(frag['fragile_files'])} files) ===")
        for f in frag["fragile_files"][:8]:
            short = f["file"].replace("tests/", "")
            pats = ", ".join(f"{k}={v}" for k, v in f["patterns"].items())
            print(f"    {short}: {pats}")

    # Test staleness
    stale = brain.test_staleness()
    if stale:
        print(f"\n=== STALE TESTS ({len(stale)} pairs) ===")
        for s in stale[:8]:
            t = s["test"].replace("tests/", "")
            src = s["source"].replace("tree_sitter_analyzer/", "")
            print(f"    {t} ← {src} ({s['days_behind']}d behind)")

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


def cmd_coverage(brain: ProjectBrain, file_path: str) -> None:
    """Show per-symbol test coverage for a file."""
    cov = brain.get_test_coverage(file_path)
    print(f"File: {cov['file']}")
    print(f"  Total symbols: {cov['total_symbols']}")
    print(f"  Coverage: {cov['coverage_pct']}% ({cov['covered_count']}/{cov['total_symbols']})")
    print(f"  Test files: {', '.join(cov['test_files']) or 'NONE'}")
    print(f"  Real test files: {', '.join(cov['real_test_files']) or 'NONE'}")
    if cov['covered_symbols']:
        print("\n  Covered symbols:")
        for s in cov['covered_symbols']:
            print(f"    + {s}")
    if cov['uncovered_symbols']:
        print(f"\n  Uncovered symbols ({len(cov['uncovered_symbols'])}):")
        for s in cov['uncovered_symbols'][:20]:
            print(f"    - {s}")
        if len(cov['uncovered_symbols']) > 20:
            print(f"    ... +{len(cov['uncovered_symbols']) - 20} more")
    if cov['test_metrics']:
        print("\n  Test quality:")
        for tm in cov['test_metrics']:
            print(f"    {tm['file']}: {tm['test_count']} tests, "
                  f"{tm['assert_count']} asserts, {tm['mock_count']} mocks")


def cmd_test_health(brain: ProjectBrain) -> None:
    """Show project-wide test quality."""
    health = brain.test_health()
    print("\n=== TEST HEALTH ===")
    print(f"  Test functions: {health['total_test_functions']}")
    print(f"  Total asserts: {health['total_asserts']} (density: {health['assert_density']})")
    print(f"  Total mocks: {health['total_mocks']} (ratio: {health['mock_ratio']})")
    print(f"  Zero-assert tests: {len(health['zero_assert_tests'])}")
    print(f"  Orphan sources: {len(health['orphan_sources'])}")

    if health['zero_assert_tests']:
        from collections import Counter
        file_counts = Counter(t["file"] for t in health["zero_assert_tests"])
        print("\n  Zero-assert tests by file:")
        for f, c in file_counts.most_common():
            short = f.replace("tests/", "")
            print(f"    {c:3d} | {short}")
        print("\n  Zero-assert test names (first 30):")
        for t in health['zero_assert_tests'][:30]:
            print(f"    {t['file'].replace('tests/', '')}::{t['test']}")

    if health['high_mock_files']:
        print("\n  High mock ratio files:")
        for f in health['high_mock_files']:
            q = brain._test_quality.get(f, {})
            print(f"    {f.replace('tests/', '')} (mocks={q.get('mock_count', 0)}, "
                  f"asserts={q.get('assert_count', 0)})")

    if health['orphan_sources']:
        print("\n  Orphan sources (no test coverage):")
        for f in sorted(health['orphan_sources']):
            short = f.replace("tree_sitter_analyzer/", "")
            print(f"    {short}")

    if health['module_coverage']:
        print("\n  Module coverage:")
        for mod, cov in sorted(health['module_coverage'].items()):
            total = cov['total']
            covered = cov['covered']
            pct = round(covered / max(1, total) * 100, 1)
            print(f"    {mod}: {covered}/{total} symbols ({pct}%)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Brain Circuit — project self-diagnosis")
    parser.add_argument("--impact", nargs="+", help="Show blast radius for files")
    parser.add_argument("--tests", nargs="+", help="Show tests to run for files")
    parser.add_argument("--deps", type=str, help="Show dependencies for a file")
    parser.add_argument("--dependents", type=str, help="Show files that import this file")
    parser.add_argument("--coverage", type=str, help="Show per-symbol test coverage for a file")
    parser.add_argument("--test-health", action="store_true", help="Show test quality overview")
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
    elif args.coverage:
        cmd_coverage(brain, args.coverage)
    elif args.test_health:
        cmd_test_health(brain)
    else:
        cmd_diagnose(brain)


if __name__ == "__main__":
    main()
