"""Tests for tree_sitter_analyzer.cli.commands.constraint_check_command."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.cli.commands.constraint_check_command import (
    _evaluate_with_explicit_file,
    _exit_code_for,
    run_check_constraints,
)

_APPLY_TOON = (
    "tree_sitter_analyzer.mcp.utils.format_helper.apply_toon_format_to_response"
)
_COMMAND = "tree_sitter_analyzer.cli.commands.constraint_check_command"
_EVALUATE = _COMMAND + ".evaluate"
_LOAD_EXPLICIT = _COMMAND + "._load_explicit"
_RUN_AND_PERSIST = _COMMAND + "._run_and_persist"
_EVAL_EXPLICIT = _COMMAND + "._evaluate_with_explicit_file"
_ASYNCIO_RUN = _COMMAND + ".asyncio.run"
_PRINT_RESULT = _COMMAND + "._print_result"
_RESOLVE_OFMT = _COMMAND + "._resolve_output_format"


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


class TestEvaluateWithExplicitFile:
    def _call(
        self,
        tmp_path: Path,
        constraint_file: str,
        *,
        severity_min: str = "warn",
        path_filter: str = "",
        output_format: str = "json",
        persist: bool = True,
    ) -> dict:
        return _evaluate_with_explicit_file(
            project_root=str(tmp_path),
            constraint_file=constraint_file,
            severity_min=severity_min,
            path_filter=path_filter,
            output_format=output_format,
            persist=persist,
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
        with patch(_LOAD_EXPLICIT, return_value=[object()]):
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

        with patch(_LOAD_EXPLICIT, return_value=[object()]):
            with patch(_RUN_AND_PERSIST, return_value=([], 5)):
                with patch(_APPLY_TOON, side_effect=lambda p, fmt: p):
                    result = self._call(tmp_path, str(yaml_file))
        assert result["verdict"] == "SAFE"
        assert result["success"] is True
        assert result["evaluated_edge_count"] == 5

    def test_read_only_missing_edges_fails_closed_with_nonzero_exit(self, tmp_path):
        # PR #1254 review 3766246590: an absent edge capability is not SAFE.
        yaml_file = tmp_path / "constraints.yml"
        yaml_file.write_text(
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
        db_dir = tmp_path / ".ast-cache"
        db_dir.mkdir()
        sqlite3.connect(str(db_dir / "index.db")).close()

        with patch(_APPLY_TOON, side_effect=lambda p, fmt: p):
            result = self._call(tmp_path, str(yaml_file), persist=False)

        expected_error = "CORRUPT_INDEX"
        assert (
            result["success"],
            result["verdict"],
            result["error_code"],
            result["error"],
            result["violations"],
            result["rule_count"],
            _exit_code_for(result),
        ) == (
            False,
            "ERROR",
            "CONSTRAINT_INDEX_UNKNOWN",
            expected_error,
            [],
            1,
            1,
        )

    def test_read_only_corrupt_edges_fails_closed_with_nonzero_exit(self, tmp_path):
        # PR #1254 review 3766246590: evaluator database failures are not SAFE.
        yaml_file = tmp_path / "constraints.yml"
        yaml_file.write_text(
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
        db_dir = tmp_path / ".ast-cache"
        db_dir.mkdir()
        conn = sqlite3.connect(str(db_dir / "index.db"))
        conn.execute("CREATE TABLE edges(kind TEXT)")
        conn.execute("INSERT INTO edges VALUES ('calls')")
        conn.commit()
        conn.close()

        with patch(_EVALUATE, side_effect=sqlite3.DatabaseError("CORRUPT_INDEX")):
            with patch(_APPLY_TOON, side_effect=lambda p, fmt: p):
                result = self._call(tmp_path, str(yaml_file), persist=False)

        expected_error = "CORRUPT_INDEX"
        assert (
            result["success"],
            result["verdict"],
            result["error_code"],
            result["error"],
            result["violations"],
            result["rule_count"],
            _exit_code_for(result),
        ) == (
            False,
            "ERROR",
            "CONSTRAINT_INDEX_UNKNOWN",
            expected_error,
            [],
            1,
            1,
        )

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


def _ns(**kwargs: object) -> SimpleNamespace:
    return SimpleNamespace(
        severity_min=kwargs.get("severity_min", "warn"),
        constraint_path_filter=kwargs.get("constraint_path_filter", ""),
        constraint_file=kwargs.get("constraint_file", None),
        constraints_read_only=kwargs.get("constraints_read_only", False),
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


def test_read_only_option_forwards_persist_false(tmp_path):
    args = _ns(constraints_read_only=True)
    safe_result = {"success": True, "verdict": "SAFE"}
    with patch(_RESOLVE_OFMT, return_value="json"):
        with patch(_ASYNCIO_RUN, return_value=safe_result):
            with patch(_PRINT_RESULT):
                with patch(
                    "tree_sitter_analyzer.cli.commands.constraint_check_command._run_tool"
                ) as run_tool:

                    async def result():
                        return safe_result

                    run_tool.return_value = result()
                    run_check_constraints(args, str(tmp_path))
    assert run_tool.call_args.kwargs["persist"] is False


def test_read_only_explicit_zero_rules_is_safe_without_index(tmp_path: Path) -> None:
    # PR #1254 review 3767373489: empty policy needs no graph authority.
    config = tmp_path / "empty.yml"
    config.write_text("version: 1\nconstraints: []\n")

    result = _evaluate_with_explicit_file(
        project_root=str(tmp_path),
        constraint_file=str(config),
        severity_min="warn",
        path_filter="",
        output_format="json",
        persist=False,
    )

    assert result == {
        "success": True,
        "verdict": "SAFE",
        "violations": [],
        "rule_count": 0,
        "evaluated_edge_count": 0,
        "constraint_file": str(config),
    }
    assert not (tmp_path / ".ast-cache").exists()


def test_read_only_explicit_file_parses_bytes_without_temporary_staging(
    tmp_path: Path,
) -> None:
    # PR #1254 review 3768614254: read-only CLI must not honor project-local TMPDIR.
    config = tmp_path / "candidate.yml"
    config.write_text("version: 1\nconstraints: []\n")

    with patch(
        "tree_sitter_analyzer.cli.commands.constraint_check_command._load_explicit",
        side_effect=AssertionError("read-only route staged the config"),
    ):
        result = _evaluate_with_explicit_file(
            project_root=str(tmp_path),
            constraint_file=str(config),
            severity_min="warn",
            path_filter="",
            output_format="json",
            persist=False,
        )

    assert result == {
        "success": True,
        "verdict": "SAFE",
        "violations": [],
        "rule_count": 0,
        "evaluated_edge_count": 0,
        "constraint_file": str(config),
    }


def test_read_only_explicit_file_maps_portable_oserror_to_index_error(
    tmp_path: Path,
) -> None:
    # PR #1254 review 3768452298: explicit-file portable errors stay structured.
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

    with patch.object(
        __import__(
            "tree_sitter_analyzer.cli.commands.constraint_check_command",
            fromlist=["ConstraintCheckTool"],
        ).ConstraintCheckTool,
        "_run_read_only",
        side_effect=OSError("portable index disappeared"),
    ):
        result = _evaluate_with_explicit_file(
            project_root=str(tmp_path),
            constraint_file=str(config),
            severity_min="warn",
            path_filter="",
            output_format="json",
            persist=False,
        )

    assert result == {
        "success": False,
        "verdict": "ERROR",
        "error_code": "CONSTRAINT_INDEX_UNKNOWN",
        "error": "portable index disappeared",
        "violations": [],
        "rule_count": 1,
    }


def test_explicit_config_evidence_ignores_read_induced_atime(tmp_path, monkeypatch):
    # PR #1254 review 3771670600: reads cannot invalidate their own evidence.
    import tree_sitter_analyzer.cli.commands.constraint_check_execution as owner

    config = tmp_path / "rules.yml"
    payload = b"version: 1\n"
    config.write_bytes(payload)
    stable = config.stat()
    accessed = SimpleNamespace(
        st_dev=stable.st_dev,
        st_ino=stable.st_ino,
        st_mode=stable.st_mode,
        st_size=stable.st_size,
        st_mtime_ns=stable.st_mtime_ns,
        st_ctime_ns=stable.st_ctime_ns,
        st_atime_ns=stable.st_atime_ns + 1,
        st_file_attributes=getattr(stable, "st_file_attributes", 0),
    )
    real_path_stat = Path.stat
    path_stats = iter((stable, accessed))

    def config_stat(path, **kwargs):
        if path == config:
            return next(path_stats)
        return real_path_stat(path, **kwargs)

    monkeypatch.setattr(Path, "stat", config_stat)
    monkeypatch.setattr(owner, "os", SimpleNamespace(fstat=lambda _fd: accessed))

    result = owner.explicit_config_evidence(config, float("inf"))

    assert result == (payload, owner._identity(accessed))


@pytest.mark.parametrize("phase", ["open", "final_fd", "final_path"])
def test_explicit_identity_changes(tmp_path, monkeypatch, phase):
    import tree_sitter_analyzer.cli.commands.constraint_check_execution as owner

    config = tmp_path / "rules.yml"
    config.write_bytes(b"version: 1\n")
    stable = config.stat()
    changed = SimpleNamespace(
        st_dev=stable.st_dev,
        st_ino=stable.st_ino,
        st_mode=stable.st_mode,
        st_size=stable.st_size,
        st_mtime_ns=stable.st_mtime_ns + 1,
        st_ctime_ns=stable.st_ctime_ns,
        st_file_attributes=getattr(stable, "st_file_attributes", 0),
    )
    fstats = iter((changed,)) if phase == "open" else iter((stable, changed))
    monkeypatch.setattr(owner, "os", SimpleNamespace(fstat=lambda _fd: next(fstats)))
    if phase == "final_path":
        real_path_stat = Path.stat
        path_stats = iter((stable, changed))

        def config_stat(path, **kwargs):
            if path == config:
                return next(path_stats)
            return real_path_stat(path, **kwargs)

        monkeypatch.setattr(owner, "os", SimpleNamespace(fstat=lambda _fd: stable))
        monkeypatch.setattr(Path, "stat", config_stat)
    with pytest.raises(OSError, match="^constraint file changed during read$"):
        owner.explicit_config_evidence(config, float("inf"))


def test_explicit_config_evidence_rejects_directory(tmp_path):
    import tree_sitter_analyzer.cli.commands.constraint_check_execution as owner

    with pytest.raises(OSError, match="^constraint file is not a regular file$"):
        owner.explicit_config_evidence(tmp_path, float("inf"))


def _ctime_variant(info, delta):
    return SimpleNamespace(
        st_dev=info.st_dev,
        st_ino=info.st_ino,
        st_mode=info.st_mode,
        st_size=info.st_size,
        st_mtime_ns=info.st_mtime_ns,
        st_ctime_ns=info.st_ctime_ns + delta,
        st_file_attributes=getattr(info, "st_file_attributes", 0),
    )


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="st_ctime is creation time only on Windows; POSIX ctime is asserted below",
)
def test_identity_ignores_creation_time_on_windows(tmp_path):
    # CI develop 32256066101 (windows-latest, 3.12): os.stat(path) and
    # os.fstat(fd) disagree on st_ctime_ns for ~9% of freshly created files,
    # so projecting it made unmutated configs read as CONSTRAINT_CONFIG_CHANGED.
    import tree_sitter_analyzer.cli.commands.constraint_check_execution as owner

    config = tmp_path / "rules.yml"
    config.write_bytes(b"version: 1\n")
    info = config.stat()

    assert owner._identity(_ctime_variant(info, 1)) == owner._identity(info)


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX-only: st_ctime is inode change time and must stay projected",
)
def test_identity_honors_inode_change_time_on_posix(tmp_path):
    # The Windows carve-out above must not weaken POSIX, where st_ctime is the
    # inode change time and therefore a real mutation signal.
    import tree_sitter_analyzer.cli.commands.constraint_check_execution as owner

    config = tmp_path / "rules.yml"
    config.write_bytes(b"version: 1\n")
    info = config.stat()

    assert owner._identity(_ctime_variant(info, 1)) != owner._identity(info)


def test_identity_is_stable_across_path_stat_and_handle_fstat(tmp_path):
    # CI develop 32256066101: the line-39/line-54 checks compare a path stat
    # against a handle fstat, so every projected field must agree across both
    # APIs for an untouched file. 300 trials because the Windows divergence
    # reproduced in only ~9% of them.
    import tree_sitter_analyzer.cli.commands.constraint_check_execution as owner

    mismatches = []
    for index in range(300):
        config = tmp_path / f"rules{index}.yml"
        config.write_bytes(b"version: 1\n")
        path_identity = owner._identity(config.stat(follow_symlinks=False))
        with config.open("rb", buffering=0) as stream:
            handle_identity = owner._identity(os.fstat(stream.fileno()))
        if path_identity != handle_identity:
            mismatches.append((index, path_identity, handle_identity))

    assert mismatches == []
