#!/usr/bin/env python3
"""
Change Impact Analysis MCP Tool.

Combines git diff with dependency graph to provide change impact analysis.
Tells AI agents: what changed, what's affected, what tests to run.
"""

from __future__ import annotations

import subprocess  # nosec B404
from pathlib import Path
from typing import Any

from ...project_graph import BlastRadius, DependencyGraph
from ..utils.format_helper import apply_toon_format_to_response
from .base_tool import BaseMCPTool

TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["diff", "staged", "branch"],
            "default": "diff",
            "description": "diff=unstaged, staged=staged, branch=vs main",
        },
        "include_tests": {
            "type": "boolean",
            "default": True,
            "description": "Find related test files",
        },
        "output_format": {
            "type": "string",
            "enum": ["json", "toon"],
            "default": "toon",
        },
    },
    "additionalProperties": False,
}


def _run_git(args: list[str], cwd: str | None = None) -> tuple[int, str]:
    try:
        result = subprocess.run(  # nosec B603
            ["git"] + args,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=10,
        )
        return result.returncode, result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return 1, ""


def _get_changed_files(mode: str, project_root: str | None) -> list[str]:
    if mode == "staged":
        rc, out = _run_git(["diff", "--cached", "--name-only"], cwd=project_root)
    elif mode == "branch":
        rc, out = _run_git(["diff", "--name-only", "HEAD~1", "HEAD"], cwd=project_root)
    else:
        rc, out = _run_git(["diff", "--name-only"], cwd=project_root)

    if rc != 0 or not out:
        return []
    return [f for f in out.splitlines() if f.strip()]


def _get_diff_stat(mode: str, project_root: str | None) -> str:
    if mode == "staged":
        rc, out = _run_git(["diff", "--cached", "--stat"], cwd=project_root)
    elif mode == "branch":
        rc, out = _run_git(["diff", "--stat", "HEAD~1", "HEAD"], cwd=project_root)
    else:
        rc, out = _run_git(["diff", "--stat"], cwd=project_root)
    return out if rc == 0 else ""


def _find_test_files(
    changed_files: list[str],
    graph_nodes: set[str],
) -> dict[str, list[str]]:
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

    all_nodes = graph_nodes
    test_files = {
        n
        for n in all_nodes
        if any(n.startswith(d) for d in test_dirs) or n.endswith(test_suffixes)
    }

    mapping: dict[str, list[str]] = {}
    for cf in changed_files:
        stem = Path(cf).stem
        related = []
        for tf in sorted(test_files):
            tf_stem = Path(tf).stem
            if (
                stem in tf_stem
                or tf_stem.replace("_test", "").replace("test_", "") == stem
            ):
                related.append(tf)
        mapping[cf] = related or ["(auto-discover: run full suite)"]

    return mapping


def _assess_risk(
    changed_files: list[str],
    affected: set[str],
    graph: DependencyGraph,
) -> str:
    if not changed_files:
        return "none"
    total_affected = len(affected)
    if total_affected <= 2:
        return "low"
    if total_affected <= 8:
        return "medium"
    return "high"


class ChangeImpactTool(BaseMCPTool):
    """Analyze the impact of code changes using git diff + dependency graph."""

    def get_tool_schema(self) -> dict[str, Any]:
        return TOOL_SCHEMA

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "analyze_change_impact",
            "description": (
                "After editing: git diff + dep graph → affected files, tests to run, risk. "
                "MUST call after edits. No built-in tool provides this."
            ),
            "inputSchema": self.get_tool_schema(),
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        if "mode" in arguments and arguments["mode"] not in (
            "diff",
            "staged",
            "branch",
        ):
            raise ValueError("mode must be diff|staged|branch")
        return True

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        mode = arguments.get("mode", "diff")
        include_tests = arguments.get("include_tests", True)
        output_format = arguments.get("output_format", "toon")

        changed_files = _get_changed_files(mode, self.project_root)

        if not changed_files:
            result: dict[str, Any] = {
                "success": True,
                "mode": mode,
                "changed_files": [],
                "summary": "No changes detected",
            }
            return apply_toon_format_to_response(result, output_format)

        diff_stat = _get_diff_stat(mode, self.project_root)

        try:
            graph = DependencyGraph(self.project_root or ".")
        except Exception:
            graph = None

        affected: set[str] = set()
        file_impacts: list[dict[str, Any]] = []

        if graph:
            blast = BlastRadius(graph)
            for cf in changed_files:
                fwd = blast.forward(cf)
                affected.update(fwd)
                file_impacts.append(
                    {
                        "file": cf,
                        "direct_dependents": sorted(graph.dependents_of(cf))[:20],
                        "total_affected": len(fwd),
                    }
                )
        else:
            file_impacts = [{"file": cf} for cf in changed_files]

        risk = _assess_risk(changed_files, affected, graph) if graph else "unknown"

        test_mapping = {}
        if include_tests and graph:
            test_mapping = _find_test_files(changed_files, set(graph.nodes()))

        all_tests = sorted(
            {
                t
                for tests in test_mapping.values()
                for t in tests
                if not t.startswith("(")
            }
        )

        result = {
            "success": True,
            "mode": mode,
            "changed_count": len(changed_files),
            "changed_files": changed_files[:50],
            "affected_count": len(affected),
            "affected_files": sorted(affected)[:50] if affected else [],
            "risk_level": risk,
            "file_impacts": file_impacts[:20],
            "tests_to_run": all_tests[:30] if all_tests else [],
            "test_mapping": test_mapping if test_mapping else {},
            "diff_stat": diff_stat[:500] if diff_stat else "",
        }

        return apply_toon_format_to_response(result, output_format)
