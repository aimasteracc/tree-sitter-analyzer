"""Focused frozen/read-only exactness tests for constraint checking."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import tree_sitter_analyzer.diff_snapshot_registry as snapshots
from tests.unit.mcp.tools._constraint_check_support import (
    create_frozen_scope as _create_frozen_scope,
)
from tests.unit.mcp.tools._constraint_check_support import (
    edges_db as _edges_db,
)
from tests.unit.mcp.tools._constraint_check_support import (
    frozen_arguments as _frozen_arguments,
)
from tests.unit.mcp.tools._constraint_check_support import (
    make_tool as _make_tool,
)
from tests.unit.mcp.tools._constraint_check_support import (
    run as _run,
)
from tests.unit.mcp.tools._constraint_check_support import (
    stage_minimal_constraints as _stage_minimal_constraints,
)

pytest.importorskip("yaml")

# Round 6 exactness regressions (PR #1254 review semantics).


def test_read_only_zero_rules_needs_no_index(tmp_path: Path) -> None:
    (tmp_path / "architectural-constraints.yml").write_text(
        "version: 1\nconstraints: []\n"
    )

    result = _run(_make_tool(tmp_path).execute({"persist": False}))

    assert result == {
        "success": True,
        "verdict": "SAFE",
        "action_version": "edit.constraints/v1",
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
        "action_version": "edit.constraints/v1",
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


def test_read_only_rejects_symlinked_index(tmp_path: Path) -> None:
    real = tmp_path / "real.db"
    _edges_db(real)
    link = tmp_path / ".ast-cache" / "index.db"
    link.parent.mkdir()
    link.symlink_to(real)

    expected = "INDEX_PATH_SYMLINK"
    with pytest.raises(ValueError, match=f"^{expected}$"):
        _make_tool(tmp_path)._run_read_only(
            link, [object()], path_filter="", min_severity_rank=1
        )


@pytest.mark.parametrize("suffix", ["-wal", "-journal"])
def test_read_only_rejects_nonempty_writer_sidecar(tmp_path: Path, suffix: str) -> None:
    db_path = tmp_path / ".ast-cache" / "index.db"
    _edges_db(db_path)
    Path(str(db_path) + suffix).write_bytes(b"active writer")

    expected = "CONCURRENT_WRITER"
    with pytest.raises(ValueError, match=f"^{expected}$"):
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
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.constraint_index_snapshot.portable_snapshot_required",
        lambda: False,
    )
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


def test_persist_capacity_failure_is_structured_and_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #1254 review 3768096795: capacity exhaustion cannot return SAFE.
    _stage_minimal_constraints(tmp_path)
    db_path = tmp_path / ".ast-cache" / "index.db"
    db_path.parent.mkdir()
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE edges(kind TEXT)")
    conn.execute("INSERT INTO edges VALUES ('calls')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.constraint_check_tool.evaluate",
        lambda *_args: (_ for _ in ()).throw(
            RuntimeError("CONSTRAINT_EVALUATION_CAPACITY")
        ),
    )

    result = _run(_make_tool(tmp_path).execute({"output_format": "json"}))

    assert result == {
        "success": False,
        "verdict": "ERROR",
        "error_code": "CONSTRAINT_EVALUATION_CAPACITY",
        "error": "CONSTRAINT_EVALUATION_CAPACITY",
    }


def test_read_only_zero_rules_rechecks_live_config_before_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #1254 review 3768708964: an empty rules read cannot race a new rule.
    import tree_sitter_analyzer.mcp.tools.constraint_check_tool as constraint_tool

    config = tmp_path / "architectural-constraints.yml"
    config.write_text("version: 1\nconstraints: []\n")
    real_load = constraint_tool.load_live_constraints

    def load_then_tighten(root: str, deadline: float):
        snapshot, rules = real_load(root, deadline)
        config.write_text(
            "version: 1\nconstraints:\n"
            "  - {id: r, severity: error, rule: forbid, from: 'a/**', "
            "to: 'b/**', reason: tightened}\n"
        )
        return snapshot, rules

    monkeypatch.setattr(constraint_tool, "load_live_constraints", load_then_tighten)
    result = _run(_make_tool(tmp_path).execute({"persist": False}))

    assert (result["success"], result["error_code"]) == (
        False,
        "CONSTRAINT_CONFIG_CHANGED",
    )


def test_read_only_nonempty_rules_rechecks_live_config_after_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #1254 review 3768708964: a completed graph read cannot publish stale rules.
    _stage_minimal_constraints(tmp_path)
    tool = _make_tool(tmp_path)

    def evaluate_then_tighten(*_args, **_kwargs):
        config = tmp_path / "architectural-constraints.yml"
        config.write_text(config.read_text() + "\n# tightened\n")
        return [], 0

    monkeypatch.setattr(tool, "_run_read_only", evaluate_then_tighten)
    result = _run(tool.execute({"persist": False, "output_format": "json"}))

    assert (result["success"], result["error_code"]) == (
        False,
        "CONSTRAINT_CONFIG_CHANGED",
    )


def test_frozen_scope_decodes_wire_path_before_index_coverage() -> None:
    # PR #1254 review 3769281313: extension/exclusion checks use raw Git paths.
    from tree_sitter_analyzer.git_path_codec import path_to_wire
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor
    from tree_sitter_analyzer.mcp.tools.constraint_check_frozen import (
        _supported_scope_is_covered,
    )

    raw_path = b"tests/golden/corpus_\xff.py".decode("utf-8", "surrogateescape")
    assert path_to_wire(raw_path).startswith("git-path-b64:")
    assert (
        _supported_scope_is_covered([raw_path], make_source_scope_descriptor()) is False
    )
