"""RED tests for ``ConstraintCheckTool`` (MCP tool ``check_constraints``).

The implementation does NOT exist yet — every test in this file is
expected to fail today with ``ImportError`` at the
``from tree_sitter_analyzer.mcp.tools.constraint_check_tool import ...``
line. This pins down the public contract that the GREEN phase must
satisfy.

What we lock in here:

* Tool name is ``check_constraints`` (must round-trip through
  ``get_tool_definition()``).
* The response payload exposes ``violations`` (a list), ``rule_count``
  (an int), and a canonical ``verdict``.
* The ``verdict`` mapping:
    - any error-severity violation → ``UNSAFE``
    - only warn-severity violations → ``CAUTION``
    - no violations → ``SAFE``
  This is the only place in the codebase that emits ``UNSAFE`` from
  the constraint layer (per spec); safe_to_edit picks it up from here.
* The optional ``path_filter`` argument narrows results by glob.

Seeding strategy: we write rows directly into
``<project>/.ast-cache/index.db``'s ``ast_constraint_violations`` table.
That table is part of the spec — if it isn't created by the
implementation we'll fail loudly when we try to write to it, which is
exactly what we want for a RED test.
"""

from __future__ import annotations

import asyncio
import sqlite3
import time
from pathlib import Path

import pytest

import tree_sitter_analyzer.diff_snapshot_registry as snapshots
from tests.unit._diff_snapshot_support import install_fake_snapshot_materializer

pytest.importorskip("yaml")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    """Drive a coroutine to completion under pytest's per-test event loop."""
    return asyncio.run(coro)


