"""Tests for tree_sitter_analyzer.cli.commands.constraint_check_command."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tree_sitter_analyzer.cli.commands.constraint_check_command import (
    _evaluate_with_explicit_file,
    _load_explicit,
    _run_and_persist,
    _run_tool,
    _violations_ddl,
    get_default_project_root,
)

# Module-level patch targets
_APPLY_TOON = (
    "tree_sitter_analyzer.mcp.utils.format_helper.apply_toon_format_to_response"
)
_RESOLVE_FMT = "tree_sitter_analyzer.cli.output_format.resolve_mcp_tool_format"
_LOAD_CONSTRAINTS = (
    "tree_sitter_analyzer.cli.commands.constraint_check_command.load_constraints"
)
_EVALUATE = "tree_sitter_analyzer.cli.commands.constraint_check_command.evaluate"
_LOAD_EXPLICIT = (
    "tree_sitter_analyzer.cli.commands.constraint_check_command._load_explicit"
)
_RUN_AND_PERSIST = (
    "tree_sitter_analyzer.cli.commands.constraint_check_command._run_and_persist"
)
_EVAL_EXPLICIT = (
    "tree_sitter_analyzer.cli.commands.constraint_check_command"
    "._evaluate_with_explicit_file"
)
_ASYNCIO_RUN = "tree_sitter_analyzer.cli.commands.constraint_check_command.asyncio.run"
_PRINT_RESULT = (
    "tree_sitter_analyzer.cli.commands.constraint_check_command._print_result"
)
_RESOLVE_OFMT = (
    "tree_sitter_analyzer.cli.commands.constraint_check_command._resolve_output_format"
)
_CCT_CLS = (
    "tree_sitter_analyzer.cli.commands.constraint_check_command.ConstraintCheckTool"
)


def _v(
    severity: str = "error",
    rule_id: str = "R1",
    caller_file: str = "a.py",
    caller_name: str = "foo",
    caller_line: int = 10,
    callee_name: str = "bar",
    callee_file: str = "b.py",
    detected_at: int | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        severity=severity,
        rule_id=rule_id,
        caller_file=caller_file,
        caller_name=caller_name,
        caller_line=caller_line,
        callee_name=callee_name,
        callee_file=callee_file,
        detected_at=detected_at,
    )


# ---------------------------------------------------------------------------
# Violation stub
# ---------------------------------------------------------------------------


class TestGetDefaultProjectRoot:
    def test_returns_project_root_attr(self):
        args = SimpleNamespace(project_root="/srv/proj")
        assert get_default_project_root(args) == "/srv/proj"

    def test_falls_back_to_cwd_when_none(self):
        args = SimpleNamespace(project_root=None)
        assert get_default_project_root(args)  # truthy

    def test_falls_back_to_cwd_when_attr_missing(self):
        assert get_default_project_root(SimpleNamespace())  # truthy


# ---------------------------------------------------------------------------
# _load_explicit
# ---------------------------------------------------------------------------


class TestLoadExplicit:
    def test_canonical_name_calls_load_constraints_on_parent(self, tmp_path):
        yaml_file = tmp_path / "architectural-constraints.yml"
        yaml_file.write_text("rules: []")
        with patch(_LOAD_CONSTRAINTS, return_value=[]) as mock_load:
            result = _load_explicit(yaml_file)
        mock_load.assert_called_once_with(str(tmp_path))
        assert result == []

    def test_non_canonical_name_stages_into_tempdir(self, tmp_path):
        yaml_file = tmp_path / "my-constraints.yml"
        yaml_file.write_text("rules: []")
        staged_roots: list[str] = []

        def capture(root: str) -> list:
            staged_roots.append(root)
            return ["rule1"]

        with patch(_LOAD_CONSTRAINTS, side_effect=capture):
            result = _load_explicit(yaml_file)

        assert staged_roots[0] != str(tmp_path)  # was staged, not the original dir
        assert result == ["rule1"]

    def test_non_canonical_creates_canonical_filename_in_tempdir(self, tmp_path):
        yaml_file = tmp_path / "custom.yml"
        yaml_file.write_text("rules: []")

        def capture_and_check(root: str) -> list:
            staged = Path(root) / "architectural-constraints.yml"
            assert staged.exists(), "canonical filename not staged"
            return []

        with patch(_LOAD_CONSTRAINTS, side_effect=capture_and_check):
            _load_explicit(yaml_file)

    def test_non_canonical_content_is_copied(self, tmp_path):
        yaml_file = tmp_path / "other.yml"
        content = "rules:\n  - id: R99\n"
        yaml_file.write_text(content)
        file_contents: list[str] = []

        def capture(root: str) -> list:
            staged = Path(root) / "architectural-constraints.yml"
            file_contents.append(staged.read_text())
            return []

        with patch(_LOAD_CONSTRAINTS, side_effect=capture):
            _load_explicit(yaml_file)

        assert file_contents[0] == content


# ---------------------------------------------------------------------------
# _run_and_persist
# ---------------------------------------------------------------------------


class TestRunAndPersist:
    def _empty_db(self, tmp_path: Path) -> Path:
        db = tmp_path / "index.db"
        sqlite3.connect(str(db)).close()
        return db

    def _db_with_edges(self, tmp_path: Path) -> Path:
        from tree_sitter_analyzer.graph.edge_store import EDGE_STORE_SCHEMA

        db = tmp_path / "index.db"
        conn = sqlite3.connect(str(db))
        # B1.3: the edge-count gate counts CALLS rows in the unified ``edges``
        # table (ast_call_edges was dropped).
        conn.executescript(EDGE_STORE_SCHEMA)
        conn.execute(
            "INSERT INTO edges (source_node_id, target_node_id, kind) "
            "VALUES ('a.py:f:1', 'b.py:g:1', 'calls')"
        )
        conn.commit()
        conn.close()
        return db

    def test_no_call_edges_table_returns_empty(self, tmp_path):
        db = self._empty_db(tmp_path)
        violations, edge_count = _run_and_persist(db, [])
        assert violations == []
        assert edge_count == 0

    @pytest.mark.slow_ok  # Windows xdist-load budget exemption; test logic is trivial, no perf claim (#976)
    def test_empty_call_edges_table_returns_empty(self, tmp_path):
        db = tmp_path / "index.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE ast_call_edges (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()
        violations, edge_count = _run_and_persist(db, [])
        assert violations == []
        assert edge_count == 0

    def test_evaluate_exception_degrades_gracefully(self, tmp_path):
        db = self._db_with_edges(tmp_path)
        with patch(_EVALUATE, side_effect=RuntimeError("boom")):
            violations, edge_count = _run_and_persist(db, [])
        assert violations == []
        assert edge_count == 1

    def test_violations_persisted_to_db(self, tmp_path):
        db = self._db_with_edges(tmp_path)
        v = _v(detected_at=12345)
        with patch(_EVALUATE, return_value=[v]):
            violations, _ = _run_and_persist(db, ["c"])
        assert len(violations) == 1
        conn = sqlite3.connect(str(db))
        rows = conn.execute("SELECT rule_id FROM ast_constraint_violations").fetchall()
        conn.close()
        assert rows == [("R1",)]

    def test_returns_edge_count_from_db(self, tmp_path):
        db = self._db_with_edges(tmp_path)
        with patch(_EVALUATE, return_value=[]):
            _, edge_count = _run_and_persist(db, [])
        assert edge_count == 1

    def test_read_only_evaluation_returns_rows_without_creating_cache_table(
        self, tmp_path
    ):
        db = self._db_with_edges(tmp_path)
        violation = _v()

        with patch(_EVALUATE, return_value=[violation]):
            result = _run_and_persist(db, ["c"], persist=False)

        conn = sqlite3.connect(str(db))
        tables = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name = 'ast_constraint_violations'"
        ).fetchall()
        conn.close()
        assert result == ([violation], 1)
        assert tables == []

    def test_read_only_missing_edges_table_reraises_operational_error(self, tmp_path):
        db = self._empty_db(tmp_path)

        with pytest.raises(sqlite3.OperationalError, match="no such table: edges"):
            _run_and_persist(db, [], persist=False)

    def test_read_only_evaluator_exception_is_not_degraded(self, tmp_path):
        db = self._db_with_edges(tmp_path)

        with patch(_EVALUATE, side_effect=RuntimeError("evaluation failed")):
            with pytest.raises(RuntimeError, match="^evaluation failed$"):
                _run_and_persist(db, [], persist=False)

    def test_violations_table_cleared_before_insert(self, tmp_path):
        db = self._db_with_edges(tmp_path)
        # Pre-populate violations table with a stale row
        conn = sqlite3.connect(str(db))
        conn.execute(_violations_ddl())
        conn.execute(
            """INSERT INTO ast_constraint_violations
               VALUES ('OLD', 'f.py', 'fn', 1, 'bar', 'g.py', 'warn', 0)"""
        )
        conn.commit()
        conn.close()

        new_v = _v(rule_id="NEW", detected_at=1)
        with patch(_EVALUATE, return_value=[new_v]):
            _run_and_persist(db, ["c"])

        conn = sqlite3.connect(str(db))
        rows = conn.execute("SELECT rule_id FROM ast_constraint_violations").fetchall()
        conn.close()
        # OLD row must be gone; only NEW should be present
        rule_ids = [r[0] for r in rows]
        assert "OLD" not in rule_ids
        assert "NEW" in rule_ids

    def test_duplicate_pk_violations_do_not_crash_persist(self, tmp_path):
        """Regression for #544: two violations with the same PK must not crash.

        If ``evaluate()`` returns two ``Violation`` objects that share the
        same ``(rule_id, caller_file, caller_line, callee_name)`` PRIMARY
        KEY (e.g., one call site resolved to two ``callee_file`` targets),
        the old ``executemany`` would raise
        ``UNIQUE constraint failed: ast_constraint_violations.rule_id, ...``.

        After the fix the persist path must succeed and write exactly 1 row
        (the dedup is in ``evaluate()``, so ``_run_and_persist`` receives a
        clean list — this test verifies the full stack from mock to DB).
        """
        db = self._db_with_edges(tmp_path)
        # Two violations with identical PK but different callee_file.
        dup_v1 = _v(
            rule_id="R1",
            caller_file="a.py",
            caller_line=10,
            callee_name="bar",
            callee_file="b.py",
            detected_at=1,
        )
        dup_v2 = _v(
            rule_id="R1",
            caller_file="a.py",
            caller_line=10,
            callee_name="bar",
            callee_file="c.py",
            detected_at=1,
        )

        # We intentionally bypass the real evaluate() and inject the two
        # duplicates directly to test the persist layer in isolation.
        with patch(_EVALUATE, return_value=[dup_v1, dup_v2]):
            # Must NOT raise sqlite3.IntegrityError.
            violations, edge_count = _run_and_persist(db, ["c"])

        conn = sqlite3.connect(str(db))
        rows = conn.execute(
            "SELECT rule_id, caller_file, caller_line, callee_name "
            "FROM ast_constraint_violations"
        ).fetchall()
        conn.close()
        # Exactly 1 row persisted (PK is unique); the constraint did not crash.
        assert len(rows) == 1, (
            f"Expected exactly 1 persisted row after dedup, got {len(rows)}: {rows}"
        )
        assert rows[0] == ("R1", "a.py", 10, "bar")


# ---------------------------------------------------------------------------
# _run_tool
# ---------------------------------------------------------------------------


class TestRunTool:
    def test_builds_tool_and_returns_execute_coroutine(self, tmp_path):
        import asyncio

        mock_tool = MagicMock()
        mock_tool.execute = AsyncMock(return_value={"success": True})

        with patch(_CCT_CLS, return_value=mock_tool):
            result = asyncio.run(_run_tool(str(tmp_path), "warn", "", "json"))

        assert result == {"success": True}
        mock_tool.execute.assert_called_once_with(
            {"path_filter": "", "severity_min": "warn", "output_format": "json"}
        )

    def test_passes_path_filter_and_severity(self, tmp_path):
        import asyncio

        mock_tool = MagicMock()
        mock_tool.execute = AsyncMock(return_value={"success": False})

        with patch(_CCT_CLS, return_value=mock_tool):
            asyncio.run(_run_tool(str(tmp_path), "error", "src/*", "toon"))

        called_payload = mock_tool.execute.call_args[0][0]
        assert called_payload["severity_min"] == "error"
        assert called_payload["path_filter"] == "src/*"
        assert called_payload["output_format"] == "toon"

    def test_read_only_omits_persistence_from_tool_execution(self, tmp_path):
        import asyncio

        mock_tool = MagicMock()
        mock_tool.execute = AsyncMock(return_value={"success": True})

        with patch(_CCT_CLS, return_value=mock_tool):
            asyncio.run(_run_tool(str(tmp_path), "warn", "", "json", persist=False))

        mock_tool.execute.assert_awaited_once_with(
            {
                "path_filter": "",
                "severity_min": "warn",
                "output_format": "json",
                "persist": False,
            }
        )


def _unexpected_evaluator(*_args):
    raise ValueError("bad evaluator")


def test_persistence_swallows_unexpected_evaluator_errors(tmp_path: Path) -> None:
    from tree_sitter_analyzer.cli.commands.constraint_check_persistence import (
        run_and_persist,
    )

    db = TestRunAndPersist()._db_with_edges(tmp_path)
    assert run_and_persist(
        db,
        [],
        persist=True,
        evaluator=_unexpected_evaluator,
        violations_ddl=_violations_ddl,
    ) == ([], 1)


def test_read_only_propagates_unexpected_evaluator_errors(tmp_path: Path) -> None:
    from tree_sitter_analyzer.cli.commands.constraint_check_persistence import (
        run_and_persist,
    )

    db = TestRunAndPersist()._db_with_edges(tmp_path)
    with pytest.raises(ValueError, match="^bad evaluator$"):
        run_and_persist(
            db,
            [],
            persist=False,
            evaluator=_unexpected_evaluator,
            violations_ddl=_violations_ddl,
        )


def test_explicit_persist_capacity_failure_is_structured(
    tmp_path: Path,
) -> None:
    # PR #1254 review 3768096795: explicit-file persistence must fail closed.
    config = tmp_path / "candidate.yml"
    config.write_text(
        """version: 1
constraints:
  - id: no-cli-to-mcp
    severity: error
    rule: forbid
    from: cli/**
    to: mcp/**
    reason: boundary
"""
    )
    db_path = tmp_path / ".ast-cache" / "index.db"
    db_path.parent.mkdir()
    db_path.touch()

    with patch(
        "tree_sitter_analyzer.cli.commands.constraint_check_command._run_and_persist",
        side_effect=RuntimeError("CONSTRAINT_EVALUATION_CAPACITY"),
    ):
        result = _evaluate_with_explicit_file(
            project_root=str(tmp_path),
            constraint_file=str(config),
            severity_min="warn",
            path_filter="",
            output_format="json",
            persist=True,
        )

    assert result == {
        "success": False,
        "verdict": "ERROR",
        "error_code": "CONSTRAINT_EVALUATION_CAPACITY",
        "error": "CONSTRAINT_EVALUATION_CAPACITY",
        "violations": [],
        "rule_count": 1,
    }
