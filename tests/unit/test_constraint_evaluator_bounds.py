"""Bounded evaluator deadline and materialization contracts."""

from __future__ import annotations

import sqlite3

import pytest


def test_evaluator_returns_empty_when_compiler_filters_all_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tree_sitter_analyzer.constraints import Constraint
    from tree_sitter_analyzer.constraints import evaluator as evaluator_module

    rule = Constraint("r", "warn", "forbid", "**", "**", "test")
    monkeypatch.setattr(evaluator_module, "compile_constraints", lambda _rules: [])

    assert evaluator_module.evaluate([rule], object()) == []


def test_evaluator_rejects_negative_capacity() -> None:
    from tree_sitter_analyzer.constraints import Constraint, evaluate

    rule = Constraint("r", "warn", "forbid", "**", "**", "test")
    conn = sqlite3.connect(":memory:")
    try:
        with pytest.raises(ValueError, match="^capacity must be non-negative$"):
            evaluate([rule], conn, capacity=-1)
    finally:
        conn.close()


def test_evaluator_checks_callback_for_each_materialized_violation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tree_sitter_analyzer.constraints import Constraint, Violation
    from tree_sitter_analyzer.constraints import evaluator as evaluator_module

    violation = Violation("r", "a.py", "a", 1, "b", "b.py", "warn", 0)
    monkeypatch.setattr(
        evaluator_module,
        "_iter_violations",
        lambda *_args, **_kwargs: iter((violation,)),
    )
    callbacks: list[str] = []

    result = evaluator_module.evaluate(
        [Constraint("r", "warn", "forbid", "**", "**", "test")],
        object(),
        check_callback=lambda: callbacks.append("checked"),
    )

    assert result == [violation]
    assert callbacks == ["checked"]


def test_evaluator_capacity_bounds_materialized_violations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tree_sitter_analyzer.constraints import Constraint, Violation
    from tree_sitter_analyzer.constraints import evaluator as evaluator_module

    violation = Violation("r", "a.py", "a", 1, "b", "b.py", "warn", 0)
    monkeypatch.setattr(
        evaluator_module,
        "_iter_violations",
        lambda *_args, **_kwargs: iter((violation,)),
    )

    with pytest.raises(RuntimeError, match="^CONSTRAINT_EVALUATION_CAPACITY$"):
        evaluator_module.evaluate(
            [Constraint("r", "warn", "forbid", "**", "**", "test")],
            object(),
            capacity=0,
        )