def _init_violations_db(db_path: Path) -> None:
    """Create the ``ast_constraint_violations`` table per spec.

    The implementation may also create this from inside ``execute()`` —
    that's fine; the IF NOT EXISTS makes the helper idempotent. We
    create it eagerly here so tests can seed rows before the tool runs.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ast_constraint_violations (
                rule_id      TEXT NOT NULL,
                caller_file  TEXT NOT NULL,
                caller_name  TEXT NOT NULL,
                caller_line  INTEGER NOT NULL,
                callee_name  TEXT NOT NULL,
                callee_file  TEXT NOT NULL DEFAULT '',
                severity     TEXT NOT NULL,
                detected_at  INTEGER NOT NULL,
                PRIMARY KEY (rule_id, caller_file, caller_line, callee_name)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _seed_violation(
    db_path: Path,
    *,
    rule_id: str,
    caller_file: str,
    callee_file: str,
    severity: str,
    caller_line: int = 1,
    callee_name: str = "callee_fn",
    caller_name: str = "caller_fn",
) -> None:
    """Insert a single synthetic violation row.

    All keyword args mirror the spec's column names so a failure trace
    points the implementer at the exact field that diverged.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO ast_constraint_violations
                (rule_id, caller_file, caller_name, caller_line,
                 callee_name, callee_file, severity, detected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rule_id,
                caller_file,
                caller_name,
                caller_line,
                callee_name,
                callee_file,
                severity,
                int(time.time()),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _stage_minimal_constraints(project: Path) -> None:
    """Write a 1-rule architectural-constraints.yml into the project.

    The tool needs *some* rule loaded so ``rule_count`` is non-zero and
    the SAFE-when-no-violations path is distinguishable from the
    "no constraints configured" path.
    """
    (project / "architectural-constraints.yml").write_text(
        """
version: 1
constraints:
  - id: test-rule
    severity: error
    rule: forbid
    from: "src/a/**"
    to: "src/b/**"
    reason: "Test fixture rule."
""".lstrip()
    )


def _make_tool(project_root: Path):
    """Construct ``ConstraintCheckTool`` bound to ``project_root``."""
    from tree_sitter_analyzer.mcp.tools.constraint_check_tool import (
        ConstraintCheckTool,
    )

    tool = ConstraintCheckTool(str(project_root))
    tool.set_project_path(str(project_root))
    return tool


# ---------------------------------------------------------------------------
# Verdict mapping — the core contract for this feature.
# ---------------------------------------------------------------------------


class TestConstraintCheckVerdict:
    """Map violations to canonical verdict vocabulary."""

    def test_check_constraints_returns_violation_list(self, tmp_path: Path) -> None:
        """Happy path: at least one violation surfaces with a rule_count >= 1."""
        _stage_minimal_constraints(tmp_path)
        db_path = tmp_path / ".ast-cache" / "index.db"
        _init_violations_db(db_path)
        _seed_violation(
            db_path,
            rule_id="test-rule",
            caller_file="src/a/foo.py",
            callee_file="src/b/bar.py",
            severity="error",
        )

        tool = _make_tool(tmp_path)
        result = _run(tool.execute({}))

        assert "violations" in result, (
            f"Response must expose a 'violations' field. Got keys: {list(result)}"
        )
        assert isinstance(result["violations"], list)
        assert result["violations"]
        assert result.get("rule_count", 0), (
            f"rule_count must reflect loaded rules. Got: {result.get('rule_count')!r}"
        )

    def test_check_constraints_verdict_unsafe_when_error_severity(
        self, tmp_path: Path
    ) -> None:
        """Error-severity violation must escalate to ``UNSAFE``.

        This is the ONLY place in MVP that produces the ``UNSAFE``
        verdict, per spec. safe_to_edit and change_impact pick it up
        from here.
        """
        _stage_minimal_constraints(tmp_path)
        db_path = tmp_path / ".ast-cache" / "index.db"
        _init_violations_db(db_path)
        _seed_violation(
            db_path,
            rule_id="test-rule",
            caller_file="src/a/foo.py",
            callee_file="src/b/bar.py",
            severity="error",
        )

        tool = _make_tool(tmp_path)
        result = _run(tool.execute({}))

        assert result["verdict"] == "UNSAFE", (
            f"Error-severity violation must produce verdict='UNSAFE'. "
            f"Got: {result.get('verdict')!r}"
        )

    def test_check_constraints_verdict_caution_when_only_warn(
        self, tmp_path: Path
    ) -> None:
        """Only warn-severity violations → ``CAUTION`` (not ``UNSAFE``)."""
        _stage_minimal_constraints(tmp_path)
        db_path = tmp_path / ".ast-cache" / "index.db"
        _init_violations_db(db_path)
        _seed_violation(
            db_path,
            rule_id="test-rule",
            caller_file="src/a/foo.py",
            callee_file="src/b/bar.py",
            severity="warn",
        )

        tool = _make_tool(tmp_path)
        result = _run(tool.execute({}))

        assert result["verdict"] == "CAUTION", (
            f"Warn-only violations must produce verdict='CAUTION', not "
            f"escalate to UNSAFE. Got: {result.get('verdict')!r}"
        )

    def test_check_constraints_verdict_safe_when_no_violations(
        self, tmp_path: Path
    ) -> None:
        """Constraints loaded, zero violations → ``SAFE``."""
        _stage_minimal_constraints(tmp_path)
        db_path = tmp_path / ".ast-cache" / "index.db"
        _init_violations_db(db_path)
        # NOTE: no _seed_violation — table is intentionally empty.

        tool = _make_tool(tmp_path)
        result = _run(tool.execute({}))

        assert result["verdict"] == "SAFE", (
            f"Empty violations table must produce verdict='SAFE'. "
            f"Got: {result.get('verdict')!r}"
        )
        assert result["violations"] == [], (
            f"Expected empty violations list, got: {result['violations']}"
        )


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


class TestConstraintCheckFiltering:
    """Optional ``path_filter`` narrows results by caller-file glob."""

    def test_path_filter_narrows_results(self, tmp_path: Path) -> None:
        """Filter is applied against ``caller_file`` and respects ``**``."""
        _stage_minimal_constraints(tmp_path)
        db_path = tmp_path / ".ast-cache" / "index.db"
        _init_violations_db(db_path)

        # Two violations in two distinct path roots.
        _seed_violation(
            db_path,
            rule_id="test-rule",
            caller_file="mcp/handler.py",
            callee_file="cli/runner.py",
            severity="error",
            caller_line=10,
        )
        _seed_violation(
            db_path,
            rule_id="test-rule",
            caller_file="docs/example.py",
            callee_file="cli/runner.py",
            severity="error",
            caller_line=20,
        )

        tool = _make_tool(tmp_path)
        result = _run(tool.execute({"path_filter": "mcp/**"}))

        callers = [v["caller_file"] for v in result["violations"]]
        assert callers == ["mcp/handler.py"], (
            f"path_filter='mcp/**' must keep only the mcp/* row. Got: {callers}"
        )


# ---------------------------------------------------------------------------
# RFC-0022 P0.3 read-only frozen-snapshot contract
# ---------------------------------------------------------------------------


def _create_frozen_scope(monkeypatch, project: Path, paths: list[str]):
    """Install an isolated registry and create one leased frozen scope."""
    install_fake_snapshot_materializer(monkeypatch, project)
    registry = snapshots.DiffSnapshotRegistry()
    monkeypatch.setattr(snapshots, "REGISTRY", registry)
    created = registry.create(str(project), "diff", paths)
    assert created["success"] is True

    from contextlib import contextmanager
    from types import SimpleNamespace

    import tree_sitter_analyzer.index_snapshot as index_snapshots

    @contextmanager
    def lease(_root):
        yield SimpleNamespace(
            snapshot_id="is_test",
            completeness="complete",
            source_generation=created["source_generation"],
            reason=None,
            canonical_root=str(project.resolve()),
            index_fingerprint="sha256:" + "1" * 64,
        )

    @contextmanager
    def acquire(_snapshot_id, _root, _generation):
        conn = sqlite3.connect(project / ".ast-cache" / "index.db")
        try:
            yield SimpleNamespace(), conn
        finally:
            conn.close()

    monkeypatch.setattr(index_snapshots, "lease_existing_snapshot", lease)
    monkeypatch.setattr(index_snapshots, "acquire_index_snapshot", acquire)
    return registry, created


def test_constraint_annotation_discloses_legacy_write_side_effect() -> None:
    definition = _make_tool(Path(".")).get_tool_definition()
    assert definition["annotations"] == {
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }


def test_persist_false_performs_zero_project_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage_minimal_constraints(tmp_path)
    db_path = tmp_path / ".ast-cache" / "index.db"
    _init_violations_db(db_path)
    before = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    tool = _make_tool(tmp_path)
    monkeypatch.setattr(tool, "_run_read_only", lambda *a, **k: ([], 0))
    monkeypatch.setattr(
        tool,
        "_run_and_persist",
        lambda *a, **k: pytest.fail("persist=false entered the write-through path"),
    )

    result = _run(tool.execute({"persist": False, "output_format": "json"}))

    after = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert result["verdict"] == "SAFE"
    assert after == before


def test_frozen_scope_intersection_excludes_outside_project_debt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage_minimal_constraints(tmp_path)
    db_path = tmp_path / ".ast-cache" / "index.db"
    _init_violations_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE edges(kind TEXT)")
    conn.commit()
    conn.close()
    registry, created = _create_frozen_scope(monkeypatch, tmp_path, ["src/scope.py"])
    from tree_sitter_analyzer.constraints import Violation

    def violation(rule_id: str, caller: str, callee: str, severity: str, line: int):
        return Violation(rule_id, caller, "caller", line, "callee", callee, severity, 1)

    violations = [
        violation("caller-in-scope", "src/scope.py", "vendor/a.py", "warn", 10),
        violation("callee-in-scope", "vendor/b.py", "src/scope.py", "warn", 20),
        violation("outside-debt", "legacy/a.py", "legacy/b.py", "error", 30),
    ]
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.constraint_check_tool.evaluate",
        lambda constraints, conn: violations,
    )

    result = _run(
        _make_tool(tmp_path).execute(
            {
                "persist": False,
                "diff_snapshot_id": created["diff_snapshot_id"],
                "scope_paths": created["assessed_scope_paths"],
                "output_format": "json",
            }
        )
    )

    assert result["verdict"] == "CAUTION"
    assert [row["rule_id"] for row in result["violations"]] == [
        "caller-in-scope",
        "callee-in-scope",
    ]
    assert result["diff_snapshot_id"] == created["diff_snapshot_id"]
    assert result["source_generation"] == created["source_generation"]
    assert result["assessed_scope_paths"] == ["src/scope.py"]
    assert (
        registry.close_lease(created["diff_snapshot_id"], created["route_lease_id"])
        is True
    )


