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
import time
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

    @pytest.mark.timeout(120)
    def test_eval_perf_on_synthetic_edges_under_500ms(self, tmp_path: Path) -> None:
        """50k edges × 5 rules in <500 ms (Linux/macOS) / <2000 ms (Windows).

        The budget reflects how often this runs (every
        ``analyze_change_impact`` call) and the size of a moderately
        large repo's call-edge table. Going over the budget means the
        evaluator is fighting the agent's loop instead of helping it.

        Marked ``slow_ok`` because the synthesis itself takes longer
        than the per-test 5s budget on slow runners — but the measured
        eval window stays within budget regardless.
        Marked ``quarantine`` + ``timeout(120)`` because Windows CI
        runners are ~10x slower than Linux; the 30s default timeout kills
        the 50k-row setup before evaluate() is even reached.
        """
        from tree_sitter_analyzer.constraints import (
            evaluate,
            load_constraints,
        )

        project = _stage_constraints_file(tmp_path, "dogfood_minimal.yml")
        db_path = project / ".ast-cache" / "index.db"

        # Synthesize 50,000 edges across five layered file roots.
        # Roughly 10% are intentional violations so the evaluator's
        # "violation" path is exercised, not just the early-exit happy path.
        rows: list[tuple[str, str, int, str, str, str]] = []
        for i in range(50_000):
            if i % 10 == 0:
                caller_file = f"tree_sitter_analyzer/mcp/mod_{i}.py"
                callee_file = f"tree_sitter_analyzer/cli/cli_{i}.py"
            else:
                caller_file = f"src/pkg_{i % 50}/mod_{i}.py"
                callee_file = f"src/pkg_{(i + 1) % 50}/mod_{i + 1}.py"
            rows.append(
                (
                    f"caller_{i}",
                    caller_file,
                    i % 1000 + 1,
                    f"callee_{i}",
                    "",
                    callee_file,
                )
            )
        _build_call_edges_db(db_path, rows)

        # Augment the dogfood file with three more rules to hit 5 total —
        # done in-memory so we don't bloat the checked-in fixture.
        extra_rules_yml = """
  - id: bench-rule-extra-1
    severity: warn
    rule: forbid
    from: "src/pkg_1/**"
    to: "src/pkg_2/**"
    reason: "extra"
  - id: bench-rule-extra-2
    severity: warn
    rule: forbid
    from: "src/pkg_3/**"
    to: "src/pkg_4/**"
    reason: "extra"
  - id: bench-rule-extra-3
    severity: info
    rule: forbid
    from: "src/pkg_5/**"
    to: "src/pkg_6/**"
    reason: "extra"
""".rstrip("\n")
        cfg = project / "architectural-constraints.yml"
        cfg.write_text(cfg.read_text() + "\n" + extra_rules_yml + "\n")

        constraints = load_constraints(str(project))
        assert len(constraints) == 5, (
            f"Benchmark setup expects 5 rules, got {len(constraints)}"
        )

        import sys

        if sys.gettrace() is not None:
            pytest.skip(
                "tracked: coverage instrumentation invalidates the 500 ms "
                "wall-clock perf budget; non-coverage CI enforces it."
            )

        # Hosted Windows runners and macOS 26 ARM64 runners are materially
        # slower than Linux for this SQLite-heavy benchmark. Keep the strict
        # Linux budget while allowing both constrained hosted platforms enough
        # headroom to preserve the regression signal without runner flakiness.
        budget_ms = 2000.0 if sys.platform in {"win32", "darwin"} else 500.0

        conn = sqlite3.connect(str(db_path))
        try:
            t0 = time.monotonic()
            violations = evaluate(constraints, conn)
            elapsed_ms = (time.monotonic() - t0) * 1000
        finally:
            conn.close()

        # Sanity: the synthesised data really did trigger violations.
        assert violations, "Benchmark data should produce violations"

        assert elapsed_ms < budget_ms, (
            f"evaluate() over 50k edges × 5 rules took {elapsed_ms:.0f} ms; "
            f"budget is {budget_ms:.0f} ms on {sys.platform}. See spec — "
            f"constraint checking runs on every change_impact call and must stay cheap."
        )

    def test_duplicate_pk_violations_deduplicated(self, tmp_path: Path) -> None:
        """evaluate() dedupes violations that share the same PK.

        Regression test for #544: when the ``edges`` table contains two rows
        for the same call site (same caller_file, caller_line, callee_name)
        but with different ``callee_resolved_file`` values (e.g., because the
        same call was indexed twice via different resolution paths), both rows
        can match the same constraint rule and produce two ``Violation``
        objects with identical ``(rule_id, caller_file, caller_line,
        callee_name)`` — which is the PRIMARY KEY of
        ``ast_constraint_violations``.  The old code's ``executemany`` would
        then crash with ``UNIQUE constraint failed``.

        Fix: evaluate() must deduplicate on PK before returning so the persist
        path always receives at most one Violation per PK tuple.

        The test asserts that exactly 1 violation is returned (not 2) so the
        pin is tight and drift raises the test rather than silently passing
        with a loose bound.
        """
        import json as _json

        from tree_sitter_analyzer.constraints import evaluate, load_constraints
        from tree_sitter_analyzer.graph.edge_store import (
            EDGE_STORE_SCHEMA,
            EdgeKind,
            symbol_node,
        )

        project = _stage_constraints_file(tmp_path, "dogfood_minimal.yml")
        db_path = project / ".ast-cache" / "index.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # Build two edges with identical (caller_file, caller_line, callee_name)
        # but different callee_resolved_file — simulating a call site that was
        # resolved to two targets by different indexing passes.
        caller_file = "tree_sitter_analyzer/mcp/x.py"
        caller_name = "do_thing"
        caller_line = 42
        callee_name = "cli_helper"
        callee_file_a = "tree_sitter_analyzer/cli/y.py"
        callee_file_b = "tree_sitter_analyzer/cli/z.py"

        conn = sqlite3.connect(str(db_path))
        try:
            conn.executescript(EDGE_STORE_SCHEMA)
            for callee_file in (callee_file_a, callee_file_b):
                source = symbol_node(caller_file, caller_name, caller_line)
                target = symbol_node(callee_file, callee_name, 0)
                metadata = _json.dumps(
                    {
                        "language": "python",
                        "caller_name": caller_name,
                        "caller_line": caller_line,
                        "callee_name": callee_name,
                        "callee_full": callee_name,
                        "callee_resolution": "project",
                        "callee_resolved_file": callee_file,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                conn.execute(
                    "INSERT OR REPLACE INTO edges "
                    "(source_node_id, target_node_id, kind, line, provenance, "
                    " metadata, caller_name, callee_name, file_path, caller_line, "
                    " callee_full, callee_line, language, callee_resolution, "
                    " callee_resolved_file) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        source,
                        target,
                        EdgeKind.CALLS.value,
                        caller_line,
                        "tree-sitter",
                        metadata,
                        caller_name,
                        callee_name,
                        caller_file,
                        caller_line,
                        callee_name,
                        0,
                        "python",
                        "project",
                        callee_file,
                    ),
                )
            conn.commit()

            constraints = load_constraints(str(project))
            # Must NOT raise — two same-PK violations must be deduplicated.
            violations = evaluate(constraints, conn)
        finally:
            conn.close()

        # Exactly 1 violation: the PK is (rule_id, caller_file, caller_line,
        # callee_name).  Two edges with the same call site are ONE violation,
        # not two.  The exact count is pinned so drift raises the test.
        assert len(violations) == 1, (
            f"Expected exactly 1 violation after PK deduplication, "
            f"got {len(violations)}: {violations}"
        )
        v = violations[0]
        assert v.rule_id == "dogfood-mcp-no-cli"
        assert v.caller_file == caller_file
        assert v.caller_line == caller_line
        assert v.callee_name == callee_name

    def test_scope_predicate_filters_before_duplicate_pk_resolution(
        self, tmp_path: Path
    ) -> None:
        # PR #1254 review 3765918811: an out-of-scope duplicate must not win dedup.
        from tree_sitter_analyzer.constraints import Constraint, evaluate

        conn = sqlite3.connect(tmp_path / "scope.db")
        try:
            conn.execute(
                "CREATE TABLE edges (kind TEXT, caller_name TEXT, file_path TEXT, "
                "caller_line INTEGER, callee_name TEXT, callee_resolved_file TEXT)"
            )
            conn.executemany(
                "INSERT INTO edges VALUES ('calls', 'caller', 'outside/caller.py', "
                "7, 'target', ?)",
                [("targets/outside.py",), ("targets/in_scope.py",)],
            )
            rule = Constraint(
                id="scoped",
                severity="error",
                rule="forbid",
                from_glob="outside/**",
                to_glob="targets/**",
                reason="test",
            )

            violations = evaluate(
                [rule],
                conn,
                scope_predicate=lambda _caller, callee: callee == "targets/in_scope.py",
            )
        finally:
            conn.close()

        assert [violation.callee_file for violation in violations] == [
            "targets/in_scope.py"
        ]
