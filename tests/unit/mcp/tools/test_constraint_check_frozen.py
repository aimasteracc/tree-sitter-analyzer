"""Focused frozen/read-only exactness tests for constraint checking."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

import tree_sitter_analyzer.diff_snapshot_registry as snapshots
from tests.unit.mcp.tools._constraint_check_support import (
    create_frozen_scope as _create_frozen_scope,
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
    stage_minimal_constraints as _stage_minimal_constraints,
)
from tree_sitter_analyzer.constraints import Violation

pytest.importorskip("yaml")

# ---------------------------------------------------------------------------
# RFC-0022 P0.3 read-only frozen-snapshot contract
# ---------------------------------------------------------------------------


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


def test_config_only_frozen_change_evaluates_full_source_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #1254 review 3768452296: tightening rules governs existing source too.
    _stage_minimal_constraints(tmp_path)
    db_path = tmp_path / ".ast-cache" / "index.db"
    _init_violations_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE edges(kind TEXT)")
    registry, created = _create_frozen_scope(
        monkeypatch, tmp_path, ["architectural-constraints.yml"]
    )
    observed: list[object] = []

    def evaluator(_constraints, _conn, **kwargs):
        observed.append(kwargs.get("scope_predicate", "absent"))
        return []

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.constraint_check_tool.evaluate", evaluator
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

    assert result["verdict"] == "SAFE"
    assert created["assessed_scope_paths"] == ["architectural-constraints.yml"]
    assert observed == ["absent"]
    assert (
        registry.close_lease(created["diff_snapshot_id"], created["route_lease_id"])
        is True
    )


def test_frozen_constraint_consumer_fails_closed_on_unsafe_config_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #1254 review 3769193867: config failure belongs to this consumer.
    from tests.unit._diff_snapshot_support import install_fake_snapshot_materializer
    from tree_sitter_analyzer.source_oracle import SafePath

    install_fake_snapshot_materializer(monkeypatch, tmp_path)
    monkeypatch.setattr(
        snapshots,
        "safe_workspace_path",
        lambda *_args, **_kwargs: SafePath(None, (), "symlink"),
    )
    registry = snapshots.DiffSnapshotRegistry()
    monkeypatch.setattr(snapshots, "REGISTRY", registry)
    created = registry.create(str(tmp_path), "diff", [])

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

    assert created["success"] is True
    assert result["error_code"] == "CONSTRAINT_CONFIG_UNSAFE"


def test_renamed_primary_config_activates_fallback_over_full_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #1254 review 3772454791: renamed-away config changes precedence.
    _stage_minimal_constraints(tmp_path)
    fallback = tmp_path / ".tree-sitter-analyzer/constraints.yml"
    fallback.parent.mkdir()
    (tmp_path / "architectural-constraints.yml").replace(fallback)
    db_path = tmp_path / ".ast-cache/index.db"
    _init_violations_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE edges(kind TEXT)")
    registry, created = _create_frozen_scope(
        monkeypatch, tmp_path, ["architectural-constraints.yml", "renamed.yml"]
    )
    state = registry._states[str(created["diff_snapshot_id"])]
    state.snapshot = replace(state.snapshot, mode="staged")
    observed = []

    def evaluator(_constraints, _conn, **kwargs):
        observed.append(kwargs.get("scope_predicate", "absent"))
        return [
            Violation(
                "fallback-block",
                "src/a/x.py",
                "caller",
                7,
                "callee",
                "src/b/y.py",
                "error",
                1,
            )
        ]

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.constraint_check_tool.evaluate", evaluator
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

    assert (
        state.snapshot.constraint_config_path == ".tree-sitter-analyzer/constraints.yml"
    )
    actual = (
        result["verdict"],
        [row["rule_id"] for row in result["violations"]],
        observed,
        result["assessed_scope_paths"],
    )
    assert actual == (
        "UNSAFE",
        ["fallback-block"],
        ["absent"],
        ["architectural-constraints.yml", "renamed.yml"],
    )
    assert (
        registry.close_lease(created["diff_snapshot_id"], created["route_lease_id"])
        is True
    )


# Codex P1 (#1297): in explicit read_existing mode the graph-backed frozen
# route must require and acquire the caller-reserved index capability; a
# fresh lease would answer the rules against the wrong snapshot.  The
# platform gate keeps these portable (the module-level route is what the
# certified Linux axis exercises).
def _frozen_tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, paths):
    import tree_sitter_analyzer.mcp.tools.constraint_check_frozen as frozen

    _stage_minimal_constraints(tmp_path)
    db_path = tmp_path / ".ast-cache" / "index.db"
    _init_violations_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE edges(kind TEXT)")
    registry, created = _create_frozen_scope(monkeypatch, tmp_path, paths)
    return frozen, registry, created


def test_read_existing_frozen_constraints_require_reserved_index_capability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frozen, _, created = _frozen_tool(
        tmp_path, monkeypatch, ["architectural-constraints.yml"]
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.constraint_check_tool.read_access.read_existing_platform_supported",
        lambda: True,
    )
    tool = _make_tool(tmp_path)
    result = _run(
        tool.execute(
            {
                "persist": False,
                "diff_snapshot_id": created["diff_snapshot_id"],
                "scope_paths": created["assessed_scope_paths"],
                "access_mode": "read_existing",
                "output_format": "json",
            }
        )
    )
    assert result["success"] is False
    assert result["error_code"] == "CONSTRAINT_INDEX_CAPABILITY_REQUIRED"
    assert result["diff_snapshot_id"] == created["diff_snapshot_id"]


# Codex P1 (#1297): when the reserved index pair is supplied, the frozen
# route acquires exactly that capability rather than minting a fresh lease.
def test_read_existing_frozen_constraints_acquire_reserved_index_capability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frozen, registry, created = _frozen_tool(
        tmp_path, monkeypatch, ["architectural-constraints.yml"]
    )
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor

    reserved_scope = make_source_scope_descriptor()
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.constraint_check_tool.read_access.read_existing_platform_supported",
        lambda: True,
    )
    acquired: list[tuple[str, object]] = []

    class _Index:
        completeness = "complete"
        reason = None
        source_generation = created["source_generation"]
        source_scope = reserved_scope
        snapshot_id = "reserved-index"
        index_fingerprint = "sha256:" + "2" * 64

    class _Context:
        def __init__(self, index, conn):
            self._index = index
            self._conn = conn

        def __enter__(self):
            return self._index, self._conn

        def __exit__(self, *exc):
            self._conn.close()
            return False

    def acquire(snapshot_id, project_root, source_generation=None, **kwargs):
        acquired.append((snapshot_id, source_generation))
        conn = sqlite3.connect(tmp_path / ".ast-cache" / "index.db")
        return _Context(_Index(), conn)

    monkeypatch.setattr(
        "tree_sitter_analyzer.index_snapshot.acquire_index_snapshot", acquire
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.constraint_check_tool.evaluate",
        lambda *a, **k: [],
    )
    result = _run(
        _make_tool(tmp_path).execute(
            {
                "persist": False,
                "diff_snapshot_id": created["diff_snapshot_id"],
                "snapshot_id": "reserved-index",
                "source_generation": created["source_generation"],
                "scope_paths": created["assessed_scope_paths"],
                "access_mode": "read_existing",
                "output_format": "json",
            }
        )
    )
    assert acquired == [("reserved-index", created["source_generation"])]
    assert result["success"] is True
    assert result["snapshot_id"] == "reserved-index"
    assert (
        registry.close_lease(created["diff_snapshot_id"], created["route_lease_id"])
        is True
    )