def test_frozen_constraints_reject_scope_not_exactly_owned_by_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, created = _create_frozen_scope(monkeypatch, tmp_path, ["src/a.py"])

    result = _run(
        _make_tool(tmp_path).execute(
            {
                "persist": False,
                "diff_snapshot_id": created["diff_snapshot_id"],
                "scope_paths": ["src/a.py", "outside.py"],
                "output_format": "json",
            }
        )
    )

    assert result["error_code"] == "DIFF_SNAPSHOT_SCOPE_MISMATCH"
    assert (
        registry.close_lease(created["diff_snapshot_id"], created["route_lease_id"])
        is True
    )


def test_frozen_constraints_reject_closed_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, created = _create_frozen_scope(monkeypatch, tmp_path, ["src/a.py"])
    assert (
        registry.close_lease(created["diff_snapshot_id"], created["route_lease_id"])
        is True
    )

    result = _run(
        _make_tool(tmp_path).execute(
            {
                "persist": False,
                "diff_snapshot_id": created["diff_snapshot_id"],
                "scope_paths": created["assessed_scope_paths"],
                "output_format": "json",
            }
        )
    )

    assert result["error_code"] == "DIFF_SNAPSHOT_EXPIRED"


def test_frozen_constraints_without_config_is_not_applicable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, created = _create_frozen_scope(monkeypatch, tmp_path, ["src/a.py"])

    result = _run(
        _make_tool(tmp_path).execute(
            {
                "persist": False,
                "diff_snapshot_id": created["diff_snapshot_id"],
                "scope_paths": created["assessed_scope_paths"],
                "output_format": "json",
            }
        )
    )

    assert result["state"] == "not_applicable"
    assert result["reason"] == "NO_CONFIG"
    assert result["violations"] == []
    assert result["diff_snapshot_id"] == created["diff_snapshot_id"]
    assert result["source_generation"] == created["source_generation"]
    assert (
        registry.close_lease(created["diff_snapshot_id"], created["route_lease_id"])
        is True
    )


