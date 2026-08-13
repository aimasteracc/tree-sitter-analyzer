"""Focused frozen/read-only exactness tests for constraint checking."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

import tree_sitter_analyzer.diff_snapshot_registry as snapshots
from tests.unit.mcp.tools._constraint_check_support import (
    create_frozen_scope as _create_frozen_scope,
)
from tests.unit.mcp.tools._constraint_check_support import (
    frozen_arguments as _frozen_arguments,
)
from tests.unit.mcp.tools._constraint_check_support import (
    init_violations_db as _init_violations_db,
)
from tests.unit.mcp.tools._constraint_check_support import (
    make_tool as _make_tool,
)
from tests.unit.mcp.tools._constraint_check_support import (
    run as _run,
)
from tests.unit.mcp.tools._constraint_check_support import (
    seed_violation as _seed_violation,
)
from tests.unit.mcp.tools._constraint_check_support import (
    stage_minimal_constraints as _stage_minimal_constraints,
)

pytest.importorskip("yaml")


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
