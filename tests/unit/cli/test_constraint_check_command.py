"""Tests for tree_sitter_analyzer.cli.commands.constraint_check_command."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.cli.commands.constraint_check_command import (
    _compute_verdict,
    _evaluate_with_explicit_file,
    _exit_code_for,
    _explicit_config_evidence,
    _failure_envelope,
    _filter_violations,
    _format_response,
    _load_explicit,
    _print_result,
    _resolve_output_format,
    _violations_ddl,
    get_default_project_root,
)

# Module-level patch targets
_APPLY_TOON = (
    "tree_sitter_analyzer.mcp.utils.format_helper.apply_output_format_to_response"
)
_RESOLVE_FMT = "tree_sitter_analyzer.cli.output_format.resolve_output_format"
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


class TestFormatResponse:
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


class TestResolveOutputFormat:
    def test_delegates_to_resolve_output_format(self):
        args = SimpleNamespace(format="json")
        with patch(_RESOLVE_FMT, return_value="json") as mock_fn:
            result = _resolve_output_format(args)
        mock_fn.assert_called_once_with(args)
        assert result == "json"


class TestPrintResult:
    def test_json_prints_json(self, capsys):
        _print_result({"success": True, "verdict": "SAFE"}, "json")
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["verdict"] == "SAFE"

    def test_json_output_is_indented(self, capsys):
        _print_result({"k": "v"}, "json")
        out = capsys.readouterr().out
        assert "\n" in out  # indent=2 produces newlines


class TestGetDefaultProjectRoot:
    def test_returns_project_root_attr(self):
        args = SimpleNamespace(project_root="/srv/proj")
        assert get_default_project_root(args) == "/srv/proj"

    def test_falls_back_to_cwd_when_none(self):
        args = SimpleNamespace(project_root=None)
        assert get_default_project_root(args)  # truthy

    def test_falls_back_to_cwd_when_attr_missing(self):
        assert get_default_project_root(SimpleNamespace())  # truthy


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


def test_explicit_config_evidence_rejects_input_above_one_mib(tmp_path: Path) -> None:
    # PR #1254 review 3769281328: explicit read-only input stays bounded.
    config = tmp_path / "candidate.yml"
    config.write_bytes(b"x" * (1024 * 1024 + 1))

    with pytest.raises(RuntimeError, match="^CONSTRAINT_CONFIG_CAPACITY$"):
        _explicit_config_evidence(config, float("inf"))


def test_explicit_config_evidence_honors_expired_deadline(tmp_path: Path) -> None:
    # PR #1254 review 3769281328: reads share the evaluation deadline contract.
    config = tmp_path / "candidate.yml"
    config.write_bytes(b"version: 1\nconstraints: []\n")

    with pytest.raises(RuntimeError, match="^CONSTRAINT_CONFIG_DEADLINE$"):
        _explicit_config_evidence(config, 0.0)


def test_explicit_zero_rules_revalidates_bytes_before_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #1254 review 3769193838: the zero-rule fast path retains rule authority.
    config = tmp_path / "candidate.yml"
    config.write_text("version: 1\nconstraints: []\n")
    real_evidence = __import__(
        "tree_sitter_analyzer.cli.commands.constraint_check_command",
        fromlist=["_explicit_config_evidence"],
    )._explicit_config_evidence
    reads = 0

    def tighten(path: Path, deadline: float):
        nonlocal reads
        evidence = real_evidence(path, deadline)
        reads += 1
        if reads == 1:
            config.write_text("version: 1\nconstraints: [{id: changed}]\n")
        return evidence

    monkeypatch.setattr(
        "tree_sitter_analyzer.cli.commands.constraint_check_command._explicit_config_evidence",
        tighten,
    )
    result = _evaluate_with_explicit_file(
        project_root=str(tmp_path),
        constraint_file=str(config),
        severity_min="warn",
        path_filter="",
        output_format="json",
        persist=False,
    )

    assert (result["success"], result["verdict"], result["error_code"], reads) == (
        False,
        "ERROR",
        "CONSTRAINT_CONFIG_CHANGED",
        2,
    )


def test_explicit_rules_revalidate_identity_after_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #1254 review 3769193838: same bytes under a replacement identity fail closed.
    config = tmp_path / "candidate.yml"
    config.write_text(
        "version: 1\nconstraints:\n"
        "  - {id: r, severity: error, rule: forbid, from: 'a/**', "
        "to: 'b/**', reason: boundary}\n"
    )

    def replace_during_evaluation(*_args, **_kwargs):
        replacement = tmp_path / "replacement.yml"
        replacement.write_bytes(config.read_bytes())
        replacement.replace(config)
        return [], 0

    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.constraint_check_tool.ConstraintCheckTool._run_read_only",
        replace_during_evaluation,
    )
    result = _evaluate_with_explicit_file(
        project_root=str(tmp_path),
        constraint_file=str(config),
        severity_min="warn",
        path_filter="",
        output_format="json",
        persist=False,
    )

    assert (result["success"], result["verdict"], result["error_code"]) == (
        False,
        "ERROR",
        "CONSTRAINT_CONFIG_CHANGED",
    )


def test_explicit_config_recheck_treats_read_failure_as_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tree_sitter_analyzer.cli.commands.constraint_check_command as owner

    config = tmp_path / "candidate.yml"
    config.write_bytes(b"version: 1\nconstraints: []\n")
    before = owner._explicit_config_evidence(config, float("inf"))
    monkeypatch.setattr(
        owner,
        "_explicit_config_evidence",
        lambda *_args: (_ for _ in ()).throw(OSError("unreadable")),
    )
    assert owner._explicit_config_changed(config, before, float("inf")) is True


def test_explicit_nonempty_rules_publish_when_config_remains_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #1254 review 3772454771: explicit config and evaluation share one budget.
    config = tmp_path / "candidate.yml"
    config.write_text(
        "version: 1\nconstraints:\n"
        "  - {id: r, severity: warn, rule: forbid, from: 'a/**', "
        "to: 'b/**', reason: boundary}\n"
    )
    observed = []
    monkeypatch.setattr(
        "tree_sitter_analyzer.cli.commands.constraint_check_command._explicit_config_evidence",
        lambda path, deadline: (
            observed.append(deadline) or _explicit_config_evidence(path, deadline)
        ),
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.constraint_check_tool.ConstraintCheckTool._run_read_only",
        lambda *_args, deadline, **_kwargs: (observed.append(deadline) or [], 0),
    )
    result = _evaluate_with_explicit_file(
        project_root=str(tmp_path),
        constraint_file=str(config),
        severity_min="warn",
        path_filter="",
        output_format="json",
        persist=False,
    )
    actual = result["success"], result["verdict"], result["rule_count"]
    assert actual == (True, "SAFE", 1)
    assert observed == [observed[0]] * 3


def test_run_check_constraints_forwards_read_existing_controls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Codex P1 (#1257): the --check-constraints route must forward the
    # RFC-0022 read-existing controls through the in-process bridge so the
    # CLI path can consume certified snapshots like the MCP facade route.
    import tree_sitter_analyzer.cli.commands.constraint_check_command as owner

    seen: dict[str, object] = {}

    class FakeConstraintCheckTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, object]) -> dict[str, object]:
            seen["arguments"] = dict(arguments)
            return {"success": True, "verdict": "SAFE", "violations": []}

    monkeypatch.setattr(owner, "ConstraintCheckTool", FakeConstraintCheckTool)
    monkeypatch.setattr(owner, "_print_result", lambda result, output_format: None)

    args = SimpleNamespace(
        severity_min="warn",
        constraint_path_filter="",
        constraint_file=None,
        constraints_read_only=False,
        output_format="json",
        access_mode="read_existing",
        diff_snapshot_id="ds_test",
        snapshot_id="idxsnap_01",
        source_generation="gen_01",
    )

    exit_code = owner.run_check_constraints(args, "/repo")

    assert exit_code == 0
    assert seen == {
        "project_root": "/repo",
        "arguments": {
            "path_filter": "",
            "severity_min": "warn",
            "output_format": "json",
            "access_mode": "read_existing",
            "diff_snapshot_id": "ds_test",
            "snapshot_id": "idxsnap_01",
            "source_generation": "gen_01",
        },
    }
