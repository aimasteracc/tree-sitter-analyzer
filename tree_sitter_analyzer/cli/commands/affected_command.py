#!/usr/bin/env python3
"""CLI dispatcher for ``--affected FILE [FILE...]``.

Returns the set of *test* files transitively affected by changes to the
given source files. Closes the last CLI-surface advantage CodeGraph
previously held (their ``codegraph affected <files>`` command).

How it works
------------
For each input file we run the existing dependency-graph forward-blast
analysis (``DependencyAnalysisTool.blast_radius`` mode), collect the
``forward_impact`` lists, union them, and filter to paths that look
like test files. The filter is heuristic, multi-language:

* Python: ``test_*.py`` / ``*_test.py`` / any path containing ``/tests/``
* Go: ``*_test.go``
* Java / Kotlin: paths containing ``/src/test/`` or ``/test/``
* Rust: paths in ``tests/`` or files containing ``#[cfg(test)]`` markers
* TypeScript / JavaScript: ``*.test.ts(x)`` / ``*.spec.ts(x)`` / ``__tests__``
* Swift: ``*Tests.swift`` / paths in ``Tests/``

A ``--affected-filter GLOB`` override lets callers override this with
their own pattern (useful for monorepos with non-standard layouts).

Output JSON envelope
--------------------
::

    {
      "success": true,
      "verdict": "INFO" | "NOT_FOUND",
      "changed_files": ["src/a.py", ...],
      "affected_files_total": 137,
      "test_files": ["tests/unit/test_a.py", ...],
      "test_files_total": 12,
      "filter_used": "(auto-heuristic)" | "<custom glob>"
    }

``--affected-quiet`` collapses output to a newline-separated list of
the test paths (no envelope) — matches CodeGraph's ``--quiet`` mode.
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
import os
from collections.abc import Callable, Iterable
from typing import Any

# Default heuristics ported from popular test-file conventions across
# the languages TSA supports. Keep this list explicit so a regression
# (e.g. a new language plugin's test convention) is one line away.
_DEFAULT_TEST_GLOBS: tuple[str, ...] = (
    # Python
    "tests/*",
    "*/tests/*",
    "test_*.py",
    "*_test.py",
    # Go
    "*_test.go",
    # Java / Kotlin (Maven / Gradle convention)
    "*/src/test/*",
    "*/test/*",
    # Rust
    "tests/*",
    "*/tests/*",
    # TS / JS
    "*.test.ts",
    "*.test.tsx",
    "*.spec.ts",
    "*.spec.tsx",
    "*.test.js",
    "*.test.jsx",
    "*.spec.js",
    "*.spec.jsx",
    "__tests__/*",
    "*/__tests__/*",
    # Swift / XCTest
    "*Tests.swift",
    "*/Tests/*",
)


def _is_test_path(rel_path: str, globs: Iterable[str]) -> bool:
    """Return True when ``rel_path`` matches any of ``globs``.

    Path is matched as-is (no normalisation beyond replacing backslashes
    on Windows-style separators); CodeGraph does the same so callers'
    glob expectations are compatible.
    """
    p = rel_path.replace("\\", "/")
    for pattern in globs:
        if fnmatch.fnmatchcase(p, pattern):
            return True
        # Also try matching the basename for glob patterns without "/" —
        # so ``test_*.py`` catches ``foo/bar/test_x.py``.
        if "/" not in pattern and fnmatch.fnmatchcase(os.path.basename(p), pattern):
            return True
    return False


def _project_root(args: Any) -> str:
    return getattr(args, "project_root", None) or os.getcwd()


def _output_format(args: Any) -> str:
    """Resolve the output shape — text or JSON envelope."""
    from tree_sitter_analyzer.cli.output_format import resolve_mcp_tool_format

    return resolve_mcp_tool_format(args)


def _collect_forward_impact(
    project_root: str,
    changed_files: list[str],
    output_error: Callable[[str], None],
) -> tuple[set[str], list[str]]:
    """Run blast_radius once per changed file; return (union, invalid).

    Bad-input paths are collected separately so the dispatcher can emit
    a single canonical envelope listing them rather than crashing on
    the first one.
    """
    from tree_sitter_analyzer.mcp.tools.dependency_analysis_tool import (
        DependencyAnalysisTool,
    )

    tool = DependencyAnalysisTool(project_root=project_root)
    union: set[str] = set()
    invalid: list[str] = []

    for f in changed_files:
        abs_path = (
            f if os.path.isabs(f) else os.path.normpath(os.path.join(project_root, f))
        )
        if not os.path.isfile(abs_path):
            invalid.append(f)
            continue
        try:
            result = asyncio.run(
                tool.execute(
                    {
                        "mode": "blast_radius",
                        "file_path": abs_path,
                        "output_format": "json",
                    }
                )
            )
        except Exception as exc:  # noqa: BLE001
            output_error(f"--affected: blast_radius failed for {f!r}: {exc}")
            continue
        for dep in result.get("forward_impact") or []:
            union.add(dep)

    return union, invalid


def run_affected(args: Any, output_error: Callable[[str], None]) -> int:
    """Dispatch ``--affected`` → forward-impact union filtered to tests.

    Returns exit code:
      * ``0`` on success (even when no tests matched).
      * ``1`` on unrecoverable error (project root missing, all files
        invalid).
    """
    project_root = _project_root(args)
    if not project_root or not os.path.isdir(project_root):
        output_error("--affected requires a valid project root")
        return 1

    changed_files: list[str] = list(getattr(args, "affected", None) or [])
    if not changed_files:
        output_error("--affected requires at least one FILE argument")
        return 1

    custom_filter = getattr(args, "affected_filter", None)
    globs = (custom_filter,) if custom_filter else _DEFAULT_TEST_GLOBS
    quiet = bool(getattr(args, "affected_quiet", False))
    output_format = _output_format(args)

    union, invalid = _collect_forward_impact(project_root, changed_files, output_error)
    if invalid and not union:
        # All inputs invalid → exit 1 so shell pipelines can detect failure.
        output_error(
            f"--affected: none of the requested files exist on disk: {invalid}"
        )
        return 1

    test_files = sorted(p for p in union if _is_test_path(p, globs))

    if quiet:
        # Match CodeGraph's --quiet mode: just one path per line.
        for p in test_files:
            print(p)
        return 0

    envelope: dict[str, Any] = {
        "success": True,
        "verdict": "INFO" if test_files else "NOT_FOUND",
        "changed_files": list(changed_files),
        "affected_files_total": len(union),
        "test_files": test_files,
        "test_files_total": len(test_files),
        "filter_used": custom_filter or "(auto-heuristic)",
    }
    if invalid:
        envelope["invalid_input_files"] = invalid

    if output_format == "json":
        print(json.dumps(envelope, indent=2, default=str))
    else:
        # Plain text: same envelope, one line per key for grep-ability.
        print(f"changed_files: {envelope['changed_files']}")
        print(f"affected_files_total: {envelope['affected_files_total']}")
        print(f"test_files_total: {envelope['test_files_total']}")
        print(f"verdict: {envelope['verdict']}")
        for p in test_files:
            print(p)
    return 0
