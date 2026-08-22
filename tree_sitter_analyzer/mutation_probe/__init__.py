#!/usr/bin/env python3
"""Mutation probe: "does this test constrain this code?" (RFC-0029).

Public API
----------
:func:`probe`
    Ask whether a test node detects a mutation at a code location.

:class:`ConstrainsResult`
    The result type.

:data:`FailureKind`
    Literal type for run outcomes.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from .engine import apply_mutation
from .runner import is_timeout, run_test
from .types import ConstrainsResult, FailureKind

__all__ = [
    "ConstrainsResult",
    "FailureKind",
    "probe",
]


def _file_to_module_name(abs_file: str, project_root: str) -> str:
    """Convert an absolute file path to a dotted Python module name.

    Walks up the path from *abs_file*, strips the ``.py`` extension, and
    joins the components with ``"."``.  Does NOT verify ``__init__.py``
    presence — relies on the project layout following the standard package
    convention (which this project does).

    Examples
    --------
    ``/project/tree_sitter_analyzer/import_graph.py``
    → ``"tree_sitter_analyzer.import_graph"``
    """
    path = Path(abs_file)
    root = Path(os.path.abspath(project_root))
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    parts = list(rel.with_suffix("").parts)
    return ".".join(parts)


def _unknown(
    reason: str,
    mutation: str,
    baseline_failure: FailureKind = "NOT_RUN",
    mutated_failure: FailureKind = "NOT_RUN",
    baseline_ms: float = 0.0,
    mutated_ms: float = 0.0,
    overhead_ms: float = 0.0,
) -> ConstrainsResult:
    return ConstrainsResult(
        verdict="unknown",
        reason=reason,
        mutation=mutation,
        baseline_failure=baseline_failure,
        mutated_failure=mutated_failure,
        baseline_ms=baseline_ms,
        mutated_ms=mutated_ms,
        overhead_ms=overhead_ms,
    )


def probe(
    test_node_id: str,
    code_location: str,
    project_root: str = ".",
    timeout: float = 60.0,
) -> ConstrainsResult:
    """Ask: does *test_node_id* constrain the code at *code_location*?

    Parameters
    ----------
    test_node_id:
        Fully-qualified pytest node id,
        e.g. ``"tests/unit/latency/test_latency.py::test_p50_positive"``.
    code_location:
        ``"path/to/file.py:N"`` — a path relative to *project_root* and a
        1-indexed line number.
    project_root:
        Root of the project (default: current directory).
    timeout:
        Wall-clock budget in seconds for the entire probe call (both runs
        combined).  The 60 s default is the RFC-defined budget.

    Returns
    -------
    :class:`ConstrainsResult` with one of:

    * ``"constrains"`` — baseline passed, mutated run failed with an
      assertion-derived failure.
    * ``"does_not_constrain"`` — mutated run passed (the test did not detect
      the change).
    * ``"unknown"`` — any fail-closed condition (see ``reason`` for the
      subcode).

    Fail-closed rules
    -----------------
    The function NEVER returns ``"constrains"`` unless all of:
    - baseline green,
    - exactly one applicable mutation found,
    - mutated run failed with an *assertion-derived* exception.
    """
    wall_start = time.perf_counter()

    # Parse code_location → file path + line number.
    try:
        colon_idx = code_location.rfind(":")
        if colon_idx <= 0:
            raise ValueError("missing colon")
        file_part = code_location[:colon_idx]
        lineno = int(code_location[colon_idx + 1 :])
    except (ValueError, TypeError):
        return _unknown(
            "INVALID_LOCATION",
            f"invalid code_location {code_location!r}",
        )

    project_root_abs = os.path.abspath(project_root)
    abs_file = os.path.normpath(os.path.join(project_root_abs, file_part))

    if not os.path.isfile(abs_file):
        return _unknown(
            "FILE_NOT_FOUND",
            f"file not found: {abs_file!r}",
        )

    with open(abs_file, "rb") as fh:
        original_bytes = fh.read()

    # Apply mutation (in memory, never written to disk).
    mutation_result = apply_mutation(original_bytes, lineno)
    if mutation_result is None:
        return _unknown(
            "NO_INVERTIBLE_BRANCH",
            f"no applicable mutation at {code_location}",
        )

    module_name = _file_to_module_name(abs_file, project_root_abs)

    # Step 1 — Baseline run (unmodified tree).
    half_budget = timeout / 2.0
    b_kind, b_ms, b_out = run_test(
        node_id=test_node_id,
        project_root=project_root_abs,
        timeout_s=half_budget,
    )

    if is_timeout(b_out):
        return _unknown(
            "TIMEOUT",
            mutation_result.description,
            baseline_failure="NOT_RUN",
            baseline_ms=b_ms,
            overhead_ms=(time.perf_counter() - wall_start) * 1000.0 - b_ms,
        )

    if b_kind == "NOT_RUN":
        return _unknown(
            "NOT_ISOLABLE",
            mutation_result.description,
            baseline_failure="NOT_RUN",
            baseline_ms=b_ms,
            overhead_ms=(time.perf_counter() - wall_start) * 1000.0 - b_ms,
        )

    if b_kind != "NONE":
        return _unknown(
            "BASELINE_NOT_GREEN",
            mutation_result.description,
            baseline_failure=b_kind,
            baseline_ms=b_ms,
            overhead_ms=(time.perf_counter() - wall_start) * 1000.0 - b_ms,
        )

    # Step 2 — Mutated run.
    used_s = b_ms / 1000.0
    remaining = max(timeout - used_s, 10.0)
    m_kind, m_ms, m_out = run_test(
        node_id=test_node_id,
        project_root=project_root_abs,
        timeout_s=remaining,
        mutated_module=module_name,
        mutated_bytes=mutation_result.mutated_bytes,
    )

    wall_total_ms = (time.perf_counter() - wall_start) * 1000.0
    overhead_ms = wall_total_ms - b_ms - m_ms

    if is_timeout(m_out):
        return _unknown(
            "TIMEOUT",
            mutation_result.description,
            baseline_failure="NONE",
            mutated_failure="NOT_RUN",
            baseline_ms=b_ms,
            mutated_ms=m_ms,
            overhead_ms=overhead_ms,
        )

    if m_kind == "NOT_RUN":
        return _unknown(
            "NOT_ISOLABLE",
            mutation_result.description,
            baseline_failure="NONE",
            mutated_failure="NOT_RUN",
            baseline_ms=b_ms,
            mutated_ms=m_ms,
            overhead_ms=overhead_ms,
        )

    if m_kind == "NON_ASSERTION":
        return _unknown(
            "MUTATED_RUN_CRASHED",
            mutation_result.description,
            baseline_failure="NONE",
            mutated_failure="NON_ASSERTION",
            baseline_ms=b_ms,
            mutated_ms=m_ms,
            overhead_ms=overhead_ms,
        )

    if m_kind == "ASSERTION":
        return ConstrainsResult(
            verdict="constrains",
            reason=None,
            mutation=mutation_result.description,
            baseline_failure="NONE",
            mutated_failure="ASSERTION",
            baseline_ms=b_ms,
            mutated_ms=m_ms,
            overhead_ms=overhead_ms,
        )

    # m_kind == "NONE" → mutated run passed → test does not constrain.
    return ConstrainsResult(
        verdict="does_not_constrain",
        reason="MUTATED_RUN_PASSED",
        mutation=mutation_result.description,
        baseline_failure="NONE",
        mutated_failure="NONE",
        baseline_ms=b_ms,
        mutated_ms=m_ms,
        overhead_ms=overhead_ms,
    )
