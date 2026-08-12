"""Focused frozen/read-only exactness tests for constraint checking."""

from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from tests.unit.mcp.tools._constraint_check_support import (
    create_frozen_scope as _create_frozen_scope,
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


def test_read_only_deadline_interrupts_response_materialization(tmp_path, monkeypatch):
    # Final zero gate: Python row assembly belongs to the same absolute deadline.
    from tree_sitter_analyzer.constraints.schema import Violation

    calls = {"count": 0}

    def clock():
        calls["count"] += 1
        return 1.0 if calls["count"] < 3 else 3.0

    monkeypatch.setattr(time, "monotonic", clock)
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE edges (kind TEXT)")
    conn.execute("INSERT INTO edges VALUES ('calls')")
    row = Violation("r", "a.py", "a", 1, "b", "b.py", "warn", 0)
    with pytest.raises(RuntimeError, match="INDEX_SNAPSHOT_DEADLINE"):
        _make_tool(tmp_path)._evaluate_connection(
            conn,
            [object()],
            path_filter="",
            min_severity_rank=0,
            evaluator=lambda *_args, **_kwargs: [row],
            deadline=2.0,
        )
    conn.close()


def test_evaluate_connection_rejects_deadline_after_response_sort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tree_sitter_analyzer.constraints.schema import Violation

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE edges (kind TEXT)")
    conn.execute("INSERT INTO edges VALUES ('calls')")
    conn.commit()
    calls = 0

    def clock() -> float:
        nonlocal calls
        calls += 1
        return 0.0 if calls < 4 else 2.0

    monkeypatch.setattr(time, "monotonic", clock)
    violation = Violation("r", "a.py", "a", 1, "b", "b.py", "warn", 0)
    try:
        with pytest.raises(RuntimeError, match="^INDEX_SNAPSHOT_DEADLINE$"):
            _make_tool(tmp_path)._evaluate_connection(
                conn,
                [object()],
                min_severity_rank=0,
                evaluator=lambda *_args, **_kwargs: [violation],
                deadline=1.0,
            )
    finally:
        conn.close()

    assert calls == 4


def test_staged_zero_rules_final_guard_does_not_probe_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #1254 review 3767273230: staged zero-rule evaluation owns index bytes only.
    from dataclasses import replace

    from tree_sitter_analyzer.mcp.tools import constraint_check_frozen

    (tmp_path / "architectural-constraints.yml").write_text(
        "version: 1\nconstraints: []\n"
    )
    registry, created = _create_frozen_scope(monkeypatch, tmp_path, ["src/a.py"])
    state = registry._states[str(created["diff_snapshot_id"])]
    state.snapshot = replace(state.snapshot, mode="staged")
    monkeypatch.setattr(
        constraint_check_frozen.source_oracle,
        "safe_workspace_path",
        lambda *a, **k: pytest.fail("staged zero-rule guard probed worktree"),
    )

    result = _run(_make_tool(tmp_path).execute(_frozen_arguments(created)))

    assert (result["success"], result["rule_count"], result["verdict"]) == (
        True,
        0,
        "SAFE",
    )


def test_frozen_directory_scope_matches_descendants_not_sibling_prefix(
    tmp_path: Path,
) -> None:
    # PR #1254 review 3767373475: frozen directory scope uses path-component prefix.
    from tree_sitter_analyzer.constraints import Violation

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE edges(kind TEXT)")
    candidates = [
        Violation("child", "src/pkg/a.py", "a", 1, "b", "out.py", "warn", 1),
        Violation("sibling", "src/package/a.py", "a", 2, "b", "out.py", "warn", 1),
    ]
    try:
        rows, _ = _make_tool(tmp_path)._evaluate_connection(
            conn,
            [object()],
            min_severity_rank=1,
            scope_paths=frozenset({"src/pkg"}),
            evaluator=lambda _rules, _conn, **_kwargs: candidates,
        )
    finally:
        conn.close()

    assert [row["rule_id"] for row in rows] == ["child"]


def test_ordinary_read_only_rejects_custom_excluded_source_scope() -> None:
    # PR #1254 review 3767507293: ordinary checks require whole-project authority.
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor
    from tree_sitter_analyzer.mcp.tools.constraint_index_snapshot import (
        ordinary_source_scope_is_full,
    )

    assert (
        ordinary_source_scope_is_full(make_source_scope_descriptor()),
        ordinary_source_scope_is_full(
            make_source_scope_descriptor(exclude_patterns=("legacy/**",))
        ),
        ordinary_source_scope_is_full(make_source_scope_descriptor(roots=("src",))),
    ) == (True, False, False)


def test_malformed_path_scalar_is_structured_index_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #1254 review 3767568278: path scalar failures cannot escape MCP.
    _stage_minimal_constraints(tmp_path)
    monkeypatch.setattr(
        _make_tool(tmp_path),
        "_run_read_only",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AttributeError("caller_file must be text")
        ),
    )
    tool = _make_tool(tmp_path)
    monkeypatch.setattr(
        tool,
        "_run_read_only",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AttributeError("caller_file must be text")
        ),
    )

    result = _run(tool.execute({"persist": False, "output_format": "json"}))

    assert (result["success"], result["verdict"], result["error_code"]) == (
        False,
        "ERROR",
        "CONSTRAINT_INDEX_UNKNOWN",
    )
    assert result["error"] == "caller_file must be text"