def test_frozen_constraints_reject_generation_changed_after_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, created = _create_frozen_scope(monkeypatch, tmp_path, ["src/a.py"])
    monkeypatch.setattr(
        snapshots,
        "oracle_generation",
        lambda *args, **kwargs: (
            "sg_changed",
            snapshots.RootIdentity(str(tmp_path.resolve()), 1, 2),
        ),
    )

    result = _run(
        _make_tool(tmp_path).execute(
            {
                "persist": False,
                "diff_snapshot_id": created["diff_snapshot_id"],
                "scope_paths": created["assessed_scope_paths"],
                "output_format": "json",
            }
        )
    )

    assert result["error_code"] == "DIFF_SNAPSHOT_SOURCE_CHANGED"
    assert (
        registry.close_lease(created["diff_snapshot_id"], created["route_lease_id"])
        is True
    )


def test_frozen_constraints_missing_edges_schema_is_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage_minimal_constraints(tmp_path)
    db_path = tmp_path / ".ast-cache" / "index.db"
    _init_violations_db(db_path)
    registry, created = _create_frozen_scope(monkeypatch, tmp_path, ["src/a.py"])

    result = _run(
        _make_tool(tmp_path).execute(
            {
                "persist": False,
                "diff_snapshot_id": created["diff_snapshot_id"],
                "scope_paths": created["assessed_scope_paths"],
                "output_format": "json",
            }
        )
    )
    assert (result["success"], result["error_code"]) == (
        False,
        "CONSTRAINT_INDEX_UNKNOWN",
    )
    assert (
        registry.close_lease(created["diff_snapshot_id"], created["route_lease_id"])
        is True
    )


def test_frozen_constraints_rejects_config_changed_during_index_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage_minimal_constraints(tmp_path)
    db_path = tmp_path / ".ast-cache" / "index.db"
    _init_violations_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE edges(kind TEXT)")
    conn.commit()
    conn.close()
    registry, created = _create_frozen_scope(monkeypatch, tmp_path, ["src/a.py"])
    from dataclasses import replace

    import tree_sitter_analyzer.source_oracle as oracle

    real_safe = oracle.safe_workspace_path
    config_reads = 0

    def changed_config(*args, **kwargs):
        nonlocal config_reads
        result = real_safe(*args, **kwargs)
        if args[1] == "architectural-constraints.yml":
            config_reads += 1
            if config_reads == 1:
                return replace(result, data=(result.data or b"") + b"\n# changed")
        return result

    monkeypatch.setattr(oracle, "safe_workspace_path", changed_config)
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.constraint_check_tool.evaluate",
        lambda constraints, conn: [],
    )
    result = _run(
        _make_tool(tmp_path).execute(
            {
                "persist": False,
                "diff_snapshot_id": created["diff_snapshot_id"],
                "scope_paths": created["assessed_scope_paths"],
            }
        )
    )
    assert result["error_code"] == "CONSTRAINT_CONFIG_CHANGED"
    assert (
        registry.close_lease(created["diff_snapshot_id"], created["route_lease_id"])
        is True
    )


