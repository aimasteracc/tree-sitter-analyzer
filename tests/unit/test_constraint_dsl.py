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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS edges (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                source_node_id TEXT NOT NULL,
                target_node_id TEXT NOT NULL,
                kind           TEXT NOT NULL,
                line           INTEGER,
                provenance     TEXT DEFAULT 'tree-sitter',
                metadata       TEXT,
                caller_name    TEXT NOT NULL DEFAULT '',
                callee_name    TEXT NOT NULL DEFAULT '',
                file_path      TEXT NOT NULL DEFAULT '',
                UNIQUE(source_node_id, target_node_id, kind, line)
            )
            """
        )
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
                )
            )
        conn.executemany(
            "INSERT OR REPLACE INTO edges "
            "(source_node_id, target_node_id, kind, line, provenance, metadata, "
            " caller_name, callee_name, file_path) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            params,
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestConstraintParser:
    """Cover the YAML-to-Constraint pipeline end to end."""

    def test_parse_valid_yaml(self, tmp_path: Path) -> None:
        """Three rules, three severities, exceptions preserved on rule 2."""
        from tree_sitter_analyzer.constraints import load_constraints

        project = _stage_constraints_file(tmp_path, "valid.yml")
        constraints = load_constraints(str(project))

        assert len(constraints) == 3, (
            f"Expected 3 constraints from valid.yml, got {len(constraints)}: "
            f"{[c.id for c in constraints]}"
        )

        severities = {c.id: c.severity for c in constraints}
        assert severities == {
            "mcp-must-not-call-cli": "error",
            "tests-should-not-import-private-helpers": "warn",
            "docs-should-not-touch-runtime": "info",
        }

        # The rule with exceptions must round-trip them as a sequence.
        by_id = {c.id: c for c in constraints}
        rule_with_exc = by_id["tests-should-not-import-private-helpers"]
        assert list(rule_with_exc.exceptions) == ["tests/fixtures/**"]

        # The other two rules must default to an empty exceptions list,
        # NOT to ``None`` — downstream code iterates without a guard.
        for cid in (
            "mcp-must-not-call-cli",
            "docs-should-not-touch-runtime",
        ):
            assert list(by_id[cid].exceptions) == []

    def test_parse_invalid_yaml_raises(self, tmp_path: Path) -> None:
        """Unclosed flow sequence → ConstraintParseError with line context.

        The "line" requirement matters because the error message is what
        the agent reads. Without a line pointer the agent has to re-read
        the whole file to find the typo.
        """
        from tree_sitter_analyzer.constraints import load_constraints
        from tree_sitter_analyzer.constraints.parser import ConstraintParseError

        project = _stage_constraints_file(tmp_path, "invalid.yml")

        with pytest.raises(ConstraintParseError) as excinfo:
            load_constraints(str(project))

        msg = str(excinfo.value).lower()
        assert "line" in msg, (
            f"ConstraintParseError must include line context. Got: {excinfo.value!r}"
        )

    def test_parse_unknown_top_level_key_raises(self, tmp_path: Path) -> None:
        """``rulez:`` instead of ``constraints:`` is fatal and names the typo."""
        from tree_sitter_analyzer.constraints import load_constraints
        from tree_sitter_analyzer.constraints.parser import ConstraintParseError

        project = _stage_constraints_file(tmp_path, "unknown_top_key.yml")

        with pytest.raises(ConstraintParseError) as excinfo:
            load_constraints(str(project))

        # The typo'd key must appear verbatim in the error so the agent
        # can grep its own constraints.yml without ambiguity.
        assert "rulez" in str(excinfo.value), (
            "ConstraintParseError must name the unknown top-level key. "
            f"Got: {excinfo.value!r}"
        )

    def test_parse_unknown_per_rule_key_warns_and_skips(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Forward-compat: unknown per-rule keys are warn-and-skip, NOT fatal.

        Why this matters: an organisation may roll out a new constraint
        type (e.g. ``require:``) before all analyzer installs are on the
        latest version. Older analyzers must still parse the file — they
        just skip rules they don't understand — so the rollout doesn't
        block on lockstep upgrades.
        """
        from tree_sitter_analyzer.constraints import load_constraints

        project = _stage_constraints_file(tmp_path, "unknown_per_rule_key.yml")

        # Capture from the specific constraint-parser logger so Py3.13's
        # stricter propagation defaults don't drop the warning.
        with caplog.at_level(
            "WARNING", logger="tree_sitter_analyzer.constraints.parser"
        ):
            constraints = load_constraints(str(project))

        # The malformed rule must be dropped, not crash, not coerced into
        # a half-built Constraint.
        bad_rules = [c for c in constraints if c.id == "typo-per-rule"]
        assert bad_rules == [], (
            "Rule with unknown 'severityy' key must be skipped entirely, "
            f"but got: {bad_rules}"
        )

        # A warning must be logged so the operator can see the skip; the
        # offending key name must appear in the message for grep-ability.
        warnings = [r.message for r in caplog.records if r.levelname == "WARNING"]
        assert any("severityy" in m for m in warnings), (
            f"Expected WARNING naming 'severityy'. Got: {warnings}"
        )

    def test_missing_config_returns_empty_constraints(self, tmp_path: Path) -> None:
        """A repo with no constraints.yml is a valid state, not an error."""
        from tree_sitter_analyzer.constraints import load_constraints

        # tmp_path is fresh and empty — no architectural-constraints.yml,
        # no .tree-sitter-analyzer/constraints.yml.
        constraints = load_constraints(str(tmp_path))

        assert constraints == [], (
            f"Expected empty list when no config file exists, got: {constraints}"
        )


