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


def test_tool_schema_reexport_preserves_public_api(tmp_path: Path) -> None:
    from tree_sitter_analyzer.mcp.tools.constraint_check_schema import (
        TOOL_SCHEMA as extracted_schema,
    )
    from tree_sitter_analyzer.mcp.tools.constraint_check_tool import TOOL_SCHEMA

    assert (
        _make_tool(tmp_path).get_tool_schema() is TOOL_SCHEMA,
        TOOL_SCHEMA is extracted_schema,
    ) == (
        True,
        True,
    )


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


def _create_frozen_scope(
    monkeypatch, project: Path, paths: list[str], *, source_scope=None
):
    """Install an isolated registry and create one leased frozen scope."""
    import tree_sitter_analyzer.index_snapshot as index_snapshots
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor

    source_scope = source_scope or make_source_scope_descriptor()
    index_snapshots.REGISTRY.close_all()
    install_fake_snapshot_materializer(monkeypatch, project)
    registry = snapshots.DiffSnapshotRegistry()
    monkeypatch.setattr(snapshots, "REGISTRY", registry)
    created = registry.create(str(project), "diff", paths)
    assert created["success"] is True

    from contextlib import contextmanager
    from types import SimpleNamespace

    @contextmanager
    def lease(_root):
        yield SimpleNamespace(
            snapshot_id="is_test",
            completeness="complete",
            source_generation=created["source_generation"],
            reason=None,
            canonical_root=str(project.resolve()),
            index_fingerprint="sha256:" + "1" * 64,
            source_scope=source_scope,
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
        lambda constraints, conn, **_kwargs: violations,
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
        lambda constraints, conn, **_kwargs: [],
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
    _stage_minimal_constraints(tmp_path)
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


def test_staged_frozen_constraints_without_config_precedes_divergent_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #1254 review 3765918788: no graph is needed when no config exists.
    registry, created = _create_frozen_scope(monkeypatch, tmp_path, ["src/a.py"])
    from dataclasses import replace

    state = registry._states[str(created["diff_snapshot_id"])]
    state.snapshot = replace(
        state.snapshot,
        mode="staged",
        staged_source_matches_worktree=False,
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

    assert (result["success"], result["state"], result["reason"]) == (
        True,
        "not_applicable",
        "NO_CONFIG",
    )


def test_staged_frozen_no_config_final_guard_does_not_probe_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #1254 review 3766246581: staged NO_CONFIG stays on the index plane.
    registry, created = _create_frozen_scope(monkeypatch, tmp_path, ["src/a.py"])
    from dataclasses import replace

    state = registry._states[str(created["diff_snapshot_id"])]
    state.snapshot = replace(state.snapshot, mode="staged")

    from tree_sitter_analyzer.mcp.tools import constraint_check_frozen

    def reject_worktree_probe(*args, **kwargs):
        raise AssertionError("staged NO_CONFIG probed the worktree")

    monkeypatch.setattr(
        constraint_check_frozen.source_oracle,
        "safe_workspace_path",
        reject_worktree_probe,
    )

    result = _run(_make_tool(tmp_path).execute(_frozen_arguments(created)))

    assert (result["success"], result["state"], result["reason"]) == (
        True,
        "not_applicable",
        "NO_CONFIG",
    )
    assert registry.close_lease(created["diff_snapshot_id"], created["route_lease_id"])


def test_read_only_missing_edges_returns_structured_index_error(tmp_path: Path) -> None:
    # PR #1254 review 3765918809: persist=false must not leak SQLite failures.
    _stage_minimal_constraints(tmp_path)
    _init_violations_db(tmp_path / ".ast-cache" / "index.db")

    result = _run(_make_tool(tmp_path).execute({"persist": False}))

    assert (result["success"], result["error_code"], result["verdict"]) == (
        False,
        "CONSTRAINT_INDEX_UNKNOWN",
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
    conn = sqlite3.connect(db_path)
    try:
        result, count = _make_tool(tmp_path)._evaluate_connection(
            conn,
            [object()],
            path_filter="src/**",
            min_severity_rank=1,
        )
    finally:
        conn.close()
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


def _frozen_arguments(created: dict[str, object]) -> dict[str, object]:
    return {
        "persist": False,
        "diff_snapshot_id": created["diff_snapshot_id"],
        "scope_paths": created["assessed_scope_paths"],
        "output_format": "json",
    }


def test_frozen_executor_reports_missing_project_root() -> None:
    from tree_sitter_analyzer.mcp.tools.constraint_check_frozen import execute_frozen
    from tree_sitter_analyzer.mcp.tools.constraint_check_tool import ConstraintCheckTool

    result = execute_frozen(
        ConstraintCheckTool(None),
        {"diff_snapshot_id": "ds_missing", "output_format": "json"},
    )

    assert (result["success"], result["error_code"]) == (
        False,
        "MISSING_PROJECT_ROOT",
    )


def test_frozen_constraints_reject_invalid_captured_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "architectural-constraints.yml").write_text("constraints: [")
    registry, created = _create_frozen_scope(monkeypatch, tmp_path, ["src/a.py"])

    result = _run(_make_tool(tmp_path).execute(_frozen_arguments(created)))

    assert (result["success"], result["error_code"]) == (
        False,
        "CONSTRAINT_CONFIG_INVALID",
    )
    assert registry.close_lease(created["diff_snapshot_id"], created["route_lease_id"])


@pytest.mark.parametrize(
    ("snapshot_id", "completeness", "generation", "reason", "error_code"),
    [
        (None, "complete", "captured", "NO_INDEX", "NO_INDEX"),
        ("is_test", "partial", "captured", "INDEX_PARTIAL", "INDEX_PARTIAL"),
        ("is_test", "complete", "other", None, "SOURCE_GENERATION_MISMATCH"),
    ],
)
def test_frozen_constraints_require_matching_complete_index_capability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    snapshot_id,
    completeness,
    generation,
    reason,
    error_code,
) -> None:
    from contextlib import contextmanager
    from types import SimpleNamespace

    import tree_sitter_analyzer.index_snapshot as index_snapshots

    _stage_minimal_constraints(tmp_path)
    registry, created = _create_frozen_scope(monkeypatch, tmp_path, ["src/a.py"])

    @contextmanager
    def lease(_root):
        yield SimpleNamespace(
            snapshot_id=snapshot_id,
            completeness=completeness,
            source_generation=(
                created["source_generation"] if generation == "captured" else generation
            ),
            reason=reason,
        )

    monkeypatch.setattr(index_snapshots, "lease_existing_snapshot", lease)

    result = _run(_make_tool(tmp_path).execute(_frozen_arguments(created)))

    assert (result["success"], result["error_code"]) == (False, error_code)
    assert registry.close_lease(created["diff_snapshot_id"], created["route_lease_id"])


def test_frozen_constraints_reject_supported_path_outside_index_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #1254 review 3766246604: graph evidence cannot cover paths it omitted.
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor

    _stage_minimal_constraints(tmp_path)
    registry, created = _create_frozen_scope(
        monkeypatch,
        tmp_path,
        ["src/a.py", "README.md"],
        source_scope=make_source_scope_descriptor(roots=("lib",)),
    )

    result = _run(_make_tool(tmp_path).execute(_frozen_arguments(created)))

    assert (result["success"], result["error_code"], result["verdict"]) == (
        False,
        "CONSTRAINT_INDEX_SCOPE_MISMATCH",
        "ERROR",
    )
    assert registry.close_lease(created["diff_snapshot_id"], created["route_lease_id"])


def test_frozen_constraints_map_index_capture_failure_to_structured_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from contextlib import contextmanager

    import tree_sitter_analyzer.index_snapshot as index_snapshots

    _stage_minimal_constraints(tmp_path)
    registry, created = _create_frozen_scope(monkeypatch, tmp_path, ["src/a.py"])

    @contextmanager
    def failed_lease(_root):
        raise OSError("index disappeared")
        yield

    monkeypatch.setattr(index_snapshots, "lease_existing_snapshot", failed_lease)

    result = _run(_make_tool(tmp_path).execute(_frozen_arguments(created)))

    assert (result["success"], result["error_code"]) == (
        False,
        "CONSTRAINT_CAPTURE_UNKNOWN",
    )
    assert result["error"] == "index disappeared"
    assert registry.close_lease(created["diff_snapshot_id"], created["route_lease_id"])


def test_frozen_constraints_release_consumer_after_snapshot_read_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tree_sitter_analyzer.mcp.tools.constraint_check_frozen import execute_frozen

    released = []

    class BrokenConsumer:
        @property
        def snapshot(self):
            raise OSError("snapshot unavailable")

        def release(self):
            released.append(True)

    class BrokenRegistry:
        def acquire(self, snapshot_id, project_root):
            return BrokenConsumer(), None

    monkeypatch.setattr(snapshots, "REGISTRY", BrokenRegistry())

    result = execute_frozen(
        _make_tool(tmp_path),
        {
            "diff_snapshot_id": "ds_broken",
            "scope_paths": [],
            "output_format": "json",
        },
    )

    assert (result["error_code"], result["error"], released) == (
        "CONSTRAINT_CAPTURE_UNKNOWN",
        "snapshot unavailable",
        [True],
    )


def test_constraint_arguments_reject_non_boolean_persist(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="^persist must be a boolean$"):
        _make_tool(tmp_path).validate_arguments({"persist": "false"})


def test_constraint_arguments_reject_unknown_severity(tmp_path: Path) -> None:
    with pytest.raises(
        ValueError,
        match=(
            r"^severity_min must be one of \['error', 'info', 'warn'\]; "
            r"got 'critical'$"
        ),
    ):
        _make_tool(tmp_path).validate_arguments({"severity_min": "critical"})


def test_scope_predicate_accepts_caller_or_callee_and_rejects_outside(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tree_sitter_analyzer.constraints import Violation

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE edges(kind TEXT)")
    candidates = [
        Violation("caller", "src/in.py", "a", 1, "b", "out.py", "warn", 1),
        Violation("callee", "out.py", "a", 2, "b", "src/in.py", "warn", 1),
        Violation("outside", "a.py", "a", 3, "b", "b.py", "warn", 1),
    ]

    def scoped_evaluate(_constraints, _conn, *, scope_predicate):
        return [
            item
            for item in candidates
            if scope_predicate(item.caller_file, item.callee_file)
        ]

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.constraint_check_tool.evaluate",
        scoped_evaluate,
    )
    try:
        rows, edge_count = _make_tool(tmp_path)._evaluate_connection(
            conn,
            [object()],
            min_severity_rank=1,
            scope_paths=frozenset({"src/in.py"}),
        )
    finally:
        conn.close()

    assert (edge_count, [row["rule_id"] for row in rows]) == (
        0,
        ["callee", "caller"],
    )


def test_frozen_scope_rejects_missing_source_scope_descriptor() -> None:
    from tree_sitter_analyzer.mcp.tools.constraint_check_frozen import (
        _supported_scope_is_covered,
    )

    assert _supported_scope_is_covered(["src/a.py"], None) is False


def test_frozen_scope_rejects_supported_excluded_path() -> None:
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor
    from tree_sitter_analyzer.mcp.tools.constraint_check_frozen import (
        _supported_scope_is_covered,
    )

    scope = make_source_scope_descriptor(exclude_patterns=("src/*.py",))

    assert _supported_scope_is_covered(["src/a.py"], scope) is False


def test_constraint_arguments_reject_snapshot_with_default_persistence(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="^diff_snapshot_id requires persist=false$"):
        _make_tool(tmp_path).validate_arguments(
            {"diff_snapshot_id": "ds_snapshot", "scope_paths": []}
        )


# Round 6 exactness regressions (PR #1254 review semantics).


def test_read_only_zero_rules_needs_no_index(tmp_path: Path) -> None:
    (tmp_path / "architectural-constraints.yml").write_text(
        "version: 1\nconstraints: []\n"
    )

    result = _run(_make_tool(tmp_path).execute({"persist": False}))

    assert result == {
        "success": True,
        "verdict": "SAFE",
        "violations": [],
        "rule_count": 0,
        "evaluated_edge_count": 0,
    }
    assert not (tmp_path / ".ast-cache").exists()


def test_persist_missing_index_returns_legacy_safe_response(tmp_path: Path) -> None:
    _stage_minimal_constraints(tmp_path)

    result = _run(_make_tool(tmp_path).execute({"output_format": "json"}))

    assert result == {
        "success": True,
        "verdict": "SAFE",
        "violations": [],
        "rule_count": 1,
        "evaluated_edge_count": 0,
        "note": ("No AST cache at .ast-cache/index.db; run codegraph_autoindex first."),
    }
    assert not (tmp_path / ".ast-cache").exists()


def test_read_only_missing_index_fails_closed(tmp_path: Path) -> None:
    _stage_minimal_constraints(tmp_path)

    result = _run(_make_tool(tmp_path).execute({"persist": False}))

    assert (result["success"], result["error_code"], result["verdict"]) == (
        False,
        "CONSTRAINT_INDEX_UNKNOWN",
        "ERROR",
    )
    assert result["error"] == "MISSING_INDEX"


def test_read_only_corrupt_index_fails_closed(tmp_path: Path) -> None:
    _stage_minimal_constraints(tmp_path)
    db_path = tmp_path / ".ast-cache" / "index.db"
    db_path.parent.mkdir()
    db_path.write_bytes(b"not a sqlite database")

    result = _run(_make_tool(tmp_path).execute({"persist": False}))

    assert (result["success"], result["error_code"], result["verdict"]) == (
        False,
        "CONSTRAINT_INDEX_UNKNOWN",
        "ERROR",
    )


def test_read_only_malformed_config_is_structured_caution(tmp_path: Path) -> None:
    (tmp_path / "architectural-constraints.yml").write_text("constraints: [")

    result = _run(_make_tool(tmp_path).execute({"persist": False}))

    assert (result["success"], result["verdict"], result["rule_count"]) == (
        False,
        "CAUTION",
        0,
    )
    assert result["violations"] == []
    assert "constraint parse error" in result["error"]


def _edges_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE edges(kind TEXT)")
    conn.execute("INSERT INTO edges VALUES ('calls')")
    conn.commit()
    conn.close()


def test_read_only_rejects_symlinked_index(tmp_path: Path) -> None:
    real = tmp_path / "real.db"
    _edges_db(real)
    link = tmp_path / ".ast-cache" / "index.db"
    link.parent.mkdir()
    link.symlink_to(real)

    with pytest.raises(ValueError, match="^INDEX_PATH_SYMLINK$"):
        _make_tool(tmp_path)._run_read_only(
            link, [object()], path_filter="", min_severity_rank=1
        )


@pytest.mark.parametrize("suffix", ["-wal", "-journal"])
def test_read_only_rejects_nonempty_writer_sidecar(tmp_path: Path, suffix: str) -> None:
    db_path = tmp_path / ".ast-cache" / "index.db"
    _edges_db(db_path)
    Path(str(db_path) + suffix).write_bytes(b"active writer")

    with pytest.raises(ValueError, match="^CONCURRENT_WRITER$"):
        _make_tool(tmp_path)._run_read_only(
            db_path, [object()], path_filter="", min_severity_rank=1
        )


def test_read_only_immutable_connection_blocks_evaluator_writes(tmp_path: Path) -> None:
    db_path = tmp_path / ".ast-cache" / "index.db"
    _edges_db(db_path)

    def writing_evaluator(_constraints, conn):
        conn.execute("INSERT INTO edges VALUES ('calls')")
        return []

    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA query_only=ON")
        try:
            _make_tool(tmp_path)._evaluate_connection(
                conn,
                [object()],
                path_filter="",
                min_severity_rank=1,
                evaluator=writing_evaluator,
            )
        finally:
            conn.close()
    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM edges").fetchone() == (1,)
    finally:
        conn.close()
    assert not Path(str(db_path) + "-wal").exists()


def test_evaluate_connection_rolls_back_only_its_own_transaction(
    tmp_path: Path,
) -> None:
    tool = _make_tool(tmp_path)
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE edges(kind TEXT)")
    conn.commit()

    def insert_then_return(_constraints, connection):
        connection.execute("INSERT INTO edges VALUES ('calls')")
        return []

    rows, count = tool._evaluate_connection(
        conn, [object()], min_severity_rank=1, evaluator=insert_then_return
    )
    assert (rows, count, conn.in_transaction) == ([], 0, False)
    assert conn.execute("SELECT COUNT(*) FROM edges").fetchone() == (0,)

    conn.execute("BEGIN")
    rows, count = tool._evaluate_connection(
        conn, [object()], min_severity_rank=1, evaluator=insert_then_return
    )
    assert (rows, count, conn.in_transaction) == ([], 0, True)
    assert conn.execute("SELECT COUNT(*) FROM edges").fetchone() == (1,)
    conn.rollback()
    conn.close()


def test_frozen_zero_rules_precedes_divergent_staged_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import replace

    (tmp_path / "architectural-constraints.yml").write_text(
        "version: 1\nconstraints: []\n"
    )
    registry, created = _create_frozen_scope(monkeypatch, tmp_path, ["src/a.py"])
    state = registry._states[str(created["diff_snapshot_id"])]
    state.snapshot = replace(
        state.snapshot,
        mode="staged",
        staged_source_matches_worktree=False,
        staged_config_matches_worktree=False,
    )

    result = _run(_make_tool(tmp_path).execute(_frozen_arguments(created)))

    assert (result["success"], result["state"], result["verdict"]) == (
        True,
        "applicable",
        "SAFE",
    )
    assert (result["rule_count"], result["evaluated_edge_count"]) == (0, 0)


def test_frozen_index_lease_receives_snapshot_hard_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from contextlib import contextmanager
    from types import SimpleNamespace

    import tree_sitter_analyzer.index_snapshot as index_snapshots

    _stage_minimal_constraints(tmp_path)
    registry, created = _create_frozen_scope(monkeypatch, tmp_path, ["src/a.py"])
    snapshot = registry._states[str(created["diff_snapshot_id"])].snapshot
    observed = []

    @contextmanager
    def lease(_root, *, deadline=None):
        observed.append(deadline)
        yield SimpleNamespace(
            snapshot_id=None,
            completeness="unknown",
            source_generation=None,
            reason="NO_INDEX",
        )

    monkeypatch.setattr(index_snapshots, "lease_existing_snapshot", lease)
    result = _run(_make_tool(tmp_path).execute(_frozen_arguments(created)))

    assert result["error_code"] == "NO_INDEX"
    assert observed == [snapshot.created_monotonic + snapshots.HARD_LIFETIME_SECONDS]


def test_counterpart_graph_requires_full_default_index_scope() -> None:
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor
    from tree_sitter_analyzer.mcp.tools.constraint_check_frozen import (
        _supported_scope_is_covered,
    )

    # The changed endpoint is inside src, but its caller/callee counterpart may
    # be outside src, so a src-only graph cannot certify absence of violations.
    partial = make_source_scope_descriptor(roots=("src",))
    assert _supported_scope_is_covered(["src/a.py"], partial) is False
    assert (
        _supported_scope_is_covered(["src/a.py"], make_source_scope_descriptor())
        is True
    )


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("README.md", True),
        ("tests/golden/corpus_python/sample.py", False),
        ("src/.private/a.py", False),
    ],
)
def test_frozen_scope_default_policy_edge_cases(path: str, expected: bool) -> None:
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor
    from tree_sitter_analyzer.mcp.tools.constraint_check_frozen import (
        _supported_scope_is_covered,
    )

    assert (
        _supported_scope_is_covered([path], make_source_scope_descriptor()) is expected
    )


