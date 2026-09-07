"""Issue #1376：setup_backend 行为组，原测试 AST 保持不变。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.unit._benchmark_harness_matrix_helpers import (
    TestCodeGraphCompareSetupGate as _TestCodeGraphCompareSetupGate,
)


class TestCodeGraphCompareSetupGate(_TestCodeGraphCompareSetupGate):
    """Model-backed matrix work must be fail-closed behind setup validation."""

    @pytest.mark.parametrize("arm_id", ("native-only", "codegraph-warm", "tsa-warm"))
    def test_codex_backend_validator_allows_isolated_smoke_arms(self, arm_id: str):
        from benchmarks.codegraph_compare.adapters.claude_runner import (
            validate_backend_arm_support,
        )

        validate_backend_arm_support("codex", arm_id)

    def test_backend_validator_allows_supported_combinations(self):
        from benchmarks.codegraph_compare.adapters.claude_runner import (
            validate_backend_arm_support,
        )

        validate_backend_arm_support("codex", "native-only")
        validate_backend_arm_support("claude", "tsa-warm")

    @pytest.mark.parametrize(
        ("arm_id", "server_name"),
        (
            ("tsa-warm", "tree-sitter-analyzer"),
            ("codegraph-warm", "codegraph"),
        ),
    )
    def test_codex_indexed_arm_command_ignores_user_config_and_requires_one_server(
        self, arm_id: str, server_name: str, monkeypatch, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.adapters import RunConfig
        from benchmarks.codegraph_compare.adapters.claude_runner import (
            _build_agent_cmd,
        )

        monkeypatch.setattr(
            "benchmarks.codegraph_compare.adapters.claude_runner.resolve_codegraph_executable",
            lambda: Path("/preinstalled/codegraph"),
        )
        command = _build_agent_cmd(
            arm_id,
            "gpt-5",
            tmp_path,
            RunConfig(arm_id, tmp_path, "system"),
            "Read",
            "ToolSearch",
            "codex",
        )

        assert "--ignore-user-config" in command
        assert "--strict-config" in command
        assert f"mcp_servers.{server_name}.required=true" in command
        assert "sandbox_workspace_write.network_access=false" in command
        configured_servers = [
            value
            for value in command
            if value.startswith("mcp_servers.") and value.endswith(".required=true")
        ]
        assert configured_servers == [f"mcp_servers.{server_name}.required=true"]
        if arm_id == "tsa-warm":
            assert not any(
                value.endswith(
                    'enabled_tools=["nav","search","structure","health","index","project"]'
                )
                for value in command
            )
            assert not any('"index"' in value for value in command)
        if arm_id == "codegraph-warm":
            assert (
                'mcp_servers.codegraph.env={ CODEGRAPH_TELEMETRY = "0", '
                'CODEGRAPH_NO_DAEMON = "1" }'
            ) in command

    def test_codex_arm_tool_preflight_qualifies_both_indexed_servers(
        self, monkeypatch, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.adapters import claude_runner

        executable = tmp_path / "server"
        executable.write_text("fixture", encoding="utf-8")
        monkeypatch.setattr(
            claude_runner,
            "_codex_mcp_config_args",
            lambda arm, repo: ["-c", f"fixture={arm}:{repo.name}"],
        )

        def fake_run(command, **kwargs):
            server = "tree-sitter-analyzer" if "tsa-warm" in command[3] else "codegraph"
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    [
                        {
                            "name": server,
                            "enabled": True,
                            "transport": {
                                "command": str(executable),
                                "args": ["serve", "--mcp"],
                            },
                        }
                    ]
                ),
                stderr="",
            )

        monkeypatch.setattr(claude_runner.subprocess, "run", fake_run)

        evidence = claude_runner.preflight_codex_arm_tools(
            {"tsa-warm": tmp_path, "codegraph-warm": tmp_path}
        )

        assert set(evidence) == {"tsa-warm", "codegraph-warm"}
        assert all(item["enabled"] for item in evidence.values())

    def test_codex_arm_tool_preflight_rejects_missing_executable(
        self, monkeypatch, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.adapters import claude_runner

        monkeypatch.setattr(
            claude_runner,
            "_codex_mcp_config_args",
            lambda arm, repo: ["-c", f"fixture={arm}:{repo.name}"],
        )
        monkeypatch.setattr(
            claude_runner.subprocess,
            "run",
            lambda command, **kwargs: subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    [
                        {
                            "name": "tree-sitter-analyzer",
                            "enabled": True,
                            "transport": {
                                "command": str(tmp_path / "missing"),
                                "args": [],
                            },
                        }
                    ]
                ),
                stderr="",
            ),
        )

        with pytest.raises(ValueError, match="executable is unavailable"):
            claude_runner.preflight_codex_arm_tools(
                {"tsa-warm": tmp_path, "codegraph-warm": tmp_path}
            )

    def test_codex_native_command_ignores_user_config_without_mcp_servers(
        self, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.adapters import RunConfig
        from benchmarks.codegraph_compare.adapters.claude_runner import (
            _build_agent_cmd,
        )

        command = _build_agent_cmd(
            "native-only",
            "gpt-5",
            tmp_path,
            RunConfig("native-only", tmp_path, "system"),
            "Read",
            "ToolSearch",
            "codex",
        )

        assert "--ignore-user-config" in command
        assert "--strict-config" in command
        assert not any(value.startswith("mcp_servers.") for value in command)

    def test_codex_metrics_count_mcp_calls_as_index_queries(self):
        from benchmarks.codegraph_compare.adapters.claude_runner import (
            _parse_codex_tool_calls_from_stream,
        )

        metrics = _parse_codex_tool_calls_from_stream(
            [
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "mcp_tool_call",
                            "server": "codegraph",
                            "tool": "codegraph_search",
                        },
                    }
                )
            ]
        )

        assert metrics == (1, 0, 0, 1)