# ---------------------------------------------------------------------------
# Glob semantics
# ---------------------------------------------------------------------------


class TestGlobMatching:
    """Pin the recursive ``**`` semantics — easy to get wrong."""

    def test_glob_matches_recursive(self) -> None:
        """``**`` descends into arbitrary subdirectories.

        Counter-test: a sibling directory that *shares the top-level
        prefix* must not match, otherwise the rule produces false
        positives. This was the bug bash item that triggered the spec
        to call out ``**`` explicitly.
        """
        from tree_sitter_analyzer.constraints.parser import match_glob

        # Recursive descent matches.
        assert (
            match_glob(
                "tree_sitter_analyzer/mcp/**",
                "tree_sitter_analyzer/mcp/tools/foo.py",
            )
            is True
        )

        # Sibling path with shared prefix must NOT match — the ``/`` in
        # ``mcp/`` is significant.
        assert (
            match_glob(
                "tree_sitter_analyzer/mcp/**",
                "tree_sitter_analyzer/cli/mcp_commands.py",
            )
            is False
        )


# ---------------------------------------------------------------------------
# Evaluator tests — exercise the streaming edge scan.
# ---------------------------------------------------------------------------


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

    @pytest.mark.slow_ok
    def test_eval_perf_on_synthetic_edges_under_500ms(self, tmp_path: Path) -> None:
        """50k edges × 5 rules in <500 ms.

        The budget reflects how often this runs (every
        ``analyze_change_impact`` call) and the size of a moderately
        large repo's call-edge table. Going over the budget means the
        evaluator is fighting the agent's loop instead of helping it.

        Marked ``slow_ok`` because the synthesis itself takes longer
        than the per-test 5s budget on slow runners — but the measured
        eval window stays at 500 ms regardless.
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

        conn = sqlite3.connect(str(db_path))
        try:
            t0 = time.monotonic()
            violations = evaluate(constraints, conn)
            elapsed_ms = (time.monotonic() - t0) * 1000
        finally:
            conn.close()

        # Sanity: the synthesised data really did trigger violations.
        assert len(violations) > 0, "Benchmark data should produce violations"

        assert elapsed_ms < 500, (
            f"evaluate() over 50k edges × 5 rules took {elapsed_ms:.0f} ms; "
            f"budget is 500 ms. See spec — constraint checking runs on "
            f"every change_impact call and must stay cheap."
        )