def test_frozen_scope_fails_when_replayed_root_no_longer_covers_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tree_sitter_analyzer.mcp.tools.constraint_check_frozen as frozen

    class MutableReplayScope:
        exclude_patterns = ()
        effective_excludes = frozenset()

        def __init__(self):
            self.reads = 0

        @property
        def roots(self):
            self.reads += 1
            # Pass the initial authority check, then model a replay whose root
            # counterpart does not cover the selected source path.
            return (".",) if self.reads == 1 else ("lib",)

    monkeypatch.setattr(frozen, "SourceScopeDescriptor", MutableReplayScope)

    assert (
        frozen._supported_scope_is_covered(["src/a.py"], MutableReplayScope()) is False
    )


def test_read_only_rejects_elapsed_deadline_before_index_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(time, "monotonic", lambda: 8.0)

    with pytest.raises(RuntimeError, match="^INDEX_SNAPSHOT_DEADLINE$"):
        _make_tool(tmp_path)._run_read_only(
            tmp_path / "ignored.db",
            [object()],
            path_filter="",
            min_severity_rank=1,
            deadline=8.0,
        )


def test_read_only_requires_project_root() -> None:
    from tree_sitter_analyzer.mcp.tools.constraint_check_tool import ConstraintCheckTool

    with pytest.raises(ValueError, match="^MISSING_PROJECT_ROOT$"):
        ConstraintCheckTool(None)._run_read_only(
            Path("ignored.db"),
            [object()],
            path_filter="",
            min_severity_rank=1,
        )


