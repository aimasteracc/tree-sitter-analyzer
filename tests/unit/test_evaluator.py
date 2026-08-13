"""Exact top-level constraint evaluator behaviors."""

from __future__ import annotations


def test_evaluate_empty_rule_set_does_not_touch_database() -> None:
    from tree_sitter_analyzer.constraints.evaluator import evaluate

    class RejectDatabaseAccess:
        def execute(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("empty rules must not query the database")

    assert evaluate([], RejectDatabaseAccess()) == []


def test_iter_violations_discards_duplicate_persisted_identity(monkeypatch) -> None:
    import tree_sitter_analyzer.constraints.evaluator as owner
    from tree_sitter_analyzer.constraints.parser import compile_constraints
    from tree_sitter_analyzer.constraints.schema import Constraint

    rules = compile_constraints(
        [Constraint("r", "error", "forbid", "src/**", "dst/**", "boundary")]
    )
    rows = [
        ("caller", "src/a.py", 7, "callee", "dst/b.py"),
        ("caller", "src/a.py", 7, "callee", "dst/c.py"),
    ]
    monkeypatch.setattr(owner, "_build_import_index", lambda *_a, **_k: None)
    monkeypatch.setattr(owner, "_build_select_query", lambda *_a: ("sql", ()))

    class Connection:
        def execute(self, *_args):
            return iter(rows)

    result = list(owner._iter_violations(rules, Connection(), 1))
    assert [
        (v.rule_id, v.caller_file, v.caller_line, v.callee_name) for v in result
    ] == [("r", "src/a.py", 7, "callee")]
