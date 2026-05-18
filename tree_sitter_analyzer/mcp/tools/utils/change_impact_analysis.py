"""Change-impact analysis helpers shared by MCP and CLI entry points."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ....project_graph import BlastRadius, DependencyGraph
from .change_impact_response import (
    LARGE_DIRTY_DIFF_THRESHOLD,
    AgentSummaryContext,
    ChangeImpactResponseContext,
    build_agent_summary,
    build_change_impact_response,
    build_no_changes_result,
)
from .change_impact_response import (
    build_agent_summary_only_response as build_agent_summary_only_response,
)
from .change_impact_verification import (
    AUTO_DISCOVER_TEST_HINT,
    DOCS_ONLY_TEST_HINT,
    _build_verification_plan,
    _is_docs_only_change,
)
from .test_discovery_stems import related_stem_matches, related_test_stems_for_path
from .verification_command import (
    DefaultTestCommand,
    build_test_command,
    detect_default_test_command,
)

TESTS_TO_RUN_DISPLAY_LIMIT = 30
FOCUSED_TEST_COMMAND_LIMIT = 20


@dataclass(frozen=True)
class ChangeImpactRequest:
    """Inputs needed to build a change-impact response."""

    mode: str
    changed_files: list[str]
    diff_stat: str
    project_root: str | None
    include_tests: bool
    scope_paths: list[str] | None = None


def _find_test_files(
    changed_files: list[str],
    graph_nodes: set[str],
) -> dict[str, list[str]]:
    """Map changed files to related test files using stem matching."""
    test_dirs = {"tests/", "test/", "spec/", "__tests__/"}
    test_suffixes = (
        "_test.py",
        "_test.js",
        "_test.ts",
        "Test.java",
        ".test.py",
        ".test.js",
        ".test.ts",
        "_spec.py",
        "_spec.js",
    )

    test_files = {
        node
        for node in graph_nodes
        if _is_runnable_test_file(node, test_dirs, test_suffixes)
    }

    mapping: dict[str, list[str]] = {}
    for changed_file in changed_files:
        if _is_docs_only_change(changed_file):
            mapping[changed_file] = [DOCS_ONLY_TEST_HINT]
            continue

        related = [
            test_file
            for test_file in sorted(test_files)
            if _test_file_matches_change(test_file, changed_file)
        ]
        mapping[changed_file] = related or [AUTO_DISCOVER_TEST_HINT]

    return mapping


def _test_file_matches_change(test_file: str, changed_file: str) -> bool:
    """Return True when a test filename appears related to a changed file."""
    changed_stem = Path(changed_file).stem
    test_stem = Path(test_file).stem
    direct_stem = test_stem.replace("_test", "").replace("test_", "")
    if changed_stem in test_stem or direct_stem == changed_stem:
        return True
    return any(
        related_stem_matches(test_stem, related_stem)
        for related_stem in related_test_stems_for_path(changed_file)
    )


def _is_runnable_test_file(
    path: str,
    test_dirs: set[str],
    test_suffixes: tuple[str, ...],
) -> bool:
    """Return True for files that are intended to be direct pytest targets."""
    normalized = path.replace("\\", "/")
    name = Path(normalized).name
    if name in {"conftest.py", "__init__.py"}:
        return False
    in_test_dir = any(
        normalized.startswith(directory) or f"/{directory}" in normalized
        for directory in test_dirs
    )
    return (
        (in_test_dir and name.startswith("test_"))
        or name.endswith(test_suffixes)
        or (in_test_dir and (".test." in name or ".spec." in name))
    )


def _assess_risk(
    changed_files: list[str],
    affected: set[str],
    graph: DependencyGraph,
) -> str:
    """Assess change risk level based on blast radius size."""
    if not changed_files:
        return "none"
    total_affected = len(affected)
    if total_affected <= 2:
        return "low"
    if total_affected <= 8:
        return "medium"
    return "high"


def _build_file_impacts(
    changed_files: list[str],
    graph: DependencyGraph | None,
) -> tuple[set[str], list[dict[str, Any]]]:
    """Build per-file impact rows and the total affected file set."""
    if graph is None:
        return set(), [{"file": changed_file} for changed_file in changed_files]

    affected: set[str] = set()
    file_impacts: list[dict[str, Any]] = []
    blast = BlastRadius(graph)
    for changed_file in changed_files:
        fwd = blast.forward(changed_file)
        affected.update(fwd)
        file_impacts.append(
            {
                "file": changed_file,
                "direct_dependents": sorted(graph.dependents_of(changed_file))[:20],
                "total_affected": len(fwd),
            }
        )

    return affected, file_impacts


def _build_test_plan(
    changed_files: list[str],
    graph: DependencyGraph | None,
    include_tests: bool,
) -> tuple[dict[str, list[str]], list[str]]:
    """Build changed-file-to-test mapping and a sorted runnable test list."""
    if not include_tests or graph is None:
        return {}, []

    test_mapping = _find_test_files(changed_files, set(graph.nodes()))
    tests_to_run = sorted(
        {
            test_path
            for tests in test_mapping.values()
            for test_path in tests
            if not test_path.startswith("(")
        }
    )
    return test_mapping, tests_to_run


def _load_dependency_graph(project_root: str | None) -> DependencyGraph | None:
    """Build the dependency graph, returning None when analysis is unavailable."""
    try:
        return DependencyGraph(project_root or ".")
    except Exception:
        return None


def _build_verification_strategy(
    *,
    changed_count: int,
    tests_to_run: list[str],
    verification: dict[str, Any],
) -> dict[str, Any]:
    """Build an action-oriented verification strategy for agents."""
    default_command = DefaultTestCommand(
        verification["test_runner"],
        verification["default_test_command"],
    )
    can_build_focused_command = 0 < len(tests_to_run) <= FOCUSED_TEST_COMMAND_LIMIT
    focused_command = (
        build_test_command(default_command, tests_to_run)
        if verification["test_required"] and can_build_focused_command
        else ""
    )
    final_command = verification["verification_command"]

    steps, strategy, hint = _select_verification_path(
        verification=verification,
        focused_command=focused_command,
        final_command=final_command,
        tests_to_run_count=len(tests_to_run),
        default_command=default_command.command,
    )
    hint = _append_large_dirty_hint(hint, changed_count)

    return {
        "focused_test_command": focused_command,
        "verification_strategy": strategy,
        "verification_steps": steps,
        "verification_hint": hint,
    }


def _select_verification_path(
    *,
    verification: dict[str, Any],
    focused_command: str,
    final_command: str,
    tests_to_run_count: int,
    default_command: str,
) -> tuple[list[str], str, str]:
    """Choose verification steps, strategy label, and hint text."""
    if not verification["test_required"]:
        return (
            ["git diff --check"],
            "docs_only",
            "Docs-only diff; skip pytest unless code changes are added.",
        )
    if focused_command and focused_command != final_command:
        return (
            [focused_command, final_command],
            "focused_then_default",
            "Run focused tests while iterating; run the default suite once at the "
            "queue boundary because unmapped runtime changes remain.",
        )
    if tests_to_run_count > FOCUSED_TEST_COMMAND_LIMIT:
        return (
            [default_command],
            "default_for_large_diff",
            f"{tests_to_run_count} mapped tests exceed the focused command limit "
            f"({FOCUSED_TEST_COMMAND_LIMIT}); use queue-specific focused tests while "
            "editing and run the default suite once at the verification boundary.",
        )
    return (
        [final_command],
        "single_command",
        "Run the recommended verification command for this diff.",
    )


def _append_large_dirty_hint(hint: str, changed_count: int) -> str:
    """Append large-diff guidance without obscuring the primary hint."""
    if changed_count > LARGE_DIRTY_DIFF_THRESHOLD:
        return (
            f"{hint} Large dirty worktree detected ({changed_count} changed files); "
            "avoid rerunning the default suite after every tiny edit."
        )
    return hint


def _build_change_impact_result(request: ChangeImpactRequest) -> dict[str, Any]:
    """Build the full change-impact response for changed files."""
    graph = _load_dependency_graph(request.project_root)
    affected, file_impacts = _build_file_impacts(request.changed_files, graph)
    risk = _assess_risk(request.changed_files, affected, graph) if graph else "unknown"
    test_mapping, all_tests = _build_test_plan(
        request.changed_files, graph, request.include_tests
    )
    default_test_command = detect_default_test_command(request.project_root)
    verification = _build_verification_plan(
        request.changed_files,
        all_tests,
        test_mapping,
        default_test_command,
    )
    strategy = _build_verification_strategy(
        changed_count=len(request.changed_files),
        tests_to_run=all_tests,
        verification=verification,
    )
    visible_tests = all_tests[:TESTS_TO_RUN_DISPLAY_LIMIT]

    agent_summary = build_agent_summary(
        AgentSummaryContext(
            risk=risk,
            changed_files=request.changed_files,
            scope_paths=request.scope_paths,
            verification=verification,
            strategy=strategy,
            affected_count=len(affected),
            tests_to_run_count=len(all_tests),
        )
    )

    return build_change_impact_response(
        ChangeImpactResponseContext(
            request=request,
            risk=risk,
            affected=affected,
            file_impacts=file_impacts,
            visible_tests=visible_tests,
            all_tests=all_tests,
            verification=verification,
            strategy=strategy,
            test_mapping=test_mapping,
            agent_summary=agent_summary,
        )
    )


_build_no_changes_result = build_no_changes_result
_build_agent_summary = build_agent_summary
_build_change_impact_response = build_change_impact_response