def test_portable_snapshot_rejects_symlinked_database(
    tmp_path: Path,
) -> None:
    # PR #1254 review 3767273223: pathname fallback must never follow links.
    from tree_sitter_analyzer.mcp.tools.constraint_index_snapshot import (
        portable_ordinary_snapshot,
    )

    cache = tmp_path / ".ast-cache"
    cache.mkdir()
    real = tmp_path / "real.db"
    sqlite3.connect(real).close()
    (cache / "index.db").symlink_to(real)

    with pytest.raises(ValueError, match="^INDEX_PATH_SYMLINK$"):
        with portable_ordinary_snapshot(str(tmp_path), deadline=time.monotonic() + 1.0):
            pytest.fail("symlink snapshot published")


def test_portable_snapshot_rejects_nonempty_writer_sidecar(
    tmp_path: Path,
) -> None:
    # PR #1254 review 3767273223: WAL bytes make a pathname copy ambiguous.
    from tree_sitter_analyzer.mcp.tools.constraint_index_snapshot import (
        portable_ordinary_snapshot,
    )

    cache = tmp_path / ".ast-cache"
    cache.mkdir()
    sqlite3.connect(cache / "index.db").close()
    (cache / "index.db-wal").write_bytes(b"writer")

    with pytest.raises(ValueError, match="^CONCURRENT_WRITER$"):
        with portable_ordinary_snapshot(str(tmp_path), deadline=time.monotonic() + 1.0):
            pytest.fail("sidecar snapshot published")


def test_tool_schema_reexport_preserves_public_api(tmp_path: Path) -> None:
    from tree_sitter_analyzer.mcp.tools.constraint_check_schema import (
        TOOL_SCHEMA as extracted_schema,
    )
    from tree_sitter_analyzer.mcp.tools.constraint_check_tool import TOOL_SCHEMA

    assert (
        _make_tool(tmp_path).get_tool_schema() is TOOL_SCHEMA,
        TOOL_SCHEMA is extracted_schema,
    ) == (True, True)


def test_constraint_arguments_reject_snapshot_with_default_persistence(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="^diff_snapshot_id requires persist=false$"):
        _make_tool(tmp_path).validate_arguments(
            {"diff_snapshot_id": "ds_snapshot", "scope_paths": []}
        )


def test_evaluate_connection_passes_supported_evaluator_controls(
    tmp_path: Path,
) -> None:
    from tree_sitter_analyzer.mcp.tools.constraint_check_tool import (
        _MAX_MATERIALIZED_VIOLATIONS,
    )

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE edges(kind TEXT)")
    conn.commit()
    received: dict[str, object] = {}

    def controlled_evaluator(
        _constraints,
        _conn,
        *,
        check_callback,
        capacity,
    ):
        received.update(check_callback=check_callback, capacity=capacity)
        return []

    try:
        rows, edge_count = _make_tool(tmp_path)._evaluate_connection(
            conn,
            [object()],
            min_severity_rank=0,
            evaluator=controlled_evaluator,
        )
    finally:
        conn.close()

    assert rows == []
    assert edge_count == 0
    assert callable(received["check_callback"])
    assert received["capacity"] == _MAX_MATERIALIZED_VIOLATIONS


def test_evaluate_connection_supports_legacy_evaluator_signature(
    tmp_path: Path,
) -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE edges(kind TEXT)")
    conn.commit()
    calls: list[tuple[object, sqlite3.Connection]] = []

    def legacy_evaluator(constraints, connection):
        calls.append((constraints, connection))
        return []

    rules = [object()]
    try:
        rows, edge_count = _make_tool(tmp_path)._evaluate_connection(
            conn,
            rules,
            min_severity_rank=0,
            evaluator=legacy_evaluator,
        )
        assert calls == [(rules, conn)]
    finally:
        conn.close()

    assert rows == []
    assert edge_count == 0


