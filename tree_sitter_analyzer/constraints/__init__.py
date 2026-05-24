#!/usr/bin/env python3
"""Architectural constraint DSL (Feature 3).

YAML-defined inhibition rules → call-graph edge scan → violations
report. Wired into safe_to_edit and analyze_change_impact so a single
read of either gate tool tells an agent it is about to make a
structurally forbidden edit.

Public API:
    load_constraints(project_root) -> list[Constraint]
    evaluate(constraints, db_conn) -> list[Violation]
    Constraint, Violation
    ConstraintParseError
"""

from __future__ import annotations

from .evaluator import evaluate
from .parser import ConstraintParseError, load_constraints, match_glob
from .schema import Constraint, Violation

__all__ = [
    "Constraint",
    "ConstraintParseError",
    "Violation",
    "evaluate",
    "load_constraints",
    "match_glob",
]