def test_read_only_supports_legacy_index_snapshot_seams(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from contextlib import contextmanager
    from types import SimpleNamespace

    import tree_sitter_analyzer.index_snapshot as index_snapshots

    observed = []

    @contextmanager
    def legacy_lease(root):
        observed.append(("lease", root))
        yield SimpleNamespace(
            snapshot_id="is_legacy",
            completeness="complete",
            source_generation="sg_legacy",
            reason=None,
        )

    @contextmanager
    def legacy_acquire(snapshot_id, root, generation):
        observed.append(("acquire", snapshot_id, root, generation))
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE edges(kind TEXT)")
        try:
            yield SimpleNamespace(), conn
        finally:
            conn.close()

    monkeypatch.setattr(index_snapshots, "lease_existing_snapshot", legacy_lease)
    monkeypatch.setattr(index_snapshots, "acquire_index_snapshot", legacy_acquire)

    rows, edge_count = _make_tool(tmp_path)._run_read_only(
        tmp_path / "ignored.db",
        [object()],
        path_filter="",
        min_severity_rank=1,
        evaluator=lambda _constraints, _conn: [],
    )

    assert (rows, edge_count) == ([], 0)
    assert observed == [
        ("lease", str(tmp_path)),
        ("acquire", "is_legacy", str(tmp_path), "sg_legacy"),
    ]


def test_evaluate_connection_rejects_deadline_before_query(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(time, "monotonic", lambda: 2.0)
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE edges(kind TEXT)")
    conn.commit()
    try:
        with pytest.raises(RuntimeError, match="^INDEX_SNAPSHOT_DEADLINE$"):
            _make_tool(tmp_path)._evaluate_connection(
                conn,
                [object()],
                min_severity_rank=1,
                evaluator=lambda _constraints, _conn: [],
                deadline=1.0,
            )
    finally:
        conn.close()


def test_evaluate_connection_rejects_deadline_after_query(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ticks = iter((0.0, 2.0))
    monkeypatch.setattr(time, "monotonic", lambda: next(ticks, 2.0))
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE edges(kind TEXT)")
    conn.commit()
    try:
        with pytest.raises(RuntimeError, match="^INDEX_SNAPSHOT_DEADLINE$"):
            _make_tool(tmp_path)._evaluate_connection(
                conn,
                [object()],
                min_severity_rank=1,
                evaluator=lambda _constraints, _conn: [],
                deadline=1.0,
            )
    finally:
        conn.close()


def test_progress_handler_timeout_rolls_back_and_removes_handler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ticks = iter((0.0, 0.0, 2.0))
    monkeypatch.setattr(time, "monotonic", lambda: next(ticks, 2.0))
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE edges(kind TEXT)")
    conn.commit()

    def exercise_handler(_constraints, connection):
        with pytest.raises(sqlite3.OperationalError, match="interrupted"):
            connection.execute(
                "WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n) "
                "SELECT sum(x) FROM n"
            ).fetchone()
        raise RuntimeError("evaluation timed out")

    with pytest.raises(RuntimeError, match="^evaluation timed out$"):
        _make_tool(tmp_path)._evaluate_connection(
            conn,
            [object()],
            min_severity_rank=1,
            evaluator=exercise_handler,
            deadline=1.0,
        )

    assert conn.in_transaction is False
    assert conn.execute("SELECT COUNT(*) FROM edges").fetchone() == (0,)
    conn.close()
