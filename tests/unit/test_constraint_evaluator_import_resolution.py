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

    def test_phantom_bare_name_resolution_skipped_when_no_import(
        self, tmp_path: Path
    ) -> None:
        """Regression #780: bare-name callee resolved to forbidden module is
        SKIPPED when the caller has no import from that module.

        Scenario mirrors the real bug: ``_hash_one_file`` in a core file
        calls ``sha256_hash.update()``.  The synapse resolver resolves
        ``update`` to ``file_health_blocks.py`` (a forbidden mcp module)
        because both define a method named ``update``.  The caller imports
        only ``hashlib`` — no ``mcp`` import at all.  The evaluator must
        NOT flag this as a constraint violation.
        """
        from tree_sitter_analyzer.constraints import evaluate, load_constraints

        project = _stage_constraints_file(tmp_path, "dogfood_minimal.yml")
        db_path = project / ".ast-cache" / "index.db"

        # Edge: core/_hash_one_file calls update(), resolver wrongly sets
        # callee_resolved_file to an mcp module.
        _build_call_edges_db(
            db_path,
            rows=[
                (
                    "_hash_one_file",  # caller_name
                    "tree_sitter_analyzer/core/analysis_session.py",  # caller_file
                    188,  # caller_line
                    "update",  # callee_name
                    "sha256_hash.update",  # callee_full
                    "tree_sitter_analyzer/mcp/tools/utils/file_health_blocks.py",  # callee_file (WRONG resolution)
                ),
            ],
        )

        # Populate ast_imports: analysis_session.py imports only hashlib,
        # NOT file_health_blocks or any mcp module.
        _populate_ast_imports(
            db_path,
            rows=[
                ("tree_sitter_analyzer/core/analysis_session.py", "hashlib"),
                ("tree_sitter_analyzer/core/analysis_session.py", "json"),
                ("tree_sitter_analyzer/core/analysis_session.py", "pathlib"),
            ],
        )

        constraints = load_constraints(str(project))
        conn = sqlite3.connect(str(db_path))
        try:
            violations = evaluate(constraints, conn)
        finally:
            conn.close()

        assert len(violations) == 0, (
            f"Expected 0 violations (phantom bare-name resolution must be filtered), "
            f"got {len(violations)}: {violations}"
        )

    def test_real_violation_not_filtered_when_import_present(
        self, tmp_path: Path
    ) -> None:
        """Regression #780: a genuine cross-boundary call IS flagged when the
        caller actually imports from the forbidden module.

        Ensures the import-reachability guard does not over-filter real
        violations — only phantom bare-name resolutions are suppressed.
        """
        from tree_sitter_analyzer.constraints import evaluate, load_constraints

        project = _stage_constraints_file(tmp_path, "dogfood_minimal.yml")
        db_path = project / ".ast-cache" / "index.db"

        # Edge: mcp/x.py calls cli_helper() which is genuinely in cli/y.py.
        _build_call_edges_db(
            db_path,
            rows=[
                (
                    "do_thing",  # caller_name
                    "tree_sitter_analyzer/mcp/x.py",  # caller_file
                    42,  # caller_line
                    "cli_helper",  # callee_name
                    "cli_helper",  # callee_full
                    "tree_sitter_analyzer/cli/y.py",  # callee_file (REAL violation)
                ),
            ],
        )

        # mcp/x.py really does import from cli/y — this is the genuine case.
        _populate_ast_imports(
            db_path,
            rows=[
                ("tree_sitter_analyzer/mcp/x.py", "tree_sitter_analyzer.cli.y"),
            ],
        )

        constraints = load_constraints(str(project))
        conn = sqlite3.connect(str(db_path))
        try:
            violations = evaluate(constraints, conn)
        finally:
            conn.close()

        assert len(violations) == 1, (
            f"Expected exactly 1 real violation (import IS present), "
            f"got {len(violations)}: {violations}"
        )
        v = violations[0]
        assert v.rule_id == "dogfood-mcp-no-cli"
        assert v.caller_file == "tree_sitter_analyzer/mcp/x.py"
        assert v.callee_file == "tree_sitter_analyzer/cli/y.py"


def test_constraint_bytes_reject_non_utf8():
    from tree_sitter_analyzer.constraints.parser import (
        ConstraintParseError,
        load_constraints_bytes,
    )

    with pytest.raises(ConstraintParseError, match="Could not decode"):
        load_constraints_bytes(b"\xff", "constraints.yml")


def test_constraint_loader_wraps_read_failure(tmp_path, monkeypatch):
    from tree_sitter_analyzer.constraints.parser import (
        ConstraintParseError,
        load_constraints,
    )

    config = tmp_path / "architectural-constraints.yml"
    config.write_text("version: 1\nconstraints: []\n")
    monkeypatch.setattr(
        Path, "read_bytes", lambda _self: (_ for _ in ()).throw(OSError("denied"))
    )
    with pytest.raises(ConstraintParseError, match="Could not read"):
        load_constraints(tmp_path)


def test_evaluator_callback_covers_python_import_materialization() -> None:
    from tree_sitter_analyzer.constraints import Constraint, evaluate

    # PR #1254 review 3767373475: Python-side DB materialization obeys callback.
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_imports(file_path TEXT, module_path TEXT)")
    conn.execute("INSERT INTO ast_imports VALUES ('a.py', 'b')")
    calls = []
    try:
        with pytest.raises(RuntimeError, match="^deadline$"):
            evaluate(
                [Constraint("r", "warn", "deny", "**", "**", "test")],
                conn,
                check_callback=lambda: (
                    calls.append("check")
                    or (_ for _ in ()).throw(RuntimeError("deadline"))
                ),
            )
    finally:
        conn.close()
    assert calls == ["check"]


def test_evaluator_bounds_python_import_materialization() -> None:
    from tree_sitter_analyzer.constraints import Constraint, evaluate

    # PR #1254 review 3767373475: API capacity bounds Python-owned collections.
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_imports(file_path TEXT, module_path TEXT)")
    conn.executemany(
        "INSERT INTO ast_imports VALUES (?, ?)", [("a.py", "b"), ("c.py", "d")]
    )
    try:
        with pytest.raises(RuntimeError, match="^CONSTRAINT_EVALUATION_CAPACITY$"):
            evaluate(
                [Constraint("r", "warn", "deny", "**", "**", "test")], conn, capacity=1
            )
    finally:
        conn.close()
