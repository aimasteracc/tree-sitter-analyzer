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
from types import SimpleNamespace

import pytest

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


def test_explicit_access_rejects_unhashable_severity(tmp_path: Path) -> None:
    tool = _make_tool(tmp_path)

    with pytest.raises(ValueError, match=r"^severity_min must be one of"):
        tool.validate_arguments({"access_mode": "read_existing", "severity_min": []})


def test_explicit_access_requires_diff_snapshot(tmp_path: Path) -> None:
    tool = _make_tool(tmp_path)

    with pytest.raises(
        ValueError,
        match=r"^diff_snapshot_id is required for access_mode=read_existing$",
    ):
        tool.validate_arguments({"access_mode": "read_existing", "persist": False})


def test_explicit_access_defaults_unavailable_output_to_json(tmp_path: Path) -> None:
    tool = _make_tool(tmp_path)

    result = _run(
        tool.execute(
            {
                "access_mode": "read_existing",
                "persist": False,
                "diff_snapshot_id": "ds_test",
                "scope_paths": [],
            }
        )
    )

    assert result == {
        "success": True,
        "verdict": "WARN",
        "access_mode": "read_existing",
        "access_state": "unknown",
        "access_reason": "READ_EXISTING_AUTHORITY_UNCERTIFIED",
        "source_snapshots": [],
        # RFC-0022 P0.5: wire owner echo on the unavailable envelope.
        "action_version": "edit.constraints/v1",
        "output_format": "json",
    }


def test_execute_without_project_root_returns_setup_instruction() -> None:
    from tree_sitter_analyzer.mcp.tools.constraint_check_tool import (
        ConstraintCheckTool,
    )

    result = _run(ConstraintCheckTool(None).execute({}))

    assert result == {
        "success": False,
        "error": "Project root not set. Call set_project_path first.",
        # RFC-0022 P0.5: wire owner echo on the missing-root envelope.
        "action_version": "edit.constraints/v1",
    }


def test_execute_read_existing_fails_closed_without_project_root() -> None:
    # Codex P1 (#1257): with project_root unbound the SecurityValidator
    # receives base_path=None and skips its project-boundary layer, so an
    # arbitrary relative scope path validates. The route must fail closed
    # with the stable MISSING_PROJECT_ROOT error instead of classifying.
    from tree_sitter_analyzer.mcp.tools.constraint_check_tool import (
        ConstraintCheckTool,
    )

    with pytest.raises(ValueError) as exc_info:
        _run(
            ConstraintCheckTool(None).execute(
                {
                    "access_mode": "read_existing",
                    "diff_snapshot_id": "ds_test",
                    "scope_paths": ["src/a.py"],
                    "persist": False,
                    "output_format": "json",
                }
            )
        )

    assert str(exc_info.value) == (
        "MISSING_PROJECT_ROOT: project_root must be bound before "
        "read_existing path validation"
    )


def test_persistent_unexpected_runtime_error_is_not_misclassified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage_minimal_constraints(tmp_path)
    db = tmp_path / ".ast-cache" / "index.db"
    db.parent.mkdir()
    db.touch()
    tool = _make_tool(tmp_path)
    monkeypatch.setattr(
        tool,
        "_run_and_persist",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("unexpected")),
    )
    with pytest.raises(RuntimeError, match="^unexpected$"):
        _run(tool.execute({}))


def test_read_only_reuses_one_absolute_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #1254 review 3772454771: config, graph, and publish share one budget.
    import tree_sitter_analyzer.mcp.tools.constraint_check_tool as owner

    observed: list[float] = []
    snapshot = ("architectural-constraints.yml", b"rules", ())
    monkeypatch.setattr(owner, "time", SimpleNamespace(monotonic=lambda: 1.0))
    monkeypatch.setattr(
        owner,
        "load_live_constraints",
        lambda _root, deadline: (observed.append(deadline) or snapshot, [object()]),
    )
    monkeypatch.setattr(
        owner,
        "_live_config_snapshot",
        lambda _root, deadline: observed.append(deadline) or snapshot,
    )
    tool = _make_tool(tmp_path)
    monkeypatch.setattr(
        tool,
        "_run_read_only",
        lambda *_args, deadline, **_kwargs: (observed.append(deadline) or [], 0),
    )

    result = _run(tool.execute({"persist": False, "output_format": "json"}))

    assert (result["success"], result["verdict"]) == (True, "SAFE")
    assert observed == [11.0, 11.0, 11.0]
