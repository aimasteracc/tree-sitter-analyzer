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

    monkeypatch.setattr(evaluator_module, "_build_import_index", lambda *_a, **_k: {})
    monkeypatch.setattr(evaluator_module, "_has_import_evidence", lambda *_a: True)
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
    assert callbacks == ["checked"] * 8


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
    monkeypatch.setattr(evaluator_module, "_has_import_evidence", lambda *_a: False)
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


def test_candidate_caller_capacity_counts_only_exact_eligible_rows() -> None:
    """每个精确资格分支都必须在容量计数前排除不相关调用方。"""
    from tree_sitter_analyzer.constraints import Constraint
    from tree_sitter_analyzer.constraints.evaluator import _candidate_caller_files
    from tree_sitter_analyzer.constraints.parser import compile_constraints

    rows = [
        ("caller", "outside/caller.py", 1, "target", "blocked/a/target.py"),
        ("caller", "src/a/unrelated.py", 2, "target", "blocked/a/target.py"),
        ("caller", "src/a/selected.py", 3, "target", "allowed/a/target.py"),
        ("caller", "src/a/selected.py", 4, "target", "blocked/a/unrelated.py"),
        (
            "caller",
            "src/excepted/selected.py",
            5,
            "target",
            "blocked/a/target.py",
        ),
        ("caller", "src/one/selected.py", 6, "target", "blocked/a/target.py"),
        ("caller", "src/two/selected.py", 7, "target", "blocked/a/target.py"),
        ("caller", "src/three/selected.py", 8, "target", "blocked/a/target.py"),
    ]

    class Connection:
        def execute(self, _sql: str, _params: object):
            return iter(rows)

    compiled = compile_constraints(
        [
            Constraint(
                "rule",
                "warn",
                "forbid",
                "src/**/selected.py",
                "blocked/**/target.py",
                "boundary",
                ("src/excepted/**",),
            )
        ]
    )

    with pytest.raises(RuntimeError, match="^CONSTRAINT_EVALUATION_CAPACITY$"):
        _candidate_caller_files(
            Connection(),
            "SELECT",
            (),
            compiled,
            scope_predicate=None,
            check_callback=None,
            capacity=2,
        )


# Issue #1470：以下回归测试固定真实全量索引暴露的容量与截止时间边界。
def test_evaluator_ignores_import_rows_outside_candidate_callers() -> None:
    """无关文件的海量导入记录不能耗尽约束响应容量。"""
    from tree_sitter_analyzer.constraints import Constraint, evaluate

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_imports(file_path TEXT, module_path TEXT)")
    conn.execute(
        "CREATE TABLE edges("
        "kind TEXT, caller_name TEXT, file_path TEXT, caller_line INTEGER, "
        "callee_name TEXT, callee_resolved_file TEXT)"
    )
    conn.executemany(
        "INSERT INTO ast_imports VALUES (?, ?)",
        [(f"vendor/{index}.py", "vendor.target") for index in range(25)],
    )
    conn.execute("INSERT INTO ast_imports VALUES ('src/caller.py', 'allowed.target')")
    conn.execute(
        "INSERT INTO edges VALUES "
        "('calls', 'caller', 'src/caller.py', 7, 'target', 'allowed/target.py')"
    )
    try:
        violations = evaluate(
            [Constraint("r", "warn", "forbid", "src/**", "blocked/**", "test")],
            conn,
            capacity=2,
        )
    finally:
        conn.close()

    assert violations == []


def test_evaluator_bounds_only_exact_candidate_callers() -> None:
    """无字面前缀的规则不能让近似候选耗尽容量。"""
    from tree_sitter_analyzer.constraints import Constraint, evaluate

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_imports(file_path TEXT, module_path TEXT)")
    conn.execute(
        "CREATE TABLE edges("
        "kind TEXT, caller_name TEXT, file_path TEXT, caller_line INTEGER, "
        "callee_name TEXT, callee_resolved_file TEXT)"
    )
    conn.executemany(
        "INSERT INTO edges VALUES ('calls', 'caller', ?, 7, 'target', 'blocked/target.py')",
        [(f"src/unrelated_{index}.py",) for index in range(5)],
    )
    try:
        violations = evaluate(
            [Constraint("r", "warn", "forbid", "**/selected.py", "blocked/**", "test")],
            conn,
            capacity=2,
        )
    finally:
        conn.close()

    assert violations == []


def test_evaluator_checks_deadline_while_scanning_duplicate_candidates() -> None:
    """重复候选行的预扫描也必须持续检查截止时间。"""
    from tree_sitter_analyzer.constraints import Constraint, evaluate

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_imports(file_path TEXT, module_path TEXT)")
    conn.execute(
        "CREATE TABLE edges("
        "kind TEXT, caller_name TEXT, file_path TEXT, caller_line INTEGER, "
        "callee_name TEXT, callee_resolved_file TEXT)"
    )
    conn.executemany(
        "INSERT INTO edges VALUES ('calls', 'caller', 'src/selected.py', ?, "
        "'target', 'blocked/target.py')",
        [(index,) for index in range(5)],
    )
    checks = 0

    def check_deadline() -> None:
        nonlocal checks
        checks += 1
        if checks == 3:
            raise RuntimeError("deadline")

    try:
        with pytest.raises(RuntimeError, match="^deadline$"):
            evaluate(
                [
                    Constraint(
                        "r", "warn", "forbid", "**/selected.py", "blocked/**", "test"
                    )
                ],
                conn,
                check_callback=check_deadline,
            )
    finally:
        conn.close()

    assert checks == 3


def test_evaluator_scans_edges_once_without_import_evidence() -> None:
    """缺少导入表时不能为无效预扫描重复读取调用边。"""
    from tree_sitter_analyzer.constraints import Constraint, evaluate

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE edges("
        "kind TEXT, caller_name TEXT, file_path TEXT, caller_line INTEGER, "
        "callee_name TEXT, callee_resolved_file TEXT)"
    )
    conn.execute(
        "INSERT INTO edges VALUES "
        "('calls', 'caller', 'src/selected.py', 7, 'target', 'blocked/target.py')"
    )
    statements: list[str] = []
    conn.set_trace_callback(statements.append)
    try:
        violations = evaluate(
            [Constraint("r", "warn", "forbid", "src/**", "blocked/**", "test")],
            conn,
        )
    finally:
        conn.close()

    edge_selects = [
        statement
        for statement in statements
        if statement.startswith("SELECT caller_name")
    ]
    assert len(violations) == 1
    assert len(edge_selects) == 1
