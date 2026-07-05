"""Tests for --doctor CLI command (installation diagnostics)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch


class TestCheckUv:
    def test_pass_when_uv_found(self) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import _check_uv

        with patch("shutil.which", return_value="/usr/local/bin/uv"):
            result = _check_uv()
        assert result.status == "PASS"
        assert result.message == "/usr/local/bin/uv"

    def test_fail_when_uv_missing(self) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import _check_uv

        with patch("shutil.which", return_value=None):
            result = _check_uv()
        assert result.status == "FAIL"
        assert "not found" in result.message


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
        from tree_sitter_analyzer.cli.commands.doctor import _check_agent_configs

        fake_paths = [
            ("Test Agent", str(tmp_path / "nonexistent.json")),
        ]
        with patch(
            "tree_sitter_analyzer.cli.commands.doctor._agent_config_paths",
            return_value=fake_paths,
        ):
            results = _check_agent_configs()
        assert len(results) == 1
        assert results[0].status == "WARN"
        assert "not found" in results[0].message

    def test_pass_when_tsa_entry_present_and_absolute(self, tmp_path: Path) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import _check_agent_configs

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
        with patch(
            "tree_sitter_analyzer.cli.commands.doctor._agent_config_paths",
            return_value=[("Test Agent", str(config))],
        ):
            results = _check_agent_configs()
        assert len(results) == 1
        assert results[0].status == "PASS"

    def test_warn_when_tsa_entry_missing(self, tmp_path: Path) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import _check_agent_configs

        config = tmp_path / "mcp.json"
        config.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
        with patch(
            "tree_sitter_analyzer.cli.commands.doctor._agent_config_paths",
            return_value=[("Test Agent", str(config))],
        ):
            results = _check_agent_configs()
        assert len(results) == 1
        assert results[0].status == "WARN"
        assert "not found" in results[0].message

    def test_warn_when_tsa_entry_has_relative_root(self, tmp_path: Path) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import _check_agent_configs

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
        with patch(
            "tree_sitter_analyzer.cli.commands.doctor._agent_config_paths",
            return_value=[("Test Agent", str(config))],
        ):
            results = _check_agent_configs()
        assert len(results) == 1
        assert results[0].status == "WARN"
        assert "relative path" in results[0].message

    def test_warn_when_json_parse_error(self, tmp_path: Path) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import _check_agent_configs

        config = tmp_path / "mcp.json"
        config.write_text("{ invalid json }", encoding="utf-8")
        with patch(
            "tree_sitter_analyzer.cli.commands.doctor._agent_config_paths",
            return_value=[("Test Agent", str(config))],
        ):
            results = _check_agent_configs()
        assert len(results) == 1
        assert results[0].status == "WARN"
        assert "cannot read" in results[0].message


class TestRunDoctor:
    def test_returns_zero_when_no_failures(self, tmp_path: Path, capsys) -> None:
        from tree_sitter_analyzer.cli.commands.doctor import run_doctor

        with (
            patch("shutil.which", return_value="/usr/bin/tool"),
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
