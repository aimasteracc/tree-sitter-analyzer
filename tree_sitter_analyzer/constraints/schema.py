#!/usr/bin/env python3
"""Immutable data classes for architectural-constraints DSL.

A ``Constraint`` represents one parsed YAML rule. The dataclass is
``frozen=True`` so a constraint cannot be mutated after parsing — every
"modification" must produce a new instance. This matches the
project-wide immutability convention (see CLAUDE.md / coding-style.md).

A ``Violation`` represents one offending call edge that was caught by
``evaluate()``. It carries the rule identity plus the edge endpoints so
downstream tooling (safe_to_edit, change_impact) can attribute the
breach without re-running the evaluator.

Both dataclasses use ``tuple`` (not ``list``) for sequence fields so
they remain hashable and can be cached / put into sets if needed by
later phases.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Constraint:
    """One parsed architectural rule.

    YAML keys ``from:`` and ``to:`` are reserved words in Python, so the
    parser renames them to ``from_glob`` / ``to_glob`` on load. The raw
    YAML strings are kept here (compiled patterns live in
    ``parser._CompiledConstraint`` for fast matching during evaluation).

    Fields:
        id: Stable identifier for the rule. Used to dedupe and attribute
            violations across runs.
        severity: One of ``error``, ``warn``, ``info``.
        rule: Currently only ``forbid`` is supported. Future rule types
            (``require``, ``layer``) reserved.
        from_glob: Caller-side fnmatch-style glob (``**`` supported).
        to_glob: Callee-side fnmatch-style glob.
        reason: Human-readable explanation surfaced to agents.
        exceptions: Tuple of caller-side globs that suppress the rule.
            Empty tuple (not None) when no exceptions are configured —
            downstream code iterates without a guard.
    """

    id: str
    severity: str
    rule: str
    from_glob: str
    to_glob: str
    reason: str
    exceptions: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Violation:
    """One offending call edge produced by ``evaluate()``.

    The combination of (rule_id, caller_file, caller_line, callee_name)
    is unique per evaluator run; the same combination is the PRIMARY KEY
    of ``ast_constraint_violations`` so write-through caching is
    natural.

    Fields mirror the spec's column names exactly so a failure trace
    points the implementer at the right SQL column.
    """

    rule_id: str
    caller_file: str
    caller_name: str
    caller_line: int
    callee_name: str
    callee_file: str
    severity: str
    detected_at: int  # unix timestamp seconds, set by the evaluator