def test_evaluate_connection_bounds_custom_evaluator_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tree_sitter_analyzer.constraints.schema import Violation
    from tree_sitter_analyzer.mcp.tools import constraint_check_tool

    monkeypatch.setattr(constraint_check_tool, "_MAX_MATERIALIZED_VIOLATIONS", 1)
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE edges(kind TEXT)")
    conn.commit()
    violations = [
        Violation("r1", "a.py", "a", 1, "b", "b.py", "warn", 0),
        Violation("r2", "c.py", "c", 2, "d", "d.py", "warn", 0),
    ]

    try:
        with pytest.raises(RuntimeError, match="^CONSTRAINT_EVALUATION_CAPACITY$"):
            _make_tool(tmp_path)._evaluate_connection(
                conn,
                [object()],
                min_severity_rank=0,
                evaluator=lambda _constraints, _conn: violations,
            )
    finally:
        conn.close()


def test_root_directory_scope_contains_all_relative_paths():
    from tree_sitter_analyzer.mcp.tools.constraint_check_tool import _path_is_in_scope

    assert _path_is_in_scope("src/a.py", frozenset({"."})) is True
    assert _path_is_in_scope("src/a.py", frozenset({""})) is True


def test_portable_snapshot_rejects_pathname_swap_before_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #1254 P1: an opened fd must match the exact pre-open lstat identity.
    import os

    import tree_sitter_analyzer.mcp.tools.constraint_index_snapshot as owner

    cache = tmp_path / ".ast-cache"
    cache.mkdir()
    database = cache / "index.db"
    replacement = cache / "replacement.db"
    sqlite3.connect(database).close()
    sqlite3.connect(replacement).close()
    real_open = owner._open
    swapped = False

    def swap_then_open(path, flags):
        nonlocal swapped
        if not swapped and Path(path) == database:
            swapped = True
            os.replace(replacement, database)
        return real_open(path, flags)

    monkeypatch.setattr(owner, "_open", swap_then_open)

    with pytest.raises(ValueError, match="^CONCURRENT_WRITER$"):
        with owner.portable_ordinary_snapshot(
            str(tmp_path), deadline=time.monotonic() + 1.0
        ):
            pytest.fail("mismatched opened descriptor published")


@pytest.mark.parametrize("failure", [FileNotFoundError, OSError])
def test_portable_missing_cache_is_structured_index_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: type[OSError],
) -> None:
    # Windows CI incident 2026-07-01: portable acquisition may see a missing cache.
    import tree_sitter_analyzer.mcp.tools.constraint_index_snapshot as owner

    _stage_minimal_constraints(tmp_path)
    monkeypatch.setattr(owner, "portable_snapshot_required", lambda: True)
    monkeypatch.setattr(
        owner,
        "_identity",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            failure("portable cache unavailable")
        ),
    )

    result = _run(
        _make_tool(tmp_path).execute({"persist": False, "output_format": "json"})
    )

    assert result == {
        "success": False,
        "verdict": "ERROR",
        "error_code": "CONSTRAINT_INDEX_UNKNOWN",
        "error": "portable cache unavailable",
    }


def test_portable_corrupt_copy_closes_connections_before_temporary_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Windows CI incident 2026-07-01: open SQLite handles block temp unlink.
    import tree_sitter_analyzer.mcp.tools.constraint_index_snapshot as owner

    cache = tmp_path / ".ast-cache"
    cache.mkdir()
    database = cache / "index.db"
    sqlite3.connect(database).close()
    events: list[str] = []

    class Source:
        def execute(self, _sql):
            return self

        def fetchone(self):
            return (4096,)

        def backup(self, *_args, **_kwargs):
            raise sqlite3.DatabaseError("corrupt private copy")

        def close(self):
            events.append("source.close")

    class Private:
        def execute(self, _sql):
            return self

        def fetchone(self):
            return (2,)

        def close(self):
            events.append("private.close")

    connections = iter((Source(), Private()))

    @contextmanager
    def locked_temporary_copy(_data, _root):
        try:
            yield tmp_path / "private-index.db"
        finally:
            events.append("temporary.exit")
            if events[:2] != ["source.close", "private.close"]:
                raise PermissionError("temporary copy is still locked")

    monkeypatch.setattr(owner, "_temporary_copy", locked_temporary_copy)
    monkeypatch.setattr(
        owner.sqlite3, "connect", lambda *_args, **_kwargs: next(connections)
    )
    monkeypatch.setattr(owner, "require_memory_temp_store", lambda _conn: None)

    with pytest.raises(sqlite3.DatabaseError, match="^corrupt private copy$"):
        with owner.portable_ordinary_snapshot(
            str(tmp_path), deadline=time.monotonic() + 1.0
        ):
            pytest.fail("corrupt snapshot published")

    assert events == ["source.close", "private.close", "temporary.exit"]
