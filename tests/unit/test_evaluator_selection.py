"""RED tests for the Inhibition / Constraint DSL (Feature 3).

The ``tree_sitter_analyzer.constraints`` package does NOT exist yet — every
test in this file is expected to fail today, most with ``ImportError`` on
the first ``from tree_sitter_analyzer.constraints import ...`` line. That
is intentional: this is the contract the implementer must satisfy in the
follow-up GREEN phase.

What this file pins down:

1. **Parser shape**: ``load_constraints(project_root)`` returns ``list[Constraint]``
   where each Constraint is an immutable dataclass with ``id``, ``severity``,
   ``rule``, ``from_glob``, ``to_glob``, ``reason``, ``exceptions``.
2. **Parser failure modes**:
   * Malformed YAML → ``ConstraintParseError`` with a line-number context
     in the message (so the agent can self-correct without re-reading the
     whole file).
   * Unknown top-level key → ``ConstraintParseError`` naming the key.
   * Unknown per-rule key → warn-and-skip the rule, do NOT crash. This is
     the forward-compat seam: a newer constraints.yml that uses a key the
     analyzer hasn't learned yet still loads.
3. **Glob semantics**: ``match_glob`` must handle ``**`` recursive descent
   *and* must NOT match unrelated paths that share a top-level prefix.
4. **Evaluation core**: ``evaluate(constraints, db_conn)`` streams the
   ``ast_call_edges`` table, returns ``list[Violation]``, and respects
   ``exceptions``.
5. **Performance budget**: 50k synthetic edges × 5 rules under 500 ms.
   This budget is intentional — constraint checking runs on every
   ``analyze_change_impact`` invocation, so it has to be cheap.
6. **Graceful missing config**: no constraints file → empty list, not an
   exception. A repo with no constraints.yml is a perfectly valid state.

Fixtures live at ``tests/fixtures/constraints/`` and are checked in.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

# PyYAML ships transitively via ``mcp``; skip if missing so the file
# stays importable on minimal installs (the implementation module will
# fail-loud at import-time on its own).
pytest.importorskip("yaml")


FIXTURES = Path(__file__).parent.parent / "fixtures" / "constraints"


# ---------------------------------------------------------------------------
# Helpers — kept module-local so the RED tests are completely self-contained.
# ---------------------------------------------------------------------------


def _stage_constraints_file(tmp_path: Path, fixture_name: str) -> Path:
    """Copy a fixture into ``<tmp_path>/architectural-constraints.yml``.

    The loader resolves config relative to ``project_root`` and prefers
    the root-level file over ``.tree-sitter-analyzer/constraints.yml``,
    per spec. Returning ``tmp_path`` lets each test scope its filesystem
    cleanly via pytest's ``tmp_path`` fixture.
    """
    src = FIXTURES / fixture_name
    assert src.exists(), f"Missing fixture: {src}"
    dst = tmp_path / "architectural-constraints.yml"
    dst.write_bytes(src.read_bytes())
    return tmp_path


def _build_call_edges_db(
    db_path: Path, rows: list[tuple[str, str, int, str, str, str]]
) -> None:
    """Create a minimal sqlite db with the unified ``edges`` schema.

    B1.2 moved the constraint evaluator's read source from ``ast_call_edges``
    to the single ``edges`` table.  The CALLS rows are written in the
    production shape (node ids via ``symbol_node``, scalars in metadata JSON,
    real name/file columns); the callee's resolved file lives in
    ``metadata.callee_resolved_file`` so the evaluator's COALESCE-to-file_path
    logic behaves exactly as it did against the legacy resolution columns.

    Each row tuple is (caller_name, caller_file, caller_line, callee_name,
    callee_full, callee_file).
    """
    import json as _json

    from tree_sitter_analyzer.graph.edge_store import EdgeKind, symbol_node

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        from tree_sitter_analyzer.graph.edge_store import EDGE_STORE_SCHEMA

        conn.executescript(EDGE_STORE_SCHEMA)
        params = []
        for (
            caller_name,
            caller_file,
            caller_line,
            callee_name,
            _callee_full,
            callee_file,
        ) in rows:
            source = symbol_node(caller_file, caller_name, caller_line)
            target = symbol_node(callee_file or caller_file, callee_name, 0)
            metadata = {
                "language": "python",
                "caller_name": caller_name,
                "caller_line": caller_line,
                "callee_name": callee_name,
                "callee_full": _callee_full,
                "callee_resolution": "project" if callee_file else "unknown",
                "callee_resolved_file": callee_file,
            }
            # B1.3: resolution scalars are real columns the evaluator reads
            # directly (no json_extract), so populate them alongside metadata.
            params.append(
                (
                    source,
                    target,
                    EdgeKind.CALLS.value,
                    0,
                    "tree-sitter",
                    _json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                    caller_name,
                    callee_name,
                    caller_file,
                    caller_line,
                    _callee_full,
                    0,
                    "python",
                    "project" if callee_file else "unknown",
                    callee_file,
                )
            )
        conn.executemany(
            "INSERT OR REPLACE INTO edges "
            "(source_node_id, target_node_id, kind, line, provenance, metadata, "
            " caller_name, callee_name, file_path, caller_line, callee_full, "
            " callee_line, language, callee_resolution, callee_resolved_file) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            params,
        )
        conn.commit()
    finally:
        conn.close()


def _populate_ast_imports(
    db_path: Path,
    rows: list[tuple[str, str]],
) -> None:
    """Insert rows into ``ast_imports`` in the given DB.

    Each tuple is ``(file_path, module_path)``.  The table is created if
    absent so this helper can be called on a DB built by
    ``_build_call_edges_db`` (which only creates the ``edges`` schema).
    """
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ast_imports (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path   TEXT NOT NULL,
                language    TEXT NOT NULL DEFAULT 'python',
                module_path TEXT NOT NULL,
                local_name  TEXT NOT NULL DEFAULT '',
                is_relative INTEGER NOT NULL DEFAULT 0,
                is_star     INTEGER NOT NULL DEFAULT 0,
                alias_of    TEXT NOT NULL DEFAULT '',
                line        INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.executemany(
            "INSERT INTO ast_imports (file_path, module_path) VALUES (?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


class TestEvaluator:
    """Synthesize an ast_call_edges row and verify the evaluator's verdict."""

    def test_violation_detected_mcp_to_cli(self, tmp_path: Path) -> None:
        """A real edge that crosses a forbidden boundary → 1 error violation."""
        from tree_sitter_analyzer.constraints import (
            evaluate,
            load_constraints,
        )

        # Stage constraints + db with one offending edge.
        project = _stage_constraints_file(tmp_path, "dogfood_minimal.yml")
        db_path = project / ".ast-cache" / "index.db"
        _build_call_edges_db(
            db_path,
            rows=[
                (
                    "do_thing",  # caller_name
                    "tree_sitter_analyzer/mcp/x.py",  # caller_file
                    42,  # caller_line
                    "cli_helper",  # callee_name
                    "cli_helper",  # callee_full
                    "tree_sitter_analyzer/cli/y.py",  # callee_file
                ),
            ],
        )

        constraints = load_constraints(str(project))
        conn = sqlite3.connect(str(db_path))
        try:
            violations = evaluate(constraints, conn)
        finally:
            conn.close()

        # Exactly one violation, with the right severity and source.
        assert len(violations) == 1, (
            f"Expected exactly one violation, got {len(violations)}: {violations}"
        )
        v = violations[0]
        assert v.severity == "error"
        assert v.rule_id == "dogfood-mcp-no-cli"
        assert v.caller_file == "tree_sitter_analyzer/mcp/x.py"
        assert v.callee_file == "tree_sitter_analyzer/cli/y.py"
        assert v.caller_line == 42

    def test_exception_suppresses_violation(self, tmp_path: Path) -> None:
        """An edge whose caller is in ``exceptions:`` produces zero violations.

        The exception list is the only way a rule can be locally overridden
        without disabling the whole rule, so this test pins down that the
        match is exact (not a substring).
        """
        from tree_sitter_analyzer.constraints import (
            evaluate,
            load_constraints,
        )

        project = _stage_constraints_file(tmp_path, "exception_rule.yml")
        db_path = project / ".ast-cache" / "index.db"
        _build_call_edges_db(
            db_path,
            rows=[
                (
                    "use_cli",
                    "mcp/bridge.py",  # caller is explicitly excepted
                    10,
                    "run_cli",
                    "run_cli",
                    "cli/runner.py",
                ),
            ],
        )

        constraints = load_constraints(str(project))
        conn = sqlite3.connect(str(db_path))
        try:
            violations = evaluate(constraints, conn)
        finally:
            conn.close()

        assert violations == [], (
            f"Excepted caller must produce zero violations, got: {violations}"
        )

    def test_evaluate_keeps_rows_when_from_glob_has_no_literal_prefix(
        self, tmp_path: Path
    ) -> None:
        """A leading wildcard disables SQL prefix filtering without data loss."""
        from tree_sitter_analyzer.constraints import evaluate
        from tree_sitter_analyzer.constraints.schema import Constraint

        db_path = tmp_path / "index.db"
        _build_call_edges_db(
            db_path,
            rows=[
                (
                    "use_cli",
                    "custom/bridge.py",
                    7,
                    "run_cli",
                    "run_cli",
                    "cli/runner.py",
                ),
            ],
        )
        constraint = Constraint(
            id="wildcard-caller",
            severity="error",
            rule="forbid",
            from_glob="**",
            to_glob="cli/**",
            reason="test wildcard fallback",
        )

        conn = sqlite3.connect(str(db_path))
        try:
            violations = evaluate([constraint], conn)
        finally:
            conn.close()

        assert len(violations) == 1
        assert violations[0].rule_id == "wildcard-caller"

    def test_select_query_keeps_callee_filter_when_callers_exceed_limit(
        self,
    ) -> None:
        """PR #1225: an oversized caller set must not discard the callee filter."""
        from tree_sitter_analyzer.constraints.evaluator import (
            _MAX_SQL_PREFIX_FILTERS,
            _build_select_query,
        )
        from tree_sitter_analyzer.constraints.parser import compile_constraints
        from tree_sitter_analyzer.constraints.schema import Constraint

        constraints = [
            Constraint(
                id=f"rule-{index}",
                severity="error",
                rule="forbid",
                from_glob=f"package-{index}/**",
                to_glob="forbidden/**",
                reason="test SQL filter bound",
            )
            for index in range(_MAX_SQL_PREFIX_FILTERS + 1)
        ]

        conn = sqlite3.connect(":memory:")
        try:
            select_sql, params = _build_select_query(
                conn,
                compile_constraints(constraints),
            )
        finally:
            conn.close()

        assert select_sql.count("instr(file_path, ?) = 1") == 0
        assert select_sql.count("callee_resolved_file") == 4
        assert params == ("forbidden/",)

    def test_select_query_keeps_caller_filter_when_callees_exceed_limit(
        self,
    ) -> None:
        """PR #1225: an oversized callee set must not discard the caller filter."""
        from tree_sitter_analyzer.constraints.evaluator import (
            _MAX_SQL_PREFIX_FILTERS,
            _build_select_query,
        )
        from tree_sitter_analyzer.constraints.parser import compile_constraints
        from tree_sitter_analyzer.constraints.schema import Constraint

        constraints = [
            Constraint(
                id=f"rule-{index}",
                severity="error",
                rule="forbid",
                from_glob="tree_sitter_analyzer/mcp/**",
                to_glob=f"forbidden-{index}/**",
                reason="test independent SQL filter bound",
            )
            for index in range(_MAX_SQL_PREFIX_FILTERS + 1)
        ]

        conn = sqlite3.connect(":memory:")
        try:
            select_sql, params = _build_select_query(
                conn,
                compile_constraints(constraints),
            )
        finally:
            conn.close()

        assert select_sql.count("instr(file_path, ?) = 1") == 1
        assert select_sql.count("callee_resolved_file") == 2
        assert params == ("tree_sitter_analyzer/mcp/",)

    def test_select_query_falls_back_when_both_prefix_sets_exceed_limit(
        self,
    ) -> None:
        """PR #1225: two oversized prefix sets retain the unfiltered fallback."""
        from tree_sitter_analyzer.constraints.evaluator import (
            _MAX_SQL_PREFIX_FILTERS,
            _build_select_query,
        )
        from tree_sitter_analyzer.constraints.parser import compile_constraints
        from tree_sitter_analyzer.constraints.schema import Constraint

        constraints = [
            Constraint(
                id=f"rule-{index}",
                severity="error",
                rule="forbid",
                from_glob=f"package-{index}/**",
                to_glob=f"forbidden-{index}/**",
                reason="test SQL filter fallback",
            )
            for index in range(_MAX_SQL_PREFIX_FILTERS + 1)
        ]

        conn = sqlite3.connect(":memory:")
        try:
            select_sql, params = _build_select_query(
                conn,
                compile_constraints(constraints),
            )
        finally:
            conn.close()

        assert select_sql.endswith("FROM edges WHERE kind = 'calls'")
        assert params == ()
