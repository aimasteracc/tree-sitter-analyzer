"""Tests for tree_sitter_analyzer.cli.commands.constraint_check_command."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from tree_sitter_analyzer.cli.commands.constraint_check_command import (
    _compute_verdict,
    _evaluate_with_explicit_file,
    _exit_code_for,
    _failure_envelope,
    _filter_violations,
    _format_response,
    _load_explicit,
    _print_result,
    _resolve_output_format,
    _run_and_persist,
    _run_tool,
    _violations_ddl,
    get_default_project_root,
    run_check_constraints,
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


# ---------------------------------------------------------------------------
# Violation stub
# ---------------------------------------------------------------------------


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
# _exit_code_for
# ---------------------------------------------------------------------------


class TestExitCodeFor:
    def test_success_false_returns_1(self):
        assert _exit_code_for({"success": False}) == 1

    def test_missing_success_returns_1(self):
        assert _exit_code_for({}) == 1

    def test_unsafe_verdict_returns_1(self):
        assert _exit_code_for({"success": True, "verdict": "UNSAFE"}) == 1

    def test_caution_verdict_returns_2(self):
        assert _exit_code_for({"success": True, "verdict": "CAUTION"}) == 2

    def test_safe_verdict_returns_0(self):
        assert _exit_code_for({"success": True, "verdict": "SAFE"}) == 0

    def test_missing_verdict_defaults_to_safe_returns_0(self):
        # Default verdict is "SAFE" when key is absent
        assert _exit_code_for({"success": True}) == 0


# ---------------------------------------------------------------------------
# _compute_verdict
# ---------------------------------------------------------------------------


class TestComputeVerdict:
    def test_empty_rows_returns_safe(self):
        assert _compute_verdict([]) == "SAFE"

    def test_error_severity_returns_unsafe(self):
        assert _compute_verdict([{"severity": "error"}]) == "UNSAFE"

    def test_warn_severity_returns_caution(self):
        assert _compute_verdict([{"severity": "warn"}]) == "CAUTION"

    def test_info_severity_returns_safe(self):
        assert _compute_verdict([{"severity": "info"}]) == "SAFE"

    def test_error_takes_priority_over_warn(self):
        rows = [{"severity": "warn"}, {"severity": "error"}]
        assert _compute_verdict(rows) == "UNSAFE"

    def test_multiple_warns_no_error_returns_caution(self):
        rows = [{"severity": "warn"}, {"severity": "warn"}]
        assert _compute_verdict(rows) == "CAUTION"


# ---------------------------------------------------------------------------
# _filter_violations
# ---------------------------------------------------------------------------


class TestFilterViolations:
    def test_no_path_filter_passes_all_at_or_above_severity(self):
        violations = [_v(severity="error"), _v(severity="warn")]
        rows = _filter_violations(violations, path_filter="", min_severity_rank=1)
        assert len(rows) == 2

    def test_severity_floor_excludes_lower_ranked(self):
        # rank: info=0, warn=1, error=2; min_severity_rank=2 → only "error"
        violations = [
            _v(severity="error"),
            _v(severity="warn"),
            _v(severity="info"),
        ]
        rows = _filter_violations(violations, path_filter="", min_severity_rank=2)
        assert len(rows) == 1
        assert rows[0]["severity"] == "error"

    def test_empty_path_filter_skips_glob(self):
        violations = [_v(caller_file="anything.py")]
        rows = _filter_violations(violations, path_filter="", min_severity_rank=0)
        assert len(rows) == 1

    def test_returned_rows_are_dicts(self):
        rows = _filter_violations([_v()], path_filter="", min_severity_rank=0)
        assert isinstance(rows[0], dict)

    def test_row_contains_all_expected_keys(self):
        v = _v(
            severity="error",
            rule_id="R42",
            caller_file="x.py",
            caller_name="fn",
            caller_line=5,
            callee_name="baz",
            callee_file="y.py",
            detected_at=999,
        )
        rows = _filter_violations([v], path_filter="", min_severity_rank=0)
        assert rows[0] == {
            "rule_id": "R42",
            "caller_file": "x.py",
            "caller_name": "fn",
            "caller_line": 5,
            "callee_name": "baz",
            "callee_file": "y.py",
            "severity": "error",
            "detected_at": 999,
        }

    def test_unknown_severity_rank_treated_as_zero(self):
        violations = [_v(severity="unknown_level")]
        rows = _filter_violations(violations, path_filter="", min_severity_rank=0)
        assert len(rows) == 1

    def test_min_severity_rank_zero_passes_everything(self):
        violations = [_v(severity="info"), _v(severity="warn"), _v(severity="error")]
        rows = _filter_violations(violations, path_filter="", min_severity_rank=0)
        assert len(rows) == 3


# ---------------------------------------------------------------------------
# _violations_ddl
# ---------------------------------------------------------------------------


class TestViolationsDDL:
    def test_returns_string(self):
        assert isinstance(_violations_ddl(), str)

    def test_contains_table_name(self):
        assert "ast_constraint_violations" in _violations_ddl()

    def test_is_valid_sqlite(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(_violations_ddl())  # must not raise
        conn.close()

    def test_is_idempotent_if_not_exists(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(_violations_ddl())
        conn.execute(_violations_ddl())  # second call must not raise
        conn.close()


# ---------------------------------------------------------------------------
# _format_response
# ---------------------------------------------------------------------------


class TestFormatResponse:
    def test_returns_value_from_apply_toon(self):
        payload = {"success": True, "verdict": "SAFE"}
        sentinel = {"toon_content": "ok", "success": True}
        with patch(_APPLY_TOON, return_value=sentinel):
            result = _format_response(payload, "toon")
        assert result is sentinel

    def test_passes_payload_and_format_to_helper(self):
        payload = {"success": True}
        captured: list = []

        def capture(p, fmt):
            captured.append((p, fmt))
            return p

        with patch(_APPLY_TOON, side_effect=capture):
            _format_response(payload, "json")
        assert captured[0][0] is payload
        assert captured[0][1] == "json"


# ---------------------------------------------------------------------------
# _failure_envelope
# ---------------------------------------------------------------------------


class TestFailureEnvelope:
    def test_success_is_false(self):
        with patch(_APPLY_TOON, side_effect=lambda p, fmt: p):
            result = _failure_envelope("oops", "json")
        assert result["success"] is False

    def test_verdict_is_caution(self):
        with patch(_APPLY_TOON, side_effect=lambda p, fmt: p):
            result = _failure_envelope("oops", "json")
        assert result["verdict"] == "CAUTION"

    def test_error_message_included(self):
        with patch(_APPLY_TOON, side_effect=lambda p, fmt: p):
            result = _failure_envelope("bad yaml", "json")
        assert result["error"] == "bad yaml"

    def test_violations_is_empty_list(self):
        with patch(_APPLY_TOON, side_effect=lambda p, fmt: p):
            result = _failure_envelope("err", "json")
        assert result["violations"] == []

    def test_rule_count_is_zero(self):
        with patch(_APPLY_TOON, side_effect=lambda p, fmt: p):
            result = _failure_envelope("err", "json")
        assert result["rule_count"] == 0


# ---------------------------------------------------------------------------
# _resolve_output_format
# ---------------------------------------------------------------------------


class TestResolveOutputFormat:
    def test_delegates_to_resolve_mcp_tool_format(self):
        args = SimpleNamespace(format="json")
        with patch(_RESOLVE_FMT, return_value="json") as mock_fn:
            result = _resolve_output_format(args)
        mock_fn.assert_called_once_with(args)
        assert result == "json"

    def test_returns_toon_when_resolver_says_toon(self):
        args = SimpleNamespace()
        with patch(_RESOLVE_FMT, return_value="toon"):
            result = _resolve_output_format(args)
        assert result == "toon"


# ---------------------------------------------------------------------------
# _print_result
# ---------------------------------------------------------------------------


class TestPrintResult:
    def test_toon_prints_toon_content(self, capsys):
        _print_result({"toon_content": "## Verdict\nSAFE"}, "toon")
        out = capsys.readouterr().out
        assert "## Verdict" in out

    def test_json_prints_json(self, capsys):
        _print_result({"success": True, "verdict": "SAFE"}, "json")
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["verdict"] == "SAFE"

    def test_toon_missing_key_prints_empty_string(self, capsys):
        _print_result({}, "toon")
        assert capsys.readouterr().out.strip() == ""

    def test_json_output_is_indented(self, capsys):
        _print_result({"k": "v"}, "json")
        out = capsys.readouterr().out
        assert "\n" in out  # indent=2 produces newlines


# ---------------------------------------------------------------------------
# get_default_project_root
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


# ---------------------------------------------------------------------------
# _evaluate_with_explicit_file
# ---------------------------------------------------------------------------


class TestEvaluateWithExplicitFile:
    def _call(
        self,
        tmp_path: Path,
        constraint_file: str,
        *,
        severity_min: str = "warn",
        path_filter: str = "",
        output_format: str = "json",
    ) -> dict:
        return _evaluate_with_explicit_file(
            project_root=str(tmp_path),
            constraint_file=constraint_file,
            severity_min=severity_min,
            path_filter=path_filter,
            output_format=output_format,
        )

    def test_file_not_found_returns_failure(self, tmp_path):
        with patch(_APPLY_TOON, side_effect=lambda p, fmt: p):
            result = self._call(tmp_path, str(tmp_path / "missing.yml"))
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_parse_error_returns_failure(self, tmp_path):
        from tree_sitter_analyzer.constraints.parser import ConstraintParseError

        yaml_file = tmp_path / "constraints.yml"
        yaml_file.write_text("")
        with patch(_LOAD_EXPLICIT, side_effect=ConstraintParseError("bad")):
            with patch(_APPLY_TOON, side_effect=lambda p, fmt: p):
                result = self._call(tmp_path, str(yaml_file))
        assert result["success"] is False
        assert "parse error" in result["error"]

    def test_no_db_returns_safe_with_note(self, tmp_path):
        yaml_file = tmp_path / "constraints.yml"
        yaml_file.write_text("")
        with patch(_LOAD_EXPLICIT, return_value=[]):
            with patch(_APPLY_TOON, side_effect=lambda p, fmt: p):
                result = self._call(tmp_path, str(yaml_file))
        assert result["verdict"] == "SAFE"
        assert "note" in result
        assert result["evaluated_edge_count"] == 0

    def test_with_db_no_violations_returns_safe(self, tmp_path):
        yaml_file = tmp_path / "constraints.yml"
        yaml_file.write_text("")
        db_dir = tmp_path / ".ast-cache"
        db_dir.mkdir()
        sqlite3.connect(str(db_dir / "index.db")).close()

        with patch(_LOAD_EXPLICIT, return_value=[]):
            with patch(_RUN_AND_PERSIST, return_value=([], 5)):
                with patch(_APPLY_TOON, side_effect=lambda p, fmt: p):
                    result = self._call(tmp_path, str(yaml_file))
        assert result["verdict"] == "SAFE"
        assert result["success"] is True
        assert result["evaluated_edge_count"] == 5

    def test_constraint_file_path_included_in_result(self, tmp_path):
        yaml_file = tmp_path / "constraints.yml"
        yaml_file.write_text("")
        db_dir = tmp_path / ".ast-cache"
        db_dir.mkdir()
        sqlite3.connect(str(db_dir / "index.db")).close()

        with patch(_LOAD_EXPLICIT, return_value=[]):
            with patch(_RUN_AND_PERSIST, return_value=([], 0)):
                with patch(_APPLY_TOON, side_effect=lambda p, fmt: p):
                    result = self._call(tmp_path, str(yaml_file))
        assert "constraint_file" in result

    def test_with_db_and_error_violations_returns_unsafe(self, tmp_path):
        yaml_file = tmp_path / "constraints.yml"
        yaml_file.write_text("")
        db_dir = tmp_path / ".ast-cache"
        db_dir.mkdir()
        sqlite3.connect(str(db_dir / "index.db")).close()

        error_v = _v(severity="error")
        with patch(_LOAD_EXPLICIT, return_value=[]):
            with patch(_RUN_AND_PERSIST, return_value=([error_v], 3)):
                with patch(_APPLY_TOON, side_effect=lambda p, fmt: p):
                    result = self._call(tmp_path, str(yaml_file))
        assert result["verdict"] == "UNSAFE"


# ---------------------------------------------------------------------------
# run_check_constraints — main dispatcher
# ---------------------------------------------------------------------------


def _ns(**kwargs: object) -> SimpleNamespace:
    return SimpleNamespace(
        severity_min=kwargs.get("severity_min", "warn"),
        constraint_path_filter=kwargs.get("constraint_path_filter", ""),
        constraint_file=kwargs.get("constraint_file", None),
    )


class TestRunCheckConstraints:
    def test_with_constraint_file_routes_to_evaluate_explicit(self, tmp_path):
        args = _ns(constraint_file="/some/path.yml")
        safe_result = {"success": True, "verdict": "SAFE"}
        with patch(_RESOLVE_OFMT, return_value="json"):
            with patch(_EVAL_EXPLICIT, return_value=safe_result) as mock_eval:
                with patch(_PRINT_RESULT):
                    code = run_check_constraints(args, str(tmp_path))
        mock_eval.assert_called_once()
        assert code == 0

    def test_without_constraint_file_calls_asyncio_run(self, tmp_path):
        args = _ns()
        safe_result = {"success": True, "verdict": "SAFE"}
        with patch(_RESOLVE_OFMT, return_value="json"):
            with patch(_ASYNCIO_RUN, return_value=safe_result) as mock_run:
                with patch(_PRINT_RESULT):
                    code = run_check_constraints(args, str(tmp_path))
        mock_run.assert_called_once()
        assert code == 0

    def test_caution_verdict_returns_exit_2(self, tmp_path):
        args = _ns()
        caution_result = {"success": True, "verdict": "CAUTION"}
        with patch(_RESOLVE_OFMT, return_value="json"):
            with patch(_ASYNCIO_RUN, return_value=caution_result):
                with patch(_PRINT_RESULT):
                    code = run_check_constraints(args, str(tmp_path))
        assert code == 2

    def test_failure_result_returns_exit_1(self, tmp_path):
        args = _ns()
        fail_result = {"success": False, "verdict": "UNSAFE"}
        with patch(_RESOLVE_OFMT, return_value="json"):
            with patch(_ASYNCIO_RUN, return_value=fail_result):
                with patch(_PRINT_RESULT):
                    code = run_check_constraints(args, str(tmp_path))
        assert code == 1

    def test_severity_min_defaults_to_warn_when_none(self, tmp_path):
        args = SimpleNamespace(
            severity_min=None,
            constraint_path_filter="",
            constraint_file="/f.yml",
        )
        safe_result = {"success": True, "verdict": "SAFE"}
        with patch(_RESOLVE_OFMT, return_value="json"):
            with patch(_EVAL_EXPLICIT, return_value=safe_result) as mock_eval:
                with patch(_PRINT_RESULT):
                    run_check_constraints(args, str(tmp_path))
        called_kwargs = mock_eval.call_args.kwargs
        assert called_kwargs["severity_min"] == "warn"

    def test_print_result_called_with_result_and_format(self, tmp_path):
        args = _ns()
        safe_result = {"success": True, "verdict": "SAFE"}
        with patch(_RESOLVE_OFMT, return_value="toon"):
            with patch(_ASYNCIO_RUN, return_value=safe_result):
                with patch(_PRINT_RESULT) as mock_print:
                    run_check_constraints(args, str(tmp_path))
        mock_print.assert_called_once_with(safe_result, "toon")

    def test_path_filter_passed_to_evaluate_explicit(self, tmp_path):
        args = _ns(constraint_file="/f.yml", constraint_path_filter="src/**")
        safe_result = {"success": True, "verdict": "SAFE"}
        with patch(_RESOLVE_OFMT, return_value="json"):
            with patch(_EVAL_EXPLICIT, return_value=safe_result) as mock_eval:
                with patch(_PRINT_RESULT):
                    run_check_constraints(args, str(tmp_path))
        called_kwargs = mock_eval.call_args.kwargs
        assert called_kwargs["path_filter"] == "src/**"