@pytest.mark.parametrize(
    "divergent_field",
    ["staged_source_matches_worktree", "staged_config_matches_worktree"],
)
def test_staged_frozen_constraints_reject_live_graph_for_divergent_plane(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, divergent_field: str
) -> None:
    # PR #1254 reviews 3765536002/3765536016: fail closed without staged graph capability.
    registry, created = _create_frozen_scope(monkeypatch, tmp_path, ["src/a.py"])
    from dataclasses import replace

    state = registry._states[str(created["diff_snapshot_id"])]
    state.snapshot = replace(
        state.snapshot,
        mode="staged",
        **{divergent_field: False},
    )

    result = _run(
        _make_tool(tmp_path).execute(
            {
                "persist": False,
                "diff_snapshot_id": created["diff_snapshot_id"],
                "scope_paths": created["assessed_scope_paths"],
                "output_format": "json",
            }
        )
    )

    assert (result["success"], result["error_code"], result["verdict"]) == (
        False,
        "CONSTRAINT_STAGED_INDEX_UNKNOWN",
        "ERROR",
    )


def test_persist_path_writes_evaluated_violations(tmp_path, monkeypatch):
    from tree_sitter_analyzer.constraints import Violation

    db_path = tmp_path / "index.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE edges(kind TEXT)")
    conn.execute("INSERT INTO edges VALUES ('calls')")
    conn.commit()
    conn.close()
    item = Violation("r", "src/a.py", "a", 4, "b", "src/b.py", "warn", 0)
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.constraint_check_tool.evaluate",
        lambda constraints, conn: [item],
    )
    rows, count = _make_tool(tmp_path)._run_and_persist(db_path, [object()])
    conn = sqlite3.connect(db_path)
    persisted = conn.execute(
        "SELECT rule_id, caller_file, severity FROM ast_constraint_violations"
    ).fetchall()
    conn.close()
    assert (rows, count, persisted) == ([item], 1, [("r", "src/a.py", "warn")])


def test_persist_path_evaluator_failure_preserves_cache(tmp_path, monkeypatch):
    db_path = tmp_path / "index.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE edges(kind TEXT)")
    conn.execute("INSERT INTO edges VALUES ('calls')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.constraint_check_tool.evaluate",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("broken")),
    )
    assert _make_tool(tmp_path)._run_and_persist(db_path, [object()]) == ([], 1)


def test_cached_violation_filters_severity_and_path(tmp_path):
    db_path = tmp_path / "index.db"
    _init_violations_db(db_path)
    _seed_violation(
        db_path,
        rule_id="warn",
        caller_file="src/a.py",
        callee_file="dst.py",
        severity="warn",
    )
    _seed_violation(
        db_path,
        rule_id="info",
        caller_file="other/b.py",
        callee_file="dst.py",
        severity="info",
    )
    rows = _make_tool(tmp_path)._read_filtered_violations(
        db_path, path_filter="src/**", min_severity_rank=1
    )
    assert [row["rule_id"] for row in rows] == ["warn"]


def test_read_only_evaluation_closes_connection_and_filters_rows(tmp_path, monkeypatch):
    from tree_sitter_analyzer.constraints import Violation

    db_path = tmp_path / "index.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE edges(kind TEXT)")
    conn.execute("INSERT INTO edges VALUES ('calls')")
    conn.commit()
    conn.close()
    rows = [
        Violation("low", "src/a.py", "a", 1, "b", "dst.py", "info", 1),
        Violation("path", "other/a.py", "a", 2, "b", "dst.py", "warn", 1),
        Violation("keep", "src/b.py", "a", 3, "b", "dst.py", "warn", 1),
    ]
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.constraint_check_tool.evaluate",
        lambda *_args: rows,
    )
    result, count = _make_tool(tmp_path)._run_read_only(
        db_path,
        [object()],
        path_filter="src/**",
        min_severity_rank=1,
    )
    assert (count, [row["rule_id"] for row in result]) == (1, ["keep"])


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"diff_snapshot_id": "", "persist": False}, "non-empty string"),
        ({"diff_snapshot_id": "ds", "persist": False}, "scope_paths as strings"),
        (
            {
                "diff_snapshot_id": "ds",
                "persist": False,
                "scope_paths": [],
                "path_filter": "src/**",
            },
            "DIFF_SNAPSHOT_CONFLICTING_ARGUMENTS",
        ),
        ({"scope_paths": []}, "scope_paths requires diff_snapshot_id"),
    ],
)
def test_constraint_snapshot_argument_conflicts_are_exact(tmp_path, arguments, message):
    with pytest.raises(ValueError, match=message):
        _make_tool(tmp_path).validate_arguments(arguments)
