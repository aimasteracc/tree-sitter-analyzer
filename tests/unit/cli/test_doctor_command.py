# fmt: off
"""Tests for --doctor CLI command (installation diagnostics)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SUPPORTED_UV_RESULT = subprocess.CompletedProcess([], 0, "uv 0.11.0\n", "")


def _probe_process(completed: subprocess.CompletedProcess):
    process = MagicMock()
    process.args = completed.args
    process.returncode = completed.returncode
    process.communicate.return_value = (completed.stdout, completed.stderr)
    return process


def _check_configs(paths: list[tuple[str, str]]):
    from tree_sitter_analyzer.cli.commands.doctor import _check_agent_configs

    with patch("tree_sitter_analyzer.cli.commands.doctor._agent_config_paths", return_value=paths):
        return _check_agent_configs()


class TestTerminateProcessTree:
    def test_windows_uses_taskkill_for_descendants(self) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import _terminate_process_tree

        process = MagicMock(pid=123)
        terminated = subprocess.CompletedProcess([], 0)
        with (
            patch("tree_sitter_analyzer.cli.commands.doctor.os.name", "nt"),
            patch(
                "tree_sitter_analyzer.cli.commands.doctor.subprocess.run",
                return_value=terminated,
            ) as run,
        ):
            _terminate_process_tree(process)
        assert run.call_args.args[0] == [
            r"C:\Windows/System32/taskkill.exe",
            "/PID",
            "123",
            "/T",
            "/F",
        ]
        process.kill.assert_not_called()

    def test_windows_falls_back_when_taskkill_returns_failure(self) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import _terminate_process_tree

        process = MagicMock(pid=123)
        terminated = subprocess.CompletedProcess([], 1)
        with (
            patch("tree_sitter_analyzer.cli.commands.doctor.os.name", "nt"),
            patch(
                "tree_sitter_analyzer.cli.commands.doctor.subprocess.run",
                return_value=terminated,
            ),
        ):
            _terminate_process_tree(process)
        process.kill.assert_called_once_with()

    def test_windows_falls_back_when_taskkill_fails(self) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import _terminate_process_tree

        process = MagicMock(pid=123)
        with (
            patch("tree_sitter_analyzer.cli.commands.doctor.os.name", "nt"),
            patch(
                "tree_sitter_analyzer.cli.commands.doctor.subprocess.run",
                side_effect=OSError("taskkill unavailable"),
            ),
        ):
            _terminate_process_tree(process)
        process.kill.assert_called_once_with()

    def test_posix_escalates_process_group_to_sigkill(self) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import _terminate_process_tree

        process = MagicMock(pid=123)
        process.communicate.side_effect = [
            subprocess.TimeoutExpired([], 1),
            (b"", b""),
        ]
        with (
            patch("tree_sitter_analyzer.cli.commands.doctor.os.name", "posix"),
            patch("tree_sitter_analyzer.cli.commands.doctor.os.killpg") as killpg,
        ):
            _terminate_process_tree(process)
        assert killpg.call_args_list == [
            ((123, 15),),
            ((123, 0),),
            ((123, 9),),
        ]

    def test_posix_reaps_after_group_is_already_gone(self) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import _terminate_process_tree

        process = MagicMock(pid=123)
        process.communicate.side_effect = [
            subprocess.TimeoutExpired([], 1),
            subprocess.TimeoutExpired([], 1),
            (b"", b""),
        ]
        with (
            patch("tree_sitter_analyzer.cli.commands.doctor.os.name", "posix"),
            patch(
                "tree_sitter_analyzer.cli.commands.doctor.os.killpg",
                side_effect=ProcessLookupError,
            ),
        ):
            _terminate_process_tree(process)
        process.kill.assert_called_once_with()


class TestCheckUv:
    @pytest.mark.parametrize(
        ("completed", "status", "message"),
        (
            (SUPPORTED_UV_RESULT, "PASS", "/usr/local/bin/uv (0.11.0)"),
            (subprocess.CompletedProcess([], 0, "uv 0.10.9\n", ""), "FAIL", "0.10.9 at /usr/local/bin/uv is too old — required uv >= 0.11.0; rerun install.sh or update uv manually"),
            (subprocess.CompletedProcess([], 0, "not-uv 0.11.0\n", ""), "FAIL", "cannot determine version at /usr/local/bin/uv — required uv >= 0.11.0"),
            (subprocess.CompletedProcess([], 0, " uv 0.11.0\n", ""), "FAIL", "cannot determine version at /usr/local/bin/uv — required uv >= 0.11.0"),
            (subprocess.CompletedProcess([], 0, "\nuv 0.11.0\n", ""), "FAIL", "cannot determine version at /usr/local/bin/uv — required uv >= 0.11.0"),
            (subprocess.CompletedProcess([], 0, "uv 0.11.0.1\n", ""), "FAIL", "cannot determine version at /usr/local/bin/uv — required uv >= 0.11.0"),
            (subprocess.CompletedProcess([], 0, b"uv 0.11.0\xff\n", b""), "FAIL", "undecodable version output from /usr/local/bin/uv --version"),
        ),
    )
    def test_uv_version_boundary(self, completed, status, message) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import _check_uv

        with patch("shutil.which", return_value="/usr/local/bin/uv"), patch("tree_sitter_analyzer.cli.commands.doctor.subprocess.Popen", return_value=_probe_process(completed)):
            result = _check_uv()
        assert (result.status, result.message) == (status, message)

    def test_fail_when_uv_version_component_exceeds_integer_limit(self) -> None:
        # PR #1233: adversarial numeric output must produce a diagnostic, not a traceback.
        from tree_sitter_analyzer.cli.commands.doctor import _check_uv

        completed = subprocess.CompletedProcess([], 0, f"uv {'1' * 5000}.11.0\n", "")
        with patch("shutil.which", return_value="/usr/local/bin/uv"), patch(
            "tree_sitter_analyzer.cli.commands.doctor.subprocess.Popen",
            return_value=_probe_process(completed),
        ):
            result = _check_uv()
        assert (result.status, result.message) == (
            "FAIL",
            "cannot determine version at /usr/local/bin/uv — required uv >= 0.11.0",
        )

    def test_windows_probe_starts_in_new_process_group(self) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import _check_uv

        process = _probe_process(SUPPORTED_UV_RESULT)
        with (
            patch("shutil.which", return_value=r"C:\tools\uv.exe"),
            patch("tree_sitter_analyzer.cli.commands.doctor.os.name", "nt"),
            patch(
                "tree_sitter_analyzer.cli.commands.doctor.subprocess.Popen",
                return_value=process,
            ) as popen,
        ):
            result = _check_uv()
        assert (result.status, popen.call_args.kwargs["creationflags"]) == (
            "PASS",
            0x00000200,
        )

    def test_fail_when_uv_version_check_times_out(self) -> None:
        # NO1-006A (2026-08-08): doctor must not hang on a broken uv executable.
        from tree_sitter_analyzer.cli.commands.doctor import _check_uv

        process = MagicMock()
        process.communicate.side_effect = subprocess.TimeoutExpired(
            ["uv", "--version"], 5
        )
        with (
            patch("shutil.which", return_value="/usr/local/bin/uv"),
            patch(
                "tree_sitter_analyzer.cli.commands.doctor.subprocess.Popen",
                return_value=process,
            ),
            patch("tree_sitter_analyzer.cli.commands.doctor._terminate_process_tree") as terminate,
        ):
            result = _check_uv()
        terminate.assert_called_once_with(process)
        assert (result.status, result.message) == (
            "FAIL", "timed out running /usr/local/bin/uv --version"
        )

    def test_fail_when_uv_missing(self) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import _check_uv

        with patch("shutil.which", return_value=None):
            result = _check_uv()
        assert (result.status, result.message) == (
            "FAIL", "not found — install from https://docs.astral.sh/uv/"
        )

    @pytest.mark.slow_ok
    @pytest.mark.skipif(
        os.name == "nt",
        reason="tracked: POSIX process-group cleanup has a separate Windows implementation",
    )
    def test_timeout_terminates_uv_descendant(self, tmp_path: Path) -> None:
        # PR #1233: doctor timeout cleanup must not orphan a uv shim's child.
        from tree_sitter_analyzer.cli.commands.doctor import _check_uv

        child_pid_file = tmp_path / "child.pid"
        uv = tmp_path / "uv"
        uv.write_text(
            "#!/bin/sh\nsh -c 'trap \'\' TERM; sleep 60' &\necho $! > "
            f"{child_pid_file!s}\nwait\n",
            encoding="utf-8",
        )
        uv.chmod(0o755)
        with patch("shutil.which", return_value=str(uv)):
            result = _check_uv()

        child_pid = int(child_pid_file.read_text(encoding="utf-8"))
        deadline = time.monotonic() + 3
        child_exited = False
        while time.monotonic() < deadline:
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                child_exited = True
                break
            time.sleep(0.05)
        assert (result.status, child_exited) == ("FAIL", True)


class TestCheckUvx:
    def test_pass_when_uvx_found(self) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import _check_uvx

        with patch("shutil.which", return_value="/usr/local/bin/uvx"):
            result = _check_uvx()
        assert result.status == "PASS"

    def test_warn_when_uvx_missing(self) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import _check_uvx

        with patch("shutil.which", return_value=None):
            result = _check_uvx()
        assert result.status == "WARN"
        assert "reinstall uv" in result.message


class TestCheckFd:
    def test_pass_when_fd_found(self) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import _check_fd

        with patch("shutil.which", return_value="/usr/bin/fd"):
            result = _check_fd()
        assert result.status == "PASS"

    def test_warn_when_fd_missing(self) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import _check_fd

        with patch("shutil.which", return_value=None):
            result = _check_fd()
        assert result.status == "WARN"


class TestCheckRg:
    def test_pass_when_rg_found(self) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import _check_rg

        with patch("shutil.which", return_value="/usr/bin/rg"):
            result = _check_rg()
        assert result.status == "PASS"

    def test_warn_when_rg_missing(self) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import _check_rg

        with patch("shutil.which", return_value=None):
            result = _check_rg()
        assert result.status == "WARN"


class TestCheckProjectRoot:
    def test_fail_when_env_var_not_set(self) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import _check_project_root

        with patch.dict(os.environ, {}, clear=True):
            env = {
                k: v for k, v in os.environ.items() if k != "TREE_SITTER_PROJECT_ROOT"
            }
            with patch.dict(os.environ, env, clear=True):
                result = _check_project_root()
        assert result.status == "FAIL"
        assert "not set" in result.message

    def test_fail_when_relative_path(self) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import _check_project_root

        with patch.dict(os.environ, {"TREE_SITTER_PROJECT_ROOT": "./relative"}):
            result = _check_project_root()
        assert result.status == "FAIL"
        assert "relative path" in result.message

    def test_fail_when_directory_missing(self, tmp_path: Path) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import _check_project_root

        nonexistent = str(tmp_path / "does_not_exist")
        with patch.dict(os.environ, {"TREE_SITTER_PROJECT_ROOT": nonexistent}):
            result = _check_project_root()
        assert result.status == "FAIL"
        assert "does not exist" in result.message

    def test_pass_when_absolute_and_exists(self, tmp_path: Path) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import _check_project_root

        with patch.dict(os.environ, {"TREE_SITTER_PROJECT_ROOT": str(tmp_path)}):
            result = _check_project_root()
        assert result.status == "PASS"
        assert result.message == str(tmp_path)


class TestCheckAgentConfigs:
    def test_warn_when_no_config_files_exist(self, tmp_path: Path) -> None:

        fake_paths = [
            ("Test Agent", str(tmp_path / "nonexistent.json")),
        ]
        results = _check_configs(fake_paths)
        assert len(results) == 1
        assert results[0].status == "WARN"
        assert "not found" in results[0].message

    def test_pass_when_tsa_entry_present_and_absolute(self, tmp_path: Path) -> None:

        config = tmp_path / "mcp.json"
        config.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "tree-sitter-analyzer": {
                            "command": "uvx",
                            "args": [],
                            "env": {"TREE_SITTER_PROJECT_ROOT": str(tmp_path)},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        results = _check_configs([("Test Agent", str(config))])
        assert len(results) == 1
        assert results[0].status == "PASS"

    def test_warn_when_tsa_entry_missing(self, tmp_path: Path) -> None:

        config = tmp_path / "mcp.json"
        config.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
        results = _check_configs([("Test Agent", str(config))])
        assert len(results) == 1
        assert results[0].status == "WARN"
        assert "not found" in results[0].message

    def test_warn_when_tsa_entry_has_relative_root(self, tmp_path: Path) -> None:

        config = tmp_path / "mcp.json"
        config.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "tree-sitter-analyzer": {
                            "command": "uvx",
                            "args": [],
                            "env": {"TREE_SITTER_PROJECT_ROOT": "./relative"},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        results = _check_configs([("Test Agent", str(config))])
        assert len(results) == 1
        assert results[0].status == "WARN"
        assert "relative path" in results[0].message

    @pytest.mark.parametrize(
        "content",
        ("{ invalid json }", '{"mcpServers": ' + "1" * 5000 + "}", "[" * 100_000 + "]" * 100_000),
        ids=("syntax", "integer-limit", "nesting-limit"),
    )
    def test_warn_when_json_decoder_rejects_content(
        self, tmp_path: Path, content: str
    ) -> None:

        config = tmp_path / "mcp.json"
        config.write_text(content, encoding="utf-8")
        results = _check_configs([("Test Agent", str(config))])
        assert len(results) == 1
        assert results[0].status == "WARN"
        assert results[0].message == f"cannot read {config}: invalid JSON content"

    def test_warn_when_config_open_fails(self, tmp_path: Path) -> None:
        config = tmp_path / "mcp.json"
        config.touch()
        with patch("builtins.open", side_effect=OSError("denied")):
            results = _check_configs([("Test Agent", str(config))])
        assert results[0].status == "WARN"
        assert results[0].message == f"cannot read {config}: denied"

    @pytest.mark.parametrize(
        ("content", "message"),
        (
            ("[]", "config root must be a JSON object: {config}"),
            ('{"mcpServers": []}', "mcpServers must be a JSON object: {config}"),
            ('{"mcpServers": {"tree-sitter-analyzer": []}}', "MCP entry 'tree-sitter-analyzer' must be a JSON object: {config}"),
            ('{"mcpServers": {"tree-sitter-analyzer": {"env": []}}}', "MCP entry 'tree-sitter-analyzer'.env must be a JSON object: {config}"),
            ('{"mcpServers": {"tree-sitter-analyzer": {"env": {"TREE_SITTER_PROJECT_ROOT": []}}}}', "TREE_SITTER_PROJECT_ROOT must be a string in MCP entry 'tree-sitter-analyzer': {config}"),
        ),
    )
    def test_warn_when_config_boundary_is_not_object_or_string(
        self, tmp_path: Path, content: str, message: str
    ) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import (
            CheckResult,
        )

        config = tmp_path / "mcp.json"
        config.write_text(content, encoding="utf-8")
        results = _check_configs([("Test Agent", str(config))])
        assert results == [
            CheckResult("agent config: Test Agent", "WARN", message.format(config=config))
        ]



class TestRunDoctor:
    def test_returns_zero_when_no_failures(self, tmp_path: Path, capsys) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import run_doctor

        with (
            patch("shutil.which", return_value="/usr/bin/tool"),
            patch("tree_sitter_analyzer.cli.commands.doctor.subprocess.Popen", return_value=_probe_process(SUPPORTED_UV_RESULT)),
            patch.dict(os.environ, {"TREE_SITTER_PROJECT_ROOT": str(tmp_path)}),
            patch(
                "tree_sitter_analyzer.cli.commands.doctor._check_agent_configs",
                return_value=[],
            ),
        ):
            exit_code = run_doctor()
        assert exit_code == 0

    def test_returns_one_when_failure_present(self, capsys) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import run_doctor

        with (
            patch("shutil.which", return_value=None),
            patch.dict(os.environ, {}, clear=True),
            patch(
                "tree_sitter_analyzer.cli.commands.doctor._check_agent_configs",
                return_value=[],
            ),
        ):
            env = {
                k: v for k, v in os.environ.items() if k != "TREE_SITTER_PROJECT_ROOT"
            }
            with patch.dict(os.environ, env, clear=True):
                exit_code = run_doctor()
        assert exit_code == 1

    def test_text_output_contains_pass_warn_fail(self, tmp_path: Path, capsys) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import run_doctor

        with (
            patch("shutil.which", return_value="/usr/bin/tool"),
            patch.dict(os.environ, {"TREE_SITTER_PROJECT_ROOT": "./bad"}),
            patch(
                "tree_sitter_analyzer.cli.commands.doctor._check_agent_configs",
                return_value=[],
            ),
        ):
            run_doctor(json_output=False)
        captured = capsys.readouterr()
        assert "PASS" in captured.out
        assert "FAIL" in captured.out

    def test_json_output_is_valid_json(self, tmp_path: Path, capsys) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import run_doctor

        with (
            patch("shutil.which", return_value="/usr/bin/tool"),
            patch.dict(os.environ, {"TREE_SITTER_PROJECT_ROOT": str(tmp_path)}),
            patch(
                "tree_sitter_analyzer.cli.commands.doctor._check_agent_configs",
                return_value=[],
            ),
        ):
            run_doctor(json_output=True)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "checks" in data
        assert "summary" in data
        assert set(data["summary"].keys()) == {"pass", "warn", "fail"}

    def test_json_each_check_has_required_fields(self, tmp_path: Path, capsys) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import run_doctor

        with (
            patch("shutil.which", return_value="/usr/bin/tool"),
            patch.dict(os.environ, {"TREE_SITTER_PROJECT_ROOT": str(tmp_path)}),
            patch(
                "tree_sitter_analyzer.cli.commands.doctor._check_agent_configs",
                return_value=[],
            ),
        ):
            run_doctor(json_output=True)
        data = json.loads(capsys.readouterr().out)
        for check in data["checks"]:
            assert "name" in check
            assert "status" in check
            assert check["status"] in ("PASS", "WARN", "FAIL")
            assert "message" in check


class TestAgentConfigPaths:
    def test_linux_paths_include_correct_labels(self) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import _agent_config_paths

        with patch.object(sys, "platform", "linux"):
            paths = _agent_config_paths()
        labels = [label for label, _ in paths]
        assert "Claude Desktop (Linux)" in labels
        assert "Claude Code (global)" in labels
        assert "Claude Code (project-local)" in labels
        assert "Cursor" in labels
        assert "VS Code (Linux)" in labels

    def test_macos_paths_include_correct_labels(self) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import _agent_config_paths

        with patch.object(sys, "platform", "darwin"):
            paths = _agent_config_paths()
        labels = [label for label, _ in paths]
        assert "Claude Desktop (macOS)" in labels
        assert "VS Code (macOS)" in labels
        assert "Claude Code (global)" in labels
        assert "Cursor" in labels

    def test_macos_desktop_path_contains_library(self) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import _agent_config_paths

        with patch.object(sys, "platform", "darwin"):
            paths = _agent_config_paths()
        desktop_path = next(p for label, p in paths if "Desktop" in label)
        assert "Library" in desktop_path
        assert "claude_desktop_config.json" in desktop_path

    def test_linux_desktop_path_contains_config(self) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import _agent_config_paths

        with patch.object(sys, "platform", "linux"):
            paths = _agent_config_paths()
        desktop_path = next(p for label, p in paths if "Desktop" in label)
        assert ".config" in desktop_path
        assert "claude_desktop_config.json" in desktop_path

    def test_returns_five_entries_on_linux(self) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import _agent_config_paths

        with patch.object(sys, "platform", "linux"):
            paths = _agent_config_paths()
        assert len(paths) == 5

    def test_returns_five_entries_on_macos(self) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import _agent_config_paths

        with patch.object(sys, "platform", "darwin"):
            paths = _agent_config_paths()
        assert len(paths) == 5


class TestDoctorFlagsRegistered:
    def test_doctor_flag_registered_in_parser(self) -> None:
        from tree_sitter_analyzer.cli_main import create_argument_parser

        parser = create_argument_parser()
        flags = {s for a in parser._actions for s in a.option_strings}
        assert "--doctor" in flags

    def test_doctor_json_flag_registered_in_parser(self) -> None:
        from tree_sitter_analyzer.cli_main import create_argument_parser

        parser = create_argument_parser()
        flags = {s for a in parser._actions for s in a.option_strings}
        assert "--doctor-json" in flags


class TestHandleDoctor:
    def test_returns_none_when_doctor_flag_absent(self) -> None:
        from unittest.mock import MagicMock

        from tree_sitter_analyzer.cli.special_commands import (
            SpecialCommandContext,
            _handle_doctor,
        )

        args = MagicMock(spec=[])
        context = MagicMock(spec=SpecialCommandContext)
        result = _handle_doctor(args, context)
        assert result is None

    def test_calls_run_doctor_when_flag_set(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock

        from tree_sitter_analyzer.cli.special_commands import (
            SpecialCommandContext,
            _handle_doctor,
        )

        args = MagicMock()
        args.doctor = True
        args.doctor_json = False
        context = MagicMock(spec=SpecialCommandContext)

        with (
            patch("shutil.which", return_value="/usr/bin/uv"),
            patch("tree_sitter_analyzer.cli.commands.doctor.subprocess.Popen", return_value=_probe_process(SUPPORTED_UV_RESULT)),
            patch.dict(os.environ, {"TREE_SITTER_PROJECT_ROOT": str(tmp_path)}),
            patch(
                "tree_sitter_analyzer.cli.commands.doctor._check_agent_configs",
                return_value=[],
            ),
        ):
            result = _handle_doctor(args, context)
        assert result == 0


class TestMainDoctor:
    def test_main_doctor_prepends_doctor_flag(self) -> None:
        from tree_sitter_analyzer.cli_main import main_doctor

        called_with: list[str] = []

        def fake_main() -> None:
            called_with.extend(sys.argv)

        with (
            patch("tree_sitter_analyzer.cli_main.main", side_effect=fake_main),
            patch.object(sys, "argv", ["tree-sitter-analyzer-doctor"]),
        ):
            main_doctor()

        assert called_with[1] == "--doctor"
