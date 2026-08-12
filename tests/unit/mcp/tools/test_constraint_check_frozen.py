"""Focused frozen/read-only exactness tests for constraint checking."""

from __future__ import annotations

import sqlite3
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
