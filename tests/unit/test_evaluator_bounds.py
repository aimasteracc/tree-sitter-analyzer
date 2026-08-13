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


def test_iter_violations_checks_deadline_and_filters_scope_before_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tree_sitter_analyzer.constraints import Constraint
    from tree_sitter_analyzer.constraints import evaluator as evaluator_module
    from tree_sitter_analyzer.constraints.parser import compile_constraints

    rows = [
        ("caller", "src/a.py", 1, "missing", None),
        ("caller", "src/a.py", 2, "outside", "vendor/b.py"),
        ("caller", "src/a.py", 3, "inside", "lib/b.py"),
    ]

    class Connection:
        def execute(self, _sql: str, _params: object):
            return iter(rows)

    monkeypatch.setattr(evaluator_module, "_build_import_index", lambda *_a, **_k: None)
    monkeypatch.setattr(
        evaluator_module, "_build_select_query", lambda *_a: ("SELECT", ())
    )
    callbacks: list[str] = []
    result = list(
        evaluator_module._iter_violations(
            compile_constraints(
                [Constraint("rule", "warn", "forbid", "src/**", "lib/**", "boundary")]
            ),
            Connection(),
            7,
            scope_predicate=lambda _caller, callee: callee.startswith("lib/"),
            check_callback=lambda: callbacks.append("checked"),
        )
    )

    assert [(item.rule_id, item.callee_file, item.detected_at) for item in result] == [
        ("rule", "lib/b.py", 7)
    ]
    assert callbacks == ["checked", "checked", "checked", "checked"]


def test_iter_violations_accepts_optional_callbacks_and_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tree_sitter_analyzer.constraints import Constraint
    from tree_sitter_analyzer.constraints import evaluator as evaluator_module
    from tree_sitter_analyzer.constraints.parser import compile_constraints

    class Connection:
        def execute(self, _sql: str, _params: object):
            return iter((("caller", "src/a.py", 4, "callee", "lib/b.py"),))

    monkeypatch.setattr(evaluator_module, "_build_import_index", lambda *_a, **_k: None)
    monkeypatch.setattr(
        evaluator_module, "_build_select_query", lambda *_a: ("SELECT", ())
    )
    result = list(
        evaluator_module._iter_violations(
            compile_constraints(
                [Constraint("rule", "warn", "forbid", "src/**", "lib/**", "boundary")]
            ),
            Connection(),
            9,
        )
    )

    assert [(item.rule_id, item.caller_line, item.callee_file) for item in result] == [
        ("rule", 4, "lib/b.py")
    ]
