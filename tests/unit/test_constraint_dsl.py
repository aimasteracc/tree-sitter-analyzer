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

    def test_compiled_globs_preserve_literal_prefixes(self) -> None:
        """Compiled rules expose safe prefixes for evaluator fast rejection."""
        from tree_sitter_analyzer.constraints.parser import compile_constraints
        from tree_sitter_analyzer.constraints.schema import Constraint

        constraint = Constraint(
            id="prefix-contract",
            severity="error",
            rule="forbid",
            from_glob="tree_sitter_analyzer/mcp/**",
            to_glob="tree_sitter_analyzer/cli/*.py",
            reason="test",
            exceptions=(),
        )

        compiled = compile_constraints([constraint])[0]

        assert (compiled.from_prefix, compiled.to_prefix) == (
            "tree_sitter_analyzer/mcp/",
            "tree_sitter_analyzer/cli/",
        )

    @pytest.mark.parametrize(
        ("pattern", "expected_prefix"),
        [
            ("src/exact.py", "src/exact.py"),
            ("src/*/mod?.py", "src/"),
            ("src/[ab]*/mod.py", "src/"),
            ("**/generated.py", ""),
        ],
    )
    def test_literal_prefix_is_a_safe_regex_precondition(
        self,
        pattern: str,
        expected_prefix: str,
    ) -> None:
        """Every full glob match must also satisfy the fast prefix check."""
        from tree_sitter_analyzer.constraints.parser import (
            _compile_glob,
            _literal_glob_prefix,
        )

        prefix = _literal_glob_prefix(pattern)
        candidates = (
            "src/exact.py",
            "src/a/mod1.py",
            "src/b/mod.py",
            "pkg/generated.py",
            "unrelated/file.py",
        )

        assert prefix == expected_prefix
        for candidate in candidates:
            if _compile_glob(pattern).fullmatch(candidate):
                assert candidate.startswith(prefix)

    def test_literal_prefix_rejects_irrelevant_edges_before_regex(
        self,
        tmp_path: Path,
    ) -> None:
        """Unrelated callers never pay the full-regex cost in the hot loop."""
        from dataclasses import replace
        from typing import Any, cast

        from tree_sitter_analyzer.constraints.evaluator import _iter_violations
        from tree_sitter_analyzer.constraints.parser import compile_constraints
        from tree_sitter_analyzer.constraints.schema import Constraint

        class CountingPattern:
            def __init__(self, inner: Any) -> None:
                self.inner = inner
                self.calls = 0

            def fullmatch(self, value: str) -> Any:
                self.calls += 1
                return self.inner.fullmatch(value)

        constraint = Constraint(
            id="prefix-hot-loop",
            severity="error",
            rule="forbid",
            from_glob="tree_sitter_analyzer/mcp/**",
            to_glob="tree_sitter_analyzer/cli/**",
            reason="test",
            exceptions=(),
        )
        compiled = compile_constraints([constraint])[0]
        from_spy = CountingPattern(compiled.from_re)
        compiled = replace(compiled, from_re=cast(Any, from_spy))

        db_path = tmp_path / "index.db"
        rows = [
            (
                f"caller_{index}",
                f"src/pkg/mod_{index}.py",
                index + 1,
                f"callee_{index}",
                "",
                f"src/other/mod_{index}.py",
            )
            for index in range(1_000)
        ]
        _build_call_edges_db(db_path, rows)
        conn = sqlite3.connect(str(db_path))
        try:
            violations = list(_iter_violations([compiled], conn, detected_at=0))
        finally:
            conn.close()

        assert violations == []
        assert from_spy.calls == 0
